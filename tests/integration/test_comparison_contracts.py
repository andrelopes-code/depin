import pytest

from benchmarks.comparison.contracts import (
    AbsoluteTarget,
    Candidate,
    Competitor,
    Equivalence,
)
from benchmarks.contracts import Implementation, Observation, Prepared
from benchmarks.harness import HarnessError


def _implementation() -> Implementation:
    return Implementation(
        label='candidate-1.0',
        prepare=lambda: Prepared(call=object),
        observe=lambda: Observation(result='object', constructed=(), closed=()),
    )


@pytest.mark.parametrize('equivalence', [Equivalence.EQUIVALENT, Equivalence.PARTIAL])
def test_a_timed_candidate_requires_an_implementation(equivalence: Equivalence) -> None:
    with pytest.raises(HarnessError, match='requires an implementation'):
        Candidate('workload', Competitor('candidate', '1.0'), equivalence, 'stated difference', None)


def test_an_incomparable_candidate_cannot_carry_an_implementation() -> None:
    with pytest.raises(HarnessError, match='must not carry an implementation'):
        Candidate(
            'workload',
            Competitor('candidate', '1.0'),
            Equivalence.INCOMPARABLE,
            'different lifecycle',
            _implementation(),
        )


@pytest.mark.parametrize('reason', ['', ' padded', 'padded '])
def test_a_candidate_reason_is_non_empty_and_unpadded(reason: str) -> None:
    with pytest.raises(HarnessError, match='reason'):
        Candidate('workload', Competitor('candidate', '1.0'), Equivalence.PARTIAL, reason, _implementation())


def test_an_absolute_target_uses_the_lower_applicable_ceiling() -> None:
    target = AbsoluteTarget(12e-6, 0.1, 'handler budget')
    assert target.ceiling(80e-6) == pytest.approx(8e-6)
