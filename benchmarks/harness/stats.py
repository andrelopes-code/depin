"""The paired statistic a latency verdict is formed from.

The measurement protocol runs R repetitions, each measuring both revisions in
independent processes. The statistic over those repetitions is the **median of the
paired log ratios**, not a ratio of means: pairing removes the drift both sides
saw together, the log makes a slowdown and the matching speedup symmetric, and the
median keeps one thermally disturbed repetition from setting the verdict.

Its uncertainty is a 95% percentile bootstrap over the same paired differences,
2000 resamples, from a fixed seed — so a verdict is reproducible from the data
that produced it rather than merely repeatable in distribution.
"""

import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from benchmarks.harness import HarnessError

DEFAULT_RESAMPLES = 2000
LOWER_QUANTILE = 0.025
UPPER_QUANTILE = 0.975


@dataclass(frozen=True, slots=True)
class Paired:
    """A paired comparison, expressed as head-over-base excess.

    `ratio` is 0.0 when the two revisions measured the same, and 0.05 when the head
    is 5% slower — the same scale a budget is written on, so the decision rule
    compares them directly. `low` and `high` bound it at 95%.
    """

    ratio: float
    low: float
    high: float
    n: int


def _percentile(ordered: Sequence[float], quantile: float) -> float:
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _positive(values: Sequence[float], side: str) -> None:
    for index, value in enumerate(values):
        if not math.isfinite(value) or value <= 0.0:
            raise HarnessError(f'{side}[{index}] is {value!r}; a duration must be finite and positive')


def paired_ratio(
    base: Sequence[float],
    head: Sequence[float],
    *,
    seed: int,
    resamples: int = DEFAULT_RESAMPLES,
) -> Paired:
    """Compare two revisions measured in matched repetitions.

    `base[i]` and `head[i]` must be the same repetition of the same workload:
    the statistic is defined over the differences within a pair, and pairing two
    measurements that did not run together removes nothing.

    Raises:
        HarnessError: the two sequences differ in length, are empty, carry a
            duration that is not finite and positive, or `resamples` is below one.
    """
    if len(base) != len(head):
        raise HarnessError(f'{len(base)} base measurements against {len(head)} head measurements; pairs must match')
    if not base:
        raise HarnessError('no measurements to pair')
    if resamples < 1:
        raise HarnessError(f'{resamples} resamples; the bootstrap needs at least one')
    _positive(base, 'base')
    _positive(head, 'head')

    differences = [math.log(after) - math.log(before) for before, after in zip(base, head, strict=True)]
    count = len(differences)
    generator = random.Random(seed)
    resampled = sorted(
        statistics.median([differences[generator.randrange(count)] for _ in range(count)]) for _ in range(resamples)
    )
    return Paired(
        ratio=math.expm1(statistics.median(differences)),
        low=math.expm1(_percentile(resampled, LOWER_QUANTILE)),
        high=math.expm1(_percentile(resampled, UPPER_QUANTILE)),
        n=count,
    )
