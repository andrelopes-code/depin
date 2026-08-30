"""Container invariants under true thread parallelism, on a free-threaded build.

`tests/unit/test_thread_safety.py` forces interleaving with
`sys.setswitchinterval`, which is meaningless without a GIL. These tests instead
rely on threads genuinely running at the same time, and are skipped on a build
where the GIL is enabled.
"""

import asyncio
import sys
import threading
from _thread import LockType
from collections.abc import Callable, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope, ScopeFrame

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


class _RendezvousLockTable:
    def __init__(self, guard: LockType, rendezvous: threading.Barrier) -> None:
        self._guard = guard
        self._rendezvous = rendezvous
        self._values: dict[object, LockType] = {}

    def get(self, key: object) -> LockType | None:
        value = self._values.get(key)
        # Capturing before the rendezvous lets unguarded workers see absence before a write; the guard avoids deadlock.
        if value is None and not self._guard.locked():
            _ = self._rendezvous.wait()
        return value

    def __setitem__(self, key: object, value: LockType) -> None:
        self._values[key] = value


class _RendezvousFlightTable:
    def __init__(self, guard: LockType, rendezvous: threading.Barrier) -> None:
        self._guard = guard
        self._rendezvous = rendezvous
        self._values: dict[object, threading.Event] = {}

    def get(self, key: object) -> threading.Event | None:
        value = self._values.get(key)
        if value is None and not self._guard.locked():
            _ = self._rendezvous.wait()
        return value

    def __setitem__(self, key: object, value: threading.Event) -> None:
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


def test_the_per_key_lock_table_survives_concurrent_creation() -> None:
    frame = ScopeFrame()
    mutex = object.__getattribute__(frame, '_mutex')
    assert isinstance(mutex, type(threading.Lock()))
    object.__setattr__(frame, '_sync_locks', _RendezvousLockTable(mutex, threading.Barrier(THREADS)))

    key = object()
    handed_out: list[LockType] = []
    record = threading.Lock()
    start = threading.Barrier(THREADS)

    def worker() -> None:
        _ = start.wait()
        lock = frame.sync_lock_for(key)
        with record:
            handed_out.append(lock)

    _run_in_threads(worker)

    assert len(handed_out) == THREADS
    assert all(lock is handed_out[0] for lock in handed_out)


def test_async_singleton_is_single_flight_across_event_loops() -> None:
    class Pool: ...

    entered = 0
    entered_condition = threading.Condition()
    release_constructor = threading.Event()
    constructed: list[Pool] = []
    resolved: list[Pool] = []
    failures: list[BaseException] = []
    record = threading.Lock()
    start = threading.Barrier(THREADS)

    async def make_pool() -> Pool:
        await asyncio.to_thread(release_constructor.wait)
        pool = Pool()
        with record:
            constructed.append(pool)
        return pool

    frozen = Container().bind(make_pool, scope=Scope.SINGLETON, provides=Pool).freeze()
    frame = object.__getattribute__(frozen, '_root')
    mutex = object.__getattribute__(frame, '_mutex')
    object.__setattr__(frame, '_async_flights', _RendezvousFlightTable(mutex, threading.Barrier(THREADS)))

    def worker() -> None:
        nonlocal entered

        async def resolve() -> None:
            nonlocal entered
            with entered_condition:
                entered += 1
                if entered == THREADS:
                    release_constructor.set()
            value, same_value = await asyncio.gather(frozen.aresolve(Pool), frozen.aresolve(Pool))
            assert value is same_value
            with record:
                resolved.append(value)

        try:
            _ = start.wait()
            asyncio.run(resolve())
        except BaseException as exc:
            with record:
                failures.append(exc)

    _run_in_threads(worker)

    assert not failures
    assert len(constructed) == 1
    assert len(resolved) == THREADS
    assert all(value is constructed[0] for value in resolved)
