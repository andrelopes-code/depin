"""Reproducible diagnostics for contended singleton and scope operations."""

import argparse
import subprocess
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier, Event, Lock
from typing import Literal, TypedDict

from benchmarks.harness import HarnessError, quantile, write_json
from benchmarks.harness.environment import capture
from depin import Container, Scope

Subject = Literal['depin', 'direct']
Wave = Callable[[ThreadPoolExecutor, Subject, int], float]


@dataclass(frozen=True, slots=True)
class _Value:
    serial: int = 1


@dataclass(frozen=True, slots=True)
class _Leaf:
    serial: int = 1


@dataclass(frozen=True, slots=True)
class _Root:
    leaf: _Leaf


class Percentiles(TypedDict):
    p50_seconds: float
    p95_seconds: float
    p99_seconds: float


class Profile(TypedDict):
    contract: str
    depin: Percentiles
    direct: Percentiles
    overhead: Percentiles
    ratio: Percentiles


class Result(TypedDict):
    schema_version: int
    source_revision: str
    environment: dict[str, object]
    samples: int
    workers: int
    profiles: dict[str, Profile]


def _revision() -> str:
    completed = subprocess.run(('git', 'rev-parse', 'HEAD'), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise HarnessError('cannot determine the source revision; run contention collection from a Git checkout')
    return completed.stdout.strip()


def _wait(event: Event, name: str) -> None:
    if not event.wait(timeout=10.0):
        raise HarnessError(f'contention experiment timed out waiting for {name}')


def _singleton_first_use(executor: ThreadPoolExecutor, subject: Subject, workers: int) -> float:
    gate = Barrier(workers + 1, timeout=10.0)
    provider_started = Event()
    contenders_ready = Event()
    contender_lock = Lock()
    provider_calls: list[None] = []
    contenders = 0

    def make() -> _Value:
        provider_calls.append(None)
        provider_started.set()
        _wait(contenders_ready, 'singleton contenders')
        return _Value()

    if subject == 'depin':
        frozen = Container().bind(make, provides=_Value, scope=Scope.SINGLETON).freeze()

        def resolve() -> _Value:
            return frozen.resolve(_Value)

    else:
        direct_lock = Lock()
        direct_value: _Value | None = None

        def resolve() -> _Value:
            nonlocal direct_value
            with direct_lock:
                if direct_value is None:
                    direct_value = make()
                return direct_value

    def worker(index: int) -> _Value:
        nonlocal contenders
        _ = gate.wait()
        if index:
            _wait(provider_started, 'singleton provider')
            with contender_lock:
                contenders += 1
                if contenders == workers - 1:
                    contenders_ready.set()
        return resolve()

    futures = [executor.submit(worker, index) for index in range(workers)]
    started = time.perf_counter_ns()
    _ = gate.wait()
    values = [future.result(timeout=10.0) for future in futures]
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    if len(provider_calls) != 1 or any(value is not values[0] for value in values[1:]):
        raise HarnessError('singleton contention violated the single-flight lifecycle contract')
    return elapsed


def _cached_singleton(executor: ThreadPoolExecutor, subject: Subject, workers: int) -> float:
    value = _Value()
    if subject == 'depin':
        frozen = Container().bind(_Value, scope=Scope.SINGLETON).freeze()
        value = frozen.resolve(_Value)

        def resolve() -> _Value:
            return frozen.resolve(_Value)

    else:

        def resolve() -> _Value:
            return value

    gate = Barrier(workers + 1, timeout=10.0)

    def worker() -> _Value:
        _ = gate.wait()
        return resolve()

    futures = [executor.submit(worker) for _ in range(workers)]
    started = time.perf_counter_ns()
    _ = gate.wait()
    values = [future.result(timeout=10.0) for future in futures]
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    if any(resolved is not value for resolved in values):
        raise HarnessError('cached singleton contention returned a value outside the warm cache')
    return elapsed


def _request_scopes(executor: ThreadPoolExecutor, subject: Subject, workers: int) -> float:
    if subject == 'depin':
        frozen = Container().bind(_Leaf, scope=Scope.SCOPED).bind(_Root, scope=Scope.SCOPED).freeze()

        def resolve() -> _Root:
            with frozen.scope():
                return frozen.resolve(_Root)

    else:

        def resolve() -> _Root:
            return _Root(_Leaf())

    gate = Barrier(workers + 1, timeout=10.0)

    def worker() -> _Root:
        _ = gate.wait()
        return resolve()

    futures = [executor.submit(worker) for _ in range(workers)]
    started = time.perf_counter_ns()
    _ = gate.wait()
    values = [future.result(timeout=10.0) for future in futures]
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    if len({id(value) for value in values}) != workers or len({id(value.leaf) for value in values}) != workers:
        raise HarnessError('concurrent request scopes shared a scoped value')
    return elapsed


def _percentiles(values: Sequence[float]) -> Percentiles:
    ordered = sorted(values)
    return {
        'p50_seconds': quantile(ordered, 0.50),
        'p95_seconds': quantile(ordered, 0.95),
        'p99_seconds': quantile(ordered, 0.99),
    }


def _profile(wave: Wave, *, samples: int, workers: int, contract: str) -> Profile:
    readings: dict[Subject, list[float]] = {'depin': [], 'direct': []}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='depin-contention') as executor:
        for sample in range(samples):
            order: tuple[Subject, Subject] = ('depin', 'direct') if sample % 2 == 0 else ('direct', 'depin')
            for subject in order:
                readings[subject].append(wave(executor, subject, workers))
    depin = _percentiles(readings['depin'])
    direct = _percentiles(readings['direct'])
    overhead: Percentiles = {
        'p50_seconds': depin['p50_seconds'] - direct['p50_seconds'],
        'p95_seconds': depin['p95_seconds'] - direct['p95_seconds'],
        'p99_seconds': depin['p99_seconds'] - direct['p99_seconds'],
    }
    ratio: Percentiles = {
        'p50_seconds': depin['p50_seconds'] / direct['p50_seconds'],
        'p95_seconds': depin['p95_seconds'] / direct['p95_seconds'],
        'p99_seconds': depin['p99_seconds'] / direct['p99_seconds'],
    }
    return {'contract': contract, 'depin': depin, 'direct': direct, 'overhead': overhead, 'ratio': ratio}


def collect(*, samples: int, workers: int) -> Result:
    """Measure explicitly synchronized contention without timed sleeps."""
    if samples < 5:
        raise HarnessError('contention collection requires at least 5 samples')
    if workers < 2:
        raise HarnessError('contention collection requires at least 2 workers')
    profiles = {
        'singleton_first_use': _profile(
            _singleton_first_use,
            samples=samples,
            workers=workers,
            contract='One singleton construction shared by every contending resolver.',
        ),
        'cached_singleton': _profile(
            _cached_singleton,
            samples=samples,
            workers=workers,
            contract='One warmed singleton value returned unchanged to every concurrent resolver.',
        ),
        'request_scopes': _profile(
            _request_scopes,
            samples=samples,
            workers=workers,
            contract='One independent scoped graph per concurrent worker, entered, resolved, and closed.',
        ),
    }
    return {
        'schema_version': 1,
        'source_revision': _revision(),
        'environment': capture(),
        'samples': samples,
        'workers': workers,
        'profiles': profiles,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--out', type=Path, required=True)
    chosen = parser.parse_args(argv)
    result = collect(samples=chosen.samples, workers=chosen.workers)
    write_json(chosen.out, dict(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
