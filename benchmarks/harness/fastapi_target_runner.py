#!/usr/bin/env python3
"""Neutral, copyable target-local FastAPI semantic probe runner.

The runner intentionally imports no repository module until after it has proved
that ``--source-root`` is the requested clean checkout.  Copy this file outside
both target trees and invoke it with an isolated interpreter:

    ENV/bin/python -I fastapi_target_runner.py --source-root TREE \
      --expected-revision SHA --out EXTERNAL/probes/base/rep0.json
"""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeGuard

REQUIRED_WORKLOADS = (
    'fastapi_cpu_light_endpoint',
    'fastapi_request_scoped_graph',
    'fastapi_singletons_and_transients',
    'fastapi_async_resource_teardown',
    'fastapi_endpoint_with_work',
    'fastapi_application_startup',
)
OPTIONAL_WORKLOADS = (
    'fastapi_no_injection',
    'fastapi_lazy_host_publication',
    'fastapi_lazy_frame_activation_and_drain',
    'fastapi_endpoint_program_one_key',
    'fastapi_endpoint_program_many_keys',
    'fastapi_request_seed_read',
    'fastapi_async_resource_close',
)
_BOOTSTRAP_ARGUMENT = '--depin-fastapi-inner-bootstrap'
_BOOTSTRAP_ENVIRONMENT = 'DEPIN_FASTAPI_INNER_BOOTSTRAP'


class ReportError(RuntimeError):
    """A target pytest-benchmark report that cannot be trusted."""


class JsonObject(dict[str, object]):
    """A JSON object built only by the duplicate-key-checking decoder."""


@dataclass(frozen=True, slots=True)
class DecodedReport:
    sha256: str
    aggregates: dict[str, dict[str, object]]
    metrics: dict[str, dict[str, object]]
    head_only: dict[str, dict[str, object]]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, JsonObject)


def _object(value: object, where: str) -> dict[str, object]:
    if not _is_object(value):
        raise ReportError(f'{where}: expected an object with text keys')
    return value


