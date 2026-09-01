"""The two parts of `typing-forward` that are not honest in shell.

Resolving a checker's newest release — or the one before it — from the PyPI
JSON API, and grouping the workflow's failing legs into one tracking issue per
checker and version. A checker that fails on four legs is one thread, and a
later release opens a new thread rather than burying the earlier evidence.

Standard library only, and run as ``python -m scripts.forward``: the workflow
reaches it before anything has been synced.
"""

import json
import re
import sys
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from scripts.conformance.model import ConformanceError, is_array, is_table, table

FINAL_VERSION: Final = re.compile(r'\d+(?:\.\d+)*\Z')
# GitHub rejects an issue body over 65536 characters, and a rejected report is
# a silent forward job.
BODY_LIMIT: Final = 60000
USAGE: Final = 'usage: python -m scripts.forward newest <package> <offset> | issues <reports> <out> <run-url>'


def has_a_usable_file(files: object) -> bool:
    if not is_array(files):
        return False
    return any(is_table(entry) and entry.get('yanked') is not True for entry in files)


def released_versions(package: str) -> list[tuple[tuple[int, ...], str]]:
    """Every final, unyanked release of `package`, oldest first.

    Pre-releases are excluded by shape rather than by a metadata flag: the
    forward job probes what a contributor would get from `uvx <tool>@latest`,
    and that is a final release.
    """
    with urllib.request.urlopen(f'https://pypi.org/pypi/{package}/json', timeout=60) as response:
        payload: object = json.load(response)
    releases = table(table(payload, f'the PyPI record for {package}').get('releases'), f'{package} releases')
    return sorted(
        (tuple(int(part) for part in version.split('.')), version)
        for version, files in releases.items()
        if FINAL_VERSION.fullmatch(version) and has_a_usable_file(files)
    )


def newest(package: str, offset: int) -> str:
    ordered = released_versions(package)
    if len(ordered) <= offset:
        raise ConformanceError(f'{package} has no release {offset} behind its newest; PyPI lists {len(ordered)}')
    return ordered[-1 - offset][1]


def read_fields(meta: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in meta.read_text(encoding='utf-8').splitlines():
        name, separator, value = line.partition('=')
        if separator:
            fields[name] = value
    for required in ('checker', 'version', 'leg', 'status'):
        if required not in fields:
            raise ConformanceError(f'{meta} carries no {required}')
    return fields


def collect(reports: Path) -> dict[tuple[str, str], list[tuple[str, str]]]:
    grouped: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for meta in sorted(reports.rglob('meta.env')):
        fields = read_fields(meta)
        if fields['status'] == '0':
            continue
        log = meta.parent / 'run.log'
        output = log.read_text(encoding='utf-8', errors='replace') if log.is_file() else 'the leg produced no output'
        grouped.setdefault((fields['checker'], fields['version']), []).append((fields['leg'], output))
    return grouped


def render(checker: str, version: str, legs: Sequence[tuple[str, str]], run_url: str) -> str:
    parts = [
        f'`{checker} {version}` is not green against this repository.',
        '',
        'This issue is opened by the weekly `typing-forward` workflow and is advisory: the pinned version in '
        '`conformance/checkers.toml` is unchanged, and advancing it is a pull request that shows the whole suite '
        'green on the new version.',
        '',
        f'Run: {run_url}',
        '',
    ]
    for leg, output in legs:
        parts.extend([f'### {leg}', '', '```', output.strip(), '```', ''])
    body = '\n'.join(parts)
    if len(body) <= BODY_LIMIT:
        return body
    return body[:BODY_LIMIT] + '\n\n_Truncated; the full output is in the workflow run._\n'


def write_issues(reports: Path, out: Path, run_url: str) -> int:
    grouped = collect(reports)
    out.mkdir(parents=True, exist_ok=True)
    index: list[str] = []
    for (checker, version), legs in sorted(grouped.items()):
        body = out / f'{checker}-{version}.md'
        _ = body.write_text(render(checker, version, legs, run_url), encoding='utf-8')
        index.append(f'{checker}\t{version}\t{body}')
    _ = (out / 'index.tsv').write_text(''.join(f'{line}\n' for line in index), encoding='utf-8')
    return len(index)


def main(argv: Sequence[str]) -> int:
    try:
        if len(argv) == 3 and argv[0] == 'newest':
            print(f'version={newest(argv[1], int(argv[2]))}')
            return 0
        if len(argv) == 4 and argv[0] == 'issues':
            count = write_issues(Path(argv[1]), Path(argv[2]), argv[3])
            print(f'{count} checkers to report')
            return 0
    except ConformanceError as error:
        print(f'forward: {error}')
        return 1
    print(USAGE)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
