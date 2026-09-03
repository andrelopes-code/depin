"""Calibrate comparison noise and evaluate per-workload leadership evidence."""

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from benchmarks.harness import (
    CALIBRATION_SCHEMA_VERSION,
    COMPARISON_SCHEMA_VERSION,
    HarnessError,
    gate,
    is_array,
    is_object,
    quantile,
    read_json,
    require_array,
    require_integer,
    require_number,
    require_object,
    require_schema_version,
    require_text,
    stats,
    write_json,
)
from benchmarks.harness import budgets as budget_module

MINIMUM_REPETITIONS = 5
MAXIMUM_ALLOWANCE = 0.05
CALIBRATION_INCREMENT = 0.001
EXIT_PASS = 0
EXIT_FAILURE = 1
EXIT_MALFORMED = 2
EXIT_UNSTABLE = 3
CALIBRATION_PROVENANCE_VERSION = 1
COMPARISON_PROTOCOL = 'counterbalanced-comparison-v1'


class Status(Enum):
    LEADER = 'leader'
    SHARED_LEADER = 'shared-leader'
    LOSS = 'loss'
    ABSOLUTE_FAILURE = 'absolute-failure'
    REGRESSION = 'regression'
    UNSTABLE = 'unstable'
    NO_EQUIVALENT_COMPETITOR = 'no-equivalent-competitor'


@dataclass(frozen=True, slots=True)
class CompetitorVerdict:
    label: str
    paired: stats.Paired
    passed: bool


@dataclass(frozen=True, slots=True)
class WorkloadVerdict:
    workload: str
    status: Status
    competitor: CompetitorVerdict | None
    competitive_passed: bool | None
    absolute_overhead: float | None
    absolute_ceiling: float | None
    absolute_passed: bool | None
    secondary_verdicts: tuple[gate.Verdict, ...]

    @property
    def secondary_passed(self) -> bool:
        return all(verdict.outcome is budget_module.Outcome.PASS for verdict in self.secondary_verdicts)


