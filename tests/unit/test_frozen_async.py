"""Asynchronous resolution: every provider shape reached through aresolve()."""

import asyncio
import contextlib
import threading
from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

import pytest

from depin._core.container import Container
from depin._core.frozen import FrozenContainer
from depin._core.markers import Tag, Token
from depin._core.scope import Scope, ScopeFrame
from depin.errors import AsyncInSyncContextError, CircularDependencyError


async def _checkpoint() -> None:
    loop = asyncio.get_running_loop()
    marker = loop.create_future()
    loop.call_soon(marker.set_result, None)
    await marker


@pytest.mark.asyncio
async def test_async_singleton_flights_are_keyed_by_provider_and_removed_after_failure() -> None:
    async with asyncio.timeout(1):
        await _exercise_async_singleton_flight_keys_and_cleanup()


@pytest.mark.asyncio
async def test_aresolve_unhashable_value_binding() -> None:
    origins = Token[list[str]]('origins')
    frozen = Container().value(origins, ['x']).freeze()
    assert await frozen.aresolve(origins) == ['x']


@pytest.mark.asyncio
async def test_aresolve_async_function() -> None:
    async def make() -> int:
        return 5

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    resolution = asyncio.create_task(frozen.aresolve(int))
    try:
        await _checkpoint()
        assert resolution.done()
        assert await resolution == 5
    finally:
        if not resolution.done():
            resolution.cancel()
            with pytest.raises(asyncio.CancelledError):
                await resolution


@pytest.mark.asyncio
async def test_aresolve_works_for_sync_graph_too() -> None:
    class A: ...

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    a = await frozen.aresolve(A)
    assert isinstance(a, A)


@pytest.mark.asyncio
async def test_class_with_async_dep_resolves_async() -> None:
    class A: ...

    async def make_a() -> A:
        return A()

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    frozen = Container().bind(make_a, scope=Scope.SINGLETON, provides=A).bind(B, scope=Scope.SINGLETON).freeze()
    b = await frozen.aresolve(B)
    assert isinstance(b.a, A)


def test_sync_resolve_async_chain_raises_at_call() -> None:
    class A: ...

    async def make_a() -> A:
        return A()

    frozen = Container().bind(make_a, scope=Scope.SINGLETON, provides=A).freeze()
    with pytest.raises(AsyncInSyncContextError):
        _ = frozen[A]


@pytest.mark.asyncio
async def test_aresolve_builds_a_transient_provider_every_time() -> None:
    class Ticket: ...

    async def make() -> Ticket:
        return Ticket()

    frozen = Container().bind(make, scope=Scope.TRANSIENT, provides=Ticket).freeze()
    assert await frozen.aresolve(Ticket) is not await frozen.aresolve(Ticket)


@pytest.mark.asyncio
async def test_aresolve_caches_a_singleton_across_calls() -> None:
    class Pool: ...

    frozen = Container().bind(Pool, scope=Scope.SINGLETON).freeze()
    assert await frozen.aresolve(Pool) is await frozen.aresolve(Pool)


@pytest.mark.asyncio
async def test_aresolve_caches_a_scoped_provider_within_one_scope() -> None:
    class Session: ...

    frozen = Container().bind(Session, scope=Scope.SCOPED).freeze()
    async with frozen.ascope():
        first = await frozen.aresolve(Session)
        assert first is await frozen.aresolve(Session)
    async with frozen.ascope():
        assert await frozen.aresolve(Session) is not first


@pytest.mark.asyncio
async def test_async_transient_provider_reads_scope_value_inside_a_scope() -> None:
    class RequestId: ...

    class Report:
        def __init__(self, request_id: RequestId) -> None:
            self.request_id = request_id

    request_id = RequestId()
    frozen = Container().scope_value(RequestId).bind(Report, scope=Scope.TRANSIENT).freeze()
    async with frozen.ascope() as frame:
        frame.provide(RequestId, request_id)
        assert (await frozen.aresolve(Report)).request_id is request_id


@pytest.mark.asyncio
async def test_aresolve_wires_an_async_dependency_into_a_class_constructor() -> None:
    class Repo:
        def __init__(self, size: int) -> None:
            self.size = size

    async def make_size() -> int:
        return 5

    frozen = Container().bind(make_size, scope=Scope.SINGLETON, provides=int).bind(Repo, scope=Scope.SINGLETON).freeze()
    assert (await frozen.aresolve(Repo)).size == 5


