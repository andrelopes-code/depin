"""Capture then reduce FastAPI acceptance evidence from locked revision interpreters.

Capture each side in its own source checkout and environment, then reduce only
the immutable raw files::

    <base-python> -m benchmarks.harness.fastapi_evidence capture --side base --repetition 0 --out RAW
    <head-python> -m benchmarks.harness.fastapi_evidence capture --side head --repetition 0 --out RAW
    python -m benchmarks.harness.fastapi_evidence reduce --raw RAW --out EVIDENCE \
        --base-revision BASE --head-revision HEAD --base-environment BASE_ENV --head-environment HEAD_ENV
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import median

from benchmarks.contracts import Implementation, Observation, Workload
from benchmarks.experiments import contention
from benchmarks.harness import (
    HarnessError,
    memory,
    require_array,
    require_integer,
    require_number,
    require_object,
    require_text,
    write_json,
)
from benchmarks.harness import reduce as benchmark_reduce
from benchmarks.harness.fastapi_acceptance import ATTRIBUTION_WORKLOAD, COMPONENT_WORKLOADS, TAIL_WORKLOADS
from benchmarks.harness.work import calls_per_operation
from benchmarks.workloads import WORKLOADS

BASELINE_REVISION = '086adf98459773e3175f4723b2b64e3f47306e42'
SCHEMA_VERSION = 4
REPETITIONS = 5


def _revision() -> str:
    completed = subprocess.run(('git', 'rev-parse', 'HEAD'), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise HarnessError('cannot determine the source revision for FastAPI evidence capture')
    return completed.stdout.strip()


def _target_revision(root: Path) -> str:
    completed = subprocess.run(
        ('git', '-C', str(root), 'rev-parse', 'HEAD'), capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise HarnessError(f'{root}: cannot determine target revision')
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise HarnessError(f'{path}: cannot hash ({error})') from error


def collect(
    out: Path,
    *,
    base: Path,
    head: Path,
    interpreters: Mapping[str, Path],
    cache: Path,
) -> None:
    """Run semantic probes from an external bundle against two locked checkouts."""
    if out.exists():
        raise HarnessError(f'{out}: collection destination already exists')
    runner = Path(__file__).with_name('fastapi_target_runner.py')
    bundle = out.parent / f'{out.name}-runner'
    if bundle.exists():
        raise HarnessError(f'{bundle}: external runner bundle already exists')
    bundle.mkdir(parents=True)
    copied = bundle / runner.name
    shutil.copyfile(runner, copied)
    manifests: dict[str, object] = {}
    targets = {'base': base, 'head': head}
    for side, root in targets.items():
        interpreter = interpreters.get(side)
        if interpreter is None or not interpreter.is_file():
            raise HarnessError(f'{side}: a locked target interpreter is required')
        manifests[side] = {
            'root': str(root.resolve()),
            'revision': _target_revision(root),
            'lock_sha256': _sha256(root / 'uv.lock'),
        }
    for repetition in range(REPETITIONS):
        order = ('base', 'head') if repetition % 2 == 0 else ('head', 'base')
        for side in order:
            root = targets[side]
            interpreter = interpreters[side]
            manifest = require_object(manifests[side], f'{side} manifest')
            revision = require_text(manifest.get('revision'), f'{side} manifest revision')
            lock = require_text(manifest.get('lock_sha256'), f'{side} manifest lock SHA256')
            record = out / side / f'rep{repetition}.json'
            report = bundle / 'reports' / side / f'rep{repetition}.json'
            argv = (
                str(interpreter.absolute()),
                '-I',
                str(copied),
                '--source-root',
                str(root.resolve()),
                '--expected-revision',
                revision,
                '--expected-lock-sha256',
                lock,
                '--out',
                str(record),
                '--bundle-root',
                str(bundle.resolve()),
                '--environment-root',
                str(interpreter.absolute().parent.parent),
                '--launcher',
                str(interpreter.absolute()),
                '--cache-root',
                str(cache.resolve()),
                '--side',
                side,
                '--repetition',
                str(repetition),
                '--first',
                order[0],
                '--benchmark-report',
                str(report),
            )
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                env=os.environ | {'PYTHONHASHSEED': memory.HASH_SEED},
            )
            if completed.returncode != 0:
                raise HarnessError(
                    f'{side} rep{repetition}: neutral runner failed\n{completed.stdout}{completed.stderr}'
                )
    write_json(out / 'source-manifest.json', {'runner_sha256': _sha256(copied), 'targets': manifests})


def _median(call: Callable[[], object], *, samples: int = 101) -> float:
    if samples < 5 or samples % 2 == 0:
        raise HarnessError('FastAPI evidence timing requires an odd sample count of at least five')
    readings: list[float] = []
    for _ in range(samples):
        started = time.process_time_ns()
        _ = call()
        readings.append((time.process_time_ns() - started) / 1_000_000_000)
    return sorted(readings)[samples // 2]


def _timed(implementation: Implementation) -> float:
    prepared = implementation.prepare()
    try:
        return _median(prepared.call)
    finally:
        if prepared.close is not None:
            prepared.close()


def _observation(observation: Observation) -> dict[str, object]:
    return {
        'response': observation.result,
        'constructed': list(observation.constructed),
        'closed': list(observation.closed),
    }


def _by_name() -> dict[str, Workload]:
    return {workload.name: workload for workload in WORKLOADS}


def _guard(workload: Workload) -> dict[str, object]:
    if workload.baseline is None:
        raise HarnessError(f'{workload.name}: FastAPI evidence requires a direct baseline')
    subject = _observation(workload.subject.observe())
    direct = _observation(workload.baseline.observe())
    response = subject['response'] == direct['response']
    lifecycle = subject['constructed'] == direct['constructed'] and subject['closed'] == direct['closed']
    teardown = subject['closed'] == direct['closed']
    if workload.name == 'fastapi_async_resource_teardown':
        teardown = teardown and bool(subject['closed']) and bool(direct['closed'])
    return {
        'workload': workload.name,
        'subject': subject,
        'direct': direct,
        'response_equivalent': response,
        'lifecycle_equivalent': lifecycle,
        'teardown_equivalent': teardown,
    }


def _memory(implementation: Implementation) -> dict[str, object]:
    prepared = implementation.prepare()
    try:
        allocation = memory.allocations_per_operation(prepared.call, operations=1)
        return {
            'retained': memory.retained(prepared.call),
            'peak': allocation.peak,
            'allocations': allocation.blocks,
            'work': calls_per_operation(prepared.call, operations=1),
        }
    finally:
        if prepared.close is not None:
            prepared.close()


def _components(names: Sequence[str]) -> dict[str, object]:
    inventory = _by_name()
    measured: dict[str, object] = {}
    control = _median(lambda: None)
    for name in names:
        workload = inventory.get(name)
        if workload is None:
            raise HarnessError(f'{name}: component is absent from the workload inventory')
        measured[name] = {'control': control, 'depin': _timed(workload.subject)}
    return measured


def capture(out: Path, *, side: str, repetition: int) -> None:
    """Execute target-side guards and probes, writing one immutable raw record."""
    if side not in ('base', 'head'):
        raise HarnessError(f'{side}: side must be base or head')
    if repetition not in range(REPETITIONS):
        raise HarnessError(f'{repetition}: repetition must be 0 through {REPETITIONS - 1}')
    inventory = _by_name()
    cpu = inventory.get(ATTRIBUTION_WORKLOAD)
    if cpu is None or cpu.baseline is None:
        raise HarnessError(f'{ATTRIBUTION_WORKLOAD}: direct baseline is required')
    record: dict[str, object] = {
        'schema_version': SCHEMA_VERSION,
        'side': side,
        'repetition': repetition,
        'revision': _revision(),
        'interpreter': str(Path(sys.executable).resolve()),
        'direct_p50': _timed(cpu.baseline),
        'guards': [_guard(inventory[name]) for name in TAIL_WORKLOADS],
        'memory': _memory(cpu.subject),
    }
    if side == 'head':
        no_injection = inventory.get('fastapi_no_injection')
        if no_injection is None or no_injection.baseline is None:
            raise HarnessError('fastapi_no_injection: direct/null control is required')
        profile = contention.collect(samples=5, workers=2)['profiles']['request_scopes']
        direct = profile['direct']
        depin = profile['depin']
        record['head_only'] = {
            'no_injection': {'direct': _timed(no_injection.baseline), 'depin': _timed(no_injection.subject)},
            'components': _components(COMPONENT_WORKLOADS),
            'contention': {'direct': direct.get('p99_seconds'), 'depin': depin.get('p99_seconds')},
        }
    write_json(out / side / f'rep{repetition}.json', record)


def _positive(value: object, where: str) -> float:
    result = require_number(value, where)
    if not math.isfinite(result) or result <= 0.0:
        raise HarnessError(f'{where}: expected a finite positive measurement')
    return result


def _strict_json(path: Path) -> dict[str, object]:
    """Decode an evidence record without JSON's duplicate-key or NaN leniency."""

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise HarnessError(f'{path}: duplicate JSON key {key!r}')
            result[key] = value
        return result

    def invalid(constant: str) -> object:
        raise HarnessError(f'{path}: invalid JSON constant {constant!r}')

    try:
        decoded = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
    except OSError as error:
        raise HarnessError(f'{path}: cannot be read ({error})') from error
    except json.JSONDecodeError as error:
        raise HarnessError(f'{path}: is not JSON ({error.msg} at line {error.lineno})') from error
    return require_object(decoded, str(path))