def _boolean(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise HarnessError(f'{where}: expected a boolean, found {value!r}')
    return value


def _finite_positive(value: object, where: str) -> float:
    number = require_number(value, where)
    if not math.isfinite(number) or number <= 0.0:
        raise HarnessError(f'{where}: expected a finite positive duration, found {number!r}')
    return number


def seed(dataset: dict[str, object]) -> int:
    value = require_number(dataset.get('seed'), 'dataset.seed')
    if not value.is_integer():
        raise HarnessError(f'dataset.seed: expected an integer, found {value!r}')
    return int(value)


def _accepted(dataset: dict[str, object]) -> None:
    if dataset.get('accepted') is not True:
        raise HarnessError(
            'dataset.accepted must be true; --allow-dirty is diagnostic evidence and requires clean collection'
        )


def _schema(dataset: dict[str, object]) -> None:
    require_schema_version(dataset, 'dataset', COMPARISON_SCHEMA_VERSION)


def _optional_text(value: object, where: str) -> str | None:
    if value is None:
        return None
    return require_text(value, where)


def _digest(value: object, where: str) -> str:
    digest = require_text(value, where)
    if len(digest) != 64 or any(character not in '0123456789abcdef' for character in digest):
        raise HarnessError(f'{where}: expected a lower-case SHA-256 digest')
    return digest


def protocol_material(dataset: dict[str, object]) -> dict[str, object]:
    _schema(dataset)
    protocol = require_text(dataset.get('protocol'), 'dataset.protocol')
    if protocol != COMPARISON_PROTOCOL:
        raise HarnessError(f'dataset.protocol: unsupported protocol {protocol!r}')
    targets = require_object(dataset.get('targets'), 'dataset.targets')
    pins = require_object(dataset.get('pins'), 'dataset.pins')
    for distribution, version in pins.items():
        _ = require_text(distribution, 'dataset.pins key')
        _ = require_text(version, f'dataset.pins.{distribution}')
    environment = require_object(dataset.get('environment'), 'dataset.environment')
    interpreter = require_object(environment.get('interpreter'), 'dataset.environment.interpreter')
    host = require_object(environment.get('host'), 'dataset.environment.host')
    budget_contract = require_object(
        require_object(dataset.get('deterministic'), 'dataset.deterministic').get('budget_contract'),
        'dataset.deterministic.budget_contract',
    )
    return {
        'budget_contract_sha256': _digest(
            budget_contract.get('sha256'), 'dataset.deterministic.budget_contract.sha256'
        ),
        'environment': {
            'host': {
                'available_processors': require_integer(
                    host.get('available_processors'), 'dataset.environment.host.available_processors'
                ),
                'cpu_model': _optional_text(host.get('cpu_model'), 'dataset.environment.host.cpu_model'),
                'machine': require_text(host.get('machine'), 'dataset.environment.host.machine'),
                'processor': require_text(host.get('processor'), 'dataset.environment.host.processor'),
                'system': require_text(host.get('system'), 'dataset.environment.host.system'),
            },
            'interpreter': {
                'free_threading': _boolean(
                    interpreter.get('free_threading'), 'dataset.environment.interpreter.free_threading'
                ),
                'hash_randomization': _boolean(
                    interpreter.get('hash_randomization'), 'dataset.environment.interpreter.hash_randomization'
                ),
                'implementation': require_text(
                    interpreter.get('implementation'), 'dataset.environment.interpreter.implementation'
                ),
                'version': require_text(interpreter.get('version'), 'dataset.environment.interpreter.version'),
            },
            'python_hash_seed': require_text(
                environment.get('python_hash_seed'), 'dataset.environment.python_hash_seed'
            ),
        },
        'minimum_repetitions': MINIMUM_REPETITIONS,
        'pins': pins,
        'protocol': protocol,
        'schema_version': COMPARISON_SCHEMA_VERSION,
        'targets': targets,
    }


def protocol_fingerprint(dataset: dict[str, object]) -> str:
    """Return the stable comparison protocol identity, excluding measured source revisions."""
    encoded = json.dumps(protocol_material(dataset), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _protocol_digest(protocol: dict[str, object]) -> str:
    encoded = json.dumps(protocol, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _protocol_difference(expected: object, actual: object, where: str = '') -> str | None:
    if is_object(expected) and is_object(actual):
        for key in sorted(set(expected) | set(actual)):
            nested = f'{where}.{key}' if where else key
            if key not in expected or key not in actual:
                return nested
            difference = _protocol_difference(expected[key], actual[key], nested)
            if difference is not None:
                return difference
        return None
    if is_array(expected) and is_array(actual):
        if len(expected) != len(actual):
            return where
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            difference = _protocol_difference(left, right, f'{where}[{index}]')
            if difference is not None:
                return difference
        return None
    return None if expected == actual else where


def _calibration_provenance(calibration: dict[str, object]) -> dict[str, object]:
    require_schema_version(calibration, 'calibration', CALIBRATION_SCHEMA_VERSION)
    provenance = require_object(calibration.get('provenance'), 'calibration.provenance')
    version = require_integer(provenance.get('version'), 'calibration.provenance.version')
    if version != CALIBRATION_PROVENANCE_VERSION:
        raise HarnessError(
            f'calibration.provenance.version: unsupported version {version}; expected {CALIBRATION_PROVENANCE_VERSION}'
        )
    _ = _digest(provenance.get('null_dataset_sha256'), 'calibration.provenance.null_dataset_sha256')
    fingerprint = _digest(provenance.get('protocol_fingerprint'), 'calibration.provenance.protocol_fingerprint')
    protocol = require_object(provenance.get('protocol'), 'calibration.provenance.protocol')
    if _protocol_digest(protocol) != fingerprint:
        raise HarnessError('calibration.provenance.protocol does not match its protocol_fingerprint')
    _ = require_text(provenance.get('source_revision'), 'calibration.provenance.source_revision')
    _ = require_text(provenance.get('harness_revision'), 'calibration.provenance.harness_revision')
    return provenance


def workloads(dataset: dict[str, object]) -> dict[str, dict[str, object]]:
    targets = require_object(dataset.get('targets'), 'dataset.targets')
    if not targets:
        raise HarnessError('dataset.targets: no workload descriptions; recollect the comparison dataset')
    return {name: require_object(value, f'dataset.targets.{name}') for name, value in targets.items()}


def repetitions(dataset: dict[str, object]) -> list[dict[str, object]]:
    repetitions = require_array(dataset.get('repetitions'), 'dataset.repetitions')
    if len(repetitions) < MINIMUM_REPETITIONS:
        raise HarnessError(
            f'dataset.repetitions: {len(repetitions)} repetitions; at least {MINIMUM_REPETITIONS} are needed'
        )
    return [require_object(value, f'dataset.repetitions[{index}]') for index, value in enumerate(repetitions)]


def _sample(repetition: dict[str, object], workload: str, label: str, where: str) -> dict[str, object] | None:
    samples = require_object(repetition.get('samples'), f'{where}.samples')
    return (
        None
        if (sample := samples.get(f'test_comparison[{workload}-{label}]')) is None
        else require_object(sample, where)
    )


def _qualified(sample: dict[str, object], where: str) -> float | None:
    if 'qualified' in sample and not _boolean(sample['qualified'], f'{where}.qualified'):
        return None
    median = _finite_positive(sample.get('median'), f'{where}.median')
    mean = _finite_positive(sample.get('mean'), f'{where}.mean')
    rounds = _finite_positive(sample.get('rounds'), f'{where}.rounds')
    return median if rounds >= 1000.0 or mean * rounds >= 0.5 else None


def paired_medians(
    repetitions: Sequence[dict[str, object]], workload: str, base: str, head: str
) -> tuple[list[float], list[float]]:
    before: list[float] = []
    after: list[float] = []
    for index, repetition in enumerate(repetitions):
        where = f'dataset.repetitions[{index}]'
        left, right = _sample(repetition, workload, base, where), _sample(repetition, workload, head, where)
        if left is None or right is None:
            continue
        left_median, right_median = _qualified(left, f'{where}.{base}'), _qualified(right, f'{where}.{head}')
        if left_median is None or right_median is None:
            continue
        before.append(left_median)
        after.append(right_median)
    return before, after


def calibration_entry(value: object, workload: str) -> tuple[float | None, bool]:
    fields = require_object(value, f'calibration.workloads.{workload}')
    eligible = _boolean(fields.get('eligible'), f'calibration.workloads.{workload}.eligible')
    p99_value = fields.get('p99')
    allowance_value = fields.get('allowance')
    if p99_value is None or allowance_value is None:
        if p99_value is None and allowance_value is None and not eligible:
            return None, False
        raise HarnessError(f'calibration.workloads.{workload}: p99 and allowance must both be numeric or both be null')
    p99 = require_number(p99_value, f'calibration.workloads.{workload}.p99')
    if not math.isfinite(p99) or p99 < 0.0:
        raise HarnessError(f'calibration.workloads.{workload}.p99: expected a finite non-negative number')
    allowance = require_number(allowance_value, f'calibration.workloads.{workload}.allowance')
    if not math.isfinite(allowance) or allowance < 0.0:
        raise HarnessError(f'calibration.workloads.{workload}.allowance: expected a finite non-negative number')
    expected = math.ceil(p99 / CALIBRATION_INCREMENT) * CALIBRATION_INCREMENT
    if not math.isclose(allowance, expected, rel_tol=0.0, abs_tol=1e-12):
        raise HarnessError(f'calibration.workloads.{workload}: allowance must be p99 rounded up to 0.001')
    if eligible != (allowance <= MAXIMUM_ALLOWANCE):
        raise HarnessError(f'calibration.workloads.{workload}: eligible must match the 5% allowance boundary')
    return allowance, eligible


def calibrate(dataset: dict[str, object]) -> dict[str, object]:
    """Derive deterministic per-workload allowances from a null comparison dataset."""
    _schema(dataset)
    _accepted(dataset)
    random_seed = seed(dataset)
    collected = repetitions(dataset)
    calibrated: dict[str, object] = {}
    for workload in sorted(workloads(dataset)):
        direct, depin = paired_medians(collected, workload, 'direct', 'depin')
        if len(direct) < MINIMUM_REPETITIONS:
            calibrated[workload] = {'allowance': None, 'eligible': False, 'p99': None}
            continue
        distribution = stats.bootstrap_paired_log_ratios(direct, depin, seed=random_seed)
        p99 = quantile(sorted(abs(math.expm1(value)) for value in distribution), 0.99)
        allowance = math.ceil(p99 / CALIBRATION_INCREMENT) * CALIBRATION_INCREMENT
        calibrated[workload] = {'allowance': allowance, 'eligible': allowance <= MAXIMUM_ALLOWANCE, 'p99': p99}
    canonical = json.dumps(dataset, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return {
        'provenance': {
            'harness_revision': require_text(dataset.get('harness_revision'), 'dataset.harness_revision'),
            'null_dataset_sha256': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
            'protocol': protocol_material(dataset),
            'protocol_fingerprint': protocol_fingerprint(dataset),
            'source_revision': require_text(dataset.get('source_revision'), 'dataset.source_revision'),
            'version': CALIBRATION_PROVENANCE_VERSION,
        },
        'schema_version': CALIBRATION_SCHEMA_VERSION,
        'workloads': calibrated,
    }


def _candidates(description: dict[str, object], workload: str) -> list[tuple[str, str]]:
    encoded = require_array(description.get('candidates'), f'dataset.targets.{workload}.candidates')
    candidates: list[tuple[str, str]] = []
    labels: set[str] = set()
    for index, value in enumerate(encoded):
        fields = require_object(value, f'dataset.targets.{workload}.candidates[{index}]')
        label = require_text(fields.get('label'), f'dataset.targets.{workload}.candidates[{index}].label')
        classification = require_text(
            fields.get('classification'), f'dataset.targets.{workload}.candidates[{index}].classification'
        )
        if classification not in {'equivalent', 'partial', 'incomparable'}:
            raise HarnessError(f'{workload}: candidate {label} has invalid classification {classification!r}')
        if label in {'direct', 'depin'}:
            raise HarnessError(f'{workload}: candidate label {label!r} is reserved')
        if label in labels:
            raise HarnessError(f'{workload}: candidate label {label!r} is duplicated')
        labels.add(label)
        candidates.append((label, classification))
    return candidates


def _secondary(
    description: dict[str, object], dataset: dict[str, object], workload: str, budget_file: Path
) -> tuple[gate.Verdict, ...]:
    metrics = require_array(description.get('secondary_metrics', []), f'dataset.targets.{workload}.secondary_metrics')
    if not metrics:
        return ()
    declared: list[str] = []
    for index, metric in enumerate(metrics):
        declared.append(require_text(metric, f'dataset.targets.{workload}.secondary_metrics[{index}]'))
    encoded = dataset.get('deterministic')
    if encoded is None:
        raise HarnessError(f'{workload}: missing secondary deterministic evidence; recollect the comparison dataset')
    evidence = require_object(encoded, 'dataset.deterministic')
    contract = require_object(evidence.get('budget_contract'), 'dataset.deterministic.budget_contract')
    expected_digest = require_text(contract.get('sha256'), 'dataset.deterministic.budget_contract.sha256')
    if len(expected_digest) != 64 or any(character not in '0123456789abcdef' for character in expected_digest):
        raise HarnessError('dataset.deterministic.budget_contract.sha256: expected a lower-case SHA-256 digest')
    _ = require_text(contract.get('path'), 'dataset.deterministic.budget_contract.path')
    try:
        actual_digest = hashlib.sha256(budget_file.read_bytes()).hexdigest()
    except OSError as error:
        raise HarnessError(f'{budget_file}: cannot read deterministic budget contract ({error})') from error
    if actual_digest != expected_digest:
        raise HarnessError(f'{workload}: deterministic budget contract digest differs from --budgets')
    if 'base' not in evidence or 'head' not in evidence:
        raise HarnessError(f'{workload}: missing secondary deterministic evidence; recollect the comparison dataset')
    readings: dict[str, dict[str, object]] = {}
    for side in ('base', 'head'):
        side_evidence = require_object(evidence.get(side), f'dataset.deterministic.{side}')
        source_revision = require_text(
            side_evidence.get('source_revision'), f'dataset.deterministic.{side}.source_revision'
        )
        if side == 'head' and source_revision != require_text(
            dataset.get('source_revision'), 'dataset.source_revision'
        ):
            raise HarnessError('dataset.deterministic.head.source_revision must match dataset.source_revision')
        readings[side] = require_object(side_evidence.get('readings'), f'dataset.deterministic.{side}.readings')
    return gate.deterministic_verdicts(
        workload, declared, readings['base'], readings['head'], budget_module.load(budget_file)
    )


def _absolute(
    description: dict[str, object], workload: str, depin: Sequence[float], direct: Sequence[float]
) -> tuple[float | None, float | None, bool | None]:
    target = description.get('target')
    if target is None:
        return None, None, None
    fields = require_object(target, f'dataset.targets.{workload}.target')
    fixed = _finite_positive(fields.get('fixed_seconds'), f'dataset.targets.{workload}.target.fixed_seconds')
    fraction_value = fields.get('fraction_of_direct')
    fraction = (
        None
        if fraction_value is None
        else require_number(fraction_value, f'dataset.targets.{workload}.target.fraction_of_direct')
    )
    if fraction is not None and not 0.0 < fraction <= 1.0:
        raise HarnessError(f'dataset.targets.{workload}.target.fraction_of_direct: expected a fraction within (0, 1]')
    overhead = statistics.median(after - before for before, after in zip(direct, depin, strict=True))
    ceiling = fixed if fraction is None else min(fixed, statistics.median(direct) * fraction)
    return overhead, ceiling, overhead <= ceiling


def evaluate(
    dataset: dict[str, object], calibration: dict[str, object], budget_file: Path
) -> tuple[WorkloadVerdict, ...]:
    """Evaluate all workloads from decoded comparison and calibration JSON."""
    _schema(dataset)
    _accepted(dataset)
    provenance = _calibration_provenance(calibration)
    expected_protocol = protocol_material(dataset)
    recorded_protocol = require_object(provenance['protocol'], 'calibration.provenance.protocol')
    difference = _protocol_difference(expected_protocol, recorded_protocol)
    if difference is not None:
        raise HarnessError(f'calibration.provenance.protocol.{difference} differs from the comparison dataset')
    if provenance['protocol_fingerprint'] != _protocol_digest(expected_protocol):
        raise HarnessError('calibration.provenance.protocol_fingerprint differs from the comparison dataset')
    random_seed = seed(dataset)
    collected = repetitions(dataset)
    calibration_entries = require_object(calibration.get('workloads'), 'calibration.workloads')
    verdicts: list[WorkloadVerdict] = []
    for workload, description in sorted(workloads(dataset).items()):
        calibration_value = calibration_entries.get(workload)
        if calibration_value is None:
            raise HarnessError(f'{workload}: calibration is missing; run calibrate against a null collection')
        allowance, eligible = calibration_entry(calibration_value, workload)
        if eligible and allowance is None:
            raise HarnessError(f'{workload}: eligible calibration has no allowance; recalibrate the null evidence')
        direct, depin = paired_medians(collected, workload, 'direct', 'depin')
        secondary = _secondary(description, dataset, workload, budget_file)
        overhead, ceiling, absolute = (
            _absolute(description, workload, depin, direct)
            if len(direct) >= MINIMUM_REPETITIONS
            else (None, None, None)
        )
        equivalents = [(label, kind) for label, kind in _candidates(description, workload) if kind == 'equivalent']
        competitor: CompetitorVerdict | None = None
        competitive: bool | None = None
        if eligible and allowance is not None and len(depin) >= MINIMUM_REPETITIONS and equivalents:
            measured: list[tuple[float, str, stats.Paired]] = []
            for label, _ in equivalents:
                candidate, subject = paired_medians(collected, workload, label, 'depin')
                if len(candidate) < MINIMUM_REPETITIONS or len(subject) < MINIMUM_REPETITIONS:
                    continue
                paired = stats.paired_ratio(candidate, subject, seed=random_seed)
                measured.append((statistics.median(candidate), label, paired))
            if len(measured) != len(equivalents):
                status = Status.UNSTABLE
            else:
                _, label, paired = min(measured)
                competitive = paired.ratio <= 0.0 and paired.high <= allowance
                competitor = CompetitorVerdict(label=label, paired=paired, passed=competitive)
                status = Status.LEADER if competitive and paired.high < 0.0 else Status.SHARED_LEADER
        elif not eligible or len(depin) < MINIMUM_REPETITIONS or len(direct) < MINIMUM_REPETITIONS:
            status = Status.UNSTABLE
        elif not equivalents:
            status = Status.NO_EQUIVALENT_COMPETITOR
        else:
            status = Status.UNSTABLE
        if status not in {Status.UNSTABLE, Status.NO_EQUIVALENT_COMPETITOR}:
            if competitive is False:
                status = Status.LOSS
            elif absolute is False:
                status = Status.ABSOLUTE_FAILURE
            elif not all(verdict.outcome is budget_module.Outcome.PASS for verdict in secondary):
                status = Status.REGRESSION
        verdicts.append(
            WorkloadVerdict(workload, status, competitor, competitive, overhead, ceiling, absolute, secondary)
        )
    return tuple(verdicts)


def _path(value: str) -> Path:
    candidate = Path(value)
    return candidate / 'comparison.json' if candidate.is_dir() else candidate


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f'.{path.name}.tmp')
    try:
        write_json(temporary, payload)
        temporary.replace(path)
    except OSError as error:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise HarnessError(f'{path}: cannot atomically write calibration ({error})') from error


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='python -m benchmarks.harness.leadership')
    commands = parser.add_subparsers(dest='command', required=True)
    calibration = commands.add_parser('calibrate')
    calibration.add_argument('dataset')
    calibration.add_argument('--out', required=True)
    evaluation = commands.add_parser('evaluate')
    evaluation.add_argument('dataset')
    evaluation.add_argument('--calibration', required=True)
    evaluation.add_argument('--budgets', required=True)
    return parser.parse_args(argv)


def _exit(verdicts: Sequence[WorkloadVerdict]) -> int:
    statuses = {verdict.status for verdict in verdicts}
    if Status.UNSTABLE in statuses:
        return EXIT_UNSTABLE
    if statuses - {Status.LEADER, Status.SHARED_LEADER, Status.NO_EQUIVALENT_COMPETITOR}:
        return EXIT_FAILURE
    return EXIT_PASS


def main(argv: Sequence[str] | None = None) -> int:
    """Run the calibration or evaluator command line interface."""
    try:
        arguments = _arguments(argv)
        if arguments.command == 'calibrate':
            dataset = read_json(_path(require_text(arguments.dataset, 'DATASET')))
            _write_atomic(Path(require_text(arguments.out, '--out')), calibrate(dataset))
            return EXIT_PASS
        dataset = read_json(_path(require_text(arguments.dataset, 'DATASET')))
        calibration = read_json(Path(require_text(arguments.calibration, '--calibration')))
        verdicts = evaluate(dataset, calibration, Path(require_text(arguments.budgets, '--budgets')))
        for verdict in verdicts:
            _ = sys.stdout.write(f'{verdict.status.value:<25} {verdict.workload}\n')
        return _exit(verdicts)
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return EXIT_MALFORMED


if __name__ == '__main__':
    raise SystemExit(main())
