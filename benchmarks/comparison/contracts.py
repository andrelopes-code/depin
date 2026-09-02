"""Immutable contracts for classifying and judging competitor implementations."""

from dataclasses import dataclass
from enum import Enum

from benchmarks.contracts import Implementation, Metric, Workload
from benchmarks.harness import HarnessError


class Equivalence(Enum):
    EQUIVALENT = 'equivalent'
    PARTIAL = 'partial'
    INCOMPARABLE = 'incomparable'


@dataclass(frozen=True, slots=True)
class Competitor:
    distribution: str
    version: str

    @property
    def label(self) -> str:
        return f'{self.distribution}-{self.version}'


@dataclass(frozen=True, slots=True)
class Candidate:
    workload: str
    competitor: Competitor
    equivalence: Equivalence
    reason: str
    implementation: Implementation | None

    def __post_init__(self) -> None:
        if not self.workload.isidentifier() or self.workload.lower() != self.workload:
            raise HarnessError(f'{self.workload!r}: candidate workload must be a stable lower-case identifier')
        if not self.reason or self.reason.strip() != self.reason:
            raise HarnessError(f'{self.competitor.label}: candidate reason must be non-empty and unpadded')
        if self.equivalence is Equivalence.INCOMPARABLE:
            if self.implementation is not None:
                raise HarnessError(f'{self.competitor.label}: incomparable candidate must not carry an implementation')
        elif self.implementation is None:
            raise HarnessError(
                f'{self.competitor.label}: {self.equivalence.value} candidate requires an implementation'
            )
        elif self.implementation.label != self.competitor.label:
            raise HarnessError(
                f'{self.competitor.label}: implementation label is {self.implementation.label!r}; '
                'dataset labels must include the pinned distribution and version'
            )


@dataclass(frozen=True, slots=True)
class AbsoluteTarget:
    fixed_seconds: float
    fraction_of_direct: float | None
    justification: str

    def __post_init__(self) -> None:
        if self.fixed_seconds <= 0.0:
            raise HarnessError(f'{self.fixed_seconds}: fixed target must be positive')
        if self.fraction_of_direct is not None and not 0.0 < self.fraction_of_direct <= 1.0:
            raise HarnessError(f'{self.fraction_of_direct}: direct fraction must be within (0, 1]')
        if not self.justification or self.justification.strip() != self.justification:
            raise HarnessError('target justification must be non-empty and unpadded')

    def ceiling(self, direct_seconds: float) -> float:
        proportional = self.fixed_seconds
        if self.fraction_of_direct is not None:
            proportional = direct_seconds * self.fraction_of_direct
        return min(self.fixed_seconds, proportional)


@dataclass(frozen=True, slots=True)
class ComparativeWorkload:
    workload: Workload
    candidates: tuple[Candidate, ...]
    target: AbsoluteTarget | None
    secondary_metrics: tuple[Metric, ...] = ()