@pytest.mark.asyncio
async def test_aresolve_handles_sync_providers_too() -> None:
    token: Token[int] = Token[int]('x')

    def make() -> str:
        return 'sync'

    frozen = Container().value(token, 5).bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert await frozen.aresolve(token) == 5
    assert await frozen.aresolve(str) == 'sync'


@pytest.mark.asyncio
async def test_aresolve_drains_a_sync_generator_on_scope_exit() -> None:
    events: list[str] = []

    def make() -> Generator[int]:
        yield 5
        events.append('done')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    async with frozen.ascope():
        assert await frozen.aresolve(int) == 5
    assert events == ['done']


@pytest.mark.asyncio
async def test_aresolve_drains_a_sync_context_manager_on_scope_exit() -> None:
    events: list[str] = []

    @contextlib.contextmanager
    def make() -> Generator[int]:
        yield 7
        events.append('done')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    async with frozen.ascope():
        assert await frozen.aresolve(int) == 7
    assert events == ['done']


@pytest.mark.asyncio
async def test_aresolve_reads_a_scope_value_and_injects_it() -> None:
    class Principal: ...

    class Audit:
        def __init__(self, who: Principal) -> None:
            self.who = who

    frozen = Container().scope_value(Principal).bind(Audit, scope=Scope.SCOPED).freeze()
    principal = Principal()
    async with frozen.ascope() as frame:
        frame.provide(Principal, principal)
        assert await frozen.aresolve(Principal) is principal
        assert (await frozen.aresolve(Audit)).who is principal


@pytest.mark.asyncio
async def test_async_scope_values_do_not_skip_later_tagged_dependencies() -> None:
    class ScopeValue: ...

    class BoundValue:
        def __init__(self, label: str) -> None:
            self.label = label

    class Report:
        def __init__(self, scope_value: ScopeValue, bound_value: Annotated[BoundValue, Tag('chosen')]) -> None:
            self.scope_value = scope_value
            self.bound_value = bound_value

    frozen = (
        Container()
        .scope_value(ScopeValue)
        .bind(lambda: BoundValue('chosen'), provides=BoundValue, tag='chosen')
        .bind(lambda: BoundValue('other'), provides=BoundValue, tag='other')
        .bind(Report, scope=Scope.SCOPED)
        .freeze()
    )
    supplied = ScopeValue()
    async with frozen.ascope() as frame:
        frame.provide(ScopeValue, supplied)
        report = await frozen.aresolve(Report)

    assert report.scope_value is supplied
    assert report.bound_value.label == 'chosen'


@pytest.mark.asyncio
async def test_aresolve_of_an_async_generator_yields_the_first_value() -> None:
    async def make() -> AsyncGenerator[int]:
        yield 3

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    async with frozen.ascope():
        assert await frozen.aresolve(int) == 3


@pytest.mark.asyncio
async def test_async_singleton_failure_wakes_a_follower_to_retry() -> None:
    attempts = 0
    started = asyncio.Event()
    release_failure = asyncio.Event()
    second_construction_started = asyncio.Event()

    async def make() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            await release_failure.wait()
            raise RuntimeError('first construction fails')
        second_construction_started.set()
        return 7

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    leader = asyncio.create_task(frozen.aresolve(int))
    await started.wait()

    follower = asyncio.create_task(frozen.aresolve(int))
    await _checkpoint()
    assert not second_construction_started.is_set()
    release_failure.set()
    with pytest.raises(RuntimeError, match='first construction fails'):
        await leader
    async with asyncio.timeout(1):
        assert await follower == 7
    assert attempts == 2


@pytest.mark.asyncio
async def test_cancelled_async_singleton_constructor_wakes_a_follower_to_retry() -> None:
    attempts = 0
    started = asyncio.Event()
    cancelled = asyncio.Event()
    second_construction_started = asyncio.Event()

    async def make() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        second_construction_started.set()
        return 7

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    leader = asyncio.create_task(frozen.aresolve(int))
    await started.wait()

    follower = asyncio.create_task(frozen.aresolve(int))
    try:
        await _checkpoint()
        assert not second_construction_started.is_set()
        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader
        await cancelled.wait()
        async with asyncio.timeout(1):
            assert await follower == 7
    finally:
        if not follower.done():
            follower.cancel()
            with pytest.raises(asyncio.CancelledError):
                await follower
    assert attempts == 2


