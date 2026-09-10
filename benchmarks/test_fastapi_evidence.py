"""Fail-closed coverage for FastAPI acceptance evidence reduction."""

from pathlib import Path

import pytest

from benchmarks.harness import HarnessError, read_json, write_json
from benchmarks.harness.fastapi_evidence import BASELINE_REVISION, reduce

HEAD_REVISION = 'f' * 40


def _raw(side: str, repetition: int, revision: str, interpreter: str) -> dict[str, object]:
    return {
        'schema_version': 1,
        'side': side,
        'repetition': repetition,
        'revision': revision,
        'interpreter': interpreter,
        'direct_p50': 10.0,
        'guards': [
            {
                'workload': name,
                'response': '200 {}',
                'constructed': [],
                'closed': [],
                'teardown': True,
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


def test_reduction_refuses_missing_direct_control(tmp_path: Path) -> None:
    for repetition in range(5):
        _write_pair(tmp_path, repetition)
    payload = read_json(tmp_path / 'raw' / 'head' / 'rep2.json')
    _ = payload.pop('direct_p50')
    write_json(tmp_path / 'raw' / 'head' / 'rep2.json', payload)

    with pytest.raises(HarnessError, match='direct_p50'):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})


def test_reduction_refuses_duplicate_or_wrong_raw_provenance(tmp_path: Path) -> None:
    for repetition in range(5):
        _write_pair(tmp_path, repetition)
    payload = read_json(tmp_path / 'raw' / 'base' / 'rep4.json')
    payload['repetition'] = 3
    write_json(tmp_path / 'raw' / 'base' / 'rep4.json', payload)

    with pytest.raises(HarnessError, match='repetition'):
        reduce(tmp_path / 'raw', BASELINE_REVISION, HEAD_REVISION, {'base': '/tmp/base-env', 'head': '/tmp/head-env'})
