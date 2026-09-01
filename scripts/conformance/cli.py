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
from scripts.conformance.pins import override_pins, read_pins, verify_corpus_imports, verify_lockstep
from scripts.conformance.source import run_source
from scripts.conformance.stages import run
from scripts.conformance.workspace import build_workspace, render_configs, require_wheel, resolve_wheel


def parse_arguments(argv: Sequence[str] | None) -> Selection:
    parser = argparse.ArgumentParser(prog='conformance', description='the consumer typing conformance suite')
    parser.add_argument('--checker', choices=CHECKER_NAMES, action='append', help='narrow to one checker; repeatable')
    parser.add_argument('--mode', choices=MODES, action='append', help='narrow to one install mode; repeatable')
    parser.add_argument('--only', choices=STAGES, action='append', help='narrow to one stage; repeatable')
    parser.add_argument('--wheel', help='check against this wheel instead of building one')
    parser.add_argument(
        '--pin',
        action='append',
        metavar='CHECKER=VERSION',
        help='run one checker at a version other than the one checkers.toml names; repeatable',
    )
    parser.add_argument(
        '--target-python',
        metavar='VERSION',
        help='build the interpreters and set every language target to this version instead of the pinned one',
    )
    layer = parser.add_mutually_exclusive_group()
    layer.add_argument(
        '--verify-artifact',
        action='store_true',
        help='assert only that the wheel carries depin/py.typed in RECORD, then exit',
    )
    layer.add_argument(
        '--source',
        action='store_true',
        help='check the repository source instead of the corpus: stock Pyright at zero, ty and Pyrefly '
        'against conformance/expected/*-source.txt',
    )
    chosen: dict[str, object] = dict(vars(parser.parse_args(argv)))
    wheel = chosen['wheel']
    if wheel is not None and not isinstance(wheel, str):
        raise ConformanceError('--wheel must name a path')
    target = chosen['target_python']
    if target is not None and not isinstance(target, str):
        raise ConformanceError('--target-python must name a version')
    return Selection(
        checkers=strings(chosen['checker'], '--checker') if chosen['checker'] is not None else CHECKER_NAMES,
        modes=strings(chosen['mode'], '--mode') if chosen['mode'] is not None else MODES,
        stages=strings(chosen['only'], '--only') if chosen['only'] is not None else STAGES,
        wheel=Path(wheel) if wheel is not None else None,
        verify_artifact=chosen['verify_artifact'] is True,
        source=chosen['source'] is True,
        overrides=parse_overrides(chosen['pin']),
        target_python=target,
    )


def parse_overrides(value: object) -> dict[str, str]:
    if value is None:
        return {}
    chosen: dict[str, str] = {}
    for entry in strings(value, '--pin'):
        name, separator, version = entry.partition('=')
        if not separator or not version or name not in CHECKER_NAMES:
            raise ConformanceError(f'--pin takes <checker>=<version> for one of {", ".join(CHECKER_NAMES)}: {entry!r}')
        chosen[name] = version
    return chosen


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
        pins = override_pins(read_pins(CONFORMANCE / 'checkers.toml'), selection.overrides, selection.target_python)
        verify_lockstep(pins)
        verify_corpus_imports()
    except ConformanceError as error:
        print(f'conformance: {error}')
        return 1

    if selection.verify_artifact:
        return report([], verify_artifact(selection.wheel))

    if selection.source:
        try:
            return report(*run_source(pins, selection))
        except ConformanceError as error:
            print(f'conformance: {error}')
            return 1

    with tempfile.TemporaryDirectory(prefix='depin-conformance-') as raw:
        try:
            root = Path(raw).resolve()
            workspace = build_workspace(root, pins, resolve_wheel(root, selection.wheel))
            render_configs(workspace, pins)
            results, failures = run(pins, workspace, selection)
        except ConformanceError as error:
            print(f'conformance: {error}')
            return 1

    return report(results, failures)
