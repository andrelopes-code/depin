"""A frozen container shared across threads: single-flight construction, isolated scopes."""

import sys
import threading
from collections.abc import Callable, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope

THREADS = 8
_SPIN = 20_000


@pytest.fixture(autouse=True)
def frequent_thread_switches() -> Generator[None]:
    """Force the interpreter to preempt threads mid-construction.

    A provider that returns without ever releasing the GIL is effectively atomic,
    so a container with no locking would still look correct. Shrinking the switch
    interval, combined with `_busy()` below, makes every worker preempt inside the
    provider — the interleaving these tests exist to check. Deterministic: no
    sleeps and no wall-clock assertions, only a bounded amount of work.
    """
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(previous)


def _busy() -> None:
    total = 0
    for i in range(_SPIN):
        total += i


def _run_in_threads(work: Callable[[], None]) -> None:
    threads = [threading.Thread(target=work) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_singleton_is_constructed_once_under_thread_contention() -> None:
    class Pool: ...

    constructions: list[Pool] = []
    resolved: list[Pool] = []
    lock = threading.Lock()
    # The barrier releases every worker at the same instant, so the threads
    # contend for the same cache miss instead of arriving one after another.
    gate = threading.Barrier(THREADS)

    def make() -> Pool:
        _busy()
        pool = Pool()
        with lock:
            constructions.append(pool)
        return pool

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Pool).freeze()

    def worker() -> None:
        _ = gate.wait()
        value = frozen[Pool]
        with lock:
            resolved.append(value)

    _run_in_threads(worker)

    assert len(constructions) == 1
    assert len(resolved) == THREADS
    assert all(value is constructions[0] for value in resolved)


def test_a_racing_singleton_generator_leaves_exactly_one_teardown() -> None:
    class Conn: ...

    torn_down: list[Conn] = []
    lock = threading.Lock()
    gate = threading.Barrier(THREADS)

    def connect() -> Generator[Conn]:
        _busy()
        conn = Conn()
        yield conn
        with lock:
            torn_down.append(conn)

    frozen = Container().bind(connect, scope=Scope.SINGLETON).freeze()

    def worker() -> None:
        _ = gate.wait()
        _ = frozen[Conn]

    _run_in_threads(worker)
    frozen.close()

    assert len(torn_down) == 1


def test_a_dependency_chain_builds_each_key_once_under_contention() -> None:
    class Config: ...

    class Repo:
        def __init__(self, config: Config) -> None:
            self.config = config

    built: list[str] = []
    lock = threading.Lock()
    gate = threading.Barrier(THREADS)

    def make_config() -> Config:
        _busy()
        with lock:
            built.append('config')
        return Config()

    def make_repo(config: Config) -> Repo:
        _busy()
        with lock:
            built.append('repo')
        return Repo(config)

    frozen = (
        Container()
        .bind(make_config, scope=Scope.SINGLETON, provides=Config)
        .bind(make_repo, scope=Scope.SINGLETON, provides=Repo)
        .freeze()
    )

    def worker() -> None:
        _ = gate.wait()
        _ = frozen[Repo]

    _run_in_threads(worker)

    assert sorted(built) == ['config', 'repo']


def test_scopes_opened_in_different_threads_are_independent() -> None:
    class Session: ...

    seen: list[Session] = []
    lock = threading.Lock()
    gate = threading.Barrier(THREADS)

    frozen = Container().bind(Session, scope=Scope.SCOPED).freeze()

    def worker() -> None:
        _ = gate.wait()
        with frozen.scope():
            first = frozen[Session]
            second = frozen[Session]
            assert first is second
            with lock:
                seen.append(first)

    _run_in_threads(worker)

    assert len({id(session) for session in seen}) == THREADS
