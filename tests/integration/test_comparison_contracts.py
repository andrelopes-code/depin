import math

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


@pytest.mark.parametrize('workload', ['not-valid', 'NotValid'])
def test_a_candidate_workload_must_be_a_lower_case_identifier(workload: str) -> None:
    with pytest.raises(HarnessError, match='workload'):
        Candidate(workload, Competitor('candidate', '1.0'), Equivalence.PARTIAL, 'stated difference', _implementation())


def test_a_candidate_implementation_label_must_match_the_competitor() -> None:
    implementation = Implementation(
        label='other-2.0',
        prepare=lambda: Prepared(call=object),
        observe=lambda: Observation(result='object', constructed=(), closed=()),
    )
    with pytest.raises(HarnessError, match='implementation label'):
        Candidate('workload', Competitor('candidate', '1.0'), Equivalence.PARTIAL, 'stated difference', implementation)


@pytest.mark.parametrize('fraction', [0.0, -0.1, 1.1])
def test_an_absolute_target_fraction_must_be_within_bounds(fraction: float) -> None:
    with pytest.raises(HarnessError, match='direct fraction'):
        AbsoluteTarget(12e-6, fraction, 'handler budget')


@pytest.mark.parametrize('fixed_seconds', [0.0, -1.0])
def test_an_absolute_target_fixed_seconds_must_be_positive(fixed_seconds: float) -> None:
    with pytest.raises(HarnessError, match='fixed target'):
        AbsoluteTarget(fixed_seconds, 0.1, 'handler budget')


@pytest.mark.parametrize('fixed_seconds', [math.nan, math.inf, -math.inf])
def test_an_absolute_target_fixed_seconds_must_be_finite(fixed_seconds: float) -> None:
    with pytest.raises(HarnessError, match='fixed target'):
        AbsoluteTarget(fixed_seconds, 0.1, 'handler budget')


@pytest.mark.parametrize('justification', ['', ' padded', 'padded '])
def test_an_absolute_target_justification_is_non_empty_and_unpadded(justification: str) -> None:
    with pytest.raises(HarnessError, match='justification'):
        AbsoluteTarget(12e-6, 0.1, justification)


@pytest.mark.parametrize(('direct_seconds', 'expected'), [(80e-6, 8e-6), (240e-6, 12e-6)])
def test_an_absolute_target_uses_the_lower_applicable_ceiling(direct_seconds: float, expected: float) -> None:
    target = AbsoluteTarget(12e-6, 0.1, 'handler budget')
    assert target.ceiling(direct_seconds) == pytest.approx(expected)
