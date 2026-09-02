"""Render an accepted dataset to the markdown the documentation publishes.

    python -m benchmarks.harness.report DIR

The results page is generated rather than written, and a test asserts the
committed page equals the render of the committed data. A number therefore cannot
drift from its evidence — which is the whole reason nothing here reads the clock,
the working directory, or anything else that varies between two runs over the same
data.

`DIR` is a collection directory. The published side is `head`, because a dataset is
published for the revision it was measured at; a directory holding the aggregates
directly is rendered as it stands, so a single-revision dataset needs no empty
`base` beside it.
"""

import argparse
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from benchmarks.contracts import Metric
from benchmarks.harness import (
    HarnessError,
    is_array,
    read_json,
    reduce,
    require_array,
    require_integer,
    require_number,
    require_object,
    require_text,
)
from benchmarks.harness import budgets as budget_module
from benchmarks.harness.pairs import DETERMINISTIC_FILE, ENVIRONMENT_FILE, HEAD

USAGE = 'python -m benchmarks.harness.report DIR'
UNITS = ((1.0, 's'), (1e-3, 'ms'), (1e-6, 'µs'), (1e-9, 'ns'))


def _duration(seconds: float) -> str:
    for factor, unit in UNITS:
        if seconds >= factor:
            return f'{seconds / factor:.3f} {unit}'
    return f'{seconds / UNITS[-1][0]:.3f} {UNITS[-1][1]}'


def _cell(value: object) -> str:
    """Render one value into a table cell, escaping what markdown would read as structure."""
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if is_array(value):
        return ', '.join(_cell(item) for item in value)
    return str(value).replace('|', r'\|')


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = [f'| {" | ".join(header)} |', f'|{"|".join(" --- " for _ in header)}|']
    lines += [f'| {" | ".join(row)} |' for row in rows]
    return [*lines, '']


def _environment_rows(payload: Mapping[str, object], where: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for section in sorted(payload):
        fields = require_object(payload[section], f'{where}: {section}')
        rows += [[f'{section}.{name}', _cell(fields[name])] for name in sorted(fields)]
    return rows


def _latency_rows(directory: Path) -> list[list[str]]:
    files = sorted(directory.glob('rep*.json'))
    if not files:
        return []
    measurements: dict[str, list[reduce.Aggregate]] = {}
    for path in files:
        payload = read_json(path)
        aggregates = require_object(payload.get('aggregates'), f'{path}: aggregates')
        for name, aggregate in reduce.decode_all(aggregates, str(path)).items():
            measurements.setdefault(name, []).append(aggregate)

    rows: list[list[str]] = []
    for name in sorted(measurements):
        repetitions = measurements[name]
        medians = sorted(aggregate.median for aggregate in repetitions)
        spread = medians[-1] / medians[0] - 1.0 if medians[0] > 0 else 0.0
        rows.append(
            [
                _cell(name),
                str(len(repetitions)),
                str(min(aggregate.rounds for aggregate in repetitions)),
                _duration(statistics.median(medians)),
                f'{spread:.1%}',
            ]
        )
    return rows


def _deterministic_sections(path: Path) -> list[str]:
    if not path.is_file():
        return []
    payload = read_json(path)
    lines: list[str] = []

    calls = require_object(payload.get(budget_module.WORK, {}), f'{path}: work')
    if calls:
        lines += ['## Work', '']
        lines += _table(
            ('Workload', 'Python calls per operation'),
            [[_cell(name), str(require_integer(calls[name], f'{path}: work.{name}'))] for name in sorted(calls)],
        )

    allocations = require_object(payload.get(Metric.ALLOCATIONS.value, {}), f'{path}: allocations')
    if allocations:
        allocated: list[list[str]] = []
        for name in sorted(allocations):
            fields = require_object(allocations[name], f'{path}: allocations.{name}')
            allocated.append(
                [
                    _cell(name),
                    *(
                        str(require_integer(fields.get(field), f'{path}: allocations.{name}.{field}'))
                        for field in ('blocks', 'size', 'peak')
                    ),
                ]
            )
        lines += ['## Allocations', '']
        lines += _table(('Workload', 'Blocks per operation', 'Bytes per operation', 'Peak bytes'), allocated)

    retained = require_object(payload.get(Metric.RETAINED.value, {}), f'{path}: retained')
    if retained:
        lines += ['## Retained memory', '']
        lines += _table(
            ('Workload', 'Bytes held'),
            [
                [_cell(name), str(require_integer(retained[name], f'{path}: retained.{name}'))]
                for name in sorted(retained)
            ],
        )

    curves = require_object(payload.get(Metric.SCALING.value, {}), f'{path}: scaling')
    if curves:
        measured: list[list[str]] = []
        for name in sorted(curves):
            fields = require_object(curves[name], f'{path}: scaling.{name}')
            sizes = require_array(fields.get('sizes'), f'{path}: scaling.{name}.sizes')
            costs = require_array(fields.get('costs'), f'{path}: scaling.{name}.costs')
            if len(sizes) != len(costs):
                raise HarnessError(f'{path}: scaling.{name} has {len(sizes)} sizes and {len(costs)} costs')
            previous: float | None = None
            for size, cost in zip(sizes, costs, strict=True):
                seconds = require_number(cost, f'{path}: scaling.{name}.costs')
                growth = '—' if previous is None or previous <= 0 else f'{seconds / previous:.2f}x'
                index = require_integer(size, f'{path}: scaling.{name}.sizes')
                measured.append([_cell(name), str(index), _duration(seconds), growth])
                previous = seconds
        lines += ['## Scaling', '']
        lines += _table(('Curve', 'Size', 'Cost per operation', 'Growth over the previous size'), measured)
    return lines


def render(dataset: Path) -> str:
    """Render `dataset` to markdown.

    Raises:
        HarnessError: the directory carries no environment metadata, or a section
            of it is malformed.
    """
    metadata = read_json(dataset / ENVIRONMENT_FILE)
    published = dataset / HEAD if (dataset / HEAD).is_dir() else dataset

    lines = ['# Measured results', '']
    lines += ['## Environment', '']
    lines += _table(
        ('Property', 'Value'),
        _environment_rows(
            require_object(metadata.get('environment'), f'{dataset / ENVIRONMENT_FILE}: environment'),
            str(dataset / ENVIRONMENT_FILE),
        ),
    )

    rows = _latency_rows(published)
    if rows:
        lines += ['## Latency', '']
        lines += _table(('Workload', 'Repetitions', 'Rounds', 'Median', 'Spread across repetitions'), rows)

    lines += _deterministic_sections(published / DETERMINISTIC_FILE)
    return '\n'.join(lines).rstrip('\n') + '\n'


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m benchmarks.harness.report', description=USAGE)
    parser.add_argument('dataset', help='the accepted dataset directory')
    chosen = dict(vars(parser.parse_args(argv)))
    try:
        _ = sys.stdout.write(render(Path(require_text(chosen['dataset'], 'DIR'))))
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
