"""The assertions that run before any checking.

Nothing after them means anything if one fails, so the runner reports them and
stops rather than checking a corpus whose provenance it cannot vouch for.
"""

import csv
import json
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from scripts.conformance.model import CHECKOUT, Failure, Pins, Workspace, is_table, strings, table, text
from scripts.conformance.workspace import run_outside_checkout, venv_python

IMPORT_PROBE: Final = """
import json, sys, depin
print(json.dumps({'file': depin.__file__, 'path': sys.path}))
"""

MISSING_PROBE: Final = """
import importlib, json, sys
resolved = []
for name in sys.argv[1:]:
    try:
        importlib.import_module(name)
    except ModuleNotFoundError:
        continue
    resolved.append(name)
print(json.dumps(resolved))
"""


def assert_wheel_carries_the_typing_marker(wheel: Path) -> list[Failure]:
    """`depin/py.typed` must appear in `RECORD`, located through the zip central directory.

    A `namelist()` membership test alone would pass on a wheel whose RECORD and
    payload disagree, and RECORD is what an installer copies from.
    """
    with zipfile.ZipFile(wheel) as archive:
        records = [info.filename for info in archive.infolist() if info.filename.endswith('.dist-info/RECORD')]
        if len(records) != 1:
            return [Failure('artifact', '-', 'wheel', f'expected one .dist-info/RECORD, found {len(records)}')]
        rows = csv.reader(archive.read(records[0]).decode('utf-8').splitlines())
        listed = {row[0] for row in rows if row}
        payload = set(archive.namelist())
    problems: list[Failure] = []
    if 'depin/py.typed' not in listed:
        problems.append(Failure('artifact', '-', 'wheel', f'{records[0]} does not list depin/py.typed'))
    if 'depin/py.typed' not in payload:
        problems.append(Failure('artifact', '-', 'wheel', 'the wheel payload carries no depin/py.typed'))
    return problems


def assert_installation_is_not_editable(venv: Path) -> list[Failure]:
    site = sorted(venv.glob('lib/*/site-packages')) or sorted(venv.glob('Lib/site-packages'))
    if not site:
        return [Failure('artifact', venv.name, 'install', f'no site-packages under {venv}')]
    problems: list[Failure] = []
    if sorted(site[0].glob('__editable__*.pth')):
        problems.append(Failure('artifact', venv.name, 'install', 'an __editable__*.pth exists in site-packages'))
    direct = sorted(site[0].glob('pydepin-*.dist-info/direct_url.json'))
    if not direct:
        return [*problems, Failure('artifact', venv.name, 'install', 'no pydepin-*.dist-info/direct_url.json')]
    record = table(json.loads(direct[0].read_text(encoding='utf-8')), str(direct[0]))
    if 'archive_info' not in record:
        problems.append(Failure('artifact', venv.name, 'install', 'direct_url.json carries no archive_info'))
    directory = record.get('dir_info')
    if is_table(directory) and directory.get('editable') is True:
        problems.append(Failure('artifact', venv.name, 'install', 'direct_url.json declares an editable install'))
    return problems


def assert_depin_comes_from_the_venv(workspace: Workspace, venv: Path, environment: Mapping[str, str]) -> list[Failure]:
    probe = run_outside_checkout([str(venv_python(venv)), '-c', IMPORT_PROBE], workspace.corpus, environment)
    if probe.returncode != 0:
        return [Failure('artifact', venv.name, 'import', f'importing depin failed:\n{probe.stderr.strip()}')]
    record = table(json.loads(probe.stdout), 'the import probe')
    module = Path(text(record, 'file', 'the import probe')).resolve()
    problems: list[Failure] = []
    if venv.resolve() not in module.parents:
        problems.append(Failure('artifact', venv.name, 'import', f'depin.__file__ is {module}, outside {venv}'))
    for entry in strings(record.get('path'), 'the import probe sys.path'):
        if not entry:
            continue
        candidate = Path(entry).resolve()
        if candidate == CHECKOUT or CHECKOUT in candidate.parents:
            problems.append(
                Failure('artifact', venv.name, 'import', f'sys.path carries {candidate}, inside the checkout')
            )
    return problems


def assert_framework_modules_are_unresolvable(
    workspace: Workspace, pins: Pins, environment: Mapping[str, str]
) -> list[Failure]:
    """In core-only mode every framework-requiring ext module must fail to import.

    The modules ship in the wheel; only the absent third-party package stops
    them, which is what proves the core carries no framework dependency.
    """
    command = [str(venv_python(workspace.venvs['core'])), '-c', MISSING_PROBE, *pins.framework_modules]
    probe = run_outside_checkout(command, workspace.corpus, environment)
    if probe.returncode != 0:
        return [Failure('artifact', 'core', 'unresolvable', f'the probe failed:\n{probe.stderr.strip()}')]
    resolved = strings(json.loads(probe.stdout), 'the framework-module probe')
    if resolved:
        return [Failure('artifact', 'core', 'unresolvable', f'importable without an extra: {", ".join(resolved)}')]
    return []


def check_isolation(workspace: Workspace, pins: Pins, environment: Mapping[str, str]) -> list[Failure]:
    failures = assert_wheel_carries_the_typing_marker(workspace.wheel)
    for name in ('core', 'extras'):
        failures.extend(assert_installation_is_not_editable(workspace.venvs[name]))
        failures.extend(assert_depin_comes_from_the_venv(workspace, workspace.venvs[name], environment))
    failures.extend(assert_framework_modules_are_unresolvable(workspace, pins, environment))
    return failures
