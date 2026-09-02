"""One pytest-benchmark case per implementation of every latency workload in the inventory.

Both the depin subject and its direct baseline are timed, so the two land in the
same report and a published ratio comes from one run rather than two.

The shell is also where two things the harness cannot reach from outside are set:
each case's sampling floor, derived from the cost the accepted dataset recorded for
it, and the tier and CPU reading filed into `extra_info` so the reduction step can
separate the tiers and publish CPU beside wall time.
"""

from collections.abc import Callable
from typing import Protocol

import pytest

from benchmarks.contracts import Cost, Implementation, Metric, Workload
from benchmarks.harness import published, reduce
from benchmarks.workloads import WORKLOADS


class Benchmark(Protocol):
    """The subset of pytest-benchmark's fixture this shell uses.

    Declared locally so the benchmarks do not depend on the plugin shipping
    accurate type information.
    """

    extra_info: dict[str, object]

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


_PUBLISHED: dict[str, float] = {
    name[name.index('[') + 1 : -1]: median
    for name, median in published.costs().items()
    if name.endswith(']') and '[' in name
}
"""Seconds per round per case, keyed the way this module names a case.

The report keys a benchmark by its full node name; this module knows a case by the
parameter id inside it. Reading the id back out is what keeps the two agreeing
without either of them naming the other's test function.
"""


def floor(case: str) -> int:
    """The rounds floor for one case, from the cost the accepted dataset recorded.

    A case the dataset does not cover — a workload added since it was published —
    falls back to the round-count branch of `reduce.qualifies`, which is the only
    branch that can be satisfied without knowing what the operation costs.
    """
    median = _PUBLISHED.get(case)
    return reduce.MINIMUM_ROUNDS if median is None else reduce.rounds_for(median)


_CASES: tuple[tuple[str, Workload, Implementation], ...] = tuple(
    (f'{workload.name}-{candidate.label}', workload, candidate)
    for workload in inventory()
    if workload.claim.metric is Metric.LATENCY
    for candidate in implementations(workload)
)


@pytest.mark.parametrize(
    ('workload', 'implementation'),
    [
        pytest.param(workload, candidate, marks=pytest.mark.benchmark(min_rounds=floor(name)), id=name)
        for name, workload, candidate in _CASES
    ],
)
def test_latency(benchmark: Benchmark, workload: Workload, implementation: Implementation) -> None:
    prepared = implementation.prepare()
    try:
        # pytest-benchmark returns the result of one further call it makes after
        # the timed rounds and does not measure, so reading a `Cost` off it costs
        # the measurement nothing.
        outcome = benchmark(prepared.call)
    finally:
        if prepared.close is not None:
            prepared.close()

    benchmark.extra_info['tier'] = workload.tier.value
    if isinstance(outcome, Cost):
        benchmark.extra_info['cpu_nanoseconds'] = outcome.cpu_nanoseconds
