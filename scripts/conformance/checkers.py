"""One command builder and one output parser per checker.

Every parser yields a `Diagnostic` carrying a path, a line and a **rule
identifier**. Message text is never captured, let alone matched: for one misuse
the three checkers that name a type name three different ones, and ty has
printed both sides of a disagreement identically.
"""

import json
import re
from typing import Final

from scripts.conformance.model import Checker, Diagnostic, Invocation, Outcome, integer, is_array, is_table, table, text

MYPY_DIAGNOSTIC: Final = re.compile(
    r'^(?P<path>[^:]+):(?P<line>\d+):(?:\d+:)?\s+(?:error|warning):.*\[(?P<rule>[\w-]+)\]\s*$'
)
MYPY_CHECKED: Final = re.compile(r'(?:checked|no issues found in)\s+(\d+)\s+source file')
TY_DIAGNOSTIC: Final = re.compile(r'^(?P<path>.+?):(?P<line>\d+):\d+:\s+(?:error|warning)\[(?P<rule>[\w-]+)\]')
PYREFLY_MODULES: Final = re.compile(r'(\d[\d,]*)\s+modules?\s+\(')


def mypy_command(spec: str, invocation: Invocation) -> tuple[str, ...]:
    return (
        'uvx',
        spec,
        '--config-file',
        str(invocation.config),
        '--strict',
        '--warn-unreachable',
        '--no-incremental',
        '--no-color-output',
        '--no-pretty',
        '--hide-error-context',
        *(('--disallow-any-expr',) if invocation.anti_erasure else ()),
        *(str(path) for path in invocation.files),
    )


def mypy_parse(exit_code: int, stdout: str, stderr: str) -> Outcome:
    diagnostics = tuple(
        Diagnostic(match.group('path'), int(match.group('line')), match.group('rule'))
        for line in stdout.splitlines()
        if (match := MYPY_DIAGNOSTIC.match(line))
    )
    checked = MYPY_CHECKED.search(stdout)
    return Outcome(exit_code, diagnostics, int(checked.group(1)) if checked else None, stdout + stderr)


def pyright_command(spec: str, invocation: Invocation) -> tuple[str, ...]:
    return ('uvx', spec, '--project', str(invocation.config), '--outputjson', *(str(p) for p in invocation.files))


def pyright_parse(exit_code: int, stdout: str, stderr: str) -> Outcome:
    try:
        document: object = json.loads(stdout)
    except json.JSONDecodeError:
        return Outcome(exit_code, (), None, stdout + stderr)
    report = table(document, 'the Pyright report')
    entries = report.get('generalDiagnostics')
    diagnostics: list[Diagnostic] = []
    for entry in entries if is_array(entries) else ():
        if not is_table(entry) or entry.get('severity') != 'error':
            continue
        start = table(table(entry.get('range'), 'a Pyright range').get('start'), 'a Pyright range start')
        rule = entry.get('rule')
        diagnostics.append(
            Diagnostic(
                text(entry, 'file', 'a Pyright diagnostic'),
                integer(start, 'line', 'a Pyright range start') + 1,
                rule if isinstance(rule, str) else 'general',
            )
        )
    summary = report.get('summary')
    checked = integer(summary, 'filesAnalyzed', 'the Pyright summary') if is_table(summary) else None
    return Outcome(exit_code, tuple(diagnostics), checked, stdout + stderr)


def ty_command(spec: str, invocation: Invocation) -> tuple[str, ...]:
    return (
        'uvx',
        spec,
        'check',
        '--config-file',
        str(invocation.config),
        '--python',
        str(invocation.venv),
        '--error',
        'all',
        '--output-format',
        'concise',
        *(str(path) for path in invocation.files),
    )


def ty_parse(exit_code: int, stdout: str, stderr: str) -> Outcome:
    diagnostics = tuple(
        Diagnostic(match.group('path'), int(match.group('line')), match.group('rule'))
        for line in (stdout + stderr).splitlines()
        if (match := TY_DIAGNOSTIC.match(line))
    )
    return Outcome(exit_code, diagnostics, None, stdout + stderr)


def pyrefly_command(spec: str, invocation: Invocation) -> tuple[str, ...]:
    return (
        'uvx',
        spec,
        'check',
        '--config',
        str(invocation.config),
        '--preset',
        'strict',
        '--output-format',
        'json',
        '--summary=full',
        '--progress-bar',
        'no',
        '--color',
        'never',
        *(str(path) for path in invocation.files),
    )


def pyrefly_parse(exit_code: int, stdout: str, stderr: str) -> Outcome:
    try:
        document: object = json.loads(stdout)
    except json.JSONDecodeError:
        return Outcome(exit_code, (), None, stdout + stderr)
    entries = table(document, 'the Pyrefly report').get('errors')
    diagnostics = tuple(
        Diagnostic(
            text(entry, 'path', 'a Pyrefly error'),
            integer(entry, 'line', 'a Pyrefly error'),
            text(entry, 'name', 'a Pyrefly error'),
        )
        for entry in (entries if is_array(entries) else ())
        if is_table(entry)
    )
    modules = PYREFLY_MODULES.search(stderr)
    return Outcome(exit_code, diagnostics, int(modules.group(1).replace(',', '')) if modules else None, stdout + stderr)


CHECKERS: Final = (
    Checker('mypy', 'mypy', 'mypy.ini', mypy_command, mypy_parse, 'import-not-found'),
    Checker('pyright', 'pyright', 'pyright.json', pyright_command, pyright_parse, 'reportMissingImports'),
    Checker(
        'basedpyright', 'basedpyright', 'basedpyright.json', pyright_command, pyright_parse, 'reportMissingImports'
    ),
    Checker('ty', 'ty', 'ty.toml', ty_command, ty_parse, 'unresolved-import'),
    Checker('pyrefly', 'pyrefly', 'pyrefly.toml', pyrefly_command, pyrefly_parse, 'missing-import'),
)