def _is_array(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _array(value: object, where: str) -> list[object]:
    if not _is_array(value):
        raise ReportError(f'{where}: expected an array')
    return value


def _number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ReportError(f'{where}: expected a number')
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ReportError(f'{where}: expected a finite positive number')
    return result


def _nonnegative(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ReportError(f'{where}: expected a number')
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ReportError(f'{where}: expected a finite non-negative number')
    return result


def _integer(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReportError(f'{where}: expected a positive integer')
    return value


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _strict_report(path: Path) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> JsonObject:
        decoded = JsonObject()
        for key, value in values:
            if key in decoded:
                raise ReportError(f'{path}: duplicate JSON key {key!r}')
            decoded[key] = value
        return decoded

    def invalid(constant: str) -> object:
        raise ReportError(f'{path}: invalid JSON constant {constant!r}')

    try:
        return _object(
            json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=invalid), str(path)
        )
    except OSError as error:
        raise ReportError(f'{path}: cannot read benchmark report ({error})') from error
    except json.JSONDecodeError as error:
        raise ReportError(f'{path}: invalid benchmark report ({error.msg})') from error


def decode_report(report: Path, *, side: str, repetition: int, first: str) -> DecodedReport:
    """Strictly reduce exactly the selected target-side pytest-benchmark report."""
    before = digest(report)
    payload = _strict_report(report)
    entries = _array(payload.get('benchmarks'), f'{report}: benchmarks')
    common = {f'test_latency[{workload}-{label}]' for workload in REQUIRED_WORKLOADS for label in ('direct', 'depin')}
    optional: set[str] = (
        {f'test_latency[fastapi_no_injection-{label}]' for label in ('direct', 'depin')}
        | {f'test_latency[{workload}-depin]' for workload in OPTIONAL_WORKLOADS if workload != 'fastapi_no_injection'}
        if side == 'head'
        else set()
    )
    expected = common | optional
    required = {f'test_latency[{workload}-{label}]' for workload in REQUIRED_WORKLOADS for label in ('direct', 'depin')}
    aggregates: dict[str, dict[str, object]] = {}
    metrics: dict[str, dict[str, object]] = {}
    head_only: dict[str, dict[str, object]] = {}
    for index, value in enumerate(entries):
        entry = _object(value, f'{report}: benchmarks[{index}]')
        name = entry.get('name')
        if not isinstance(name, str) or not name:
            raise ReportError(f'{report}: benchmarks[{index}].name must be text')
        if name not in expected:
            raise ReportError(f'{report}: unexpected benchmark {name!r}')
        if name in aggregates:
            raise ReportError(f'{report}: duplicate benchmark {name!r}')
        stats = _object(entry.get('stats'), f'{report}: {name}.stats')
        rounds = _integer(stats.get('rounds'), f'{report}: {name}.stats.rounds')
        data = [
            _number(item, f'{report}: {name}.stats.data')
            for item in _array(stats.get('data'), f'{report}: {name}.stats.data')
        ]
        if len(data) != rounds:
            raise ReportError(f'{report}: {name}.stats.data length does not match rounds')
        aggregate: dict[str, object] = {
            'rounds': rounds,
            'minimum': _number(stats.get('min'), f'{report}: {name}.stats.min'),
            'median': _number(stats.get('median'), f'{report}: {name}.stats.median'),
            'mean': _number(stats.get('mean'), f'{report}: {name}.stats.mean'),
            'stddev': _nonnegative(stats.get('stddev'), f'{report}: {name}.stats.stddev'),
            'iqr': _nonnegative(stats.get('iqr'), f'{report}: {name}.stats.iqr'),
            'p95': _quantile(data, 0.95),
            'p99': _quantile(data, 0.99),
        }
        if name not in common:
            head_only[name] = aggregate
            continue
        aggregates[name] = aggregate
        metrics[name] = {
            'case_id': name,
            **aggregate,
            'unit': 'seconds per operation',
            'method': 'pytest-benchmark',
            'side': side,
            'repetition': repetition,
            'first': first,
            'order': 0 if side == first else 1,
            'report_sha256': before,
        }
    if required - set(aggregates):
        raise ReportError(f'{report}: missing required benchmark cases {sorted(required - set(aggregates))}')
    if digest(report) != before:
        raise ReportError(f'{report}: benchmark report digest changed while decoding')
    return DecodedReport(before, aggregates, metrics, head_only)


def _benchmark_expression(side: str) -> str:
    workloads = REQUIRED_WORKLOADS + (OPTIONAL_WORKLOADS if side == 'head' else ())
    return ' or '.join(workloads)


def _measurement(value: float, unit: str, method: str) -> dict[str, object]:
    return {'value': value, 'unit': unit, 'method': method}


def _aggregate_measurement(decoded: DecodedReport, case: str, unit: str, method: str) -> dict[str, object]:
    aggregate = decoded.head_only.get(case)
    if aggregate is None:
        raise RuntimeError(f'{case}: target benchmark report lacks the required head-only case')
    value = aggregate.get('median')
    if not isinstance(value, float):
        raise RuntimeError(f'{case}: target benchmark median is malformed')
    return _measurement(value, unit, method)


def benchmark(root: Path, report: Path, side: str, repetition: int, first: str) -> DecodedReport:
    if report.exists():
        raise RuntimeError(f'{report} already exists; target benchmark reports are immutable')
    report.parent.mkdir(parents=True, exist_ok=True)
    command = (
        sys.executable,
        '-I',
        '-m',
        'pytest',
        str(root / 'benchmarks' / 'test_latency.py'),
        '--benchmark-only',
        '-q',
        f'--benchmark-json={report}',
        '-k',
        _benchmark_expression(side),
    )
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f'target pytest benchmark failed\n{completed.stdout}{completed.stderr}')
    if not report.is_file():
        raise RuntimeError('target pytest benchmark did not write its JSON report')
    try:
        return decode_report(report, side=side, repetition=repetition, first=first)
    except ReportError as error:
        raise RuntimeError(str(error)) from error


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(('git', '-C', str(root), *arguments), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f'git -C {root} {" ".join(arguments)} failed: {completed.stderr.strip()}')
    return completed.stdout.strip()


def clean_target(root: Path, expected: str) -> None:
    if git(root, 'rev-parse', 'HEAD') != expected:
        raise RuntimeError('target revision differs from --expected-revision')
    if git(root, 'status', '--porcelain'):
        raise RuntimeError('target checkout is dirty')


def under(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve()))
    except ValueError as error:
        raise RuntimeError(f'{resolved} is outside target root {root}') from error


