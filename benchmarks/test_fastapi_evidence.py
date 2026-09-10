"""Fail-closed coverage for FastAPI evidence reduction."""

from pathlib import Path

import pytest

from benchmarks.harness import HarnessError, read_json, require_array, require_integer, require_object, write_json
from benchmarks.harness.fastapi_acceptance import COMPONENT_WORKLOADS, TAIL_WORKLOADS, evaluate
from benchmarks.harness.fastapi_evidence import BASELINE_REVISION, reduce

HEAD_REVISION = 'f' * 40


def _aggregate(value: float) -> dict[str, object]:
    return {
        'rounds': 1000,
        'minimum': value * 0.9,
        'median': value,
        'mean': value,
        'stddev': value * 0.01,
        'iqr': value * 0.01,
        'p95': value * 1.1,
        'p99': value * 1.2,
    }


def _observation(name: str) -> dict[str, object]:
    events = ['resource'] if name == 'fastapi_async_resource_teardown' else []
    return {'result': '200 {}', 'constructed': events, 'closed': events, 'error': None}


def _raw(side: str, repetition: int, revision: str, interpreter: str) -> dict[str, object]:
    first = 'base' if repetition % 2 == 0 else 'head'
    aggregates = {
        f'test_latency[{name}-{label}]': _aggregate(
            (0.007 if side == 'head' else 0.010) + repetition / 10_000
            if label == 'depin'
            else 0.005 + repetition / 10_000
        )
        for name in TAIL_WORKLOADS
        for label in ('depin', 'direct')
    }
    payload: dict[str, object] = {
        'schema_version': 3,
        'side': side,
        'repetition': repetition,
        'revision': revision,
        'interpreter': interpreter,
        'environment': {
            'interpreter': {'implementation': 'CPython', 'version': '3.12', 'compiler': 'GCC'},
            'host': {'system': 'Linux', 'release': '6', 'machine': 'x86_64', 'available_processors': 2},
            'distributions': {'pydepin': '1', 'pytest': '1', 'pytest-benchmark': '1'},
            'cpu': {'model': 'test'},
            'kernel': '6',
            'governor': 'performance',
            'affinity': [0],
            'packages': {'pydepin': '1', 'pytest': '1', 'pytest-benchmark': '1', 'fastapi': '1', 'starlette': '1'},
            'harness_revision': 'e' * 40,
            'collection_command': ['python'],
            'locked_environment': {'base': '/tmp/base-env', 'head': '/tmp/head-env'},
        },
        'first': first,
        'benchmark_report': {'sha256': 'a' * 64, 'aggregates': aggregates},
        'benchmark_metrics': {
            case: {
                'case_id': case,
                **aggregate,
                'unit': 'seconds per operation',
                'method': 'pytest-benchmark',
                'side': side,
                'repetition': repetition,
                'first': first,
                'order': 0 if side == first else 1,
                'report_sha256': 'a' * 64,
            }
            for case, aggregate in aggregates.items()
        },
        'observations': [
            {'workload': name, 'depin': _observation(name), 'direct': _observation(name)} for name in TAIL_WORKLOADS
        ],
        'memory': {
            'retained': {'value': 100.0 + repetition, 'unit': 'bytes', 'method': 'tracemalloc-retained'},
            'allocations': {
                'value': 10.0 + repetition,
                'unit': 'allocation-count',
                'method': 'tracemalloc-allocation-count',
            },
            'peak': {'value': 200.0 + repetition, 'unit': 'bytes', 'method': 'tracemalloc-peak'},
            'work': {
                'value': 1.0,
                'unit': 'calls per operation',
                'method': 'calls-per-operation',
                'operations': 1,
                'sample_count': 1,
                'config': {'operations': 1},
            },
        },
        'contention': {
            'config': {'samples': 5, 'workers': 2},
            'direct': {'value': 0.010 + repetition / 10_000, 'unit': 'seconds', 'method': 'synchronized-wave'},
            'depin': {'value': 0.010 + repetition / 10_000, 'unit': 'seconds', 'method': 'synchronized-wave'},
        },
    }
    if side == 'head':
        payload['head_only'] = {
            'no_injection': {
                'direct': {'value': 0.010, 'unit': 'seconds per operation', 'method': 'direct-null'},
                'depin': {'value': 0.010, 'unit': 'seconds per operation', 'method': 'direct-null'},
            },
            'components': {
                name: {
                    'control': {'value': 0.001, 'unit': 'seconds per operation', 'method': 'median-control'},
                    'depin': {'value': 0.010, 'unit': 'seconds per operation', 'method': 'component-observation'},
                    'config': {'samples': 101},
                }
                for name in COMPONENT_WORKLOADS
            },
        }
    return payload


