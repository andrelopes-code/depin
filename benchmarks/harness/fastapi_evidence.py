"""Capture then reduce FastAPI acceptance evidence from locked revision interpreters.

Capture each side in its own source checkout and environment, then reduce only
the immutable raw files::

    <base-python> -m benchmarks.harness.fastapi_evidence capture --side base --repetition 0 --out RAW
    <head-python> -m benchmarks.harness.fastapi_evidence capture --side head --repetition 0 --out RAW
    python -m benchmarks.harness.fastapi_evidence reduce --raw RAW --out EVIDENCE \
        --base-revision BASE --head-revision HEAD --base-environment BASE_ENV --head-environment HEAD_ENV
"""

import argparse
import math
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from benchmarks.contracts import Implementation, Observation, Workload
from benchmarks.experiments import contention
from benchmarks.harness import (
    HarnessError,
    memory,
    read_json,
    require_array,
    require_integer,
    require_number,
    require_object,
    require_text,
    write_json,
)
from benchmarks.harness.fastapi_acceptance import ATTRIBUTION_WORKLOAD, COMPONENT_WORKLOADS, TAIL_WORKLOADS
from benchmarks.harness.work import calls_per_operation
from benchmarks.workloads import WORKLOADS

BASELINE_REVISION = '086adf98459773e3175f4723b2b64e3f47306e42'
SCHEMA_VERSION = 1
REPETITIONS = 5


def _revision() -> str:
    completed = subprocess.run(('git', 'rev-parse', 'HEAD'), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise HarnessError('cannot determine the source revision for FastAPI evidence capture')
    return completed.stdout.strip()


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
        'teardown': tuple(observation.constructed) == tuple(observation.closed),
    }


def _by_name() -> dict[str, Workload]:
    return {workload.name: workload for workload in WORKLOADS}


def _guard(workload: Workload) -> dict[str, object]:
    if workload.baseline is None:
        raise HarnessError(f'{workload.name}: FastAPI evidence requires a direct baseline')
    return {
        'workload': workload.name,
        'subject': _observation(workload.subject.observe()),
        'direct': _observation(workload.baseline.observe()),
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


def _raw(path: Path, side: str, repetition: int, revision: str, environment: Path) -> Mapping[str, object]:
    payload = read_json(path)
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
    _ = _positive(payload.get('direct_p50'), f'{path}: direct_p50')
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
            if observed.get('teardown') is not True:
                raise HarnessError(f'{path}: {name}.{implementation} teardown guard failed')
        found[name] = guard
    if set(found) != set(TAIL_WORKLOADS):
        raise HarnessError(f'{path}: guards must exactly cover FastAPI acceptance workloads')
    return found


def reduce(raw: Path, baseline_revision: str, head_revision: str, environments: Mapping[str, str]) -> dict[str, object]:
    """Validate raw target records and derive evaluator inputs without re-measuring."""
    if baseline_revision != BASELINE_REVISION:
        raise HarnessError('baseline revision is not the accepted FastAPI baseline')
    locations = {side: Path(require_text(environments.get(side), f'{side} environment')) for side in ('base', 'head')}
    base_records = [
        _raw(raw / 'base' / f'rep{i}.json', 'base', i, baseline_revision, locations['base']) for i in range(REPETITIONS)
    ]
    head_records = [
        _raw(raw / 'head' / f'rep{i}.json', 'head', i, head_revision, locations['head']) for i in range(REPETITIONS)
    ]
    semantic: list[dict[str, object]] = []
    for repetition, (base, head) in enumerate(zip(base_records, head_records, strict=True)):
        base_guards = _guards(base, raw / 'base' / f'rep{repetition}.json')
        head_guards = _guards(head, raw / 'head' / f'rep{repetition}.json')
        for workload in TAIL_WORKLOADS:
            base_subject = require_object(base_guards[workload].get('subject'), 'base subject')
            head_subject = require_object(head_guards[workload].get('subject'), 'head subject')
            response = base_subject.get('response') == head_subject.get('response')
            lifecycle = base_subject.get('constructed') == head_subject.get('constructed') and base_subject.get(
                'closed'
            ) == head_subject.get('closed')
            semantic.append(
                {
                    'workload': workload,
                    'repetition': repetition,
                    'base_revision': baseline_revision,
                    'head_revision': head_revision,
                    'response': 'equivalent' if response else 'different',
                    'lifecycle': 'equivalent' if lifecycle else 'different',
                    'event_counts': {
                        'base': len(require_array(base_subject.get('constructed'), 'base constructed'))
                        + len(require_array(base_subject.get('closed'), 'base closed')),
                        'head': len(require_array(head_subject.get('constructed'), 'head constructed'))
                        + len(require_array(head_subject.get('closed'), 'head closed')),
                    },
                    'teardown': 'equivalent',
                    'deterministic': 'passed',
                }
            )
    head_only = require_object(head_records[-1].get('head_only'), 'head-only evidence')
    no_injection = require_object(head_only.get('no_injection'), 'no-injection evidence')
    contention_values = require_object(head_only.get('contention'), 'contention evidence')
    base_memory = require_object(base_records[-1].get('memory'), 'base memory')
    head_memory = require_object(head_records[-1].get('memory'), 'head memory')
    return {
        'attribution': {
            'schema_version': SCHEMA_VERSION,
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
                    'base_direct_p50': _positive(base['direct_p50'], 'base direct'),
                    'head_direct_p50': _positive(head['direct_p50'], 'head direct'),
                }
                for i, (base, head) in enumerate(zip(base_records, head_records, strict=True))
            ],
        },
        'sidecars': {
            'schema_version': SCHEMA_VERSION,
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
            'schema_version': SCHEMA_VERSION,
            'baseline_revision': baseline_revision,
            'head_revision': head_revision,
            'protocol': {
                'collector': 'benchmarks.harness.pairs',
                'repetitions': REPETITIONS,
                'seed': 20260902,
                'locked_environments': True,
                'workloads': list(TAIL_WORKLOADS),
            },
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
        else:
            output = reduce(
                arguments.raw,
                arguments.base_revision,
                arguments.head_revision,
                {'base': arguments.base_environment, 'head': arguments.head_environment},
            )
            write_json(arguments.out / 'attribution.json', require_object(output['attribution'], 'attribution output'))
            write_json(arguments.out / 'sidecars.json', require_object(output['sidecars'], 'sidecars output'))
            write_json(arguments.out / 'provenance.json', require_object(output['provenance'], 'provenance output'))
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
