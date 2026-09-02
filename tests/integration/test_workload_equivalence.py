"""A workload's implementations do the same work, proved before any of them is timed.

Equality of two `Observation` values is what makes a published ratio mean
something: the result, the types constructed in construction order, the resources
closed in teardown order, and the error all have to match. An implementation that
skips the work is not faster, and this is where that is caught.
"""

import pytest

from benchmarks.contracts import Implementation, Workload
from benchmarks.test_latency import inventory

WORKLOADS = inventory()

PAIRED = [
    (workload, candidate)
    for workload in WORKLOADS
    if workload.baseline is not None
    for candidate in (workload.baseline, *workload.alternatives)
]

PAIRED_IDS = [f'{workload.name}-{candidate.label}' for workload, candidate in PAIRED]

UNPAIRED = [workload for workload in WORKLOADS if workload.baseline is None]

UNPAIRED_IDS = [workload.name for workload in UNPAIRED]


@pytest.mark.parametrize(('workload', 'candidate'), PAIRED, ids=PAIRED_IDS)
def test_an_implementation_observes_what_the_subject_observes(
    workload: Workload,
    candidate: Implementation,
) -> None:
    assert candidate.observe() == workload.subject.observe()


@pytest.mark.parametrize('workload', UNPAIRED, ids=UNPAIRED_IDS)
def test_a_subject_without_a_baseline_still_observes(workload: Workload) -> None:
    observed = workload.subject.observe()
    assert observed.result or observed.error


@pytest.mark.parametrize('workload', WORKLOADS, ids=[workload.name for workload in WORKLOADS])
def test_an_observation_is_reproducible(workload: Workload) -> None:
    assert workload.subject.observe() == workload.subject.observe()
