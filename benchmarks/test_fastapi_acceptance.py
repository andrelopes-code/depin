"""Acceptance coverage for the FastAPI minimum-overhead evidence gate."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from benchmarks.harness import HarnessError, read_json, require_array, require_object, write_json
from benchmarks.harness.fastapi_acceptance import (
    ATTRIBUTION_WORKLOAD,
    BASELINE_REVISION,
    CHECK_CONTENTION,
    CHECK_NO_INJECTION,
    CHECK_PEAK_MEMORY,
    COMPONENT_WORKLOADS,
    DEFAULT_SEED,
    TAIL_WORKLOADS,
    Acceptance,
    evaluate,
)

HEAD_REVISION = 'f' * 40


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
    write_json(
        dataset / 'environment.json',
        {
            'seed': DEFAULT_SEED,
            'repetitions': 5,
            'environment': {
                'interpreter': {'implementation': 'CPython', 'version': '3.12.0', 'compiler': 'test compiler'},
                'host': {'system': 'Linux', 'release': 'test-kernel', 'machine': 'x86_64', 'available_processors': 1},
                'distributions': {'pydepin': '1.0', 'pytest': '1.0', 'pytest-benchmark': '1.0'},
            },
        },
    )
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
            'baseline_revision': BASELINE_REVISION,
            'head_revision': HEAD_REVISION,
            'metric': 'p50',
            'unit': 'seconds per operation',
            'method': 'direct-request-p50',
            'scope': 'paired',
            'repetitions': [
                {'repetition': repetition, 'base_direct_p50': 50.0, 'head_direct_p50': head_direct}
                for repetition in range(5)
            ],
        },
    )
    return path


def _sidecars(tmp_path: Path, *, checks: Sequence[Mapping[str, object]] | None = None) -> Path:
    path = tmp_path / 'sidecars.json'
    default_checks: dict[str, object] = {
        'no_injection': {
            'workload': 'fastapi_no_injection',
            'metric': 'latency',
            'unit': 'seconds per operation',
            'method': 'direct-null',
            'scope': 'head-only',
            'direct': 100.0,
            'depin': 101.0,
            'limit': 0.05,
        },
        'retained_memory': {
            'workload': ATTRIBUTION_WORKLOAD,
            'metric': 'retained',
            'unit': 'bytes',
            'method': 'tracemalloc-retained',
            'scope': 'paired',
            'base': 100.0,
            'head': 100.0,
            'limit': 0.02,
        },
        'peak_memory': {
            'workload': ATTRIBUTION_WORKLOAD,
            'metric': 'peak-memory',
            'unit': 'bytes',
            'method': 'tracemalloc-peak',
            'scope': 'paired',
            'base': 100.0,
            'head': 100.0,
            'limit': 0.05,
        },
        'allocations': {
            'workload': ATTRIBUTION_WORKLOAD,
            'metric': 'allocations',
            'unit': 'allocation-count',
            'method': 'tracemalloc-allocation-count',
            'scope': 'paired',
            'base': 100.0,
            'head': 100.0,
            'limit': 0.0,
        },
        'application_startup': {
            'workload': 'fastapi_application_startup',
            'metric': 'latency',
            'unit': 'seconds per operation',
            'method': 'paired-total-p50',
            'scope': 'paired',
            'limit': 0.05,
        },
        'contention': {
            'workload': 'request_scopes',
            'metric': 'p99_seconds',
            'unit': 'seconds',
            'method': 'synchronized-wave',
            'scope': 'paired',
            'base': 100.0,
            'head': 100.0,
            'limit': 0.05,
        },
        'components': [
            {
                'workload': workload,
                'metric': 'latency',
                'unit': 'seconds per operation',
                'method': 'component-observation',
                'scope': 'head-only',
                'validated': True,
            }
            for workload in COMPONENT_WORKLOADS
        ],
    }
    if checks is not None:
        default_checks[CHECK_CONTENTION] = {'invalid': list(checks)}
    write_json(path, {'schema_version': 1, **default_checks})
    return path


def _provenance(tmp_path: Path) -> Path:
    path = tmp_path / 'provenance.json'
    write_json(
        path,
        {
            'schema_version': 1,
            'baseline_revision': BASELINE_REVISION,
            'head_revision': HEAD_REVISION,
            'protocol': {
                'collector': 'benchmarks.harness.pairs',
                'repetitions': 5,
                'seed': DEFAULT_SEED,
                'locked_environments': True,
                'workloads': list(TAIL_WORKLOADS),
            },
            'semantic_validation': [
                {
                    'workload': workload,
                    'repetition': repetition,
                    'base_revision': BASELINE_REVISION,
                    'head_revision': HEAD_REVISION,
                    'response': 'equivalent',
                    'lifecycle': 'equivalent',
                    'event_counts': {'base': 1, 'head': 1},
                    'teardown': 'equivalent',
                    'deterministic': 'passed',
                }
                for workload in TAIL_WORKLOADS
                for repetition in range(5)
            ],
            'environment': {
                'interpreter': {'implementation': 'CPython', 'version': '3.12.0'},
                'cpu': {'model': 'test CPU'},
                'kernel': 'test-kernel',
                'governor': 'performance',
                'affinity': [0],
                'packages': {
                    'pydepin': '1.0',
                    'pytest': '1.0',
                    'pytest-benchmark': '1.0',
                    'fastapi': '1.0',
                    'starlette': '1.0',
                },
                'harness_revision': HEAD_REVISION,
                'collection_command': ['python', '-m', 'benchmarks.harness.pairs'],
                'locked_environment': {'base': 'sha256:base', 'head': 'sha256:head'},
            },
        },
    )
    return path


def _evaluate(dataset: Path, attribution: Path, sidecars: Path) -> Acceptance:
    return evaluate(dataset, attribution, sidecars, _provenance(dataset.parent), evaluated_head_revision=HEAD_REVISION)


def _outcomes(result: Acceptance) -> dict[str, str]:
    return {verdict.criterion: verdict.outcome.value for verdict in result.verdicts}


def test_total_latency_improvement_does_not_prove_attributable_overhead_improvement(tmp_path: Path) -> None:
    result = _evaluate(
        _dataset(tmp_path, head_median=90.0), _attribution(tmp_path, head_direct=30.0), _sidecars(tmp_path)
    )

    assert _outcomes(result)['cpu-light-attributable-p50'] == 'fail'
    assert not result.passed


def test_attributable_upper_confidence_bound_must_clear_twenty_five_percent(tmp_path: Path) -> None:
    result = _evaluate(_dataset(tmp_path), _attribution(tmp_path, head_direct=30.0), _sidecars(tmp_path))

    assert _outcomes(result)['cpu-light-attributable-p50'] == 'fail'


def test_total_latency_tails_fail_when_they_regress_more_than_five_percent(tmp_path: Path) -> None:
    result = _evaluate(_dataset(tmp_path, head_p95=128.0, head_p99=138.0), _attribution(tmp_path), _sidecars(tmp_path))

    outcomes = _outcomes(result)
    assert outcomes['fastapi_cpu_light_endpoint:p95-total'] == 'fail'
    assert outcomes['fastapi_cpu_light_endpoint:p99-total'] == 'fail'


def test_missing_contention_fails_closed(tmp_path: Path) -> None:
    sidecars = _sidecars(tmp_path)
    payload = read_json(sidecars)
    _ = payload.pop(CHECK_CONTENTION)
    write_json(sidecars, payload)

    with pytest.raises(HarnessError, match='contention'):
        _ = _evaluate(_dataset(tmp_path), _attribution(tmp_path), sidecars)


def test_peak_memory_regression_fails_and_missing_evidence_is_refused(tmp_path: Path) -> None:
    sidecars = _sidecars(tmp_path)
    payload = read_json(sidecars)
    peak = payload[CHECK_PEAK_MEMORY]
    assert isinstance(peak, dict)
    peak['head'] = 106.0
    write_json(sidecars, payload)

    assert _outcomes(_evaluate(_dataset(tmp_path), _attribution(tmp_path), sidecars))[CHECK_PEAK_MEMORY] == 'fail'

    _ = payload.pop(CHECK_PEAK_MEMORY)
    write_json(sidecars, payload)
    with pytest.raises(HarnessError, match='peak_memory'):
        _ = _evaluate(_dataset(tmp_path), _attribution(tmp_path), sidecars)


def test_complete_evidence_passes_and_keeps_head_only_checks_separate(tmp_path: Path) -> None:
    result = _evaluate(_dataset(tmp_path), _attribution(tmp_path), _sidecars(tmp_path))

    outcomes = _outcomes(result)
    assert result.passed
    assert outcomes['cpu-light-attributable-p50'] == 'pass'
    assert outcomes['cpu-light-attributable-p50-stretch'] == 'pass'
    assert outcomes[CHECK_NO_INJECTION] == 'pass'
    assert outcomes[f'component:{COMPONENT_WORKLOADS[0]}'] == 'pass'
    assert result.head_only == tuple(
        sorted((CHECK_NO_INJECTION, *(f'component:{name}' for name in COMPONENT_WORKLOADS)))
    )


def test_attribution_requires_exactly_five_matched_repetitions(tmp_path: Path) -> None:
    path = _attribution(tmp_path)
    payload = read_json(path)
    payload['repetitions'] = []
    write_json(path, payload)

    with pytest.raises(HarnessError, match='exactly 5'):
        _ = _evaluate(_dataset(tmp_path), path, _sidecars(tmp_path))


@pytest.mark.parametrize(
    ('field', 'value', 'message'),
    [
        ('baseline_revision', '0' * 40, 'baseline_revision'),
        ('head_revision', '0' * 40, 'evaluated head'),
    ],
)
def test_wrong_revision_provenance_fails_closed(tmp_path: Path, field: str, value: str, message: str) -> None:
    provenance = _provenance(tmp_path)
    payload = read_json(provenance)
    payload[field] = value
    write_json(provenance, payload)

    with pytest.raises(HarnessError, match=message):
        _ = evaluate(
            _dataset(tmp_path),
            _attribution(tmp_path),
            _sidecars(tmp_path),
            provenance,
            evaluated_head_revision=HEAD_REVISION,
        )


@pytest.mark.parametrize(('field', 'value'), [('seed', DEFAULT_SEED + 1), ('locked_environments', False)])
def test_wrong_protocol_provenance_fails_closed(tmp_path: Path, field: str, value: object) -> None:
    provenance = _provenance(tmp_path)
    payload = read_json(provenance)
    protocol = payload['protocol']
    assert isinstance(protocol, dict)
    protocol[field] = value
    write_json(provenance, payload)

    with pytest.raises(HarnessError, match=field):
        _ = evaluate(
            _dataset(tmp_path),
            _attribution(tmp_path),
            _sidecars(tmp_path),
            provenance,
            evaluated_head_revision=HEAD_REVISION,
        )


def test_missing_semantic_lifecycle_validation_fails_closed(tmp_path: Path) -> None:
    provenance = _provenance(tmp_path)
    payload = read_json(provenance)
    payload['semantic_validation'] = []
    write_json(provenance, payload)

    with pytest.raises(HarnessError, match='semantic_validation'):
        _ = evaluate(
            _dataset(tmp_path),
            _attribution(tmp_path),
            _sidecars(tmp_path),
            provenance,
            evaluated_head_revision=HEAD_REVISION,
        )


def test_one_missing_repetition_validation_fails_closed(tmp_path: Path) -> None:
    provenance = _provenance(tmp_path)
    payload = read_json(provenance)
    validations = require_array(payload.get('semantic_validation'), 'semantic_validation')
    _ = validations.pop()
    write_json(provenance, payload)

    with pytest.raises(HarnessError, match='semantic_validation'):
        _ = evaluate(
            _dataset(tmp_path),
            _attribution(tmp_path),
            _sidecars(tmp_path),
            provenance,
            evaluated_head_revision=HEAD_REVISION,
        )


def test_one_corrupt_repetition_validation_fails_closed(tmp_path: Path) -> None:
    provenance = _provenance(tmp_path)
    payload = read_json(provenance)
    validation = require_object(
        require_array(payload.get('semantic_validation'), 'semantic_validation')[0], 'validation'
    )
    counts = require_object(validation.get('event_counts'), 'event_counts')
    counts['head'] = 2
    write_json(provenance, payload)

    with pytest.raises(HarnessError, match='event_counts'):
        _ = evaluate(
            _dataset(tmp_path),
            _attribution(tmp_path),
            _sidecars(tmp_path),
            provenance,
            evaluated_head_revision=HEAD_REVISION,
        )


@pytest.mark.parametrize('field', ['kernel', 'governor'])
def test_empty_required_environment_provenance_field_fails_closed(tmp_path: Path, field: str) -> None:
    provenance = _provenance(tmp_path)
    payload = read_json(provenance)
    environment = require_object(payload.get('environment'), 'environment')
    environment[field] = ''
    write_json(provenance, payload)

    with pytest.raises(HarnessError, match=field):
        _ = evaluate(
            _dataset(tmp_path),
            _attribution(tmp_path),
            _sidecars(tmp_path),
            provenance,
            evaluated_head_revision=HEAD_REVISION,
        )


def test_missing_required_environment_provenance_field_fails_closed(tmp_path: Path) -> None:
    provenance = _provenance(tmp_path)
    payload = read_json(provenance)
    environment = require_object(payload.get('environment'), 'environment')
    _ = environment.pop('packages')
    write_json(provenance, payload)

    with pytest.raises(HarnessError, match='packages'):
        _ = evaluate(
            _dataset(tmp_path),
            _attribution(tmp_path),
            _sidecars(tmp_path),
            provenance,
            evaluated_head_revision=HEAD_REVISION,
        )


@pytest.mark.parametrize(('field', 'value'), [('scope', 'paired'), ('unit', 'seconds'), ('method', 'manual')])
def test_typed_no_injection_evidence_rejects_wrong_schema(tmp_path: Path, field: str, value: str) -> None:
    sidecars = _sidecars(tmp_path)
    payload = read_json(sidecars)
    evidence = payload[CHECK_NO_INJECTION]
    assert isinstance(evidence, dict)
    evidence[field] = value
    write_json(sidecars, payload)

    with pytest.raises(HarnessError, match=field):
        _ = _evaluate(_dataset(tmp_path), _attribution(tmp_path), sidecars)


@pytest.mark.parametrize('replacement', [[], [{'workload': 'arbitrary'}]])
def test_component_evidence_requires_the_complete_named_inventory(tmp_path: Path, replacement: list[object]) -> None:
    sidecars = _sidecars(tmp_path)
    payload = read_json(sidecars)
    payload['components'] = replacement
    write_json(sidecars, payload)

    with pytest.raises(HarnessError, match='component'):
        _ = _evaluate(_dataset(tmp_path), _attribution(tmp_path), sidecars)


def test_swapped_direct_attribution_is_refused(tmp_path: Path) -> None:
    attribution = _attribution(tmp_path)
    payload = read_json(attribution)
    first = require_object(require_array(payload.get('repetitions'), 'repetitions')[0], 'first repetition')
    first['base_direct_p50'] = 150.0
    write_json(attribution, payload)

    with pytest.raises(HarnessError, match='attributable'):
        _ = _evaluate(_dataset(tmp_path), attribution, _sidecars(tmp_path))
