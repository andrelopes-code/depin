"""Acceptance coverage for the FastAPI minimum-overhead evidence gate."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from benchmarks.harness import HarnessError, write_json
from benchmarks.harness.fastapi_acceptance import (
    ATTRIBUTION_WORKLOAD,
    CHECK_ALLOCATION,
    CHECK_CONTENTION,
    CHECK_NO_INJECTION,
    CHECK_PEAK_MEMORY,
    CHECK_RETAINED_MEMORY,
    CHECK_STARTUP,
    TAIL_WORKLOADS,
    Acceptance,
    evaluate,
)


def _aggregate(median: float, *, p95: float = 120.0, p99: float = 130.0) -> dict[str, object]:
    return {
        'rounds': 1_000,
        'minimum': median,
        'median': median,
        'mean': median,
        'stddev': 0.0,
        'iqr': 0.0,
        'p95': p95,
        'p99': p99,
    }


def _dataset(tmp_path: Path, *, head_median: float = 70.0, head_p95: float = 120.0, head_p99: float = 130.0) -> Path:
    dataset = tmp_path / 'dataset'
    write_json(dataset / 'environment.json', {'seed': 20260909})
    for repetition in range(5):
        write_json(
            dataset / 'base' / f'rep{repetition}.json',
            {
                'repetition': repetition,
                'first': 'base' if repetition % 2 == 0 else 'head',
                'aggregates': {name: _aggregate(100.0) for name in TAIL_WORKLOADS},
            },
        )
        write_json(
            dataset / 'head' / f'rep{repetition}.json',
            {
                'repetition': repetition,
                'first': 'base' if repetition % 2 == 0 else 'head',
                'aggregates': {name: _aggregate(head_median, p95=head_p95, p99=head_p99) for name in TAIL_WORKLOADS},
            },
        )
    return dataset


def _attribution(tmp_path: Path, *, head_direct: float = 55.0) -> Path:
    path = tmp_path / 'attribution.json'
    write_json(
        path,
        {
            'schema_version': 1,
            'workload': ATTRIBUTION_WORKLOAD,
            'repetitions': [
                {'repetition': repetition, 'base_direct_p50': 50.0, 'head_direct_p50': head_direct}
                for repetition in range(5)
            ],
        },
    )
    return path


def _sidecars(tmp_path: Path, *, checks: Sequence[Mapping[str, object]] | None = None) -> Path:
    path = tmp_path / 'sidecars.json'
    default_checks = [
        {'criterion': CHECK_NO_INJECTION, 'scope': 'head-only', 'base': 100.0, 'head': 101.0, 'limit': 0.05},
        {'criterion': CHECK_RETAINED_MEMORY, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.02},
        {'criterion': CHECK_PEAK_MEMORY, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
        {'criterion': CHECK_ALLOCATION, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.0},
        {'criterion': CHECK_STARTUP, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
        {'criterion': CHECK_CONTENTION, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
        {'criterion': 'component:lazy_host', 'scope': 'head-only', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
    ]
    selected = default_checks if checks is None else [dict(check) for check in checks]
    write_json(path, {'schema_version': 1, 'checks': selected})
    return path


def _outcomes(result: Acceptance) -> dict[str, str]:
    return {verdict.criterion: verdict.outcome.value for verdict in result.verdicts}


def test_total_latency_improvement_does_not_prove_attributable_overhead_improvement(tmp_path: Path) -> None:
    result = evaluate(
        _dataset(tmp_path, head_median=90.0), _attribution(tmp_path, head_direct=30.0), _sidecars(tmp_path)
    )

    assert _outcomes(result)['cpu-light-attributable-p50'] == 'fail'
    assert not result.passed


def test_attributable_upper_confidence_bound_must_clear_twenty_five_percent(tmp_path: Path) -> None:
    result = evaluate(_dataset(tmp_path), _attribution(tmp_path, head_direct=30.0), _sidecars(tmp_path))

    assert _outcomes(result)['cpu-light-attributable-p50'] == 'fail'


def test_total_latency_tails_fail_when_they_regress_more_than_five_percent(tmp_path: Path) -> None:
    result = evaluate(_dataset(tmp_path, head_p95=128.0, head_p99=138.0), _attribution(tmp_path), _sidecars(tmp_path))

    outcomes = _outcomes(result)
    assert outcomes['fastapi_cpu_light_endpoint:p95-total'] == 'fail'
    assert outcomes['fastapi_cpu_light_endpoint:p99-total'] == 'fail'


def test_missing_contention_is_an_individual_no_verdict(tmp_path: Path) -> None:
    checks = [
        check
        for check in [
            {'criterion': CHECK_NO_INJECTION, 'scope': 'head-only', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
            {'criterion': CHECK_RETAINED_MEMORY, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.02},
            {'criterion': CHECK_PEAK_MEMORY, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
            {'criterion': CHECK_ALLOCATION, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.0},
            {'criterion': CHECK_STARTUP, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
        ]
    ]
    result = evaluate(_dataset(tmp_path), _attribution(tmp_path), _sidecars(tmp_path, checks=checks))

    assert _outcomes(result)[CHECK_CONTENTION] == 'no-verdict'


@pytest.mark.parametrize(
    ('checks', 'outcome'),
    [
        (
            [
                {'criterion': CHECK_NO_INJECTION, 'scope': 'head-only', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
                {'criterion': CHECK_RETAINED_MEMORY, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.02},
                {'criterion': CHECK_PEAK_MEMORY, 'scope': 'paired', 'base': 100.0, 'head': 106.0, 'limit': 0.05},
                {'criterion': CHECK_ALLOCATION, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.0},
                {'criterion': CHECK_STARTUP, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
                {'criterion': CHECK_CONTENTION, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
            ],
            'fail',
        ),
        (
            [
                {'criterion': CHECK_NO_INJECTION, 'scope': 'head-only', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
                {'criterion': CHECK_RETAINED_MEMORY, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.02},
                {'criterion': CHECK_ALLOCATION, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.0},
                {'criterion': CHECK_STARTUP, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
                {'criterion': CHECK_CONTENTION, 'scope': 'paired', 'base': 100.0, 'head': 100.0, 'limit': 0.05},
            ],
            'no-verdict',
        ),
    ],
)
def test_peak_memory_is_explicitly_gated_or_reported_missing(
    tmp_path: Path, checks: list[dict[str, object]], outcome: str
) -> None:
    result = evaluate(_dataset(tmp_path), _attribution(tmp_path), _sidecars(tmp_path, checks=checks))

    assert _outcomes(result)[CHECK_PEAK_MEMORY] == outcome


def test_complete_evidence_passes_and_keeps_head_only_checks_separate(tmp_path: Path) -> None:
    result = evaluate(_dataset(tmp_path), _attribution(tmp_path), _sidecars(tmp_path))

    outcomes = _outcomes(result)
    assert result.passed
    assert outcomes['cpu-light-attributable-p50'] == 'pass'
    assert outcomes['cpu-light-attributable-p50-stretch'] == 'pass'
    assert outcomes[CHECK_NO_INJECTION] == 'pass'
    assert outcomes['component:lazy_host'] == 'pass'
    assert result.head_only == ('component:lazy_host', CHECK_NO_INJECTION)


def test_attribution_requires_exactly_five_matched_repetitions(tmp_path: Path) -> None:
    path = _attribution(tmp_path)
    write_json(path, {'schema_version': 1, 'workload': ATTRIBUTION_WORKLOAD, 'repetitions': []})

    with pytest.raises(HarnessError, match='exactly 5'):
        _ = evaluate(_dataset(tmp_path), path, _sidecars(tmp_path))
