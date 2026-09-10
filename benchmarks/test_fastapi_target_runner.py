"""Focused report-bridge coverage for the neutral FastAPI target runner."""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from benchmarks.harness import fastapi_target_runner, require_array, require_object
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


def test_runtime_environment_carries_acceptance_provenance() -> None:
    captured: dict[str, object] = {
        'interpreter': {'implementation': 'CPython', 'version': '3.12.0'},
        'host': {'cpu_model': 'test CPU', 'release': 'test kernel'},
        'distributions': {'pydepin': '2.0'},
    }

    result = fastapi_target_runner.runtime_environment(
        captured,
        {
            'pydepin': '2.0',
            'pytest': '1.0',
            'pytest-benchmark': '1.0',
            'fastapi': '1.0',
            'starlette': '1.0',
        },
        affinity=(2, 3),
        governor='performance',
    )

    assert result['cpu'] == {'model': 'test CPU'}
    assert result['kernel'] == 'test kernel'
    assert result['governor'] == 'performance'
    assert result['affinity'] == [2, 3]
    assert result['packages'] == {
        'pydepin': '2.0',
        'pytest': '1.0',
        'pytest-benchmark': '1.0',
        'fastapi': '1.0',
        'starlette': '1.0',
    }


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


def test_isolated_bootstrap_reexecs_with_deterministic_hashing_and_target_only_imports() -> None:
    runner = Path('benchmarks/harness/fastapi_target_runner.py').resolve()
    completed = subprocess.run(
        (sys.executable, '-I', str(runner), '--bootstrap-probe', str(Path.cwd())),
        capture_output=True,
        text=True,
        env=os.environ | {'PYTHONPATH': '/poisoned-parent-path'},
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    probe = json.loads(completed.stdout)
    assert probe['hash_randomization'] == 0
    assert Path(probe['memory_module']).is_relative_to(Path.cwd())
    assert probe['allocation_peak'] > 0


def test_venv_launcher_binding_accepts_uv_symlink_and_rejects_wrong_prefix_or_target(tmp_path: Path) -> None:
    environment = tmp_path / 'environment'
    subprocess.run(
        ('uv', 'venv', '--python', sys.executable, str(environment)), check=True, capture_output=True, text=True
    )
    launcher = environment / 'bin' / 'python'
    wrong_target = environment / 'bin' / 'wrong-python'
    wrong_target.symlink_to('/bin/sh')
    program = (
        'import sys; from pathlib import Path; '
        f'sys.path.insert(0, {str(Path.cwd())!r}); '
        'from benchmarks.harness.fastapi_target_runner import _venv_binding; '
        f'launcher = Path({str(launcher)!r}); environment = Path({str(environment)!r}); '
        '_venv_binding(launcher, environment); '
        'assert launcher.is_symlink()\n'
        'try: _venv_binding(launcher, environment.parent)\n'
        'except RuntimeError: pass\n'
        'else: raise AssertionError("prefix")\n'
        f'try: _venv_binding(Path({str(wrong_target)!r}), environment)\n'
        'except RuntimeError: pass\n'
        'else: raise AssertionError("target")\n'
    )
    completed = subprocess.run((str(launcher), '-c', program), capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stderr
