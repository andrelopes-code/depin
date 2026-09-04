"""Terminal and atomic ``FrozenContainer`` lifecycle behavior."""

import asyncio
import contextvars
import threading
from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.container import Container
from depin._core.frozen import FrozenContainer
from depin._core.lifecycle import create_lifecycle_gate
from depin._core.scope import Scope
from depin.errors import AsyncInSyncContextError, ContainerClosedError, ContainerLifecycleError


async def _checkpoint() -> None:
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    loop.call_soon(future.set_result, None)
    await future


def test_reopen_restores_admission_after_quiescing() -> None:
    gate = create_lifecycle_gate()
    assert gate.begin_async_close()
    with pytest.raises(ContainerLifecycleError, match='shutdown is already'):
        gate.admit('test', asynchronous=False)

    gate.reopen()

    ticket = gate.admit('test', asynchronous=False)
    gate.release(ticket)


def test_sync_close_rejects_background_async_resolution() -> None:
    entered = threading.Event()
    released = threading.Event()

    class Value: ...

    async def make() -> Value:
        entered.set()
        await asyncio.to_thread(released.wait)
        return Value()

    frozen = Container().bind(make, provides=Value).freeze()
    worker = threading.Thread(target=lambda: asyncio.run(frozen.aresolve(Value)))
    worker.start()
    assert entered.wait(1)
    with pytest.raises(AsyncInSyncContextError, match='asynchronous resolutions'):
        frozen.close()
    released.set()
    worker.join(1)
    assert not worker.is_alive()


@pytest.mark.asyncio
async def test_close_inside_event_loop_requires_aclose() -> None:
    frozen = Container().freeze()
    with pytest.raises(AsyncInSyncContextError, match='close\\(\\) cannot run inside an event loop'):
        frozen.close()


def test_sync_close_rejects_active_sync_resolution() -> None:
    entered = threading.Event()
    released = threading.Event()

    class Value: ...

    def make() -> Value:
        entered.set()
        released.wait()
        return Value()

    frozen = Container().bind(make, provides=Value).freeze()
    worker = threading.Thread(target=lambda: frozen.resolve(Value))
    worker.start()
    assert entered.wait(1)
    with pytest.raises(ContainerLifecycleError, match='let them finish'):
        frozen.close()
    released.set()
    worker.join(1)
    assert not worker.is_alive()


def test_provider_cannot_close_its_own_container() -> None:
    class Value: ...

    holder: list[FrozenContainer] = []

    def make() -> Value:
        holder[0].close()
        return Value()

    frozen = Container().bind(make, provides=Value).freeze()
    holder.append(frozen)
    with pytest.raises(ContainerLifecycleError, match='inside its active resolution'):
        frozen.resolve(Value)


@pytest.mark.asyncio
async def test_provider_cannot_aclose_its_own_container_and_follower_wakes() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class Value: ...

    holder: list[FrozenContainer] = []

    async def make() -> Value:
        entered.set()
        with pytest.raises(ContainerLifecycleError):
            await holder[0].aclose()
        await release.wait()
        return Value()

    frozen = Container().bind(make, provides=Value).freeze()
    holder.append(frozen)
    resolving = asyncio.create_task(frozen.aresolve(Value))
    await entered.wait()
    closing = asyncio.create_task(frozen.aclose())
    release.set()
    await resolving
    await closing
    with pytest.raises(ContainerClosedError):
        await frozen.aresolve(Value)


def test_close_inside_sync_and_async_scopes_is_rejected() -> None:
    frozen = Container().freeze()
    with frozen.scope(), pytest.raises(ContainerLifecycleError, match='inside its active resolution'):
        frozen.close()

    async def close_inside_async_scope() -> None:
        async with frozen.ascope():
            with pytest.raises(ContainerLifecycleError, match='inside its active resolution'):
                await frozen.aclose()

    asyncio.run(close_inside_async_scope())


