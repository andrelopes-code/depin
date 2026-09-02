"""One pytest-benchmark case per implementation of every latency workload in the inventory.

Both the depin subject and its direct baseline are timed, so the two land in the
same report and a published ratio comes from one run rather than two.
"""

from collections.abc import Callable
from typing import Protocol

import pytest

from benchmarks.contracts import Implementation, Metric, Workload
from benchmarks.workloads import WORKLOADS


class Benchmark(Protocol):
    """The subset of pytest-benchmark's fixture this shell uses.

    Declared locally so the benchmarks do not depend on the plugin shipping
    accurate type information.
    """

    def __call__[T](self, function: Callable[[], T]) -> T: ...


def inventory() -> tuple[Workload, ...]:
    """Every workload this repository declares, in registration order.

    `benchmarks.workloads` is the registry each tier registers into, and it is the
    only source: a workload reachable here but absent from the registry would be
    measured and never gated, since the gate expects a result for exactly what the
    registry lists.
    """
    return WORKLOADS


def implementations(workload: Workload) -> tuple[Implementation, ...]:
    """The subject, the direct baseline where there is one, and every alternative."""
    baseline = () if workload.baseline is None else (workload.baseline,)
    return (workload.subject, *baseline, *workload.alternatives)


_CASES: tuple[tuple[str, Implementation], ...] = tuple(
    (f'{workload.name}-{candidate.label}', candidate)
    for workload in inventory()
    if workload.claim.metric is Metric.LATENCY
    for candidate in implementations(workload)
)


@pytest.mark.parametrize(
    'implementation',
    [candidate for _, candidate in _CASES],
    ids=[name for name, _ in _CASES],
)
def test_latency(benchmark: Benchmark, implementation: Implementation) -> None:
    prepared = implementation.prepare()
    try:
        _ = benchmark(prepared.call)
    finally:
        if prepared.close is not None:
            prepared.close()
