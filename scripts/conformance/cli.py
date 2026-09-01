"""Argument parsing, the table, and the exit status."""

import argparse
import tempfile
from collections.abc import Sequence
from pathlib import Path

from scripts.conformance.isolation import assert_wheel_carries_the_typing_marker
from scripts.conformance.model import (
    CHECKER_NAMES,
    CONFORMANCE,
    MODES,
    STAGES,
    ConformanceError,
    Failure,
    Result,
    Selection,
    strings,
)
from scripts.conformance.pins import read_pins, verify_corpus_imports, verify_lockstep
from scripts.conformance.stages import run
from scripts.conformance.workspace import build_workspace, render_configs, require_wheel, resolve_wheel


def parse_arguments(argv: Sequence[str] | None) -> Selection:
    parser = argparse.ArgumentParser(prog='conformance', description='the consumer typing conformance suite')
    parser.add_argument('--checker', choices=CHECKER_NAMES, action='append', help='narrow to one checker; repeatable')
    parser.add_argument('--mode', choices=MODES, action='append', help='narrow to one install mode; repeatable')
    parser.add_argument('--only', choices=STAGES, action='append', help='narrow to one stage; repeatable')
    parser.add_argument('--wheel', help='check against this wheel instead of building one')
    parser.add_argument(
        '--verify-artifact',
        action='store_true',
        help='assert only that the wheel carries depin/py.typed in RECORD, then exit',
    )
    chosen: dict[str, object] = dict(vars(parser.parse_args(argv)))
    wheel = chosen['wheel']
    if wheel is not None and not isinstance(wheel, str):
        raise ConformanceError('--wheel must name a path')
    return Selection(
        checkers=strings(chosen['checker'], '--checker') if chosen['checker'] is not None else CHECKER_NAMES,
        modes=strings(chosen['mode'], '--mode') if chosen['mode'] is not None else MODES,
        stages=strings(chosen['only'], '--only') if chosen['only'] is not None else STAGES,
        wheel=Path(wheel) if wheel is not None else None,
        verify_artifact=chosen['verify_artifact'] is True,
    )


def print_table(results: Sequence[Result]) -> None:
    columns = [
        max(len('checker'), *(len(row.checker) for row in results)),
        max(len('mode'), *(len(row.mode) for row in results)),
        max(len('stage'), *(len(row.stage) for row in results)),
    ]
    header = f'{"checker":<{columns[0]}}  {"mode":<{columns[1]}}  {"stage":<{columns[2]}}  result'
    print(header)
    print('-' * len(header))
    for row in results:
        verdict = 'pass' if row.passed else 'FAIL'
        print(
            f'{row.checker:<{columns[0]}}  {row.mode:<{columns[1]}}  {row.stage:<{columns[2]}}  {verdict}  {row.note}'
        )


def verify_artifact(wheel: Path | None) -> list[Failure]:
    """The `typing-artifact` job's own assertion, before it uploads the wheel."""
    if wheel is None:
        return [Failure('artifact', '-', 'wheel', '--verify-artifact needs --wheel')]
    try:
        return assert_wheel_carries_the_typing_marker(require_wheel(wheel))
    except ConformanceError as error:
        return [Failure('artifact', '-', 'wheel', str(error))]


def report(results: Sequence[Result], failures: Sequence[Failure]) -> int:
    if results:
        print_table(results)
    if not failures:
        print(f'\n{len(results)} checks passed' if results else 'the wheel carries depin/py.typed')
        return 0
    print(f'\n{len(failures)} failures')
    for failure in failures:
        print(f'  {failure.checker} / {failure.mode} / {failure.stage}: {failure.detail}')
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    try:
        selection = parse_arguments(argv)
        pins = read_pins(CONFORMANCE / 'checkers.toml')
        verify_lockstep(pins)
        verify_corpus_imports()
    except ConformanceError as error:
        print(f'conformance: {error}')
        return 1

    if selection.verify_artifact:
        return report([], verify_artifact(selection.wheel))

    with tempfile.TemporaryDirectory(prefix='depin-conformance-') as raw:
        try:
            root = Path(raw).resolve()
            workspace = build_workspace(root, pins, resolve_wheel(root, selection.wheel))
            render_configs(workspace)
            results, failures = run(pins, workspace, selection)
        except ConformanceError as error:
            print(f'conformance: {error}')
            return 1

    return report(results, failures)