def _report_aggregate(
    payload: Mapping[str, object], path: Path, workload: str, label: str
) -> benchmark_reduce.Aggregate:
    """Read one implementation's aggregate from the target's pytest-benchmark report.

    The report is deliberately retained with each raw target record.  A direct
    control measured by another timer is not comparable to the `depin` case, so
    it is never an input to the attribution calculation.
    """
    report = require_object(payload.get('benchmark_report'), f'{path}: benchmark report')
    aggregates = require_object(report.get('aggregates'), f'{path}: benchmark report.aggregates')
    case = f'test_latency[{workload}-{label}]'
    aggregate = benchmark_reduce.decode(case, aggregates.get(case), f'{path}: benchmark report')
    if not benchmark_reduce.qualifies(aggregate):
        raise HarnessError(f'{path}: {case} does not meet the benchmark sample-quality minimum')
    for field, value in (('median', aggregate.median), ('p95', aggregate.p95), ('p99', aggregate.p99)):
        if value is None or not math.isfinite(value) or value <= 0.0:
            raise HarnessError(f'{path}: {case}.{field} must be finite and positive')
    return aggregate


def _raw(path: Path, side: str, repetition: int, revision: str, environment: Path) -> Mapping[str, object]:
    payload = _strict_json(path)
    if require_integer(payload.get('schema_version'), f'{path}: schema_version') != SCHEMA_VERSION:
        raise HarnessError(f'{path}: unsupported schema version')
    if require_text(payload.get('side'), f'{path}: side') != side:
        raise HarnessError(f'{path}: wrong side')
    if require_integer(payload.get('repetition'), f'{path}: repetition') != repetition:
        raise HarnessError(f'{path}: wrong repetition')
    if require_text(payload.get('revision'), f'{path}: revision') != revision:
        raise HarnessError(f'{path}: wrong revision')
    interpreter = Path(require_text(payload.get('interpreter'), f'{path}: interpreter')).resolve()
    try:
        _ = interpreter.relative_to(environment.resolve())
    except ValueError as error:
        raise HarnessError(f'{path}: interpreter does not belong to declared locked environment') from error
    for workload in TAIL_WORKLOADS:
        _ = _report_aggregate(payload, path, workload, 'depin')
        _ = _report_aggregate(payload, path, workload, 'direct')
    report = require_object(payload.get('benchmark_report'), f'{path}: benchmark report')
    report_digest = require_text(report.get('sha256'), f'{path}: benchmark report.sha256')
    metrics = require_object(payload.get('benchmark_metrics'), f'{path}: benchmark metrics')
    expected_cases = {
        f'test_latency[{workload}-{label}]' for workload in TAIL_WORKLOADS for label in ('direct', 'depin')
    }
    if set(metrics) != expected_cases:
        raise HarnessError(f'{path}: benchmark metrics must exactly cover the common FastAPI inventory')
    for case in expected_cases:
        metric = require_object(metrics.get(case), f'{path}: benchmark metric {case}')
        if require_text(metric.get('case_id'), f'{path}: benchmark metric {case}.case_id') != case:
            raise HarnessError(f'{path}: benchmark metric case identifier mismatch')
        if require_text(metric.get('report_sha256'), f'{path}: benchmark metric {case}.report_sha256') != report_digest:
            raise HarnessError(f'{path}: benchmark metric digest mismatch')
        if require_text(metric.get('side'), f'{path}: benchmark metric {case}.side') != side:
            raise HarnessError(f'{path}: benchmark metric side mismatch')
        if require_integer(metric.get('repetition'), f'{path}: benchmark metric {case}.repetition') != repetition:
            raise HarnessError(f'{path}: benchmark metric repetition mismatch')
        expected_first = 'base' if repetition % 2 == 0 else 'head'
        if require_text(metric.get('first'), f'{path}: benchmark metric {case}.first') != expected_first:
            raise HarnessError(f'{path}: benchmark metric first-side mismatch')
        expected_order = 0 if side == expected_first else 1
        if require_integer(metric.get('order'), f'{path}: benchmark metric {case}.order') != expected_order:
            raise HarnessError(f'{path}: benchmark metric order mismatch')
        if require_text(metric.get('unit'), f'{path}: benchmark metric {case}.unit') != 'seconds per operation':
            raise HarnessError(f'{path}: benchmark metric unit mismatch')
        if require_text(metric.get('method'), f'{path}: benchmark metric {case}.method') != 'pytest-benchmark':
            raise HarnessError(f'{path}: benchmark metric method mismatch')
        for field in ('median', 'p95', 'p99'):
            _ = _positive(metric.get(field), f'{path}: benchmark metric {case}.{field}')
        if require_integer(metric.get('rounds'), f'{path}: benchmark metric {case}.rounds') <= 0:
            raise HarnessError(f'{path}: benchmark metric {case}.rounds must be positive')
    return payload


