"""Assemble the complete ordered competitor comparison inventory."""

from pathlib import Path

from benchmarks.comparison.adapters import ADAPTERS, Adapter
from benchmarks.comparison.contracts import Candidate, ComparativeWorkload, Equivalence
from benchmarks.comparison.targets import load
from benchmarks.contracts import Metric, Workload
from benchmarks.harness import HarnessError
from benchmarks.workloads import WORKLOADS


def _index_candidates(adapter: Adapter, workloads: tuple[Workload, ...]) -> dict[str, Candidate]:
    expected = {workload.name for workload in workloads}
    indexed: dict[str, Candidate] = {}
    for candidate in adapter.candidates(workloads):
        if candidate.workload not in expected:
            raise HarnessError(
                f'{candidate.workload}: {adapter.competitor.label} produced an extra candidate; '
                'remove it or add the workload to the ordinary inventory'
            )
        if candidate.workload in indexed:
            raise HarnessError(
                f'{candidate.workload}: {adapter.competitor.label} produced a duplicate candidate; '
                'provide exactly one candidate for this workload'
            )
        indexed[candidate.workload] = candidate
    missing = expected - set(indexed)
    if missing:
        name = sorted(missing)[0]
        raise HarnessError(
            f'{name}: {adapter.competitor.label} is missing a candidate; provide one classification for this workload'
        )
    return indexed


def _target_path() -> Path:
    return Path(__file__).parent.parent / 'leadership-targets.toml'


def build() -> tuple[ComparativeWorkload, ...]:
    """Build the ordered matrix after validating adapter and target coverage."""
    targets = load(_target_path())
    expected_target_names = {
        workload.name
        for workload in WORKLOADS
        if workload.claim.metric is Metric.LATENCY and workload.baseline is not None
    }
    actual_target_names = set(targets)
    if actual_target_names != expected_target_names:
        missing = expected_target_names - actual_target_names
        extra = actual_target_names - expected_target_names
        detail = f'missing {sorted(missing)[0]}' if missing else f'extra {sorted(extra)[0]}'
        raise HarnessError(
            f'leadership targets coverage mismatch: {detail}; align targets with direct latency workloads'
        )

    indexed = tuple(_index_candidates(adapter, WORKLOADS) for adapter in ADAPTERS)
    comparative: list[ComparativeWorkload] = []
    for workload in WORKLOADS:
        candidates = tuple(by_workload[workload.name] for by_workload in indexed)
        labels = [candidate.implementation.label for candidate in candidates if candidate.implementation is not None]
        if len(labels) != len(set(labels)):
            raise HarnessError(f'{workload.name}: duplicate competitor implementation label; use unique pinned labels')
        for candidate in candidates:
            if (
                candidate.equivalence is Equivalence.EQUIVALENT
                and candidate.implementation is not None
                and candidate.implementation.observe() != workload.subject.observe()
            ):
                raise HarnessError(
                    f'{workload.name}: {candidate.competitor.label} claims equivalence with a different observation; '
                    'classify it as partial or fix its implementation'
                )
        comparative.append(ComparativeWorkload(workload, candidates, targets.get(workload.name)))
    return tuple(comparative)
