"""Focused report-bridge coverage for the neutral FastAPI target runner."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from benchmarks.harness import require_array, require_object
from benchmarks.harness.fastapi_target_runner import REQUIRED_WORKLOADS, ReportError, benchmark, decode_report


def _entry(name: str, values: list[float]) -> dict[str, object]:
    return {
        'name': name,
        'stats': {
            'rounds': len(values),
            'min': min(values),
            'median': values[len(values) // 2],
            'mean': sum(values) / len(values),
            'stddev': 0.0001,
            'iqr': 0.0001,
            'data': values,
        },
    }


def _report(path: Path) -> None:
    entries: list[dict[str, object]] = []
    for index, workload in enumerate(REQUIRED_WORKLOADS):
        entries.extend(
            (
                _entry(f'test_latency[{workload}-direct]', [0.001 + index / 10_000] * 1_000),
                _entry(f'test_latency[{workload}-depin]', [0.010 + index / 10_000] * 1_000),
            )
        )
    path.write_text(json.dumps({'benchmarks': entries}), encoding='utf-8')


def _entries(payload: dict[str, object]) -> list[object]:
    return require_array(payload.get('benchmarks'), 'benchmarks')


def _remove_case(payload: dict[str, object]) -> None:
    _ = _entries(payload).pop()


def _duplicate_case(payload: dict[str, object]) -> None:
    entries = _entries(payload)
    entries.append(entries[0])


def _nan_case(payload: dict[str, object]) -> None:
    entry = _entries(payload)[0]
    stats = require_object(require_object(entry, 'benchmark').get('stats'), 'stats')
    stats['data'] = [float('nan')] * 1_000


def test_decode_report_records_distinct_implementation_values_and_provenance(tmp_path: Path) -> None:
    report = tmp_path / 'report.json'
    _report(report)

    decoded = decode_report(report, side='head', repetition=3, first='head')

    direct = decoded.metrics['test_latency[fastapi_cpu_light_endpoint-direct]']
    depin = decoded.metrics['test_latency[fastapi_cpu_light_endpoint-depin]']
    assert direct['median'] == 0.001
    assert depin['median'] == 0.01
    assert direct['case_id'] == 'test_latency[fastapi_cpu_light_endpoint-direct]'
    assert depin['side'] == 'head'
    assert depin['repetition'] == 3
    assert depin['first'] == 'head'
    assert depin['order'] == 0
    assert depin['report_sha256'] == decoded.sha256


def test_decode_report_projects_only_the_v3_common_inventory(tmp_path: Path) -> None:
    report = tmp_path / 'report.json'
    _report(report)
    payload = json.loads(report.read_text(encoding='utf-8'))
    _entries(payload).append(_entry('test_latency[fastapi_no_injection-depin]', [0.001] * 1_000))
    report.write_text(json.dumps(payload), encoding='utf-8')

    decoded = decode_report(report, side='head', repetition=0, first='base')

    assert 'test_latency[fastapi_no_injection-depin]' not in decoded.aggregates


@pytest.mark.parametrize(
    ('mutate', 'message'),
    [
        (_remove_case, 'missing required benchmark cases'),
        (_duplicate_case, 'duplicate benchmark'),
        (_nan_case, 'invalid JSON constant'),
    ],
)
def test_decode_report_rejects_incomplete_duplicate_or_nonfinite_cases(
    tmp_path: Path, mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    report = tmp_path / 'report.json'
    _report(report)
    payload = json.loads(report.read_text(encoding='utf-8'))
    mutate(payload)
    report.write_text(json.dumps(payload), encoding='utf-8')

    with pytest.raises(ReportError, match=message):
        _ = decode_report(report, side='base', repetition=0, first='base')


def test_benchmark_runs_the_current_checkout_latency_target_in_isolated_python(tmp_path: Path) -> None:
    decoded = benchmark(Path.cwd(), tmp_path / 'external-report.json', 'base', 0, 'base')

    assert set(decoded.aggregates) == {
        f'test_latency[{workload}-{label}]' for workload in REQUIRED_WORKLOADS for label in ('direct', 'depin')
    }