def _guards(payload: Mapping[str, object], path: Path) -> dict[str, Mapping[str, object]]:
    entries = require_array(payload.get('guards'), f'{path}: guards')
    found: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(entries):
        guard = require_object(value, f'{path}: guards[{index}]')
        name = require_text(guard.get('workload'), f'{path}: guards[{index}].workload')
        if name in found:
            raise HarnessError(f'{path}: duplicate guard {name}')
        for implementation in ('subject', 'direct'):
            observed = require_object(guard.get(implementation), f'{path}: {name}.{implementation}')
            _ = require_text(observed.get('response'), f'{path}: {name}.{implementation}.response')
            _ = require_array(observed.get('constructed'), f'{path}: {name}.{implementation}.constructed')
            _ = require_array(observed.get('closed'), f'{path}: {name}.{implementation}.closed')
        subject = require_object(guard.get('subject'), f'{path}: {name}.subject')
        direct = require_object(guard.get('direct'), f'{path}: {name}.direct')
        response = subject.get('response') == direct.get('response')
        lifecycle = subject.get('constructed') == direct.get('constructed') and subject.get('closed') == direct.get(
            'closed'
        )
        teardown = subject.get('closed') == direct.get('closed')
        if name == 'fastapi_async_resource_teardown':
            teardown = teardown and bool(subject.get('closed')) and bool(direct.get('closed'))
        if guard.get('response_equivalent') is not True or not response:
            raise HarnessError(f'{path}: {name} response equivalence failed')
        if guard.get('lifecycle_equivalent') is not True or not lifecycle:
            raise HarnessError(f'{path}: {name} lifecycle equivalence failed')
        if guard.get('teardown_equivalent') is not True or not teardown:
            raise HarnessError(f'{path}: {name} teardown equivalence failed')
        found[name] = guard
    if set(found) != set(TAIL_WORKLOADS):
        raise HarnessError(f'{path}: guards must exactly cover FastAPI acceptance workloads')
    return found