class Observation(Protocol):
    @property
    def result(self) -> object: ...

    @property
    def constructed(self) -> tuple[object, ...]: ...

    @property
    def closed(self) -> tuple[object, ...]: ...


class ObservableImplementation(Protocol):
    def observe(self) -> Observation: ...


def observed(value: Observation) -> dict[str, object]:
    result = value.result
    if not isinstance(result, str):
        raise RuntimeError('workload observation result must be text')
    constructed = value.constructed
    closed = value.closed
    return {'result': result, 'constructed': list(constructed), 'closed': list(closed), 'error': None}


def attempt(implementation: ObservableImplementation) -> dict[str, object]:
    try:
        return observed(implementation.observe())
    except BaseException as error:
        return {'result': None, 'constructed': [], 'closed': [], 'error': f'{type(error).__name__}: {error}'}


def installed(name: str, root: Path) -> tuple[str, str]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError(f'locked interpreter lacks required distribution {name!r}') from error
    if name == 'pydepin':
        contents = distribution.read_text('direct_url.json')
        if contents is None:
            raise RuntimeError('pydepin must be installed editable from the target checkout')
        try:
            payload = json.loads(contents)
        except json.JSONDecodeError as error:
            raise RuntimeError('pydepin must be installed editable from the target checkout') from error
        url = payload.get('url')
        if not isinstance(url, str) or not url.startswith('file://'):
            raise RuntimeError('pydepin direct_url must bind an editable target checkout')
        from urllib.parse import unquote, urlparse

        if Path(unquote(urlparse(url).path)).resolve() != root.resolve():
            raise RuntimeError('pydepin direct_url is not bound to the target checkout')
        return distribution.version, url
    return distribution.version, ''


def distinct(root: Path, *external: Path) -> None:
    target = root.resolve()
    for path in external:
        candidate = path.resolve()
        if candidate == target or target in candidate.parents or candidate in target.parents:
            raise RuntimeError(f'{candidate} aliases target root {target}')


def _venv_binding(launcher: Path, environment: Path) -> dict[str, str]:
    lexical_launcher = launcher.absolute()
    lexical_environment = environment.absolute()
    if not lexical_launcher.is_file():
        raise RuntimeError(f'{lexical_launcher}: locked environment launcher does not exist')
    try:
        _ = lexical_launcher.relative_to(lexical_environment)
    except ValueError as error:
        raise RuntimeError(
            f'{lexical_launcher}: launcher is outside declared environment {lexical_environment}'
        ) from error
    if lexical_launcher.resolve() != Path(sys.executable).resolve():
        raise RuntimeError('locked environment launcher target does not match the executing interpreter')
    if Path(sys.prefix).resolve() != lexical_environment.resolve():
        raise RuntimeError('executing interpreter prefix does not match declared locked environment')
    cfg = lexical_environment / 'pyvenv.cfg'
    if not cfg.is_file():
        raise RuntimeError(f'{cfg}: locked environment configuration is missing')
    return {
        'interpreter': str(lexical_launcher),
        'launcher_target': str(lexical_launcher.resolve()),
        'prefix': str(Path(sys.prefix).absolute()),
        'base_prefix': str(Path(sys.base_prefix).absolute()),
        'pyvenv_cfg_sha256': digest(cfg),
    }


def _source_argument(arguments: list[str]) -> Path | None:
    if '--source-root' in arguments:
        index = arguments.index('--source-root')
        if index + 1 == len(arguments):
            raise RuntimeError('--source-root requires a path')
        return Path(arguments[index + 1])
    if '--bootstrap-probe' in arguments:
        index = arguments.index('--bootstrap-probe')
        if index + 1 == len(arguments):
            raise RuntimeError('--bootstrap-probe requires a source root')
        return Path(arguments[index + 1])
    return None


