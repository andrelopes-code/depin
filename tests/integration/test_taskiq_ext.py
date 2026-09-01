"""The Taskiq integration, driven by a real `InMemoryBroker` and real messages.

`InMemoryBroker.kick` dispatches each message onto its own asyncio task, so the
broker exercises the same hook pairing a worker process does: ``pre_execute``,
the task body and ``post_execute`` share one task and one context, and messages
in flight overlap.

Every broker is built inside the test that uses it, with a task name of its own,
because a task is registered on the broker instance and the middleware is
constructed around one container.

Results are awaited through `outcome`, which polls with a zero interval:
`taskiq.AsyncTaskiqTask.wait_result` checks readiness before it waits, so the
poll yields to the event loop instead of sleeping and the suite stays
deterministic. Its deadline is there so a message whose result is never saved —
what a middleware that raises in ``post_execute`` produces — fails the test
instead of hanging it.

`InMemoryBroker.startup` overrides the base and never calls a middleware's
``startup`` or ``shutdown``, so nothing here depends on those firing.
"""

import asyncio
from collections.abc import Generator

from taskiq import AsyncTaskiqTask, InMemoryBroker, TaskiqMessage, TaskiqResult

from depin import Container, FrozenContainer, Scope, hosted_container
from depin.ext.taskiq import MessageScope


class Counter:
    """A scoped dependency whose identity distinguishes one message from the next."""

    def __init__(self) -> None:
        self.value = 0

    def tick(self) -> int:
        self.value += 1
        return self.value


class Resource:
    """A scoped dependency whose teardown the tests count."""


class MessageProbe:
    """A provider whose only input is the seeded `taskiq.TaskiqMessage`."""

    def __init__(self, message: TaskiqMessage) -> None:
        self.task_name = message.task_name
        self.task_id = message.task_id
        self.args = list(message.args)


class TaskFailure(Exception):
    """Raised by a task body to prove the scope still drains."""


def message_container(torn: list[Resource]) -> FrozenContainer:
    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(item)

    return Container().bind(Counter, scope=Scope.SCOPED).bind(make, scope=Scope.SCOPED, provides=Resource).freeze()


def probing_container() -> FrozenContainer:
    return Container().scope_value(TaskiqMessage).bind(MessageProbe, scope=Scope.SCOPED).freeze()


RESULT_DEADLINE = 5.0
"""Seconds a message may take before its result is declared lost."""


def broker_for(container: FrozenContainer) -> InMemoryBroker:
    return InMemoryBroker().with_middlewares(MessageScope(container))


async def outcome(sent: AsyncTaskiqTask[None]) -> TaskiqResult[None]:
    return await sent.wait_result(check_interval=0, timeout=RESULT_DEADLINE)


async def test_a_scoped_provider_is_resolved_once_per_message() -> None:
    broker = broker_for(message_container([]))
    ticks: list[int] = []

    @broker.task(task_name='depin.tests.taskiq.resolved_once')
    async def report() -> None:
        ticks.append(hosted_container().resolve(Counter).tick())
        ticks.append(hosted_container().resolve(Counter).tick())

    await broker.startup()
    (await outcome(await report.kiq())).raise_for_error()
    await broker.shutdown()

    assert ticks == [1, 2]


async def test_the_scope_drains_its_teardowns_when_the_task_finishes() -> None:
    torn: list[Resource] = []
    torn_while_running: list[int] = []
    broker = broker_for(message_container(torn))

    @broker.task(task_name='depin.tests.taskiq.drains')
    async def report() -> None:
        _ = hosted_container().resolve(Resource)
        torn_while_running.append(len(torn))

    await broker.startup()
    (await outcome(await report.kiq())).raise_for_error()
    await broker.shutdown()

    assert torn_while_running == [0]
    assert len(torn) == 1


async def test_two_messages_get_independent_scoped_instances() -> None:
    broker = broker_for(message_container([]))
    seen: list[int] = []
    ticks: list[int] = []

    @broker.task(task_name='depin.tests.taskiq.independent')
    async def report() -> None:
        counter = hosted_container().resolve(Counter)
        seen.append(id(counter))
        ticks.append(counter.tick())

    await broker.startup()
    (await outcome(await report.kiq())).raise_for_error()
    (await outcome(await report.kiq())).raise_for_error()
    await broker.shutdown()

    assert ticks == [1, 1]
    assert seen[0] != seen[1]


async def test_the_hosted_container_is_reachable_from_the_task_body() -> None:
    di = Container().freeze()
    broker = broker_for(di)
    found: list[FrozenContainer] = []

    @broker.task(task_name='depin.tests.taskiq.hosted')
    async def report() -> None:
        found.append(hosted_container())

    await broker.startup()
    (await outcome(await report.kiq())).raise_for_error()
    await broker.shutdown()

    assert found == [di]


async def test_a_provider_reads_the_seeded_message() -> None:
    broker = broker_for(probing_container())
    probes: list[MessageProbe] = []

    @broker.task(task_name='depin.tests.taskiq.seeded')
    async def report(tenant: str) -> None:
        probes.append(hosted_container().resolve(MessageProbe))

    await broker.startup()
    sent = await report.kiq('acme')
    (await outcome(sent)).raise_for_error()
    await broker.shutdown()

    assert [probe.task_name for probe in probes] == ['depin.tests.taskiq.seeded']
    assert [probe.task_id for probe in probes] == [sent.task_id]
    assert [probe.args for probe in probes] == [['acme']]


async def test_a_raising_task_drains_its_scope_and_surfaces_the_error() -> None:
    torn: list[Resource] = []
    broker = broker_for(message_container(torn))

    @broker.task(task_name='depin.tests.taskiq.raises')
    async def report() -> None:
        _ = hosted_container().resolve(Resource)
        raise TaskFailure('the task body failed')

    await broker.startup()
    result = await outcome(await report.kiq())
    await broker.shutdown()

    assert result.is_err
    assert isinstance(result.error, TaskFailure)
    assert len(torn) == 1


async def test_three_interleaved_messages_each_close_their_own_scope() -> None:
    torn: list[int] = []

    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(id(item))

    di = Container().bind(make, scope=Scope.SCOPED, provides=Resource).freeze()
    broker = broker_for(di)

    all_arrived = asyncio.Event()
    release = asyncio.Event()
    on_arrival: dict[int, int] = {}
    on_release: dict[int, int] = {}

    @broker.task(task_name='depin.tests.taskiq.interleaved')
    async def report(slot: int) -> None:
        on_arrival[slot] = id(hosted_container().resolve(Resource))
        if len(on_arrival) == 3:
            all_arrived.set()
        await release.wait()
        on_release[slot] = id(hosted_container().resolve(Resource))

    await broker.startup()
    sent = [await report.kiq(slot) for slot in (0, 1, 2)]
    await all_arrived.wait()
    release.set()
    for message in sent:
        (await outcome(message)).raise_for_error()
    await broker.shutdown()

    assert len(set(on_arrival.values())) == 3
    assert on_release == on_arrival
    assert sorted(torn) == sorted(on_arrival.values())