_LEGACY_V2_VALIDATORS = (_raw, _guards)


def _keys(payload: Mapping[str, object], expected: set[str], where: str) -> None:
    if set(payload) != expected:
        raise HarnessError(f'{where}: fields must exactly match the v3 envelope schema')


def _measurement(value: object, where: str, unit: str, method: str) -> float:
    fields = require_object(value, where)
    _keys(fields, {'value', 'unit', 'method'}, where)
    if require_text(fields.get('unit'), f'{where}.unit') != unit:
        raise HarnessError(f'{where}: unit mismatch')
    if require_text(fields.get('method'), f'{where}.method') != method:
        raise HarnessError(f'{where}: method mismatch')
    return _positive(fields.get('value'), f'{where}.value')


def _observation_v3(value: object, where: str) -> Mapping[str, object]:
    fields = require_object(value, where)
    _keys(fields, {'result', 'constructed', 'closed', 'error'}, where)
    if fields.get('error') is not None or not isinstance(fields.get('result'), str):
        raise HarnessError(f'{where}: literal observation required')
    for field in ('constructed', 'closed'):
        entries = require_array(fields.get(field), f'{where}.{field}')
        for index, entry in enumerate(entries):
            _ = require_text(entry, f'{where}.{field}[{index}]')
    return fields


def _aggregate_v3(value: object, where: str) -> benchmark_reduce.Aggregate:
    aggregate = benchmark_reduce.decode(where, value, where)
    if aggregate.rounds <= 0:
        raise HarnessError(f'{where}: rounds must be positive')
    for field in ('minimum', 'median', 'mean', 'p95', 'p99'):
        number = getattr(aggregate, field)
        if number is None or not math.isfinite(number) or number <= 0.0:
            raise HarnessError(f'{where}.{field}: expected a finite positive measurement')
    for field in ('stddev', 'iqr'):
        number = getattr(aggregate, field)
        if number is None or not math.isfinite(number) or number < 0.0:
            raise HarnessError(f'{where}.{field}: expected a finite non-negative measurement')
    return aggregate


