"""Fail-closed coverage for FastAPI acceptance evidence reduction."""

from pathlib import Path

import pytest

from benchmarks.harness import HarnessError, read_json, require_array, require_object, write_json
from benchmarks.harness.fastapi_evidence import BASELINE_REVISION, reduce

HEAD_REVISION = 'f' * 40


def _raw(side: str, repetition: int, revision: str, interpreter: str) -> dict[str, object]:
    aggregates = {
        f'test_latency[{name}-{label}]': {
            'rounds': 1000,
            'minimum': 0.001,
            'median': 0.010 if label == 'depin' else 0.005,
            'mean': 0.010 if label == 'depin' else 0.005,
            'stddev': 0.0001,
            'iqr': 0.0001,
            'p95': 0.011 if label == 'depin' else 0.006,
            'p99': 0.012 if label == 'depin' else 0.007,
        }
        for name in (
            'fastapi_cpu_light_endpoint',
            'fastapi_request_scoped_graph',
            'fastapi_singletons_and_transients',
            'fastapi_async_resource_teardown',
            'fastapi_endpoint_with_work',
            'fastapi_application_startup',
        )
        for label in ('depin', 'direct')
    }
    report_sha256 = 'a' * 64
    return {
        'schema_version': 1,
        'side': side,
        'repetition': repetition,
        'revision': revision,
        'interpreter': interpreter,
        'benchmark_report': {
            'sha256': report_sha256,
            'aggregates': aggregates,
        },
        'benchmark_metrics': {
            case: {
                'case_id': case,
                **aggregate,
                'unit': 'seconds per operation',
                'method': 'pytest-benchmark',
                'side': side,
                'repetition': repetition,
                'first': 'base' if repetition % 2 == 0 else 'head',
                'order': 0 if side == ('base' if repetition % 2 == 0 else 'head') else 1,
                'report_sha256': report_sha256,
            }
            for case, aggregate in aggregates.items()
        },
        'guards': [
            {
                'workload': name,
                'subject': {
                    'response': '200 {}',
                    'constructed': ['resource'] if name == 'fastapi_async_resource_teardown' else [],
                    'closed': ['resource'] if name == 'fastapi_async_resource_teardown' else [],
                },
                'direct': {
                    'response': '200 {}',
                    'constructed': ['resource'] if name == 'fastapi_async_resource_teardown' else [],
                    'closed': ['resource'] if name == 'fastapi_async_resource_teardown' else [],
                },
                'response_equivalent': True,
                'lifecycle_equivalent': True,
                'teardown_equivalent': True,
            }
            for name in (
                'fastapi_cpu_light_endpoint',
                'fastapi_request_scoped_graph',
                'fastapi_singletons_and_transients',
                'fastapi_async_resource_teardown',
                'fastapi_endpoint_with_work',
                'fastapi_application_startup',
            )
        ],
        'checks': {
            'no_injection': {'direct': 10.0, 'depin': 10.0},
            'retained_memory': 10.0,
            'peak_memory': 10.0,
            'allocations': 10.0,
            'contention': 10.0,
            'components': {},
        },
    }


def _write_pair(root: Path, repetition: int) -> None:
    for side, revision, interpreter in (
        ('base', BASELINE_REVISION, '/tmp/base-env/bin/python'),
        ('head', HEAD_REVISION, '/tmp/head-env/bin/python'),
    ):
        write_json(root / 'raw' / side / f'rep{repetition}.json', _raw(side, repetition, revision, interpreter))


def test_reduction_refuses_missing_benchmark_report(tmp_path: Path) -> None:
    for repetition in range(5):
        _write_pair(tmp_path, repetition)
    payload = read_json(tmp_path / 'raw' / 'head' / 'rep2.json')
    _ = payload.pop('benchmark_report')
    write_json(tmp_path / 'raw' / 'head' / 'rep2.json', payload)

    with pytest.raises(HarnessError, match='benchmark report'):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


def test_reduction_refuses_duplicate_or_wrong_raw_provenance(tmp_path: Path) -> None:
    for repetition in range(5):
        _write_pair(tmp_path, repetition)
    payload = read_json(tmp_path / 'raw' / 'base' / 'rep4.json')
    payload['repetition'] = 3
    write_json(tmp_path / 'raw' / 'base' / 'rep4.json', payload)

    with pytest.raises(HarnessError, match='repetition'):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


def test_reduction_refuses_a_metric_bound_to_another_report_digest(tmp_path: Path) -> None:
    for repetition in range(5):
        _write_pair(tmp_path, repetition)
    payload = read_json(tmp_path / 'raw' / 'head' / 'rep2.json')
    metrics = require_object(payload.get('benchmark_metrics'), 'benchmark metrics')
    metric = require_object(metrics.get('test_latency[fastapi_cpu_light_endpoint-depin]'), 'benchmark metric')
    metric['report_sha256'] = 'b' * 64
    write_json(tmp_path / 'raw' / 'head' / 'rep2.json', payload)

    with pytest.raises(HarnessError, match='digest mismatch'):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


@pytest.mark.parametrize(
    ('field', 'value', 'message'),
    [
        ('response_equivalent', False, 'response equivalence'),
        ('lifecycle_equivalent', False, 'lifecycle equivalence'),
        ('teardown_equivalent', False, 'teardown equivalence'),
    ],
)
def test_reduction_refuses_fabricated_semantic_equivalence(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    for repetition in range(5):
        _write_pair(tmp_path, repetition)
    payload = read_json(tmp_path / 'raw' / 'head' / 'rep2.json')
    guards = require_array(payload.get('guards'), 'guards')
    guard = require_object(guards[0], 'guard')
    guard[field] = value
    write_json(tmp_path / 'raw' / 'head' / 'rep2.json', payload)

    with pytest.raises(HarnessError, match=message):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


def test_zero_teardown_is_valid_for_non_resource_workloads(tmp_path: Path) -> None:
    for repetition in range(5):
        _write_pair(tmp_path, repetition)

    with pytest.raises(HarnessError, match='head-only evidence'):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


@pytest.mark.parametrize(
    ('field', 'value', 'message'),
    [
        ('constructed', ['unexpected'], 'lifecycle equivalence'),
        ('closed', ['out', 'of', 'order'], 'lifecycle equivalence'),
    ],
)
def test_reduction_refuses_mismatched_lifecycle_evidence(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    for repetition in range(5):
        _write_pair(tmp_path, repetition)
    payload = read_json(tmp_path / 'raw' / 'head' / 'rep3.json')
    guards = require_array(payload.get('guards'), 'guards')
    guard = require_object(guards[0], 'guard')
    subject = require_object(guard.get('subject'), 'subject')
    subject[field] = value
    write_json(tmp_path / 'raw' / 'head' / 'rep3.json', payload)

    with pytest.raises(HarnessError, match=message):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})
