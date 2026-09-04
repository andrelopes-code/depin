"""Collect counterbalanced competitor benchmark samples."""

import argparse
import hashlib
import math
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

from benchmarks.comparison.protocol import COMPARISON_PROTOCOL, _validate_raw, baseline_preflight
from benchmarks.harness import (
    COMPARISON_SCHEMA_VERSION,
    HarnessError,
    memory,
    read_json,
    reduce,
    require_array,
    require_integer,
    require_text,
    write_json,
)
from benchmarks.harness import environment as environment_module
from benchmarks.harness.pairs import DEFAULT_SEED, DETERMINISTIC_COMMAND

DEFAULT_REPETITIONS = 5
REPORT_PLACEHOLDER = '{report}'
COMPARISON_FILE = 'comparison.json'
COMMAND = ('-m', 'pytest', 'benchmarks/test_comparison.py', '--benchmark-only', '-q', '--benchmark-json={report}')
DEFAULT_TIMEOUT_SECONDS = 5400


def _revision(directory: Path | None = None) -> str:
    completed = subprocess.run(('git', 'rev-parse', 'HEAD'), cwd=directory, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise HarnessError('cannot determine the source revision; run collection from a Git checkout')
    return completed.stdout.strip()


def _clean_tree(directory: Path | None = None) -> bool:
    completed = subprocess.run(
        ('git', 'status', '--porcelain'), cwd=directory, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise HarnessError('cannot inspect the Git worktree; run collection from a Git checkout')
    return not completed.stdout


def _expected_pins() -> dict[str, str]:
    from benchmarks.comparison.adapters import ADAPTERS

    expected = {'pydepin': '0.17.1'}
    for adapter in ADAPTERS:
        expected[adapter.competitor.distribution] = adapter.competitor.version
    return dict(sorted(expected.items()))


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for distribution in _expected_pins():
        try:
            pins[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            pins[distribution] = 'not installed'
    return pins


def descriptions() -> dict[str, object]:
    from benchmarks.comparison.inventory import build

    descriptions: dict[str, object] = {}
    for comparative in build():
        if comparative.target is None:
            continue
        target = {
            'fixed_seconds': comparative.target.fixed_seconds,
            'fraction_of_direct': comparative.target.fraction_of_direct,
            'justification': comparative.target.justification,
        }
        descriptions[comparative.workload.name] = {
            'target': target,
            'secondary_metrics': [metric.value for metric in comparative.secondary_metrics],
            'candidates': [
                {
                    'classification': candidate.equivalence.value,
                    'label': candidate.competitor.label,
                    'reason': candidate.reason,
                }
                for candidate in comparative.candidates
            ],
        }
    return descriptions


def expected_ids(*, null: bool = False, focus: Sequence[str] = ()) -> set[str]:
    from benchmarks.comparison.inventory import build

    expected: set[str] = set()
    selected = set(focus)
    targeted = tuple(comparative for comparative in build() if comparative.target is not None)
    available = {comparative.workload.name for comparative in targeted}
    unknown = sorted(selected - available)
    if unknown:
        raise HarnessError(f'{unknown[0]}: focused workload is not in the comparison inventory')
    for comparative in targeted:
        workload = comparative.workload
        if selected and workload.name not in selected:
            continue
        expected.add(f'{workload.name}-{workload.subject.label}')
        if workload.baseline is not None:
            expected.add(f'{workload.name}-{workload.baseline.label}')
        if not null:
            for candidate in comparative.candidates:
                if candidate.implementation is not None:
                    expected.add(f'{workload.name}-{candidate.implementation.label}')
    return expected


def _environment() -> dict[str, object]:
    return environment_module.capture()


def _preflight(*, allow_dirty: bool) -> tuple[str, dict[str, str]]:
    if not _clean_tree() and not allow_dirty:
        raise HarnessError('the Git worktree is dirty; commit or stash changes, or pass --allow-dirty for diagnosis')
    expected = _expected_pins()
    pins = _pins()
    for distribution, version in expected.items():
        if pins.get(distribution) != version:
            installed = pins.get(distribution, 'not installed')
            raise HarnessError(
                f'{distribution} {installed} is installed; {version} is required. '
                'Recreate the bench environment before collecting.'
            )
    return _revision(), pins


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ''
    return value.decode() if isinstance(value, bytes) else value


def _monotonic() -> float:
    return time.monotonic()


def _run(
    command: Sequence[str],
    report: Path,
    order: str,
    *,
    repetition: int,
    timeout_seconds: int | float,
    expected: set[str],
    null: bool = False,
    focus: Sequence[str] = (),
) -> dict[str, reduce.Aggregate]:
    argv = [sys.executable, *(part.replace(REPORT_PLACEHOLDER, str(report)) for part in command)]
    child = os.environ | {
        'DEPIN_COMPARISON_ORDER': order,
        'DEPIN_COMPARISON_FOCUS': ','.join(focus),
        'DEPIN_COMPARISON_NULL': '1' if null else '0',
        'PYTHONHASHSEED': memory.HASH_SEED,
    }
    try:
        completed = subprocess.run(
            argv, env=child, capture_output=True, text=True, check=False, timeout=timeout_seconds
        )
    except subprocess.TimeoutExpired as error:
        raise HarnessError(
            f'repetition {repetition} ({order}) timed out after {timeout_seconds} seconds: {" ".join(argv)}\n'
            f'{_timeout_text(error.stdout)}{_timeout_text(error.stderr)}'
        ) from error
    if completed.returncode != 0:
        raise HarnessError(
            f'repetition {repetition} ({order}) child exited {completed.returncode}: '
            f'{" ".join(argv)}\n{completed.stdout}{completed.stderr}'
        )
    _validate_raw(report, repetition=repetition, order=order, expected=expected)
    return reduce.load(report)


def collect_deterministic(directory: Path, report: Path, *, side: str, timeout_seconds: float) -> dict[str, object]:
    argv = [sys.executable, *(part.replace('{report}', str(report)) for part in DETERMINISTIC_COMMAND)]
    environment = os.environ | {
        'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONHASHSEED': memory.HASH_SEED,
        'PYTHONPATH': str(directory),
    }
    try:
        completed = subprocess.run(
            argv, cwd=directory, env=environment, capture_output=True, text=True, check=False, timeout=timeout_seconds
        )
    except subprocess.TimeoutExpired as error:
        raise HarnessError(
            f'{side} deterministic child timed out after {timeout_seconds} seconds: {" ".join(argv)}\n'
            f'{_timeout_text(error.stdout)}{_timeout_text(error.stderr)}'
        ) from error
    if completed.returncode != 0:
        raise HarnessError(
            f'{side} deterministic child exited {completed.returncode}: {" ".join(argv)}\n'
            f'{completed.stdout}{completed.stderr}'
        )
    return read_json(report)


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f'.{path.name}.tmp')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(temporary, payload)
        temporary.replace(path)
    except OSError as error:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError as cleanup_error:
                raise HarnessError(
                    f'{temporary}: cannot clean failed atomic write ({cleanup_error}); original failure was {error}'
                ) from cleanup_error
        raise HarnessError(f'{path}: cannot atomically write comparison evidence ({error})') from error


def collect(
    *,
    repetitions: int,
    out: Path,
    baseline_dir: Path,
    baseline_revision: str,
    budgets: Path,
    null: bool = False,
    focus: Sequence[str] = (),
    allow_dirty: bool = False,
    command: Sequence[str] = COMMAND,
    timeout_seconds: int | float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Run the protocol and write its reduced evidence dataset."""
    if repetitions < DEFAULT_REPETITIONS:
        raise HarnessError(f'{repetitions} repetitions; the protocol needs at least five')
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise HarnessError(f'{timeout_seconds} timeout seconds; the child timeout must be finite and positive')
    deadline = _monotonic() + timeout_seconds
    baseline_revision = baseline_preflight(baseline_dir, baseline_revision)
    revision, pins = _preflight(allow_dirty=allow_dirty)
    try:
        budget_digest = hashlib.sha256(budgets.read_bytes()).hexdigest()
    except OSError as error:
        raise HarnessError(f'{budgets}: cannot read deterministic budget contract ({error})') from error
    if focus:
        expected = expected_ids(null=null, focus=focus)
    elif null:
        expected = expected_ids(null=True)
    else:
        expected = expected_ids()
    repetitions_data: list[dict[str, object]] = []
    scratch_parent = out.parent
    scratch_parent.mkdir(parents=True, exist_ok=True)
    for index in range(repetitions):
        order = 'forward' if index % 2 == 0 else 'reverse'
        remaining = deadline - _monotonic()
        if remaining <= 0.0:
            raise HarnessError(
                f'repetition {index} ({order}) reached the total collection deadline before child spawn; '
                'increase --timeout-seconds or reduce the collection workload'
            )
        with tempfile.TemporaryDirectory(dir=scratch_parent, prefix=f'.{out.name}-') as scratch:
            if null and focus:
                aggregates = _run(
                    command,
                    Path(scratch) / 'report.json',
                    order,
                    repetition=index,
                    timeout_seconds=remaining,
                    expected=expected,
                    null=True,
                    focus=focus,
                )
            elif null:
                aggregates = _run(
                    command,
                    Path(scratch) / 'report.json',
                    order,
                    repetition=index,
                    timeout_seconds=remaining,
                    expected=expected,
                    null=True,
                )
            elif focus:
                aggregates = _run(
                    command,
                    Path(scratch) / 'report.json',
                    order,
                    repetition=index,
                    timeout_seconds=remaining,
                    expected=expected,
                    focus=focus,
                )
            else:
                aggregates = _run(
                    command,
                    Path(scratch) / 'report.json',
                    order,
                    repetition=index,
                    timeout_seconds=remaining,
                    expected=expected,
                )
        medians = {name: aggregate.median for name, aggregate in sorted(aggregates.items())}
        rounds = {name: aggregate.rounds for name, aggregate in sorted(aggregates.items())}
        repetitions_data.append(
            {
                'order': order,
                'medians': medians,
                'rounds': rounds,
                'samples': {name: reduce.encode(aggregate) for name, aggregate in sorted(aggregates.items())},
                'duration': sum(aggregate.measured for aggregate in aggregates.values()),
            }
        )
    deterministic: dict[str, object] = {
        'budget_contract': {'path': os.path.relpath(budgets, Path.cwd()), 'sha256': budget_digest}
    }
    for side, directory, source_revision in (
        ('base', baseline_dir, baseline_revision),
        ('head', Path.cwd(), revision),
    ):
        remaining = deadline - _monotonic()
        if remaining <= 0.0:
            raise HarnessError(f'{side} deterministic child reached the total collection deadline before spawn')
        with tempfile.TemporaryDirectory(dir=scratch_parent, prefix=f'.{out.name}-{side}-') as scratch:
            readings = collect_deterministic(
                directory, Path(scratch) / 'deterministic.json', side=side, timeout_seconds=remaining
            )
        deterministic[side] = {'source_revision': source_revision, 'readings': readings}
    dataset: dict[str, object] = {
        'accepted': not allow_dirty,
        'collection_command': f'python {" ".join(command)}' + (' --null' if null else ''),
        'environment': _environment() | {'python_hash_seed': memory.HASH_SEED},
        'harness_revision': revision,
        'pins': pins,
        'protocol': COMPARISON_PROTOCOL,
        'repetitions': repetitions_data,
        'source_revision': revision,
        'seed': DEFAULT_SEED,
        'schema_version': COMPARISON_SCHEMA_VERSION,
        'deterministic': deterministic,
        'targets': descriptions(),
    }
    _write_atomic(out / COMPARISON_FILE, dataset)
    return dataset


def _arguments(argv: Sequence[str] | None) -> dict[str, object]:
    parser = argparse.ArgumentParser(prog='python -m benchmarks.comparison.collection')
    parser.add_argument('command', choices=('collect',))
    parser.add_argument('--repetitions', type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument('--out', required=True)
    parser.add_argument('--baseline-dir', required=True)
    parser.add_argument('--baseline-revision', required=True)
    parser.add_argument('--budgets', required=True)
    parser.add_argument('--allow-dirty', action='store_true')
    parser.add_argument('--null', action='store_true')
    parser.add_argument('--workload', action='append', default=[])
    parser.add_argument('--timeout-seconds', type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parsed = parser.parse_args(argv)
    return vars(parsed)


def main(argv: Sequence[str] | None = None) -> int:
    chosen = _arguments(argv)
    try:
        collect(
            repetitions=require_integer(chosen['repetitions'], '--repetitions'),
            out=Path(require_text(chosen['out'], '--out')),
            baseline_dir=Path(require_text(chosen['baseline_dir'], '--baseline-dir')),
            baseline_revision=require_text(chosen['baseline_revision'], '--baseline-revision'),
            budgets=Path(require_text(chosen['budgets'], '--budgets')),
            null=bool(chosen['null']),
            focus=tuple(require_text(value, '--workload') for value in require_array(chosen['workload'], '--workload')),
            allow_dirty=bool(chosen['allow_dirty']),
            timeout_seconds=require_integer(chosen['timeout_seconds'], '--timeout-seconds'),
        )
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