def _envelope(path: Path, side: str, repetition: int, revision: str, environment: Path) -> Mapping[str, object]:
    payload = _strict_json(path)
    expected = {
        'schema_version',
        'side',
        'repetition',
        'revision',
        'interpreter',
        'launcher_target',
        'prefix',
        'base_prefix',
        'pyvenv_cfg_sha256',
        'environment',
        'first',
        'benchmark_report',
        'benchmark_metrics',
        'observations',
        'memory',
        'contention',
    }
    if side == 'head':
        expected.add('head_only')
    _keys(payload, expected, str(path))
    if require_integer(payload.get('schema_version'), f'{path}: schema_version') != SCHEMA_VERSION:
        raise HarnessError(f'{path}: unsupported schema version')
    if (
        require_text(payload.get('side'), f'{path}: side') != side
        or require_integer(payload.get('repetition'), f'{path}: repetition') != repetition
    ):
        raise HarnessError(f'{path}: side/repetition identity mismatch')
    if require_text(payload.get('revision'), f'{path}: revision') != revision:
        raise HarnessError(f'{path}: revision mismatch')
    launcher = Path(require_text(payload.get('interpreter'), f'{path}: interpreter'))
    prefix = Path(require_text(payload.get('prefix'), f'{path}: prefix'))
    environment_root = environment.absolute()
    if not launcher.is_absolute() or not launcher.is_file() or not prefix.is_absolute():
        raise HarnessError(f'{path}: locked environment launcher and prefix must be absolute existing paths')
    try:
        _ = launcher.relative_to(environment_root)
    except ValueError as error:
        raise HarnessError(f'{path}: interpreter does not belong to declared locked environment') from error
    if prefix.resolve() != environment.resolve():
        raise HarnessError(f'{path}: interpreter prefix does not match declared locked environment')
    if Path(require_text(payload.get('launcher_target'), f'{path}: launcher target')).resolve() != launcher.resolve():
        raise HarnessError(f'{path}: launcher target does not match the lexical environment launcher')
    if Path(require_text(payload.get('base_prefix'), f'{path}: base prefix')).resolve() == environment.resolve():
        raise HarnessError(f'{path}: locked interpreter base prefix must differ from its virtual environment prefix')
    cfg = environment / 'pyvenv.cfg'
    if not cfg.is_file() or _sha256(cfg) != require_text(payload.get('pyvenv_cfg_sha256'), f'{path}: pyvenv digest'):
        raise HarnessError(f'{path}: pyvenv configuration digest mismatch')
    first = 'base' if repetition % 2 == 0 else 'head'
    if require_text(payload.get('first'), f'{path}: first') != first:
        raise HarnessError(f'{path}: first-side parity mismatch')
    report = require_object(payload.get('benchmark_report'), f'{path}: benchmark report')
    _keys(report, {'sha256', 'aggregates'}, f'{path}: benchmark report')
    digest = require_text(report.get('sha256'), f'{path}: benchmark report.sha256')
    if len(digest) != 64 or any(character not in '0123456789abcdef' for character in digest):
        raise HarnessError(f'{path}: benchmark report digest is invalid')
    aggregates = require_object(report.get('aggregates'), f'{path}: benchmark aggregates')
    expected_cases = {
        f'test_latency[{workload}-{label}]' for workload in TAIL_WORKLOADS for label in ('direct', 'depin')
    }
    if set(aggregates) != expected_cases:
        raise HarnessError(f'{path}: benchmark aggregates must exactly cover the common FastAPI inventory')
    metrics = require_object(payload.get('benchmark_metrics'), f'{path}: benchmark metrics')
    if set(metrics) != expected_cases:
        raise HarnessError(f'{path}: benchmark metrics must exactly cover the common FastAPI inventory')
    for case in expected_cases:
        aggregate_payload = require_object(aggregates.get(case), f'{path}: benchmark aggregate {case}')
        _keys(
            aggregate_payload,
            {'rounds', 'minimum', 'median', 'mean', 'stddev', 'iqr', 'p95', 'p99'},
            f'{path}: benchmark aggregate {case}',
        )
        aggregate = _aggregate_v3(aggregate_payload, f'{path}: benchmark aggregate {case}')
        metric = require_object(metrics.get(case), f'{path}: benchmark metric {case}')
        _keys(
            metric,
            {
                'case_id',
                'rounds',
                'minimum',
                'median',
                'mean',
                'stddev',
                'iqr',
                'p95',
                'p99',
                'unit',
                'method',
                'side',
                'repetition',
                'first',
                'order',
                'report_sha256',
            },
            f'{path}: benchmark metric {case}',
        )
        for field, value in (
            ('case_id', case),
            ('unit', 'seconds per operation'),
            ('method', 'pytest-benchmark'),
            ('side', side),
            ('first', first),
            ('report_sha256', digest),
        ):
            if require_text(metric.get(field), f'{path}: benchmark metric {case}.{field}') != value:
                raise HarnessError(f'{path}: benchmark metric {field} mismatch')
        if require_integer(metric.get('repetition'), f'{path}: benchmark metric repetition') != repetition:
            raise HarnessError(f'{path}: benchmark metric repetition mismatch')
        if require_integer(metric.get('order'), f'{path}: benchmark metric order') != (0 if side == first else 1):
            raise HarnessError(f'{path}: benchmark metric order mismatch')
        compared = _aggregate_v3(metric, f'{path}: benchmark metric {case}')
        if benchmark_reduce.encode(compared) != benchmark_reduce.encode(aggregate):
            raise HarnessError(f'{path}: benchmark metric aggregate mismatch')
    observations = require_array(payload.get('observations'), f'{path}: observations')
    found: dict[str, tuple[Mapping[str, object], Mapping[str, object]]] = {}
    for index, entry in enumerate(observations):
        record = require_object(entry, f'{path}: observations[{index}]')
        _keys(record, {'workload', 'depin', 'direct'}, f'{path}: observations[{index}]')
        name = require_text(record.get('workload'), f'{path}: observations[{index}].workload')
        if name in found:
            raise HarnessError(f'{path}: duplicate semantic workload')
        depin, direct = (
            _observation_v3(record.get('depin'), f'{path}: {name}.depin'),
            _observation_v3(record.get('direct'), f'{path}: {name}.direct'),
        )
        if depin != direct:
            raise HarnessError(f'{path}: {name}: semantic observation mismatch')
        if name == 'fastapi_async_resource_teardown':
            constructed = require_array(depin.get('constructed'), f'{path}: {name}.constructed')
            closed = require_array(depin.get('closed'), f'{path}: {name}.closed')
            if not constructed or closed != list(reversed(constructed)):
                raise HarnessError(f'{path}: {name}: teardown must close every constructed resource in reverse order')
        found[name] = (depin, direct)
    if set(found) != set(TAIL_WORKLOADS):
        raise HarnessError(f'{path}: observations must exactly cover FastAPI acceptance workloads')
    memory_values = require_object(payload.get('memory'), f'{path}: memory')
    _keys(memory_values, {'retained', 'allocations', 'peak', 'work'}, f'{path}: memory')
    _ = _measurement(memory_values.get('retained'), f'{path}: retained', 'bytes', 'tracemalloc-retained')
    _ = _measurement(
        memory_values.get('allocations'), f'{path}: allocations', 'allocation-count', 'tracemalloc-allocation-count'
    )
    _ = _measurement(memory_values.get('peak'), f'{path}: peak', 'bytes', 'tracemalloc-peak')
    work = require_object(memory_values.get('work'), f'{path}: work')
    _keys(work, {'value', 'unit', 'method', 'operations', 'sample_count', 'config'}, f'{path}: work')
    _ = _positive(work.get('value'), f'{path}: work.value')
    if (
        require_text(work.get('unit'), f'{path}: work.unit') != 'calls per operation'
        or require_text(work.get('method'), f'{path}: work.method') != 'calls-per-operation'
    ):
        raise HarnessError(f'{path}: work unit/method mismatch')
    if (
        require_integer(work.get('operations'), f'{path}: work.operations') < 1
        or require_integer(work.get('sample_count'), f'{path}: work.sample_count') < 1
    ):
        raise HarnessError(f'{path}: work counts must be positive')
    _ = require_object(work.get('config'), f'{path}: work.config')
    contention_values = require_object(payload.get('contention'), f'{path}: contention')
    _keys(contention_values, {'config', 'direct', 'depin'}, f'{path}: contention')
    contention_config = require_object(contention_values.get('config'), f'{path}: contention.config')
    _keys(contention_config, {'samples', 'workers'}, f'{path}: contention.config')
    if (
        require_integer(contention_config.get('samples'), f'{path}: contention.config.samples') < 5
        or require_integer(contention_config.get('workers'), f'{path}: contention.config.workers') < 2
    ):
        raise HarnessError(f'{path}: contention configuration is below the synchronized collection minimum')
    _ = _measurement(contention_values.get('direct'), f'{path}: contention.direct', 'seconds', 'synchronized-wave')
    _ = _measurement(contention_values.get('depin'), f'{path}: contention.depin', 'seconds', 'synchronized-wave')
    if side == 'head':
        head_only = require_object(payload.get('head_only'), f'{path}: head-only')
        _keys(head_only, {'no_injection', 'components'}, f'{path}: head-only')
        no_injection = require_object(head_only.get('no_injection'), f'{path}: no-injection')
        _keys(no_injection, {'direct', 'depin'}, f'{path}: no-injection')
        for label in ('direct', 'depin'):
            _ = _measurement(
                no_injection.get(label), f'{path}: no-injection.{label}', 'seconds per operation', 'direct-null'
            )
        components = require_object(head_only.get('components'), f'{path}: components')
        if set(components) != set(COMPONENT_WORKLOADS):
            raise HarnessError(f'{path}: component inventory is incomplete')
        for name in COMPONENT_WORKLOADS:
            component = require_object(components.get(name), f'{path}: component {name}')
            _keys(component, {'control', 'depin', 'config'}, f'{path}: component {name}')
            _ = _measurement(
                component.get('control'), f'{path}: component {name}.control', 'seconds per operation', 'direct-null'
            )
            _ = _measurement(
                component.get('depin'),
                f'{path}: component {name}.depin',
                'seconds per operation',
                'component-observation',
            )
            _ = require_object(component.get('config'), f'{path}: component {name}.config')
    return payload


