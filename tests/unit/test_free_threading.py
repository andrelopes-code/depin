"""Container invariants under true thread parallelism, on a free-threaded build.

`tests/unit/test_thread_safety.py` forces interleaving with
`sys.setswitchinterval`, which is meaningless without a GIL. These tests instead
rely on threads genuinely running at the same time, and are skipped on a build
where the GIL is enabled.
"""

import sys
import threading
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


def test_a_singleton_is_built_once_with_no_gil() -> None:
    class Pool: ...

    built: list[Pool] = []
    resolved: list[Pool] = []
    record = threading.Lock()
    gate = threading.Barrier(THREADS)

    def make() -> Pool:
        pool = Pool()
        with record:
            built.append(pool)
        return pool

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Pool).freeze()

    def worker() -> None:
        _ = gate.wait()
        value = frozen[Pool]
        with record:
            resolved.append(value)

    _run_in_threads(worker)

    assert len(built) == 1
    assert len(resolved) == THREADS
    assert all(value is built[0] for value in resolved)


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
    keys = tuple(range(64))
    handed_out: list[tuple[int, int]] = []
    record = threading.Lock()
    gate = threading.Barrier(THREADS)

    def worker() -> None:
        _ = gate.wait()
        pairs = [(key, id(frame.sync_lock_for(key))) for key in keys]
        with record:
            handed_out.extend(pairs)

    _run_in_threads(worker)

    by_key: dict[int, set[int]] = {}
    for key, lock_id in handed_out:
        by_key.setdefault(key, set()).add(lock_id)

    assert len(by_key) == len(keys)
    assert all(len(ids) == 1 for ids in by_key.values())