@pytest.mark.asyncio
async def test_many_async_tasks_construct_a_singleton_once() -> None:
    attempts = 0
    ready = 0
    all_ready = asyncio.Event()
    release = asyncio.Event()

    async def make() -> object:
        nonlocal attempts
        attempts += 1
        await release.wait()
        return object()

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=object).freeze()

    async def resolve() -> object:
        nonlocal ready
        ready += 1
        if ready == 32:
            all_ready.set()
        return await frozen.aresolve(object)

    tasks = [asyncio.create_task(resolve()) for _ in range(32)]
    await all_ready.wait()
    release.set()
    values = await asyncio.gather(*tasks)
    assert attempts == 1
    assert all(value is values[0] for value in values)


@pytest.mark.asyncio
async def test_async_follower_does_not_occupy_the_default_executor() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    constructed = 0

    async def make() -> int:
        nonlocal constructed
        constructed += 1
        started.set()
        await release.wait()
        return await asyncio.to_thread(lambda: 7)

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(executor)
    leader = asyncio.create_task(frozen.aresolve(int))
    try:
        await started.wait()
        follower = asyncio.create_task(frozen.aresolve(int))
        marker = loop.create_future()
        loop.call_soon(marker.set_result, None)
        await marker
        release.set()
        assert await leader == 7
        assert await follower == 7
    finally:
        executor.shutdown(wait=True)
    assert constructed == 1


@pytest.mark.asyncio
async def test_cancelled_async_follower_does_not_occupy_the_default_executor() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def make() -> int:
        started.set()
        await release.wait()
        return await asyncio.to_thread(lambda: 7)

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(executor)
    leader = asyncio.create_task(frozen.aresolve(int))
    try:
        await started.wait()
        follower = asyncio.create_task(frozen.aresolve(int))
        marker = loop.create_future()
        loop.call_soon(marker.set_result, None)
        await marker
        follower.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await follower
    finally:
        release.set()
        assert await leader == 7
        executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_sync_and_async_resolution_share_one_flight() -> None:
    started = threading.Event()
    release = threading.Event()
    constructed: list[object] = []

    def make() -> object:
        started.set()
        release.wait()
        value = object()
        constructed.append(value)
        return value

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=object).freeze()
    leader = asyncio.create_task(asyncio.to_thread(frozen.resolve, object))
    await asyncio.to_thread(started.wait)
    follower = asyncio.create_task(frozen.aresolve(object))
    marker = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(marker.set_result, None)
    await marker
    release.set()
    first, second = await asyncio.gather(leader, follower)
    assert first is second
    assert len(constructed) == 1


@pytest.mark.asyncio
async def test_async_and_sync_resolution_share_one_flight() -> None:
    provider_started = threading.Event()
    follower_waiting = threading.Event()
    release = threading.Event()
    constructed: list[object] = []
    failures: list[BaseException] = []
    record = threading.Lock()

    class Value: ...

    class RecordingEvent:
        def __init__(self, event: threading.Event) -> None:
            self._event = event

        def wait(self) -> bool:
            follower_waiting.set()
            return self._event.wait()

        def set(self) -> None:
            self._event.set()

    def make() -> Value:
        provider_started.set()
        release.wait()
        value = object()
        with record:
            constructed.append(value)
        return Value()

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Value).freeze()

    def async_leader() -> None:
        try:
            _ = asyncio.run(frozen.aresolve(Value))
        except BaseException as exc:
            with record:
                failures.append(exc)

    leader = threading.Thread(target=async_leader)
    leader.start()
    resolved: list[Value] = []
    follower: threading.Thread | None = None

    def sync_follower() -> None:
        try:
            value = frozen.resolve(Value)
            with record:
                resolved.append(value)
        except BaseException as exc:
            with record:
                failures.append(exc)

    try:
        provider_started.wait()
        root: ScopeFrame = object.__getattribute__(frozen, '_root')
        flight, constructs = root.start_flight((Value, None))
        assert not constructs
        object.__setattr__(flight, '_event', RecordingEvent(threading.Event()))
        follower = threading.Thread(target=sync_follower)
        follower.start()
        follower_waiting.wait()
    finally:
        release.set()
        leader.join()
        if follower is not None:
            follower.join()
    assert not failures
    assert len(constructed) == 1
    assert len(resolved) == 1
    assert frozen.resolve(Value) is resolved[0]


