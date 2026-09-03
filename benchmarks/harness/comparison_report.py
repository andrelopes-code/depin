"""Render accepted comparison evidence as a deterministic Markdown report."""

import argparse
import math
import statistics
import sys
import unicodedata
from collections.abc import Sequence
from pathlib import Path

from benchmarks.comparison import WORKLOADS as INVENTORY
from benchmarks.comparison.adapters import ADAPTERS
from benchmarks.harness import (
    HarnessError,
    comparison,
    leadership,
    read_json,
    require_array,
    require_object,
    require_text,
    stats,
)

USAGE = 'python -m benchmarks.harness.comparison_report DATASET --calibration PATH --budgets PATH'
UNITS = ((1.0, 's'), (1e-3, 'ms'), (1e-6, 'µs'), (1e-9, 'ns'))


def _duration(seconds: float) -> str:
    for factor, unit in UNITS:
        if seconds >= factor:
            return f'{seconds / factor:.3f} {unit}'
    return f'{seconds / UNITS[-1][0]:.3f} {UNITS[-1][1]}'


def _signed_duration(seconds: float) -> str:
    if seconds == 0.0:
        return '0.000 ns'
    magnitude = abs(seconds)
    for factor, unit in UNITS:
        if magnitude >= factor or math.isclose(magnitude, factor, rel_tol=0.0, abs_tol=1e-15):
            sign = '+' if seconds > 0.0 else '-'
            return f'{sign}{magnitude / factor:.3f} {unit}'
    sign = '+' if seconds > 0.0 else '-'
    return f'{sign}{magnitude / UNITS[-1][0]:.3f} {UNITS[-1][1]}'


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [
        f'| {" | ".join(header)} |',
        f'|{"|".join(" --- " for _ in header)}|',
        *(f'| {" | ".join(row)} |' for row in rows),
        '',
    ]


def _text(value: object, where: str) -> str:
    text = require_text(value, where)
    if any(not character.isprintable() or unicodedata.category(character).startswith('C') for character in text):
        raise HarnessError(f'{where}: expected a single printable Markdown text line')
    return text.replace('\\', r'\\').replace('|', r'\|').replace('`', r'\`')


def _workload_order(dataset: dict[str, object]) -> tuple[str, ...]:
    descriptions = leadership.workloads(dataset)
    inventory = [comparative.workload.name for comparative in INVENTORY]
    unknown = sorted(set(descriptions) - set(inventory))
    if unknown:
        raise HarnessError(f'{unknown[0]}: dataset target is not in the authoritative comparison inventory')
    return tuple(name for name in inventory if name in descriptions)


def _candidate_rows(dataset: dict[str, object], workload: str, verdict: leadership.WorkloadVerdict) -> list[list[str]]:
    description = leadership.workloads(dataset)[workload]
    encoded = require_array(description.get('candidates'), f'dataset.targets.{workload}.candidates')
    fields_by_label: dict[str, dict[str, object]] = {}
    for index, candidate in enumerate(encoded):
        fields = require_object(candidate, f'dataset.targets.{workload}.candidates[{index}]')
        label = require_text(fields.get('label'), f'dataset.targets.{workload}.candidates[{index}].label')
        _ = _text(label, f'dataset.targets.{workload}.candidates[{index}].label')
        fields_by_label[label] = fields

    ordered_labels = [adapter.competitor.label for adapter in ADAPTERS if adapter.competitor.label in fields_by_label]
    ordered_labels += sorted(set(fields_by_label) - set(ordered_labels))
    rows: list[list[str]] = []
    for label in ordered_labels:
        fields = fields_by_label[label]
        classification = require_text(
            fields.get('classification'), f'dataset.targets.{workload}.candidates.{label}.classification'
        )
        reason = _text(fields.get('reason'), f'dataset.targets.{workload}.candidates.{label}.reason')
        if classification != 'equivalent':
            rows.append(
                [
                    _text(label, f'dataset.targets.{workload}.candidates.{label}.label'),
                    classification,
                    reason,
                    '—',
                    '—',
                    '—',
                ]
            )
            continue
        candidate, depin = leadership.paired_medians(leadership.repetitions(dataset), workload, label, 'depin')
        if len(candidate) < leadership.MINIMUM_REPETITIONS or len(depin) < leadership.MINIMUM_REPETITIONS:
            rows.append(
                [
                    _text(label, f'dataset.targets.{workload}.candidates.{label}.label'),
                    classification,
                    reason,
                    '—',
                    '—',
                    '—',
                ]
            )
            continue
        paired = stats.paired_ratio(candidate, depin, seed=leadership.seed(dataset))
        rows.append(
            [
                _text(label, f'dataset.targets.{workload}.candidates.{label}.label'),
                classification,
                reason,
                _duration(statistics.median(candidate)),
                _duration(statistics.median(depin)),
                f'[{paired.low:+.2%}, {paired.high:+.2%}]',
            ]
        )
    return rows