def _bootstrap() -> Path | None:
    arguments = sys.argv[1:]
    count = arguments.count(_BOOTSTRAP_ARGUMENT)
    if count > 1:
        raise RuntimeError('duplicate deterministic bootstrap marker')
    if count == 0:
        if _BOOTSTRAP_ENVIRONMENT in os.environ:
            raise RuntimeError('deterministic bootstrap marker is present without an inner-stage argument')
        environment = os.environ.copy()
        for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP'):
            environment.pop(name, None)
        environment.update(
            {
                _BOOTSTRAP_ENVIRONMENT: '1',
                'PYTHONHASHSEED': '0',
                'PYTHONNOUSERSITE': '1',
                'PYTHONDONTWRITEBYTECODE': '1',
            }
        )
        os.execve(
            sys.executable,
            [sys.executable, str(Path(__file__).resolve()), _BOOTSTRAP_ARGUMENT, *arguments],
            environment,
        )
    if os.environ.get(_BOOTSTRAP_ENVIRONMENT) != '1':
        raise RuntimeError('missing deterministic bootstrap marker')
    arguments.remove(_BOOTSTRAP_ARGUMENT)
    sys.argv[:] = [sys.argv[0], *arguments]
    root = _source_argument(arguments)
    if root is not None:
        resolved = root.resolve()
        sys.path[:] = [entry for entry in sys.path if entry and Path(entry).resolve() != resolved]
    return root


def _bootstrap_probe(root: Path) -> None:
    sys.path.insert(0, str(root.resolve()))
    from benchmarks.harness import memory

    allocation = memory.allocations_per_operation(lambda: object(), operations=1)
    print(
        json.dumps(
            {
                'hash_randomization': sys.flags.hash_randomization,
                'memory_module': str(Path(memory.__file__).resolve()),
                'allocation_peak': allocation.peak,
            }
        )
    )


