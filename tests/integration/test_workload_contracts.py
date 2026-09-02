"""Every workload carries a complete claim, and either a baseline or a stated reason for having none."""

import pytest

from benchmarks.contracts import Claim, Implementation, Metric, Workload
from benchmarks.harness import unmeasured
from benchmarks.test_latency import implementations, inventory

ABSENT_BASELINE = 'no direct baseline'
"""The wording a claim uses to account for a workload that carries no direct baseline.

Fixed so the omission is checkable rather than reviewable: a workload may skip the
baseline only where hand-written code has no counterpart to compare against, and
the claim has to say so in words a test can find.
"""

WORKLOADS = inventory()

IDS = [workload.name for workload in WORKLOADS]

CANDIDATES = [(workload, candidate) for workload in WORKLOADS for candidate in implementations(workload)]

CANDIDATE_IDS = [f'{workload.name}-{candidate.label}' for workload, candidate in CANDIDATES]


def _prose(claim: Claim) -> tuple[tuple[str, str], ...]:
    return (
        ('question', claim.question),
        ('work', claim.work),
        ('included', claim.included),
        ('excluded', claim.excluded),
        ('semantics', claim.semantics),
        ('shape', claim.shape),
        ('concurrency', claim.concurrency),
        ('unit', claim.unit),
    )


def _claim_text(claim: Claim) -> str:
    return ' '.join((*(stated for _, stated in _prose(claim)), *claim.valid, *claim.invalid)).lower()


def test_the_inventory_is_not_empty() -> None:
    assert WORKLOADS


def test_workload_names_are_unique() -> None:
    names = [workload.name for workload in WORKLOADS]
    assert sorted(names) == sorted(set(names))


@pytest.mark.parametrize('workload', WORKLOADS, ids=IDS)
def test_the_name_is_a_stable_identifier(workload: Workload) -> None:
    assert workload.name.isidentifier()
    assert workload.name == workload.name.lower()


@pytest.mark.parametrize('workload', WORKLOADS, ids=IDS)
def test_the_claim_states_every_prose_field(workload: Workload) -> None:
    for field, stated in _prose(workload.claim):
        assert stated, f'{workload.name}.claim.{field} is empty'
        assert stated.strip() == stated, f'{workload.name}.claim.{field} is padded'


@pytest.mark.parametrize('workload', WORKLOADS, ids=IDS)
def test_the_claim_lists_both_readings(workload: Workload) -> None:
    assert workload.claim.valid, f'{workload.name} lists no valid reading'
    assert workload.claim.invalid, f'{workload.name} lists no invalid reading'
    for reading in (*workload.claim.valid, *workload.claim.invalid):
        assert reading, f'{workload.name} lists an empty reading'
        assert reading.strip() == reading, f'{workload.name} lists a padded reading'


@pytest.mark.parametrize('workload', WORKLOADS, ids=IDS)
def test_a_latency_claim_is_recorded_in_seconds_per_operation(workload: Workload) -> None:
    if workload.claim.metric is not Metric.LATENCY:
        return
    assert workload.claim.unit == 'seconds per operation'


@pytest.mark.parametrize('workload', WORKLOADS, ids=IDS)
def test_a_missing_baseline_is_explained_by_the_claim(workload: Workload) -> None:
    if workload.baseline is not None:
        return
    assert ABSENT_BASELINE in _claim_text(workload.claim), (
        f'{workload.name} carries no baseline and does not say why. '
        f'A claim that omits one names the reason, in the wording {ABSENT_BASELINE!r}.'
    )


@pytest.mark.parametrize('workload', WORKLOADS, ids=IDS)
def test_the_implementations_are_labelled_once_each(workload: Workload) -> None:
    assert workload.subject.label == 'depin'
    if workload.baseline is not None:
        assert workload.baseline.label == 'direct'
    for alternative in workload.alternatives:
        assert alternative.label not in {'depin', 'direct'}
    labels = [candidate.label for candidate in implementations(workload)]
    assert sorted(labels) == sorted(set(labels))


@pytest.mark.parametrize(
    'candidate',
    [candidate for _, candidate in CANDIDATES],
    ids=CANDIDATE_IDS,
)
def test_every_implementation_prepares_a_callable_and_releases_it(candidate: Implementation) -> None:
    prepared = candidate.prepare()
    try:
        _ = prepared.call()
    finally:
        if prepared.close is not None:
            prepared.close()


@pytest.mark.parametrize('retirement', unmeasured.RETIRED, ids=[entry.workload for entry in unmeasured.RETIRED])
def test_a_retirement_states_what_it_claimed_why_it_went_and_what_covers_the_path(
    retirement: unmeasured.Retirement,
) -> None:
    """A withdrawn workload leaves a record, or a later reader cannot tell it from an oversight."""
    for field, stated in (
        ('claimed', retirement.claimed),
        ('reason', retirement.reason),
        ('covered_by', retirement.covered_by),
    ):
        assert stated, f'{retirement.workload}.{field} is empty'
        assert stated.strip() == stated, f'{retirement.workload}.{field} is padded'


@pytest.mark.parametrize('refusal', unmeasured.REFUSED, ids=[entry.case for entry in unmeasured.REFUSED])
def test_a_refusal_names_what_an_honest_measurement_would_need_instead(refusal: unmeasured.Refusal) -> None:
    for field, stated in (('reason', refusal.reason), ('needed', refusal.needed)):
        assert stated, f'{refusal.case}.{field} is empty'
        assert stated.strip() == stated, f'{refusal.case}.{field} is padded'