def _claim(dataset: dict[str, object], workload: str) -> str:
    description = leadership.workloads(dataset)[workload]
    for comparative in INVENTORY:
        if comparative.workload.name == workload:
            authoritative = _text(comparative.workload.claim.question, f'inventory.{workload}.claim')
            if (
                'claim' in description
                and _text(description['claim'], f'dataset.targets.{workload}.claim') != authoritative
            ):
                raise HarnessError(f'{workload}: dataset claim differs from the authoritative inventory claim')
            return authoritative
    return _text(description.get('claim'), f'dataset.targets.{workload}.claim')


def _secondary(verdict: leadership.WorkloadVerdict) -> str:
    return ', '.join(f'{item.metric}: {item.outcome.value}' for item in verdict.secondary_verdicts) or '—'


def _summary_rows(
    dataset: dict[str, object], verdict: leadership.WorkloadVerdict, calibration: dict[str, object]
) -> list[list[str]]:
    entry = require_object(
        require_object(calibration.get('workloads'), 'calibration.workloads').get(verdict.workload),
        'calibration workload',
    )
    allowance = leadership.calibration_entry(entry, verdict.workload)[0]
    return [
        ['Claim', _claim(dataset, verdict.workload)],
        ['Status', verdict.status.value],
        ['Noise allowance', '—' if allowance is None else f'{allowance:.1%}'],
        ['Direct overhead', '—' if verdict.absolute_overhead is None else _signed_duration(verdict.absolute_overhead)],
        ['Absolute target', '—' if verdict.absolute_ceiling is None else _duration(verdict.absolute_ceiling)],
        ['Secondary verdict', _secondary(verdict)],
    ]


def _provenance(dataset: dict[str, object]) -> list[list[str]]:
    environment = require_object(dataset.get('environment'), 'dataset.environment')
    pins = require_object(dataset.get('pins'), 'dataset.pins')
    host_value = environment.get('host')
    if not isinstance(host_value, str):
        host = require_object(environment.get('host'), 'dataset.environment.host')
        host_text = ' '.join(
            (
                _text(host.get('system'), 'dataset.environment.host.system'),
                _text(host.get('machine'), 'dataset.environment.host.machine'),
                _text(host.get('cpu_model'), 'dataset.environment.host.cpu_model'),
            )
        )
    else:
        host_text = _text(host_value, 'dataset.environment.host')
    versions = ', '.join(
        f'{_text(name, "dataset.pins key")} {_text(pins[name], f"dataset.pins.{name}")}' for name in sorted(pins)
    )
    return [
        ['Source revision', _text(dataset.get('source_revision'), 'dataset.source_revision')],
        ['Harness revision', _text(dataset.get('harness_revision'), 'dataset.harness_revision')],
        ['Dependency versions', versions],
        ['Host', host_text],
        ['Collection command', _text(dataset.get('collection_command'), 'dataset.collection_command')],
    ]


def render(dataset: dict[str, object], calibration: dict[str, object], budgets: Path) -> str:
    """Render accepted comparison evidence using the leadership evaluator."""
    ordered_workloads = _workload_order(dataset)
    verdicts = {verdict.workload: verdict for verdict in leadership.evaluate(dataset, calibration, budgets)}
    lines = ['# Comparative performance evidence', '']
    for workload in ordered_workloads:
        verdict = verdicts[workload]
        lines += [f'## {_text(workload, "dataset.targets workload")}', '']
        lines += _table(('Measure', 'Result'), _summary_rows(dataset, verdict, calibration))
        lines += _table(
            ('Candidate', 'Classification', 'Reason', 'Candidate median', 'depin median', '95% CI vs depin'),
            _candidate_rows(dataset, workload, verdict),
        )
    lines += ['## Provenance', '']
    lines += _table(('Property', 'Value'), _provenance(dataset))
    return '\n'.join(lines).rstrip('\n') + '\n'


def _path(value: str) -> Path:
    candidate = Path(value)
    return candidate / comparison.COMPARISON_FILE if candidate.is_dir() else candidate


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='python -m benchmarks.harness.comparison_report', description=USAGE)
    parser.add_argument('dataset')
    parser.add_argument('--calibration', required=True)
    parser.add_argument('--budgets', required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Write a comparative performance report to stdout."""
    try:
        arguments = _arguments(argv)
        dataset = read_json(_path(require_text(arguments.dataset, 'DATASET')))
        calibration = read_json(Path(require_text(arguments.calibration, '--calibration')))
        _ = sys.stdout.write(render(dataset, calibration, Path(require_text(arguments.budgets, '--budgets'))))
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