@pytest.mark.asyncio
async def test_closed_loop_waiter_does_not_mask_a_live_waiter() -> None:
    frame = ScopeFrame()
    key = object()
    leader, constructs = frame.start_flight(key)
    assert constructs
    flight, joins = frame.start_flight(key)
    assert not joins
    closed_waiter_registered = threading.Event()

    def register_closed_waiter() -> None:
        loop = asyncio.new_event_loop()
        task = loop.create_task(frame.wait_async(flight))
        loop.call_soon(loop.stop)
        loop.run_forever()
        assert not task.done()
        object.__setattr__(task, '_log_destroy_pending', False)
        loop.close()
        closed_waiter_registered.set()

    thread = threading.Thread(target=register_closed_waiter)
    thread.start()
    closed_waiter_registered.wait()
    thread.join()
    value = object()

    async def wait_for_value() -> object:
        await frame.wait_async(flight)
        return value

    live_waiter = asyncio.create_task(wait_for_value())
    await _checkpoint()
    try:
        frame.finish_flight(key, leader)
        await _checkpoint()
        assert live_waiter.done()
        assert await live_waiter is value
    finally:
        if not live_waiter.done():
            live_waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await live_waiter


@pytest.mark.asyncio
async def _exercise_async_singleton_flight_keys_and_cleanup() -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    class First: ...

    class Second: ...

    async def make_first() -> First:
        first_started.set()
        await release.wait()
        return First()

    async def make_second() -> Second:
        second_started.set()
        await release.wait()
        return Second()

    async def fail_once() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError('first attempt fails')
        return attempts

    frozen = (
        Container()
        .bind(make_first, scope=Scope.SINGLETON, provides=First)
        .bind(make_second, scope=Scope.SINGLETON, provides=Second)
        .bind(fail_once, scope=Scope.SINGLETON, provides=int)
        .freeze()
    )
    first = asyncio.create_task(frozen.aresolve(First))
    second: asyncio.Task[Second] | None = None
    try:
        await _checkpoint()
        assert first_started.is_set()
        second = asyncio.create_task(frozen.aresolve(Second))
        await _checkpoint()
        assert second_started.is_set()
        release.set()
        first_value, second_value = await asyncio.gather(first, second)
        assert isinstance(first_value, First)
        assert isinstance(second_value, Second)
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
        for task in (first, second):
            if task is not None and task.cancelled():
                continue
            if task is not None and not task.done():
                with pytest.raises(asyncio.CancelledError):
                    await task

    with pytest.raises(RuntimeError, match='first attempt fails'):
        await frozen.aresolve(int)
    assert await frozen.aresolve(int) == 2


def test_sync_self_resolution_raises_instead_of_waiting_for_its_own_flight() -> None:
    frozen: FrozenContainer

    def make() -> int:
        return frozen.resolve(int)

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    finished = threading.Event()
    errors: list[BaseException] = []

    def resolve() -> None:
        try:
            _ = frozen.resolve(int)
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=resolve, daemon=True)
    thread.start()
    assert finished.wait(1)
    assert len(errors) == 1
    assert str(errors[0]) == (
        'int is already constructing in this context; '
        'resolve a different dependency or break the recursive provider call'
    )


@pytest.mark.asyncio
async def test_async_child_task_self_resolution_raises_instead_of_waiting() -> None:
    frozen: FrozenContainer

    async def make() -> int:
        child = asyncio.create_task(frozen.aresolve(int))
        return await child

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    async with asyncio.timeout(1):
        with pytest.raises(CircularDependencyError, match='already constructing'):
            await frozen.aresolve(int)


