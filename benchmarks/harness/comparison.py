"""Collect counterbalanced competitor benchmark samples."""

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

from benchmarks.harness import HarnessError, memory, reduce, require_integer, require_text, write_json
from benchmarks.harness import environment as environment_module

DEFAULT_REPETITIONS = 5
REPORT_PLACEHOLDER = '{report}'
COMPARISON_FILE = 'comparison.json'
COMMAND = ('-m', 'pytest', 'benchmarks/test_comparison.py', '--benchmark-only', '-q', '--benchmark-json={report}')


def _revision() -> str:
    completed = subprocess.run(('git', 'rev-parse', 'HEAD'), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise HarnessError('cannot determine the source revision; run collection from a Git checkout')
    return completed.stdout.strip()


def _clean_tree() -> bool:
    completed = subprocess.run(('git', 'status', '--porcelain'), capture_output=True, text=True, check=False)
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


def _descriptions() -> dict[str, object]:
    from benchmarks.comparison.inventory import build

    descriptions: dict[str, object] = {}
    for comparative in build():
        target: dict[str, object] | None = None
        if comparative.target is not None:
            target = {
                'fixed_seconds': comparative.target.fixed_seconds,
                'fraction_of_direct': comparative.target.fraction_of_direct,
                'justification': comparative.target.justification,
            }
        descriptions[comparative.workload.name] = {
            'target': target,
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


def _run(command: Sequence[str], report: Path, order: str) -> dict[str, reduce.Aggregate]:
    argv = [sys.executable, *(part.replace(REPORT_PLACEHOLDER, str(report)) for part in command)]
    child = os.environ | {'DEPIN_COMPARISON_ORDER': order, 'PYTHONHASHSEED': memory.HASH_SEED}
    completed = subprocess.run(argv, env=child, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise HarnessError(
            f'comparison child exited {completed.returncode}: {" ".join(argv)}\n{completed.stdout}{completed.stderr}'
        )
    return reduce.load(report)


def collect(
    *,
    repetitions: int,
    out: Path,
    allow_dirty: bool = False,
    command: Sequence[str] = COMMAND,
) -> dict[str, object]:
    """Run the protocol and write its reduced evidence dataset."""
    if repetitions < DEFAULT_REPETITIONS:
        raise HarnessError(f'{repetitions} repetitions; the protocol needs at least five')
    revision, pins = _preflight(allow_dirty=allow_dirty)
    repetitions_data: list[dict[str, object]] = []
    for index in range(repetitions):
        order = 'forward' if index % 2 == 0 else 'reverse'
        with tempfile.TemporaryDirectory() as scratch:
            aggregates = _run(command, Path(scratch) / 'report.json', order)
        medians = {name: aggregate.median for name, aggregate in sorted(aggregates.items())}
        rounds = {name: aggregate.rounds for name, aggregate in sorted(aggregates.items())}
        repetitions_data.append(
            {
                'order': order,
                'medians': medians,
                'rounds': rounds,
                'duration': sum(aggregate.measured for aggregate in aggregates.values()),
            }
        )
    dataset: dict[str, object] = {
        'accepted': not allow_dirty,
        'environment': _environment(),
        'harness_revision': revision,
        'pins': pins,
        'repetitions': repetitions_data,
        'source_revision': revision,
        'targets': _descriptions(),
    }
    write_json(out / COMPARISON_FILE, dataset)
    return dataset


def _arguments(argv: Sequence[str] | None) -> dict[str, object]:
    parser = argparse.ArgumentParser(prog='python -m benchmarks.harness.comparison')
    parser.add_argument('command', choices=('collect',))
    parser.add_argument('--repetitions', type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument('--out', required=True)
    parser.add_argument('--allow-dirty', action='store_true')
    parsed = parser.parse_args(argv)
    return vars(parsed)


def main(argv: Sequence[str] | None = None) -> int:
    chosen = _arguments(argv)
    try:
        collect(
            repetitions=require_integer(chosen['repetitions'], '--repetitions'),
            out=Path(require_text(chosen['out'], '--out')),
            allow_dirty=bool(chosen['allow_dirty']),
        )
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