def _sidecar(values: Sequence[float]) -> float:
    return float(median(values))


def reduce(raw: Path, baseline_revision: str, head_revision: str, environments: Mapping[str, str]) -> dict[str, object]:
    """Validate exact v3 envelopes and project the unchanged evaluator inputs."""
    if baseline_revision != BASELINE_REVISION:
        raise HarnessError('baseline revision is not the accepted FastAPI baseline')
    locations = {side: Path(require_text(environments.get(side), f'{side} environment')) for side in ('base', 'head')}
    for side in ('base', 'head'):
        directory = raw / side
        expected = {f'rep{index}.json' for index in range(REPETITIONS)}
        try:
            found = {path.name for path in directory.iterdir() if path.is_file()}
        except OSError as error:
            raise HarnessError(f'{directory}: cannot inspect raw layout ({error})') from error
        if found != expected:
            raise HarnessError(f'{directory}: requires exactly rep0.json through rep4.json')
    base_records = [
        _envelope(raw / 'base' / f'rep{i}.json', 'base', i, baseline_revision, locations['base'])
        for i in range(REPETITIONS)
    ]
    head_records = [
        _envelope(raw / 'head' / f'rep{i}.json', 'head', i, head_revision, locations['head'])
        for i in range(REPETITIONS)
    ]
    semantic: list[dict[str, object]] = []
    for repetition, (base, head) in enumerate(zip(base_records, head_records, strict=True)):
        if require_object(base.get('contention'), 'base contention').get('config') != require_object(
            head.get('contention'), 'head contention'
        ).get('config'):
            raise HarnessError('contention configuration differs between base and head')
        base_observations = {
            require_text(require_object(item, 'base observation').get('workload'), 'base workload'): require_object(
                item, 'base observation'
            )
            for item in require_array(base.get('observations'), 'base observations')
        }
        head_observations = {
            require_text(require_object(item, 'head observation').get('workload'), 'head workload'): require_object(
                item, 'head observation'
            )
            for item in require_array(head.get('observations'), 'head observations')
        }
        for workload in TAIL_WORKLOADS:
            before = require_object(base_observations[workload].get('depin'), 'base depin observation')
            after = require_object(head_observations[workload].get('depin'), 'head depin observation')
            if before != after:
                raise HarnessError(f'{workload}: cross-revision semantic observation mismatch')
            events = len(require_array(before.get('constructed'), 'constructed')) + len(
                require_array(before.get('closed'), 'closed')
            )
            semantic.append(
                {
                    'workload': workload,
                    'repetition': repetition,
                    'base_revision': baseline_revision,
                    'head_revision': head_revision,
                    'response': 'equivalent',
                    'lifecycle': 'equivalent',
                    'event_counts': {'base': events, 'head': events},
                    'teardown': 'equivalent',
                    'deterministic': 'passed',
                }
            )

    def measured(records: Sequence[Mapping[str, object]], key: str, unit: str, method: str) -> list[float]:
        return [
            _measurement(require_object(record.get('memory'), 'memory').get(key), key, unit, method)
            for record in records
        ]

    def head_measurements(key: str) -> list[float]:
        return [
            _measurement(
                require_object(
                    require_object(record.get('head_only'), 'head only').get('no_injection'), 'no injection'
                ).get(key),
                key,
                'seconds per operation',
                'direct-null',
            )
            for record in head_records
        ]

    def contention(records: Sequence[Mapping[str, object]], key: str) -> list[float]:
        return [
            _measurement(
                require_object(record.get('contention'), 'contention').get(key), key, 'seconds', 'synchronized-wave'
            )
            for record in records
        ]

    def aggregate_record(record: Mapping[str, object], repetition: int) -> dict[str, object]:
        report = require_object(record.get('benchmark_report'), 'report')
        aggregates = require_object(report.get('aggregates'), 'aggregates')
        return {
            'repetition': repetition,
            'first': record['first'],
            'aggregates': {
                name: benchmark_reduce.encode(_aggregate_v3(aggregates.get(f'test_latency[{name}-depin]'), name))
                for name in TAIL_WORKLOADS
            },
        }

    environment_payload = require_object(base_records[0].get('environment'), 'environment')
    if any(
        require_object(record.get('environment'), 'environment') != environment_payload
        for record in (*base_records, *head_records)
    ):
        raise HarnessError('environment differs between raw envelopes')
    base_retained, head_retained = (
        measured(base_records, 'retained', 'bytes', 'tracemalloc-retained'),
        measured(head_records, 'retained', 'bytes', 'tracemalloc-retained'),
    )
    base_peak, head_peak = (
        measured(base_records, 'peak', 'bytes', 'tracemalloc-peak'),
        measured(head_records, 'peak', 'bytes', 'tracemalloc-peak'),
    )
    base_allocations, head_allocations = (
        measured(base_records, 'allocations', 'allocation-count', 'tracemalloc-allocation-count'),
        measured(head_records, 'allocations', 'allocation-count', 'tracemalloc-allocation-count'),
    )
    head_only = {
        'no_injection': {'direct': _sidecar(head_measurements('direct')), 'depin': _sidecar(head_measurements('depin'))}
    }
    no_injection = require_object(head_only.get('no_injection'), 'no-injection evidence')
    contention_values = {
        'direct': _sidecar(contention(base_records, 'depin')),
        'depin': _sidecar(contention(head_records, 'depin')),
    }
    base_memory = {
        'retained': _sidecar(base_retained),
        'peak': _sidecar(base_peak),
        'allocations': _sidecar(base_allocations),
    }
    head_memory = {
        'retained': _sidecar(head_retained),
        'peak': _sidecar(head_peak),
        'allocations': _sidecar(head_allocations),
    }
    return {
        'dataset': {
            'environment.json': {'seed': 20260902, 'repetitions': REPETITIONS, 'environment': environment_payload},
            'base': {
                'repetitions': [
                    {'record': aggregate_record(record, index)} for index, record in enumerate(base_records)
                ]
            },
            'head': {
                'repetitions': [
                    {'record': aggregate_record(record, index)} for index, record in enumerate(head_records)
                ]
            },
        },
        'envelopes': {'base': list(base_records), 'head': list(head_records)},
        'attribution': {
            'schema_version': 1,
            'workload': ATTRIBUTION_WORKLOAD,
            'baseline_revision': baseline_revision,
            'head_revision': head_revision,
            'metric': 'p50',
            'unit': 'seconds per operation',
            'method': 'direct-request-p50',
            'scope': 'paired',
            'repetitions': [
                {
                    'repetition': i,
                    'base_direct_p50': _report_aggregate(
                        base, raw / 'base' / f'rep{i}.json', ATTRIBUTION_WORKLOAD, 'direct'
                    ).median,
                    'head_direct_p50': _report_aggregate(
                        head, raw / 'head' / f'rep{i}.json', ATTRIBUTION_WORKLOAD, 'direct'
                    ).median,
                }
                for i, (base, head) in enumerate(zip(base_records, head_records, strict=True))
            ],
        },
        'sidecars': {
            'schema_version': 1,
            'no_injection': {
                'workload': 'fastapi_no_injection',
                'metric': 'latency',
                'unit': 'seconds per operation',
                'method': 'direct-null',
                'scope': 'head-only',
                'direct': _positive(no_injection.get('direct'), 'no injection direct'),
                'depin': _positive(no_injection.get('depin'), 'no injection depin'),
                'limit': 0.05,
            },
            'retained_memory': {
                'workload': ATTRIBUTION_WORKLOAD,
                'metric': 'retained',
                'unit': 'bytes',
                'method': 'tracemalloc-retained',
                'scope': 'paired',
                'base': _positive(base_memory.get('retained'), 'base retained'),
                'head': _positive(head_memory.get('retained'), 'head retained'),
                'limit': 0.02,
            },
            'peak_memory': {
                'workload': ATTRIBUTION_WORKLOAD,
                'metric': 'peak-memory',
                'unit': 'bytes',
                'method': 'tracemalloc-peak',
                'scope': 'paired',
                'base': _positive(base_memory.get('peak'), 'base peak'),
                'head': _positive(head_memory.get('peak'), 'head peak'),
                'limit': 0.05,
            },
            'allocations': {
                'workload': ATTRIBUTION_WORKLOAD,
                'metric': 'allocations',
                'unit': 'allocation-count',
                'method': 'tracemalloc-allocation-count',
                'scope': 'paired',
                'base': _positive(base_memory.get('allocations'), 'base allocations'),
                'head': _positive(head_memory.get('allocations'), 'head allocations'),
                'limit': 0.0,
            },
            'application_startup': {
                'workload': 'fastapi_application_startup',
                'metric': 'latency',
                'unit': 'seconds per operation',
                'method': 'paired-total-p50',
                'scope': 'paired',
                'limit': 0.06,
            },
            'contention': {
                'workload': 'request_scopes',
                'metric': 'p99_seconds',
                'unit': 'seconds',
                'method': 'synchronized-wave',
                'scope': 'paired',
                'base': _positive(contention_values.get('direct'), 'contention direct'),
                'head': _positive(contention_values.get('depin'), 'contention depin'),
                'limit': 0.05,
            },
            'components': [
                {
                    'workload': name,
                    'metric': 'latency',
                    'unit': 'seconds per operation',
                    'method': 'component-observation',
                    'scope': 'head-only',
                    'validated': True,
                }
                for name in COMPONENT_WORKLOADS
            ],
        },
        'provenance': {
            'schema_version': 1,
            'baseline_revision': baseline_revision,
            'head_revision': head_revision,
            'protocol': {
                'collector': 'benchmarks.harness.pairs',
                'repetitions': REPETITIONS,
                'seed': 20260902,
                'locked_environments': True,
                'workloads': list(TAIL_WORKLOADS),
            },
            'environment': environment_payload,
            'semantic_validation': semantic,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture_parser = commands.add_parser('capture')
    capture_parser.add_argument('--out', type=Path, required=True)
    capture_parser.add_argument('--side', required=True)
    capture_parser.add_argument('--repetition', type=int, required=True)
    collect_parser = commands.add_parser('collect')
    collect_parser.add_argument('--out', type=Path, required=True)
    collect_parser.add_argument('--base-dir', type=Path, required=True)
    collect_parser.add_argument('--head-dir', type=Path, required=True)
    collect_parser.add_argument('--base-python', type=Path, required=True)
    collect_parser.add_argument('--head-python', type=Path, required=True)
    collect_parser.add_argument('--cache-root', type=Path, required=True)
    reduce_parser = commands.add_parser('reduce')
    reduce_parser.add_argument('--raw', type=Path, required=True)
    reduce_parser.add_argument('--out', type=Path, required=True)
    reduce_parser.add_argument('--base-revision', required=True)
    reduce_parser.add_argument('--head-revision', required=True)
    reduce_parser.add_argument('--base-environment', required=True)
    reduce_parser.add_argument('--head-environment', required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == 'capture':
            capture(arguments.out, side=arguments.side, repetition=arguments.repetition)
        elif arguments.command == 'collect':
            collect(
                arguments.out,
                base=arguments.base_dir,
                head=arguments.head_dir,
                interpreters={'base': arguments.base_python, 'head': arguments.head_python},
                cache=arguments.cache_root,
            )
        else:
            output = reduce(
                arguments.raw,
                arguments.base_revision,
                arguments.head_revision,
                {'base': arguments.base_environment, 'head': arguments.head_environment},
            )
            dataset = require_object(output['dataset'], 'dataset output')
            write_json(
                arguments.out / 'dataset' / 'environment.json',
                require_object(dataset['environment.json'], 'environment'),
            )
            for side in ('base', 'head'):
                records = require_array(
                    require_object(dataset[side], f'{side} dataset').get('repetitions'), f'{side} repetitions'
                )
                for entry in records:
                    record = require_object(require_object(entry, 'dataset entry').get('record'), 'dataset record')
                    write_json(
                        arguments.out
                        / 'dataset'
                        / side
                        / f'rep{require_integer(record.get("repetition"), "dataset repetition")}.json',
                        record,
                    )
            write_json(arguments.out / 'attribution.json', require_object(output['attribution'], 'attribution output'))
            write_json(arguments.out / 'sidecars.json', require_object(output['sidecars'], 'sidecars output'))
            write_json(arguments.out / 'provenance.json', require_object(output['provenance'], 'provenance output'))
            envelopes = require_object(output['envelopes'], 'envelopes output')
            for side in ('base', 'head'):
                for raw_value in require_array(envelopes.get(side), f'{side} envelopes'):
                    raw_envelope = require_object(raw_value, 'raw envelope')
                    write_json(
                        arguments.out
                        / 'raw'
                        / side
                        / f'rep{require_integer(raw_envelope.get("repetition"), "raw repetition")}.json',
                        raw_envelope,
                    )
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
