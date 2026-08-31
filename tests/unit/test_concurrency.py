"""Single-flight construction across concurrent tasks and across event loops."""

import asyncio
import sys
import threading
from collections.abc import Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope


class _Gate:
    """Suspends the first provider call until the test releases it.

    The provider signals `entered` and then waits on `released`, so a second
    resolution is guaranteed to run while the first is still mid-construction.
    That is the interleaving single-flight has to survive, reached without a
    sleep or any wall-clock assumption.
    """

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.released = asyncio.Event()

    async def pause(self) -> None:
        self.entered.set()
        await self.released.wait()

    async def release_once_entered(self) -> None:
        await self.entered.wait()
        self.released.set()


@pytest.mark.asyncio
async def test_concurrent_resolutions_build_a_singleton_once() -> None:
    built: list[object] = []
    gate = _Gate()

    class Pool: ...

    async def make_pool() -> Pool:
        await gate.pause()
        pool = Pool()
        built.append(pool)
        return pool

    frozen = Container().bind(make_pool, scope=Scope.SINGLETON, provides=Pool).freeze()
    async with frozen.ascope():
        both = asyncio.gather(frozen.aresolve(Pool), frozen.aresolve(Pool))
        await gate.release_once_entered()
        first, second = await both

    assert first is second
    assert len(built) == 1


@pytest.mark.asyncio
async def test_concurrent_resolutions_build_a_scoped_provider_once_per_scope() -> None:
    built: list[object] = []
    gate = _Gate()

    class Conn: ...

    async def make_conn() -> Conn:
        await gate.pause()
        conn = Conn()
        built.append(conn)
        return conn

    frozen = Container().bind(make_conn, scope=Scope.SCOPED, provides=Conn).freeze()
    async with frozen.ascope():
        both = asyncio.gather(frozen.aresolve(Conn), frozen.aresolve(Conn))
        await gate.release_once_entered()
        first, second = await both

    assert first is second
    assert len(built) == 1


@pytest.mark.asyncio
async def test_a_singleton_with_an_async_dependency_builds_both_once() -> None:
    deps: list[object] = []
    services: list[object] = []
    gate = _Gate()

    class Dep: ...

    class Service:
        def __init__(self, dep: Dep) -> None:
            self.dep = dep
            services.append(self)

    async def make_dep() -> Dep:
        await gate.pause()
        dep = Dep()
        deps.append(dep)
        return dep

    frozen = (
        Container().bind(make_dep, scope=Scope.SINGLETON, provides=Dep).bind(Service, scope=Scope.SINGLETON).freeze()
    )
    async with frozen.ascope():
        both = asyncio.gather(frozen.aresolve(Service), frozen.aresolve(Service))
        await gate.release_once_entered()
        first, second = await both

    assert first is second
    assert first.dep is second.dep
    assert len(deps) == 1
    assert len(services) == 1


def test_a_singleton_survives_a_change_of_event_loop() -> None:
    built: list[object] = []

    class Pool: ...

    async def make() -> Pool:
        pool = Pool()
        built.append(pool)
        return pool

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Pool).freeze()

    async def resolve() -> Pool:
        async with frozen.ascope():
            resolution = asyncio.create_task(frozen.aresolve(Pool))
            try:
                marker = asyncio.get_running_loop().create_future()
                asyncio.get_running_loop().call_soon(marker.set_result, None)
                await marker
                assert resolution.done()
                return await resolution
            finally:
                if not resolution.done():
                    resolution.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await resolution

    first = asyncio.run(resolve())
    second = asyncio.run(resolve())

    assert first is second
    assert len(built) == 1


def test_a_failed_build_leaves_the_key_resolvable_on_the_next_loop() -> None:
    attempts = 0

    class Flaky:
        def __init__(self) -> None:
            self.ok = True

    async def make() -> Flaky:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError('first build fails')
        return Flaky()

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Flaky).freeze()

    async def resolve() -> Flaky:
        async with frozen.ascope():
            return await frozen.aresolve(Flaky)

    with pytest.raises(RuntimeError, match='first build fails'):
        asyncio.run(resolve())

    root = object.__getattribute__(frozen, '_root')
    flight, constructs = root.start_flight((Flaky, None))
    assert constructs
    root.finish_flight((Flaky, None), flight)
    assert asyncio.run(resolve()).ok
    assert attempts == 2


def _race_reset_against_construction() -> tuple[bool, list[str]]:
    """One trial: resolve a generator singleton and reset() the container concurrently.

    Returns whether the widget ended up cached, and what teardown events ran.
    A fresh `Container` per call, so each trial starts from nothing built.
    """
    events: list[str] = []

    class Widget: ...

    def make() -> Generator[Widget]:
        widget = Widget()
        yield widget
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Widget).freeze()
    start = threading.Barrier(2)

    def build() -> None:
        start.wait()
        frozen.resolve(Widget)

    def reset() -> None:
        start.wait()
        frozen.reset()

    builder = threading.Thread(target=build)
    resetter = threading.Thread(target=reset)
    builder.start()
    resetter.start()
    builder.join()
    resetter.join()

    frame = object.__getattribute__(frozen, '_root')
    cache = object.__getattribute__(frame, '_cache')
    return (Widget, None) in cache, events


def test_reset_does_not_orphan_a_teardown_registered_during_the_drop() -> None:
    """Pins the atomicity `ScopeFrame._take_all` exists for.

    The teardown list and the cache must move together under one lock. If
    dropping the cache and taking the teardowns were two separate critical
    sections instead, a construction finishing in the gap between them could
    register its teardown after the first section already ran — surviving,
    unrun, left in the teardown list for some unrelated later drop to sweep
    up — while the second section wipes its just-published value from the
    cache regardless. That leaves a cache with no trace of the value and a
    teardown with no drop that is going to run it around the time it should.

    Raced ten thousand times with the switch interval driven down, so the
    invariant is exercised under real interleaving rather than checked once;
    a single lucky ordering proves nothing either way. This is a genuine race
    against OS thread scheduling, not a deterministic reproduction — a
    regression here is caught with high probability per run rather than
    certainty on any single run (see the fix report for a deterministic proof
    against a temporarily instrumented build).
    """
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-7)
    try:
        for _ in range(10000):
            cached, events = _race_reset_against_construction()
            assert cached or events == ['teardown'], (
                'the widget vanished from the cache without its teardown ever running'
            )
    finally:
        sys.setswitchinterval(original_interval)
