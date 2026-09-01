"""The Layer 1 gate over the repository's own source.

Stock Pyright runs at zero. ty and Pyrefly run against a committed register,
because the source carries every intentional negative behind a
``# type: ignore[code]  # pyright: ignore[code]`` pair, and ty reads neither
spelling. Demanding zero there would mean re-spelling those lines for a
pre-1.0 checker whose own ``unused-ignore-comment`` rule then fires when it
renames one; the register makes both blocking without demanding a zero the
project does not control.

Each register line is a ``file:rule:count`` triple and a one-line
classification. The count is what stops the register absorbing the second
defect of a kind it already knows about, and the stage fails on a count that
moves in either direction.
"""

import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from scripts.conformance.checkers import mypy_parse, pyrefly_parse, pyright_parse, ty_parse
from scripts.conformance.model import (
    CHECKOUT,
    CONFORMANCE,
    ConformanceError,
    Diagnostic,
    Failure,
    Outcome,
    Pins,
    Result,
    Selection,
)
from scripts.conformance.workspace import run_on_the_checkout, subprocess_environment, venv_python

SOURCE_VENV: Final = CHECKOUT / '.venv'
PYRIGHT_CONFIG: Final = (CONFORMANCE / 'config' / 'pyright-source.json').relative_to(CHECKOUT).as_posix()


@dataclass(frozen=True, slots=True)
class RegisterEntry:
    path: str
    rule: str
    count: int
    classification: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.path, self.rule)


@dataclass(frozen=True, slots=True)
class SourceCheck:
    name: str
    package: str
    build: Callable[[str], tuple[str, ...]]
    parse: Callable[[int, str, str], Outcome]
    register: str | None