def capture(
    root: Path,
    expected: str,
    expected_lock: str,
    out: Path,
    bundle: Path,
    environment: Path,
    cache: Path,
    side: str,
    repetition: int,
    first: str,
    benchmark_report: Path,
    launcher: Path,
) -> None:
    distinct(root, out, bundle, environment, cache)
    binding = _venv_binding(launcher, environment)
    clean_target(root, expected)
    if digest(root / 'uv.lock') != expected_lock:
        raise RuntimeError('target lock SHA256 differs from --expected-lock-sha256')
    if out.exists():
        raise RuntimeError(f'{out} already exists; raw target records are immutable')
    sys.path.insert(0, str(root))
    from benchmarks.experiments import contention
    from benchmarks.harness import environment as harness_environment
    from benchmarks.harness import memory, work
    from benchmarks.workloads.application.inventory import WORKLOADS as inventory

    selected = {workload.name: workload for workload in inventory}
    if set(REQUIRED_WORKLOADS) - set(selected):
        raise RuntimeError('target checkout lacks a required common FastAPI workload')
    for module in (
        'depin',
        'benchmarks',
        'benchmarks.test_latency',
        'benchmarks.workloads.application.inventory',
    ):
        loaded = __import__(module, fromlist=['__file__'])
        location = getattr(loaded, '__file__', None)
        if not isinstance(location, str):
            raise RuntimeError(f'{module} has no resolved file')
        _ = under(Path(location), root)
    _ = tuple(installed(name, root) for name in ('pydepin', 'pytest', 'pytest-benchmark', 'fastapi', 'starlette'))
    records: list[dict[str, object]] = []
    for name in REQUIRED_WORKLOADS:
        workload = selected[name]
        if workload.baseline is None:
            raise RuntimeError(f'{name} lacks a direct implementation')
        records.append(
            {
                'workload': name,
                'depin': attempt(workload.subject),
                'direct': attempt(workload.baseline),
            }
        )
    cpu = selected.get('fastapi_cpu_light_endpoint')
    if cpu is None:
        raise RuntimeError('fastapi_cpu_light_endpoint is absent from the target inventory')
    prepared = cpu.subject.prepare()
    try:
        allocation = memory.allocations_per_operation(prepared.call, operations=1)
        retained = memory.retained(prepared.call)
        calls = work.calls_per_operation(prepared.call, operations=1)
    finally:
        if prepared.close is not None:
            prepared.close()
    profile = contention.collect(samples=5, workers=2)['profiles']['request_scopes']
    decoded = benchmark(root, benchmark_report, side, repetition, first)
    clean_target(root, expected)
    payload = {
        'schema_version': 4,
        'side': side,
        'repetition': repetition,
        'revision': expected,
        **binding,
        'environment': harness_environment.capture()
        | {
            'bootstrap': {
                'outer': 'isolated-python-I',
                'inner': {
                    'hash_seed': '0',
                    'pythonpath': 'removed',
                    'user_site': 'disabled',
                    'bytecode': 'disabled',
                },
            }
        },
        'observations': records,
        'first': first,
        'benchmark_report': {
            'sha256': decoded.sha256,
            'aggregates': decoded.aggregates,
        },
        'benchmark_metrics': decoded.metrics,
        'memory': {
            'retained': _measurement(float(retained), 'bytes', 'tracemalloc-retained'),
            'allocations': _measurement(float(allocation.blocks), 'allocation-count', 'tracemalloc-allocation-count'),
            'peak': _measurement(float(allocation.peak), 'bytes', 'tracemalloc-peak'),
            'work': {
                **_measurement(float(calls), 'calls per operation', 'calls-per-operation'),
                'operations': 1,
                'sample_count': 1,
                'config': {'operations': 1},
            },
        },
        'contention': {
            'config': {'samples': 5, 'workers': 2},
            'direct': _measurement(profile['direct']['p99_seconds'], 'seconds', 'synchronized-wave'),
            'depin': _measurement(profile['depin']['p99_seconds'], 'seconds', 'synchronized-wave'),
        },
    }
    if side == 'head':
        from benchmarks.workloads.component.fastapi import WORKLOADS as components

        control = _aggregate_measurement(
            decoded, 'test_latency[fastapi_no_injection-direct]', 'seconds per operation', 'direct-null'
        )
        payload['head_only'] = {
            'no_injection': {
                'direct': control,
                'depin': _aggregate_measurement(
                    decoded, 'test_latency[fastapi_no_injection-depin]', 'seconds per operation', 'direct-null'
                ),
            },
            'components': {
                workload.name: {
                    'control': control,
                    'depin': _aggregate_measurement(
                        decoded,
                        f'test_latency[{workload.name}-depin]',
                        'seconds per operation',
                        'component-observation',
                    ),
                    'config': {'control_case': 'test_latency[fastapi_no_injection-direct]'},
                }
                for workload in components
            },
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=out.parent, delete=False) as temporary:
        json.dump(payload, temporary, sort_keys=True, separators=(',', ':'))
        temporary.write('\n')
        name = temporary.name
    Path(name).replace(out)


def main() -> int:
    root = _bootstrap()
    if sys.argv[1:2] == ['--bootstrap-probe']:
        if root is None:
            raise RuntimeError('--bootstrap-probe requires a source root')
        _bootstrap_probe(root)
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--expected-revision', required=True)
    parser.add_argument('--expected-lock-sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bundle-root', type=Path, required=True)
    parser.add_argument('--environment-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--side', choices=('base', 'head'), required=True)
    parser.add_argument('--repetition', type=int, required=True)
    parser.add_argument('--first', choices=('base', 'head'), required=True)
    parser.add_argument('--benchmark-report', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        capture(
            arguments.source_root,
            arguments.expected_revision,
            arguments.expected_lock_sha256,
            arguments.out,
            arguments.bundle_root,
            arguments.environment_root,
            arguments.cache_root,
            arguments.side,
            arguments.repetition,
            arguments.first,
            arguments.benchmark_report,
            arguments.launcher,
        )
    except RuntimeError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
