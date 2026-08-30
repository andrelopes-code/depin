"""Container invariants under true thread parallelism, on a free-threaded build.

`tests/unit/test_thread_safety.py` forces interleaving with
`sys.setswitchinterval`, which is meaningless without a GIL. These tests instead
rely on threads genuinely running at the same time, and are skipped on a build
where the GIL is enabled.
"""

# pyright: reportPrivateUsage=false

import asyncio
import multiprocessing
import sys
import threading
from _thread import LockType
from collections.abc import Callable, Generator
from multiprocessing.connection import Connection

import pytest

from depin._core.container import Container
from depin._core.scope import Scope, ScopeFrame, optional_frame

THREADS = 32


def _gil_enabled() -> bool:
    check: Callable[[], bool] | None = getattr(sys, '_is_gil_enabled', None)
    return True if check is None else check()


pytestmark = pytest.mark.skipif(_gil_enabled(), reason='requires a free-threaded interpreter')


def _run_in_threads(work: Callable[[], None]) -> None:
    threads = [threading.Thread(target=work) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def _run_cross_loop_singleton(connection: Connection) -> None:
    class Pool: ...

    provider_started = threading.Event()
    binder_suspended = threading.Event()
    release_constructor = threading.Event()
    challengers_ready = 0
    completed: list[None] = []
    constructed: list[Pool] = []
    resolved: list[Pool] = []
    failures: list[BaseException] = []
    record = threading.Lock()
    state = threading.Condition()
    challengers = threading.Condition()
    start = threading.Barrier(THREADS)

    async def make_pool() -> Pool:
        provider_started.set()
        await asyncio.to_thread(release_constructor.wait)
        pool = Pool()
        with record:
            constructed.append(pool)
        return pool

    frozen = Container().bind(make_pool, scope=Scope.SINGLETON, provides=Pool).freeze()

    def worker(index: int) -> None:
        nonlocal challengers_ready

        async def checkpoint() -> None:
            loop = asyncio.get_running_loop()
            marker = loop.create_future()
            loop.call_soon(marker.set_result, None)
            await marker

        async def resolve() -> None:
            nonlocal challengers_ready
            loop = asyncio.get_running_loop()
            loop.slow_callback_duration = 1.0
            if index == 0:
                value = await frozen.aresolve(Pool)
            else:
                if index == 1:
                    await asyncio.to_thread(provider_started.wait)
                else:
                    await asyncio.to_thread(binder_suspended.wait)
                resolution = asyncio.create_task(frozen.aresolve(Pool))
                await checkpoint()
                if index == 1:
                    binder_suspended.set()
                else:
                    with challengers:
                        challengers_ready += 1
                        challengers.notify_all()
                value = await resolution
            with record:
                resolved.append(value)

        try:
            _ = start.wait()
            asyncio.run(resolve())
            with state:
                completed.append(None)
                state.notify_all()
        except BaseException as exc:
            with state:
                failures.append(exc)
                state.notify_all()

    threads = [threading.Thread(target=worker, args=(index,), daemon=True) for index in range(THREADS)]
    for thread in threads:
        thread.start()
    provider_started.wait()
    binder_suspended.wait()
    with challengers:
        while challengers_ready != THREADS - 2:
            challengers.wait()
    release_constructor.set()
    with state:
        while not failures and len(completed) != THREADS:
            state.wait()
    if failures:
        connection.send_bytes(f'failure:{failures[0]!r}'.encode())
        connection.close()
        return
    for thread in threads:
        thread.join()
    identities = len({id(value) for value in resolved})
    connection.send_bytes(
        f'success:constructed={len(constructed)} resolved={len(resolved)} identities={identities} failures=0'.encode()
    )
    connection.close()


class _RendezvousFlightTable:
    def __init__(self, guard: LockType, rendezvous: threading.Barrier) -> None:
        self._guard = guard
        self._rendezvous = rendezvous
        self._values: dict[object, object] = {}

    def get(self, key: object) -> object | None:
        value = self._values.get(key)
        if value is None and not self._guard.locked():
            _ = self._rendezvous.wait()
        return value

    def __setitem__(self, key: object, value: object) -> None:
        self._values[key] = value

    def __delitem__(self, key: object) -> None:
        del self._values[key]


def test_a_singleton_is_built_once_with_no_gil() -> None:
    class Pool: ...

    # `Pool()` is near-instant and the pre-lock `frame.lookup` fast path absorbs
    # most of a single-key race; racing 64 keys makes a removed single-flight
    # lock observable reliably in this end-to-end test.
    TAGS = tuple(str(tag) for tag in range(64))

    built: dict[str, list[Pool]] = {tag: [] for tag in TAGS}
    resolved: dict[str, list[Pool]] = {tag: [] for tag in TAGS}
    record = threading.Lock()
    start = threading.Barrier(THREADS)
    # Re-synchronised before every key, not just once at the start: threads
    # drift apart after the first key, which would let later keys race with
    # only partial overlap. A fresh rendezvous per key keeps all THREADS
    # threads landing on each key's check-then-act window together.
    per_key = threading.Barrier(THREADS)

    def make_factory(tag: str) -> Callable[[], Pool]:
        def make() -> Pool:
            pool = Pool()
            with record:
                built[tag].append(pool)
            return pool

        return make

    container = Container()
    for tag in TAGS:
        container = container.bind(make_factory(tag), scope=Scope.SINGLETON, provides=Pool, tag=tag)
    frozen = container.freeze()

    def worker() -> None:
        _ = start.wait()
        for tag in TAGS:
            _ = per_key.wait()
            value = frozen.resolve(Pool, tag=tag)
            with record:
                resolved[tag].append(value)

    _run_in_threads(worker)

    assert all(len(pools) == 1 for pools in built.values())
    assert all(len(values) == THREADS for values in resolved.values())
    assert all(all(value is built[tag][0] for value in resolved[tag]) for tag in TAGS)


def test_scopes_stay_isolated_and_every_teardown_runs_with_no_gil() -> None:
    class Session: ...

    torn_down: list[Session] = []
    seen: list[Session] = []
    record = threading.Lock()
    gate = threading.Barrier(THREADS)

    def open_session() -> Generator[Session]:
        session = Session()
        yield session
        with record:
            torn_down.append(session)

    frozen = Container().bind(open_session, scope=Scope.SCOPED).freeze()

    # Each thread runs in its own Context, so `scope()` hands each one a separate
    # frame: this asserts isolation and teardown completeness, not lock behaviour.
    # The contended paths are covered by the other two tests in this module.
    def worker() -> None:
        _ = gate.wait()
        with frozen.scope():
            first = frozen[Session]
            second = frozen[Session]
            assert first is second
            with record:
                seen.append(first)

    _run_in_threads(worker)

    assert len({id(session) for session in seen}) == THREADS
    assert len(torn_down) == THREADS


def test_the_unified_flight_table_survives_concurrent_creation() -> None:
    frame = ScopeFrame()
    mutex = object.__getattribute__(frame, '_mutex')
    assert isinstance(mutex, type(threading.Lock()))
    object.__setattr__(frame, '_flights', _RendezvousFlightTable(mutex, threading.Barrier(THREADS)))

    key = object()
    handed_out: list[tuple[object, bool]] = []
    record = threading.Lock()
    start = threading.Barrier(THREADS)

    def worker() -> None:
        _ = start.wait()
        flight = frame._start_flight(key)
        with record:
            handed_out.append(flight)

    _run_in_threads(worker)

    assert len(handed_out) == THREADS
    assert sum(constructs for _, constructs in handed_out) == 1
    leaders = [flight for flight, constructs in handed_out if constructs]
    followers = [flight for flight, constructs in handed_out if not constructs]
    assert len(leaders) == 1
    assert len(followers) == THREADS - 1
    assert all(flight is followers[0] for flight in followers)
    assert leaders[0] is not followers[0]


def test_async_singleton_is_single_flight_across_event_loops() -> None:
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_run_cross_loop_singleton, args=(child,))
    try:
        process.start()
        child.close()
        if not parent.poll(30):
            pytest.fail('cross-loop singleton worker sent no result within 30 seconds')
        result = parent.recv_bytes().decode()
        process.join(30)
        if process.is_alive():
            pytest.fail('cross-loop singleton worker did not exit within 30 seconds')
        assert process.exitcode == 0
        assert result == 'success:constructed=1 resolved=32 identities=1 failures=0'
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)


