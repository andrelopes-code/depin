"""Asynchronous resolution: every provider shape reached through aresolve()."""

import asyncio
import contextlib
import threading
from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor

import pytest

from depin._core.container import Container
from depin._core.frozen import FrozenContainer
from depin._core.markers import Token
from depin._core.scope import Scope, ScopeFrame
from depin.errors import AsyncInSyncContextError, CircularDependencyError


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
    assert await frozen.aresolve(int) == 5


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
    follower_started = asyncio.Event()

    async def make() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            await release_failure.wait()
            raise RuntimeError('first construction fails')
        return 7

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    leader = asyncio.create_task(frozen.aresolve(int))
    await started.wait()

    async def follow() -> int:
        follower_started.set()
        return await frozen.aresolve(int)

    follower = asyncio.create_task(follow())
    await follower_started.wait()
    release_failure.set()
    with pytest.raises(RuntimeError, match='first construction fails'):
        await leader
    assert await follower == 7
    assert attempts == 2


@pytest.mark.asyncio
async def test_cancelled_async_singleton_constructor_wakes_a_follower_to_retry() -> None:
    attempts = 0
    started = asyncio.Event()
    cancelled = asyncio.Event()
    follower_started = asyncio.Event()

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
        return 7

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    leader = asyncio.create_task(frozen.aresolve(int))
    await started.wait()

    async def follow() -> int:
        follower_started.set()
        return await frozen.aresolve(int)

    follower = asyncio.create_task(follow())
    await follower_started.wait()
    leader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leader
    await cancelled.wait()
    assert await follower == 7
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
    try:
        leader = asyncio.create_task(frozen.aresolve(int))
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
    try:
        leader = asyncio.create_task(frozen.aresolve(int))
        await started.wait()
        follower = asyncio.create_task(frozen.aresolve(int))
        marker = loop.create_future()
        loop.call_soon(marker.set_result, None)
        await marker
        follower.cancel()
        with pytest.raises(asyncio.CancelledError):
            await follower
        release.set()
        assert await leader == 7
    finally:
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
    started = asyncio.Event()
    release = asyncio.Event()
    constructed: list[object] = []

    def make() -> object:
        value = object()
        constructed.append(value)
        return value

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=object).freeze()

    async def async_leader() -> object:
        started.set()
        await release.wait()
        return await frozen.aresolve(object)

    leader = asyncio.create_task(async_leader())
    await started.wait()
    follower = asyncio.create_task(asyncio.to_thread(frozen.resolve, object))
    marker = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(marker.set_result, None)
    await marker
    release.set()
    first, second = await asyncio.gather(leader, follower)
    assert first is second
    assert len(constructed) == 1


def test_sync_self_resolution_raises_instead_of_waiting_for_its_own_flight() -> None:
    frozen: FrozenContainer

    def make() -> int:
        return frozen.resolve(int)

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    with pytest.raises(CircularDependencyError, match='already constructing'):
        frozen.resolve(int)


@pytest.mark.asyncio
async def test_async_child_task_self_resolution_raises_instead_of_waiting() -> None:
    frozen: FrozenContainer

    async def make() -> int:
        child = asyncio.create_task(frozen.aresolve(int))
        return await child

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    with pytest.raises(CircularDependencyError, match='already constructing'):
        await frozen.aresolve(int)


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
    frame.finish_flight(key, first)
    assert not replacement.finished
    frame.finish_flight(key, replacement)
    assert replacement.finished