@pytest.mark.asyncio
async def test_aclose_waits_for_provider_then_drains_before_closing() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    events: list[str] = []

    class Value: ...

    async def make() -> AsyncGenerator[Value]:
        events.append('construct')
        entered.set()
        await release.wait()
        yield Value()
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Value).freeze()
    resolving = asyncio.create_task(frozen.aresolve(Value))
    await entered.wait()
    closing = asyncio.create_task(frozen.aclose())
    await _checkpoint()
    with pytest.raises(ContainerLifecycleError, match='shutdown is already'):
        await frozen.aresolve(Value)
    release.set()
    await resolving
    await closing
    assert events == ['construct', 'teardown']
    with pytest.raises(ContainerClosedError):
        await frozen.aresolve(Value)


@pytest.mark.asyncio
async def test_admitted_lineage_continues_while_unrelated_context_is_rejected() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class Dep: ...

    class Value:
        def __init__(self, dep: Dep) -> None:
            self.dep = dep

    async def make_dep() -> Dep:
        entered.set()
        await release.wait()
        return Dep()

    frozen = Container().bind(make_dep, provides=Dep).bind(Value).freeze()
    task = asyncio.create_task(frozen.aresolve(Value))
    await entered.wait()
    closing = asyncio.create_task(frozen.aclose())
    await _checkpoint()
    with pytest.raises(ContainerLifecycleError):
        await frozen.aresolve(Dep)
    release.set()
    assert isinstance(await task, Value)
    await closing


@pytest.mark.asyncio
async def test_stale_copied_ticket_does_not_authorize_admission() -> None:
    frozen = Container().freeze()
    captured: contextvars.Context
    async with frozen.ascope():
        captured = contextvars.copy_context()
    await frozen.aclose()
    with pytest.raises(ContainerClosedError):
        captured.run(frozen.warmup)


@pytest.mark.asyncio
async def test_sync_preflight_preserves_async_teardown_until_aclose() -> None:
    events: list[str] = []

    async def make() -> AsyncGenerator[str]:
        yield 'value'
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert await frozen.aresolve(str) == 'value'
    with pytest.raises(AsyncInSyncContextError, match='cannot drain async singleton'):
        await asyncio.to_thread(frozen.close)
    assert await frozen.aresolve(str) == 'value'
    await frozen.aclose()
    assert events == ['teardown']


@pytest.mark.asyncio
async def test_cancelling_aclose_while_quiescing_reopens_container() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class Value: ...

    async def make() -> Value:
        entered.set()
        await release.wait()
        return Value()

    frozen = Container().bind(make, provides=Value).freeze()
    resolving = asyncio.create_task(frozen.aresolve(Value))
    await entered.wait()
    closing = asyncio.create_task(frozen.aclose())
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    release.set()
    await resolving
    assert isinstance(await frozen.aresolve(Value), Value)


@pytest.mark.asyncio
async def test_cancelling_aclose_during_drain_finishes_closing() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def make() -> AsyncGenerator[str]:
        yield 'value'
        entered.set()
        await release.wait()

    frozen = Container().bind(make, provides=str).freeze()
    assert await frozen.aresolve(str) == 'value'
    closing = asyncio.create_task(frozen.aclose())
    await entered.wait()
    closing.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await closing
    with pytest.raises(ContainerClosedError):
        await frozen.aresolve(str)


def test_cross_loop_aclose_joins_and_drains_once() -> None:
    events: list[str] = []

    def make() -> Generator[str]:
        yield 'value'
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert frozen.resolve(str) == 'value'
    failures: list[BaseException] = []

    def close_on_loop() -> None:
        try:
            asyncio.run(frozen.aclose())
        except BaseException as exc:
            failures.append(exc)

    first = threading.Thread(target=close_on_loop)
    second = threading.Thread(target=close_on_loop)
    first.start()
    second.start()
    first.join(1)
    second.join(1)
    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    assert events == ['teardown']
