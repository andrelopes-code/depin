"""The claim contract a workload carries, and the shapes every tier is expressed in.

A workload is measurable only once it states what question it answers, what work
it performs, where the timed region starts and stops, and which conclusions it
cannot support. `Claim` is that statement, and `tests/unit/test_workload_contracts.py`
rejects a workload that does not carry a complete one.

`Implementation` separates the two things a benchmark conflates: the callable a
harness times, and what that callable observably does. The second is checkable by
an ordinary test, so equivalence between `depin` and its direct baseline is proved
before either is timed rather than inferred from the benchmark completing.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class Tier(Enum):
    """Which question a workload answers. Results from different tiers are never merged."""

    ISOLATED = 'isolated'
    COMPONENT = 'component'
    APPLICATION = 'application'
    SCALING = 'scaling'


class Metric(Enum):
    """What is recorded. A workload declares one, and the harness that reads it refuses the rest."""

    LATENCY = 'latency'
    ALLOCATIONS = 'allocations'
    RETAINED = 'retained'
    SCALING = 'scaling'


class NoiseClass(Enum):
    """The dispersion band a workload was measured into, under the paired protocol.

    Quoted as the 99th percentile of the paired statistic under the null
    hypothesis: `LOW` at or below 3%, `MEDIUM` at or below 6%, `HIGH` above it. A
    budget below its workload's band would fail on noise, so
    `benchmarks.harness.budgets` refuses one.

    A `Claim` does not carry one. The band is a measurement rather than an
    authored statement, and it belongs to the environment it was measured in, so
    it lives only in `benchmarks/budgets.toml` — where
    `benchmarks.harness.calibrate` writes it beside the p99 that produced it.
    """

    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


@dataclass(frozen=True, slots=True)
class Claim:
    """What a workload is allowed to be read as saying.

    ``included`` is the setup inside the timed region because a user necessarily
    pays for it; ``excluded`` is the setup outside it. Stating both is what makes
    a number attributable: a reader can tell whether an event loop, a container
    freeze, or a framework's routing sits inside the measurement.

    ``invalid`` is not optional. Every workload here can be misread, and the
    misreadings are more useful to record than the number is.
    """

    question: str
    work: str
    included: str
    excluded: str
    semantics: str
    shape: str
    concurrency: str
    metric: Metric
    unit: str
    valid: tuple[str, ...]
    invalid: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Observation:
    """What one implementation of a workload does, with no timing in it.

    Two implementations of the same workload are comparable only when their
    observations are equal. ``constructed`` and ``closed`` carry order, because a
    container that builds the same objects in a different order, or closes them
    in a different one, is not doing the same work.
    """

    result: str
    constructed: tuple[str, ...]
    closed: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Cost:
    """What one timed call consumed beyond wall time.

    A timed callable may return one of these instead of its result, and the
    timing shell files what it carries beside the wall-clock aggregate. Process
    CPU is the reason the type exists: a higher request rate bought with more CPU
    is not an improvement, so a throughput figure is never published without CPU
    beside it.

    Only the application tier returns one. A microbenchmark's rounds are a
    calibrated loop, and `time.process_time_ns` has a resolution that makes a
    per-round CPU reading of a microsecond-scale operation meaningless.
    """

    cpu_nanoseconds: int


@dataclass(frozen=True, slots=True)
class Prepared:
    """A workload's timed callable, and the resources its setup opened.

    ``close`` exists for the implementations that hold an event loop or an ASGI
    transport: those are set up outside the timed region and have to be released
    when the harness is done with the callable.
    """

    call: Callable[[], object]
    close: Callable[[], None] | None = None


@dataclass(frozen=True, slots=True)
class Implementation:
    """One way of performing a workload: what to time, and what it observably does.

    ``label`` names the implementation in published tables. `depin` is always
    ``'depin'``; the mandatory direct-Python baseline is always ``'direct'``; a
    competitor adapter carries the distribution name and version it was measured
    against.
    """

    label: str
    prepare: Callable[[], Prepared]
    observe: Callable[[], Observation]


@dataclass(frozen=True, slots=True)
class Workload:
    """A claim, the `depin` implementation of it, and everything it is compared with.

    ``baseline`` is the direct-Python implementation. It is optional in the type
    only because a startup workload such as `freeze()` has no direct counterpart
    — there is no handwritten equivalent of validating a graph that was never
    declared. `tests/unit/test_workload_contracts.py` requires one everywhere
    else, and requires the claim to name the reason when it is absent.

    ``alternatives`` holds competitor adapters. They are measured under the same
    equivalence rule as the baseline: an adapter whose `Observation` differs is
    rejected by the contract test rather than published with a caveat.
    """

    name: str
    tier: Tier
    claim: Claim
    subject: Implementation
    baseline: Implementation | None = None
    alternatives: tuple[Implementation, ...] = field(default_factory=tuple)