@pytest.mark.asyncio
async def test_async_dynamic_cycle_during_parameter_resolution_raises() -> None:
    frozen: FrozenContainer

    class A: ...

    class B: ...

    async def make_a(value: B) -> A:
        return A()

    async def make_b() -> B:
        child = asyncio.create_task(frozen.aresolve(A))
        await child
        return B()

    frozen = Container().bind(make_a, provides=A).bind(make_b, provides=B).freeze()
    async with asyncio.timeout(1):
        with pytest.raises(CircularDependencyError, match='already constructing'):
            await frozen.aresolve(A)


@pytest.mark.asyncio
async def test_async_nested_scope_self_resolution_raises() -> None:
    frozen: FrozenContainer

    class Value: ...

    async def make() -> Value:
        async with frozen.ascope():
            return await frozen.aresolve(Value)

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=Value).freeze()
    async with asyncio.timeout(1):
        with pytest.raises(CircularDependencyError) as exc:
            async with frozen.ascope():
                await frozen.aresolve(Value)
    assert str(exc.value) == (
        f'{Value.__qualname__} is already constructing in this context; '
        'resolve a different dependency or break the recursive provider call'
    )


@pytest.mark.asyncio
async def test_nested_async_scope_constructs_a_scoped_provider_once() -> None:
    constructed: list[object] = []

    class Value: ...

    async def make() -> Value:
        constructed.append(object())
        return Value()

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=Value).freeze()
    async with frozen.ascope(), frozen.ascope():
        first = await frozen.aresolve(Value)
        assert await frozen.aresolve(Value) is first
    assert len(constructed) == 1


@pytest.mark.asyncio
async def test_inner_scope_keeps_its_flight_and_cache_ahead_of_outer_scope() -> None:
    frozen: FrozenContainer
    first_started = asyncio.Event()
    release_outer = asyncio.Event()
    release_inner = asyncio.Event()
    calls = 0

    class Value: ...

    async def make() -> Value:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_started.set()
            await release_inner.wait()
        return Value()

    async def resolve_outer() -> Value:
        await release_outer.wait()
        return await frozen.aresolve(Value)

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=Value).freeze()
    async with frozen.ascope():
        outer = asyncio.create_task(resolve_outer())
        async with frozen.ascope():
            inner = asyncio.create_task(frozen.aresolve(Value))
            await first_started.wait()
            release_outer.set()
            outer_value = await outer
            follower = asyncio.create_task(frozen.aresolve(Value))
            release_inner.set()
            inner_value = await inner
            assert await follower is inner_value
            assert await frozen.aresolve(Value) is inner_value
            assert inner_value is not outer_value
    assert calls == 2


@pytest.mark.asyncio
async def test_stale_inherited_async_scope_context_cannot_resolve_after_abort() -> None:
    frozen: FrozenContainer
    child_started = asyncio.Event()
    release_child = asyncio.Event()
    attempts = 0

    class Value: ...

    child: asyncio.Task[Value] | None = None

    async def resolve_in_child() -> Value:
        child_started.set()
        await release_child.wait()
        return await frozen.aresolve(Value)

    async def make() -> Value:
        nonlocal attempts, child
        attempts += 1
        if attempts == 1:
            child = asyncio.create_task(resolve_in_child())
            await child_started.wait()
            raise RuntimeError('first construction fails')
        return Value()

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=Value).freeze()
    async with frozen.ascope(), frozen.ascope():
        with pytest.raises(RuntimeError, match='first construction fails'):
            await frozen.aresolve(Value)
        release_child.set()
        assert child is not None
        with pytest.raises(CircularDependencyError) as exc:
            await child
        assert str(exc.value) == (
            f'{Value.__qualname__} is already constructing in this context; '
            'resolve a different dependency or break the recursive provider call'
        )
        first = await frozen.aresolve(Value)
        assert await frozen.aresolve(Value) is first
    assert attempts == 2


@pytest.mark.asyncio
async def test_stale_and_duplicate_flight_completion_do_not_signal_replacement() -> None:
    frame = ScopeFrame()
    old, leader = frame.start_flight(object())
    assert leader
    frame.finish_flight(object(), old)
    key = object()
    first, leader = frame.start_flight(key)
    assert leader
    frame.finish_flight(key, first)
    replacement, leader = frame.start_flight(key)
    assert leader
    _follower, joins = frame.start_flight(key)
    assert not joins
    frame.finish_flight(key, first)
    assert not replacement.finished
    frame.finish_flight(key, replacement)
    assert replacement.finished