def test_scope_context_is_explicit_in_child_threads_and_inherited_by_sibling_tasks() -> None:
    class Session: ...

    frozen = Container().bind(Session, scope=Scope.SCOPED).freeze()
    observed_frames: list[ScopeFrame | None] = []
    record = threading.Lock()

    def child() -> None:
        with record:
            observed_frames.append(optional_frame())

    async def resolve_siblings() -> tuple[Session, Session]:
        return await asyncio.gather(frozen.aresolve(Session), frozen.aresolve(Session))

    with frozen.scope() as frame:
        first, second = asyncio.run(resolve_siblings())
        child_threads = [threading.Thread(target=child) for _ in range(2)]
        for thread in child_threads:
            thread.start()
        for thread in child_threads:
            thread.join()

    assert first is second
    inherited = all(observed is frame for observed in observed_frames)
    isolated = all(observed is None for observed in observed_frames)
    assert inherited or isolated


def test_override_context_isolated_or_inherited_by_child_threads() -> None:
    class Service: ...

    frozen = Container().bind(Service, scope=Scope.SINGLETON).freeze()
    replacement = Service()
    observed: list[Service] = []
    record = threading.Lock()

    def child() -> None:
        value = frozen.resolve(Service)
        with record:
            observed.append(value)

    async def resolve_siblings() -> tuple[Service, Service]:
        return await asyncio.gather(frozen.aresolve(Service), frozen.aresolve(Service))

    with frozen.override(Service, replacement):
        sibling = asyncio.run(resolve_siblings())
        child_threads = [threading.Thread(target=child) for _ in range(2)]
        for thread in child_threads:
            thread.start()
        for thread in child_threads:
            thread.join()

    assert all(value is replacement for value in sibling)
    inherited = all(value is replacement for value in observed)
    isolated = all(value is not replacement for value in observed)
    assert inherited or isolated