def _reduced(root: Path) -> dict[str, object]:
    for repetition in range(5):
        for side, revision, interpreter in (
            ('base', BASELINE_REVISION, '/tmp/base-env/bin/python'),
            ('head', HEAD_REVISION, '/tmp/head-env/bin/python'),
        ):
            write_json(root / 'raw' / side / f'rep{repetition}.json', _raw(side, repetition, revision, interpreter))
    return reduce(root / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


def test_reduction_preserves_repetitions_and_projects_evaluator_inputs(tmp_path: Path) -> None:
    output = _reduced(tmp_path)
    dataset = require_object(output['dataset'], 'dataset')
    base = require_array(require_object(dataset['base'], 'base')['repetitions'], 'base repetitions')
    assert [
        require_integer(
            require_object(require_object(value, 'entry').get('record'), 'record').get('repetition'), 'repetition'
        )
        for value in base
    ] == [0, 1, 2, 3, 4]
    assert require_object(require_object(output['sidecars'], 'sidecars')['retained_memory'], 'memory')['base'] == 102.0
    assert require_object(require_object(output['sidecars'], 'sidecars')['contention'], 'contention')['base'] == 0.0102
    semantic = require_array(require_object(output['provenance'], 'provenance')['semantic_validation'], 'semantic')
    assert len(semantic) == 30
    for name, payload in dataset.items():
        if name == 'environment.json':
            write_json(tmp_path / 'evidence' / name, require_object(payload, name))
        else:
            for entry in require_array(require_object(payload, name)['repetitions'], name):
                record = require_object(require_object(entry, 'entry')['record'], 'record')
                repetition = require_integer(record.get('repetition'), 'repetition')
                write_json(tmp_path / 'evidence' / name / f'rep{repetition}.json', record)
    for name in ('attribution', 'sidecars', 'provenance'):
        write_json(tmp_path / 'evidence' / f'{name}.json', require_object(output[name], name))
    assert evaluate(
        tmp_path / 'evidence',
        *(tmp_path / 'evidence' / f'{name}.json' for name in ('attribution', 'sidecars', 'provenance')),
        evaluated_head_revision=HEAD_REVISION,
    ).passed


@pytest.mark.parametrize(
    ('path', 'value', 'message'),
    [
        (('memory', 'retained', 'unit'), 'seconds', 'unit mismatch'),
        (('memory', 'retained', 'value'), float('nan'), 'invalid JSON constant'),
        (('contention', 'config', 'workers'), 3, 'contention configuration'),
        (('head_only', 'components'), {}, 'component inventory'),
        (('benchmark_report', 'aggregates', 'test_latency[fastapi_cpu_light_endpoint-depin]', 'extra'), 1, 'fields'),
        (('benchmark_metrics', 'test_latency[fastapi_cpu_light_endpoint-depin]', 'extra'), 1, 'fields'),
        (('observations',), [], 'observations must exactly cover'),
    ],
)
def test_reduction_refuses_invalid_envelope(tmp_path: Path, path: tuple[str, ...], value: object, message: str) -> None:
    _ = _reduced(tmp_path)
    payload = read_json(tmp_path / 'raw' / 'head' / 'rep2.json')
    target: dict[str, object] = payload
    for field in path[:-1]:
        target = require_object(target[field], field)
    target[path[-1]] = value
    write_json(tmp_path / 'raw' / 'head' / 'rep2.json', payload)
    with pytest.raises(HarnessError, match=message):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


def test_reduction_refuses_duplicate_json_key(tmp_path: Path) -> None:
    _ = _reduced(tmp_path)
    (tmp_path / 'raw' / 'base' / 'rep0.json').write_text('{"schema_version":3,"schema_version":3}', encoding='utf-8')
    with pytest.raises(HarnessError, match='duplicate JSON key'):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


def test_reduction_accepts_zero_dispersion_but_refuses_empty_resource_teardown(tmp_path: Path) -> None:
    _ = _reduced(tmp_path)
    payload = read_json(tmp_path / 'raw' / 'head' / 'rep2.json')
    aggregate = require_object(
        require_object(payload['benchmark_report'], 'report')['aggregates'], 'aggregates'
    )['test_latency[fastapi_cpu_light_endpoint-depin]']
    aggregate_fields = require_object(aggregate, 'aggregate')
    aggregate_fields['stddev'] = 0.0
    aggregate_fields['iqr'] = 0.0
    metric = require_object(payload['benchmark_metrics'], 'metrics')['test_latency[fastapi_cpu_light_endpoint-depin]']
    metric_fields = require_object(metric, 'metric')
    metric_fields['stddev'] = 0.0
    metric_fields['iqr'] = 0.0
    resource = next(
        require_object(entry, 'observation')
        for entry in require_array(payload['observations'], 'observations')
        if require_object(entry, 'observation')['workload'] == 'fastapi_async_resource_teardown'
    )
    for label in ('depin', 'direct'):
        require_object(resource[label], label)['constructed'] = []
        require_object(resource[label], label)['closed'] = []
    write_json(tmp_path / 'raw' / 'head' / 'rep2.json', payload)
    with pytest.raises(HarnessError, match='teardown must close'):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})