def parse_register(contents: str, where: str) -> tuple[RegisterEntry, ...]:
    """Read a register, rejecting anything the comparison could not act on.

    An entry with no classification is rejected rather than accepted with an
    empty one: a register whose entries are unexplained records that a
    diagnostic exists without recording why it is tolerated, which is the
    baseline file this suite refuses elsewhere.
    """
    entries: list[RegisterEntry] = []
    seen: set[tuple[str, str]] = set()
    for number, raw in enumerate(contents.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        triple, _, classification = line.partition(' ')
        if not classification.strip():
            raise ConformanceError(f'{where}:{number}: {triple} carries no classification')
        parts = triple.rsplit(':', 2)
        if len(parts) != 3:
            raise ConformanceError(f'{where}:{number}: {triple!r} is not a file:rule:count triple')
        path, rule, digits = parts
        if not path or not rule:
            raise ConformanceError(f'{where}:{number}: {triple!r} is not a file:rule:count triple')
        if not digits.isdigit() or int(digits) < 1:
            raise ConformanceError(f'{where}:{number}: {digits!r} is not a positive count')
        if (path, rule) in seen:
            raise ConformanceError(f'{where}:{number}: {path}:{rule} appears twice; one entry carries the whole count')
        seen.add((path, rule))
        entries.append(RegisterEntry(path, rule, int(digits), classification.strip()))
    return tuple(entries)


def read_register(name: str) -> tuple[RegisterEntry, ...]:
    path = CONFORMANCE / 'expected' / name
    if not path.is_file():
        raise ConformanceError(f'{name} is missing; the source gate has no register to compare against')
    return parse_register(path.read_text(encoding='utf-8'), name)


def compare(
    checker: str, register: str, entries: Sequence[RegisterEntry], diagnostics: Sequence[Diagnostic]
) -> list[Failure]:
    """Fail on an unregistered diagnostic, a stale entry, and a count that moved.

    The last two are what stop the register going stale: without them it would
    only ever grow, and an entry describing a diagnostic the checker no longer
    reports would sit there claiming a limitation that no longer exists.
    """
    observed: Counter[tuple[str, str]] = Counter((item.path.replace('\\', '/'), item.rule) for item in diagnostics)
    failures: list[Failure] = []
    for entry in entries:
        found = observed.pop(entry.key, 0)
        if found == entry.count:
            continue
        if found == 0:
            failures.append(
                Failure(
                    checker,
                    '-',
                    'source',
                    f'{register} registers {entry.count} {entry.rule} in {entry.path} and none appears; '
                    'drop the entry in the change that removed the diagnostic',
                )
            )
        else:
            failures.append(
                Failure(
                    checker,
                    '-',
                    'source',
                    f'{register} registers {entry.count} {entry.rule} in {entry.path}, {found} appear; '
                    'a count moves in either direction only by a deliberate edit to the register',
                )
            )
    for (path, rule), found in sorted(observed.items()):
        failures.append(
            Failure(checker, '-', 'source', f'{path}: {found} {rule} that {register} does not carry, and must')
        )
    return failures


def pyright_source(spec: str) -> tuple[str, ...]:
    return ('uvx', spec, '-p', PYRIGHT_CONFIG, '--outputjson')


def mypy_source(spec: str) -> tuple[str, ...]:
    return (
        'uvx',
        spec,
        '--python-executable',
        str(venv_python(SOURCE_VENV)),
        '--no-incremental',
        '--no-color-output',
        '--no-pretty',
        '--hide-error-context',
    )


def ty_source(spec: str) -> tuple[str, ...]:
    return ('uvx', spec, 'check', '--python', str(SOURCE_VENV), '--error', 'all', '--output-format', 'concise')


def pyrefly_source(spec: str) -> tuple[str, ...]:
    return (
        'uvx',
        spec,
        'check',
        '--config',
        'pyrefly.toml',
        '--preset',
        'strict',
        '--python-interpreter-path',
        str(venv_python(SOURCE_VENV)),
        '--output-format',
        'json',
        '--summary=full',
        '--progress-bar',
        'no',
        '--color',
        'never',
    )


SOURCE_CHECKS: Final = (
    SourceCheck('pyright', 'pyright', pyright_source, pyright_parse, None),
    SourceCheck('ty', 'ty', ty_source, ty_parse, 'ty-source.txt'),
    SourceCheck('pyrefly', 'pyrefly', pyrefly_source, pyrefly_parse, 'pyrefly-source.txt'),
)
SOURCE_CHECKER_NAMES: Final = tuple(check.name for check in SOURCE_CHECKS)


def invoke(check: SourceCheck, pins: Pins, environment: Mapping[str, str]) -> Outcome:
    completed = run_on_the_checkout(check.build(f'{check.package}@{pins.versions[check.name]}'), environment)
    return check.parse(completed.returncode, completed.stdout, completed.stderr)


def run_at_zero(check: SourceCheck, pins: Pins, environment: Mapping[str, str]) -> tuple[Result, list[Failure]]:
    """Stock Pyright over the same file list the other Layer 1 gates check.

    The file count is asserted twice over, because both of the configuration
    traps this file is shaped around end in a green run over an empty file
    set: an absolute path in ``include`` is dropped with a warning, and
    ``pythonPath`` is not a recognised key. A count of its own would catch a
    total drop; comparing it against mypy's catches a partial one.
    """
    outcome = invoke(check, pins, environment)
    failures: list[Failure] = []
    if outcome.diagnostics:
        detail = ', '.join(f'{item.path}:{item.line} {item.rule}' for item in outcome.diagnostics)
        failures.append(Failure(check.name, '-', 'source', detail))
    elif outcome.exit_code != 0:
        failures.append(
            Failure(
                check.name, '-', 'source', f'exit {outcome.exit_code}, no parsed diagnostic\n{outcome.output.strip()}'
            )
        )
    reference = invoke(SourceCheck('mypy', 'mypy', mypy_source, mypy_parse, None), pins, environment)
    if not outcome.checked:
        failures.append(
            Failure(
                check.name,
                '-',
                'source',
                'checked no files; a relative-path or venv setting Pyright silently drops leaves it reporting '
                'zero having checked nothing',
            )
        )
    elif reference.checked is None:
        failures.append(Failure(check.name, '-', 'source', f'mypy reported no file count:\n{reference.output.strip()}'))
    elif outcome.checked != reference.checked:
        failures.append(
            Failure(
                check.name,
                '-',
                'source',
                f'checked {outcome.checked} files where mypy checked {reference.checked}; the two Layer 1 gates '
                'must see the same code, or "both are clean" means nothing',
            )
        )
    return Result(
        check.name, '-', 'source', f'{outcome.checked} files, mypy {reference.checked}', not failures
    ), failures


def run_against_register(
    check: SourceCheck, register: str, pins: Pins, environment: Mapping[str, str]
) -> tuple[Result, list[Failure]]:
    entries = read_register(register)
    outcome = invoke(check, pins, environment)
    if not outcome.diagnostics and outcome.exit_code != 0:
        # Comparing an empty observation against the register would report
        # every entry as stale and bury the reason the checker failed to run.
        detail = f'exit {outcome.exit_code}, no parsed diagnostic\n{outcome.output.strip()}'
        return Result(check.name, '-', 'source', 'did not run', False), [Failure(check.name, '-', 'source', detail)]
    failures = compare(check.name, register, entries, outcome.diagnostics)
    note = f'{len(outcome.diagnostics)} diagnostics, {len(entries)} registered'
    return Result(check.name, '-', 'source', note, not failures), failures


def run_source(pins: Pins, selection: Selection) -> tuple[list[Result], list[Failure]]:
    if not venv_python(SOURCE_VENV).is_file():
        raise ConformanceError(f'{SOURCE_VENV} carries no interpreter; run `uv sync --locked --all-extras` first')
    chosen = [check for check in SOURCE_CHECKS if check.name in selection.checkers]
    if not chosen:
        raise ConformanceError(
            f'--source covers {", ".join(SOURCE_CHECKER_NAMES)}; mypy and Basedpyright gate `uv run`'
        )
    results: list[Result] = []
    failures: list[Failure] = []
    with tempfile.TemporaryDirectory(prefix='depin-source-') as raw:
        environment = subprocess_environment(Path(raw).resolve())
        for check in chosen:
            if check.register is None:
                result, problems = run_at_zero(check, pins, environment)
            else:
                result, problems = run_against_register(check, check.register, pins, environment)
            results.append(result)
            failures.extend(problems)
    return results, failures
