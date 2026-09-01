"""The control, positive, anti-erasure and negative stages."""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from scripts.conformance.checkers import CHECKERS
from scripts.conformance.isolation import check_isolation
from scripts.conformance.model import (
    MODES,
    Checker,
    Diagnostic,
    Failure,
    Invocation,
    Outcome,
    Pins,
    Result,
    Selection,
    Workspace,
    integer,
    load_toml,
    table,
    text,
)
from scripts.conformance.workspace import run_outside_checkout, subprocess_environment


def configuration(workspace: Workspace, checker: Checker, mode: str, override: str | None = None) -> Path:
    stem = Path(override or checker.config)
    return workspace.corpus / 'config' / f'{stem.stem}.{mode}{stem.suffix}'


def invoke(
    workspace: Workspace, checker: Checker, pins: Pins, invocation: Invocation, environment: Mapping[str, str]
) -> Outcome:
    command = checker.build(f'{checker.package}@{pins.versions[checker.name]}', invocation)
    completed = run_outside_checkout(command, workspace.corpus, environment)
    return checker.parse(completed.returncode, completed.stdout, completed.stderr)


def _relative(paths: Iterable[Path], root: Path) -> tuple[Path, ...]:
    return tuple(sorted(path.relative_to(root) for path in paths))


def positive_files(workspace: Workspace, mode: str) -> tuple[Path, ...]:
    trees = ['corpus/core', 'corpus/ext_core', *(['corpus/ext_extras'] if mode == 'extras' else [])]
    found: list[Path] = []
    for tree in trees:
        found.extend((workspace.corpus / tree).rglob('*.py'))
    return _relative(found, workspace.corpus)


def core_files(workspace: Workspace) -> tuple[Path, ...]:
    return _relative((workspace.corpus / 'corpus' / 'core').rglob('*.py'), workspace.corpus)


def negative_files(workspace: Workspace) -> tuple[Path, ...]:
    return _relative((workspace.corpus / 'negative').glob('*.py'), workspace.corpus)


def _describe(diagnostics: Sequence[Diagnostic]) -> str:
    return ', '.join(f'{item.path}:{item.line} {item.rule}' for item in diagnostics)


def run_control(
    workspace: Workspace, checker: Checker, pins: Pins, mode: str, environment: Mapping[str, str]
) -> tuple[Result, list[Failure]]:
    """The empty-interpreter control: the identical command line, no ``depin`` installed."""
    invocation = Invocation(
        config=configuration(workspace, checker, 'empty'),
        venv=workspace.venvs['empty'],
        files=positive_files(workspace, mode),
        anti_erasure=False,
    )
    outcome = invoke(workspace, checker, pins, invocation, environment)
    found = [item for item in outcome.diagnostics if item.rule == checker.missing_import_rule]
    if not found:
        return Result(checker.name, mode, 'control', 'no unresolved import', False), [
            Failure(
                checker.name,
                mode,
                'control',
                f'against an interpreter with no depin, {checker.name} reported no {checker.missing_import_rule}; '
                f'the harness is not isolated (exit {outcome.exit_code})\n{outcome.output.strip()}',
            )
        ]
    return Result(checker.name, mode, 'control', f'{len(found)} {checker.missing_import_rule}', True), []


def run_zero(
    workspace: Workspace,
    checker: Checker,
    pins: Pins,
    mode: str,
    stage: str,
    invocation: Invocation,
    environment: Mapping[str, str],
) -> tuple[Result, list[Failure]]:
    expected = len(invocation.files)
    outcome = invoke(workspace, checker, pins, invocation, environment)
    failures: list[Failure] = []
    if outcome.diagnostics:
        failures.append(Failure(checker.name, mode, stage, _describe(outcome.diagnostics)))
    elif outcome.exit_code != 0:
        failures.append(
            Failure(
                checker.name, mode, stage, f'exit {outcome.exit_code}, no parsed diagnostic\n{outcome.output.strip()}'
            )
        )
    if outcome.checked is not None and outcome.checked < expected:
        failures.append(
            Failure(
                checker.name,
                mode,
                stage,
                f'checked {outcome.checked} files where {expected} were passed; a configuration that silently '
                'drops its file set reports zero having checked nothing',
            )
        )
    note = f'{outcome.checked} files' if outcome.checked is not None else f'{expected} files, no count reported'
    return Result(checker.name, mode, stage, note, not failures), failures


