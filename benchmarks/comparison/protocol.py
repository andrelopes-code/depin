"""Calibrate comparison noise and evaluate per-workload leadership evidence."""

import hashlib
import io
import json
import math
import os
import stat
import subprocess
import tarfile
from pathlib import Path

from benchmarks.harness import (
    CALIBRATION_SCHEMA_VERSION,
    COMPARISON_SCHEMA_VERSION,
    HarnessError,
    is_array,
    is_object,
    read_json,
    require_array,
    require_integer,
    require_number,
    require_object,
    require_schema_version,
    require_text,
)

MINIMUM_REPETITIONS = 5
CALIBRATION_PROVENANCE_VERSION = 1
COMPARISON_PROTOCOL = 'counterbalanced-comparison-v1'


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


def baseline_preflight(directory: Path, revision: str) -> str:
    if not directory.is_dir():
        raise HarnessError(f'{directory}: baseline directory does not exist; materialize the requested revision')
    if (
        revision != revision.strip()
        or len(revision) != 40
        or any(character not in '0123456789abcdef' for character in revision)
    ):
        raise HarnessError(
            f'baseline revision {revision!r} must be an unpadded 40-character lower-case hexadecimal SHA'
        )
    marker = directory / '.depin-baseline-revision'
    try:
        contents = marker.read_text(encoding='utf-8')
    except OSError as error:
        raise HarnessError(f'{marker}: baseline marker is missing or unreadable ({error})') from error
    if contents != f'{revision}\n':
        raise HarnessError(f'{marker}: baseline marker must exactly match the claimed baseline revision')
    validate_baseline_archive(directory, revision)
    return revision


def archive_entries(revision: str) -> dict[str, tuple[str, int, bytes]]:
    completed = subprocess.run(('git', 'archive', '--format=tar', revision), capture_output=True, check=False)
    if completed.returncode != 0:
        message = completed.stderr.decode('utf-8', errors='replace')
        raise HarnessError(f'baseline archive {revision}: cannot read the Git archive ({message})')
    entries: dict[str, tuple[str, int, bytes]] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode='r:') as archive:
            for member in archive:
                name = member.name.rstrip('/')
                if not name:
                    continue
                if member.isdir():
                    entries[name] = ('directory', member.mode, b'')
                elif member.isfile():
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise HarnessError(f'baseline archive {revision}: cannot read {name}')
                    entries[name] = ('file', member.mode, stream.read())
                elif member.issym():
                    entries[name] = ('symlink', member.mode, member.linkname.encode('utf-8'))
                else:
                    raise HarnessError(f'baseline archive {revision}: unsupported entry {name!r}')
    except tarfile.TarError as error:
        raise HarnessError(f'baseline archive {revision}: is not a readable tar stream ({error})') from error
    return entries


def _directory_entries(directory: Path) -> dict[str, tuple[str, int, bytes]]:
    entries: dict[str, tuple[str, int, bytes]] = {}
    pending = [directory]
    while pending:
        current = pending.pop()
        for entry in current.iterdir():
            relative = entry.relative_to(directory).as_posix()
            if relative == '.depin-baseline-revision':
                continue
            try:
                details = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise HarnessError(f'baseline archive directory: cannot inspect {relative} ({error})') from error
            mode = stat.S_IMODE(details.st_mode)
            if stat.S_ISDIR(details.st_mode):
                entries[relative] = ('directory', mode, b'')
                pending.append(entry)
            elif stat.S_ISREG(details.st_mode):
                try:
                    contents = entry.read_bytes()
                except OSError as error:
                    raise HarnessError(f'baseline archive directory: cannot read {relative} ({error})') from error
                entries[relative] = ('file', mode, contents)
            elif stat.S_ISLNK(details.st_mode):
                try:
                    target = os.readlink(entry).encode('utf-8')
                except OSError as error:
                    raise HarnessError(
                        f'baseline archive directory: cannot read symlink {relative} ({error})'
                    ) from error
                entries[relative] = ('symlink', mode, target)
            else:
                raise HarnessError(f'baseline archive directory: unsupported entry {relative!r}')
    return entries


def validate_baseline_archive(directory: Path, revision: str) -> None:
    expected = archive_entries(revision)
    actual = _directory_entries(directory)
    if actual == expected:
        return
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    details = [
        *(f'missing {name}' for name in missing),
        *(f'extra {name}' for name in extra),
        *(f'different {name}' for name in changed),
    ]
    raise HarnessError(f'baseline archive {revision} does not match {directory}: {"; ".join(details)}')


def _case_id(name: str, *, repetition: int, order: str) -> str:
    marker = 'test_comparison['
    start = name.find(marker)
    if start < 0 or not name.endswith(']'):
        raise HarnessError(
            f'repetition {repetition} ({order}) has benchmark {name!r}, not a test_comparison case; '
            'run the comparison shell without changing its IDs'
        )
    return name[start + len(marker) : -1]


def _finite(value: object, *, where: str, positive: bool = False) -> None:
    number = require_number(value, where)
    if not math.isfinite(number) or number < 0.0 or (positive and number <= 0.0):
        expectation = 'finite and positive' if positive else 'finite and non-negative'
        raise HarnessError(f'{where}: {number!r} must be {expectation}; repair the pytest-benchmark report')


def _validate_raw(report: Path, *, repetition: int, order: str, expected: set[str]) -> None:
    payload = read_json(report)
    entries = require_array(payload.get('benchmarks'), f'{report}.benchmarks')
    names: set[str] = set()
    for index, entry in enumerate(entries):
        where = f'{report}.benchmarks[{index}]'
        fields = require_object(entry, where)
        name = require_text(fields.get('name'), f'{where}.name')
        case = _case_id(name, repetition=repetition, order=order)
        if case in names:
            raise HarnessError(
                f'repetition {repetition} ({order}) has duplicate benchmark ID {case!r}; repair the report'
            )
        names.add(case)
        stats = require_object(fields.get('stats'), f'{where}.stats')
        rounds = require_number(stats.get('rounds'), f'{where}.stats.rounds')
        if not math.isfinite(rounds) or rounds <= 0.0 or not rounds.is_integer():
            raise HarnessError(
                f'{where}.stats.rounds: {rounds!r} must be a finite positive integer; '
                'repair the pytest-benchmark report'
            )
        for field in ('min', 'median', 'mean'):
            _finite(stats.get(field), where=f'{where}.stats.{field}', positive=True)
        for field in ('stddev', 'iqr', 'max', 'total', 'duration'):
            if field in stats:
                _finite(stats[field], where=f'{where}.stats.{field}')
        if 'data' in stats:
            rounds_data = require_array(stats['data'], f'{where}.stats.data')
            if not rounds_data:
                raise HarnessError(f'{where}.stats.data is empty; repair the pytest-benchmark report')
            for round_index, round_value in enumerate(rounds_data):
                _finite(round_value, where=f'{where}.stats.data[{round_index}]', positive=True)
        if 'duration' in fields:
            _finite(fields['duration'], where=f'{where}.duration')
    missing = sorted(expected - names)
    unexpected = sorted(names - expected)
    if missing or unexpected:
        detail: list[str] = []
        if missing:
            detail.append(f'missing {missing}')
        if unexpected:
            detail.append(f'unexpected {unexpected}')
        raise HarnessError(
            f'repetition {repetition} ({order}) benchmark IDs differ from the expected matrix: {"; ".join(detail)}. '
            'Run the unmodified comparison shell and inspect its parametrization.'
        )