@pytest.mark.asyncio
async def test_an_alias_to_an_async_target_resolves_under_aresolve() -> None:
    class Store: ...

    class Backend: ...

    async def make() -> Backend:
        return Backend()

    di = Container().bind(make, provides=Backend).alias(Store, to=Backend).freeze()
    via_alias: object = await di.aresolve(Store)
    via_target: object = await di.aresolve(Backend)
    assert via_alias is via_target


def test_an_alias_to_an_async_target_is_rejected_by_resolve() -> None:
    class Store: ...

    class Backend: ...

    async def make() -> Backend:
        return Backend()

    di = Container().bind(make, provides=Backend).alias(Store, to=Backend).freeze()
    with pytest.raises(AsyncInSyncContextError, match='Store requires async resolution'):
        _ = di.resolve(Store)


@pytest.mark.asyncio
async def test_a_collection_with_an_async_member_resolves_under_aresolve() -> None:
    class Handler: ...

    class Backend: ...

    async def make() -> Backend:
        return Backend()

    di = Container().bind(make, provides=Backend).collect(Handler, [Backend]).freeze()
    members = await di.aresolve(list[Handler])
    assert len(members) == 1


def test_a_collection_with_an_async_member_is_rejected_by_resolve() -> None:
    class Handler: ...

    class Backend: ...

    async def make() -> Backend:
        return Backend()

    di = Container().bind(make, provides=Backend).collect(Handler, [Backend]).freeze()
    with pytest.raises(AsyncInSyncContextError, match=r'list\['):
        _ = di.resolve(list[Handler])


@pytest.mark.asyncio
async def test_an_async_seeded_key_that_also_has_a_binding_resolves_to_its_binding() -> None:
    class Clock:
        def __init__(self, label: str = 'bound') -> None:
            self.label = label

    class Report:
        def __init__(self, clock: Clock) -> None:
            self.clock = clock

    frozen = Container().bind(Clock).bind(Report, scope=Scope.SCOPED).freeze()

    async with frozen.ascope() as frame:
        frame.provide(Clock, Clock('seeded'))
        report = await frozen.aresolve(Report)

    assert report.clock.label == 'bound'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['default', 'optional'])
async def test_an_async_frame_seed_for_an_unbound_key_needs_scope_value_to_reach_a_parameter(kind: str) -> None:
    class Extra: ...

    default_value = Extra()

    class ReportWithDefault:
        def __init__(self, extra: Extra = default_value) -> None:
            self.extra = extra

    class ReportWithOptional:
        def __init__(self, extra: Extra | None = None) -> None:
            self.extra = extra

    seeded = Extra()

    if kind == 'default':
        unbound_default = Container().bind(ReportWithDefault, scope=Scope.SCOPED).freeze()
        async with unbound_default.ascope() as frame:
            frame.provide(Extra, seeded)
            without_scope_value_default = await unbound_default.aresolve(ReportWithDefault)
        assert without_scope_value_default.extra is default_value

        bound_default = Container().scope_value(Extra).bind(ReportWithDefault, scope=Scope.SCOPED).freeze()
        async with bound_default.ascope() as frame:
            frame.provide(Extra, seeded)
            with_scope_value_default = await bound_default.aresolve(ReportWithDefault)
        assert with_scope_value_default.extra is seeded
    else:
        unbound_optional = Container().bind(ReportWithOptional, scope=Scope.SCOPED).freeze()
        async with unbound_optional.ascope() as frame:
            frame.provide(Extra, seeded)
            without_scope_value_optional = await unbound_optional.aresolve(ReportWithOptional)
        assert without_scope_value_optional.extra is None

        bound_optional = Container().scope_value(Extra).bind(ReportWithOptional, scope=Scope.SCOPED).freeze()
        async with bound_optional.ascope() as frame:
            frame.provide(Extra, seeded)
            with_scope_value_optional = await bound_optional.aresolve(ReportWithOptional)
        assert with_scope_value_optional.extra is seeded