def run_negatives(
    workspace: Workspace, checker: Checker, pins: Pins, environment: Mapping[str, str]
) -> tuple[Result, list[Failure]]:
    """One misuse per file, checked one file at a time.

    Running the fixtures together would let an unrelated diagnostic satisfy a
    fixture by accident.

    This is not a per-install-mode stage. Each fixture names the interpreter it
    needs — ``mode = "extras"`` for a misuse only reachable with a framework
    installed, core-only otherwise — so running it once per checker covers it.
    """
    expected = {
        name: table(value, f'negative.toml [{name}]')
        for name, value in load_toml(workspace.corpus / 'expected' / 'negative.toml').items()
    }
    failures: list[Failure] = []
    fixtures = negative_files(workspace)
    seen: set[str] = set()
    for fixture in fixtures:
        name = fixture.stem.split('_')[0]
        seen.add(name)
        record = expected.get(name)
        if record is None:
            failures.append(Failure(checker.name, '-', 'negative', f'{fixture} has no entry in expected/negative.toml'))
            continue
        venv = workspace.venvs['extras' if record.get('mode') == 'extras' else 'core']
        invocation = Invocation(
            config=configuration(workspace, checker, venv.name), venv=venv, files=(fixture,), anti_erasure=False
        )
        outcome = invoke(workspace, checker, pins, invocation, environment)
        line = integer(record, 'line', f'negative.toml [{name}]')
        rule = text(record, checker.name, f'negative.toml [{name}]')
        if outcome.exit_code == 0:
            failures.append(Failure(checker.name, venv.name, 'negative', f'{name}: exit 0, the misuse was accepted'))
        elif not any(item.line == line and item.rule == rule for item in outcome.diagnostics):
            failures.append(
                Failure(
                    checker.name,
                    venv.name,
                    'negative',
                    f'{name}: expected {rule} on line {line}, got {_describe(outcome.diagnostics) or "nothing"}',
                )
            )
    unused = sorted(set(expected) - seen)
    if unused:
        failures.append(Failure(checker.name, '-', 'negative', f'expected/negative.toml has no fixture for {unused}'))
    return Result(checker.name, '-', 'negative', f'{len(fixtures)} fixtures', not failures), failures


def anti_erasure_invocation(workspace: Workspace, checker: Checker, mode: str) -> Invocation | None:
    """`Any` satisfies an assignment in both directions, so the oracles alone miss it.

    Two of the five can express the requirement. Basedpyright carries it with
    `reportAny` and `reportExplicitAny` over the whole positive corpus; mypy
    with ``--disallow-any-expr`` over `corpus/core` alone, which is where it is
    meaningful — third-party annotations produce `Any` expressions the corpus
    does not own. ty cannot express an anti-`Any` rule at all.
    """
    if checker.name == 'basedpyright':
        return Invocation(
            config=configuration(workspace, checker, mode, 'basedpyright-any.json'),
            venv=workspace.venvs[mode],
            files=positive_files(workspace, mode),
            anti_erasure=True,
        )
    if checker.name == 'mypy' and mode == 'core':
        return Invocation(
            config=configuration(workspace, checker, mode),
            venv=workspace.venvs[mode],
            files=core_files(workspace),
            anti_erasure=True,
        )
    return None


def run(pins: Pins, workspace: Workspace, selection: Selection) -> tuple[list[Result], list[Failure]]:
    environment = subprocess_environment(workspace.root)
    failures = check_isolation(workspace, pins, environment)
    results = [Result('artifact', '-', 'isolation', workspace.wheel.name, not failures)]
    if failures:
        return results, failures

    for checker in (item for item in CHECKERS if item.name in selection.checkers):
        for mode in (name for name in MODES if name in selection.modes):
            if 'control' in selection.stages:
                result, problems = run_control(workspace, checker, pins, mode, environment)
                results.append(result)
                failures.extend(problems)
            if 'positive' in selection.stages:
                invocation = Invocation(
                    config=configuration(workspace, checker, mode),
                    venv=workspace.venvs[mode],
                    files=positive_files(workspace, mode),
                    anti_erasure=False,
                )
                result, problems = run_zero(workspace, checker, pins, mode, 'positive', invocation, environment)
                results.append(result)
                failures.extend(problems)
            if 'anti-erasure' in selection.stages:
                erasure = anti_erasure_invocation(workspace, checker, mode)
                if erasure is not None:
                    result, problems = run_zero(workspace, checker, pins, mode, 'anti-erasure', erasure, environment)
                    results.append(result)
                    failures.extend(problems)
        if 'negative' in selection.stages:
            result, problems = run_negatives(workspace, checker, pins, environment)
            results.append(result)
            failures.extend(problems)
    return results, failures
