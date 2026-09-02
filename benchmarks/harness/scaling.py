"""An operation's cost curve over sizes, and the complexity-class test over it.

A fixed-size latency gate cannot see a complexity change: the failing-freeze walk
was cubic while every timing case in the suite stayed green, because none of them
grew. What moves under a complexity change is the *ratio* between two sizes, and a
ratio cancels the host's speed along with most of its noise — which is why this
gate is the one that catches an algorithm and the latency gate is not.
"""

import gc
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

from benchmarks.harness import HarnessError

MINIMUM_SECONDS = 0.05
REPEATS = 3


@dataclass(frozen=True, slots=True)
class Step:
    """One size-to-size comparison, against the growth the complexity class predicts.

    `excess` is how far the observed growth overshot the predicted one, on the same
    scale a budget is written on: 0.0 when the operation grew exactly as its class
    says it should, 0.15 when it grew 15% faster than that.
    """

    smaller: int
    larger: int
    observed: float
    expected: float
    excess: float


def _time_once(operation: Callable[[], object], iterations: int) -> float:
    started = time.perf_counter()
    for _ in range(iterations):
        _ = operation()
    return time.perf_counter() - started


def cost(
    operation: Callable[[], object],
    *,
    repeats: int = REPEATS,
    minimum_seconds: float = MINIMUM_SECONDS,
) -> float:
    """Seconds per invocation of `operation`, as the best of `repeats` passes.

    The pass count is calibrated up until one pass accumulates `minimum_seconds`,
    so a fast operation is not read off a single clock tick. The minimum across
    passes is kept rather than the mean, because the minimum is the reading least
    contaminated by the rest of the machine.

    Raises:
        HarnessError: `repeats` is below one, or `minimum_seconds` is not positive.
    """
    if repeats < 1:
        raise HarnessError(f'{repeats} repeats; at least one pass is needed')
    if minimum_seconds <= 0.0:
        raise HarnessError(f'{minimum_seconds} seconds; the accumulation target must be positive')
    iterations = 1
    elapsed = _time_once(operation, iterations)
    while elapsed < minimum_seconds:
        iterations *= 2
        elapsed = _time_once(operation, iterations)
    best = elapsed
    for _ in range(repeats - 1):
        best = min(best, _time_once(operation, iterations))
    return best / iterations


def curve(
    build: Callable[[int], Callable[[], object]],
    sizes: Sequence[int],
    *,
    repeats: int = REPEATS,
    minimum_seconds: float = MINIMUM_SECONDS,
) -> dict[int, float]:
    """Measure seconds per operation at each size.

    `build` returns the operation to measure at a given size; everything it does to
    set that size up stays outside the timed region. Each size is measured over
    enough iterations to accumulate `minimum_seconds`, and the best of `repeats`
    passes is kept, because the minimum is the reading least contaminated by the
    rest of the machine.

    Raises:
        HarnessError: `sizes` is empty or not strictly increasing, a size is below
            one, or `cost` rejects the pass settings.
    """
    if not sizes:
        raise HarnessError('no sizes to measure; a curve needs at least one point')
    if any(size < 1 for size in sizes):
        raise HarnessError(f'sizes {list(sizes)} carry a size below one')
    if any(later <= earlier for earlier, later in pairwise(sizes)):
        raise HarnessError(f'sizes {list(sizes)} are not strictly increasing; a curve needs an order to grow along')

    costs: dict[int, float] = {}
    for size in sizes:
        operation = build(size)
        _ = gc.collect()
        costs[size] = cost(operation, repeats=repeats, minimum_seconds=minimum_seconds)
    return costs


def steps(costs: Mapping[int, float], *, exponent: float) -> tuple[Step, ...]:
    """Compare consecutive sizes against the growth an O(n**exponent) operation predicts.

    `exponent` is the complexity class being asserted: 0 for an operation whose cost
    does not depend on size, 1 for a linear one, 2 for a quadratic one.

    Raises:
        HarnessError: fewer than two sizes, or a cost that is not positive.
    """
    sizes = sorted(costs)
    if len(sizes) < 2:
        raise HarnessError('a complexity comparison needs at least two sizes')
    for size in sizes:
        if costs[size] <= 0.0:
            raise HarnessError(f'size {size} measured {costs[size]!r}; a cost must be positive')

    measured: list[Step] = []
    for smaller, larger in pairwise(sizes):
        observed = costs[larger] / costs[smaller]
        expected = (larger / smaller) ** exponent
        measured.append(
            Step(smaller=smaller, larger=larger, observed=observed, expected=expected, excess=observed / expected - 1.0)
        )
    return tuple(measured)
