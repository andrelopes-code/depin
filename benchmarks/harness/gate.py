"""Turn a collected dataset into verdicts, and a verdict into an exit status.

    python -m benchmarks.harness.gate DIR --budgets benchmarks/budgets.toml

Latency is gated on the paired interval: fail when the interval's lower bound
exceeds the budget, inconclusive when the point estimate exceeds it but the lower
bound does not, pass otherwise. The deterministic metrics carry no interval, so
their point estimate decides on its own.

    0  every gated workload passed
    1  a regression, or an expected workload with no result
    2  the dataset or the budget file is malformed, or the command was misused
    3  inconclusive, or too few valid repetitions to conclude at all

An inconclusive verdict is a re-run at double the repetitions, decided outside this
command. Nothing here knows about that: given the same dataset, the same budgets
and the same seed, it reaches the same verdict every time.
"""

import argparse
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from benchmarks.contracts import Metric
from benchmarks.harness import (
    HarnessError,
    read_json,
    reduce,
    require_array,
    require_integer,
    require_number,
    require_object,
    require_text,
    stats,
)
from benchmarks.harness import budgets as budget_module
from benchmarks.harness.budgets import Budget, Outcome
from benchmarks.harness.pairs import BASE, DETERMINISTIC_FILE, ENVIRONMENT_FILE, HEAD, split_size

USAGE = 'python -m benchmarks.harness.gate DIR --budgets benchmarks/budgets.toml'
MINIMUM_REPETITIONS = 5
ALLOCATION_FIELDS = ('blocks', 'size')
EXIT_PASS = 0
EXIT_REGRESSION = 1
EXIT_MISUSE = 2
EXIT_INCONCLUSIVE = 3


@dataclass(frozen=True, slots=True)
class Verdict:
    """What the gate concluded about one workload under one metric, and why."""

    workload: str
    metric: str
    outcome: Outcome
    detail: str


def _index(path: Path) -> int:
    stem = path.stem
    if not stem.startswith('rep') or not stem[3:].isdigit():
        raise HarnessError(f'{path}: a repetition file is named rep<index>.json')
    return int(stem[3:])


def _repetitions(directory: Path) -> dict[int, dict[str, reduce.Aggregate]]:
    files = sorted(directory.glob('rep*.json'), key=_index)
    if not files:
        raise HarnessError(f'{directory}: carries no rep<index>.json; the side was never measured')
    loaded: dict[int, dict[str, reduce.Aggregate]] = {}
    for path in files:
        payload = read_json(path)
        index = require_integer(payload.get('repetition'), f'{path}: repetition')
        if index in loaded:
            raise HarnessError(f'{path}: repetition {index} appears twice')
        aggregates = require_object(payload.get('aggregates'), f'{path}: aggregates')
        if not aggregates:
            raise HarnessError(f'{path}: measured no workload')
        loaded[index] = reduce.decode_all(aggregates, str(path))
    return loaded


def _change(before: float, after: float) -> float:
    """Relative movement from `before` to `after`, on the scale a budget is written on."""
    if before == 0.0:
        return 0.0 if after == 0.0 else math.inf
    return after / before - 1.0


def _budget_for(available: Mapping[tuple[str, str], Budget], workload: str, metric: str) -> Budget:
    budget = available.get((workload, metric))
    if budget is None:
        raise HarnessError(
            f'{workload} is measured under {metric} on both sides but carries no budget; '
            'a workload without one is gated by nothing, so the budget file is incomplete'
        )
    return budget


def _subjects(aggregates: Mapping[str, reduce.Aggregate]) -> dict[str, reduce.Aggregate]:
    named = {reduce.subject_of(name): aggregate for name, aggregate in aggregates.items()}
    return {name: aggregate for name, aggregate in named.items() if name is not None}


def _latency(
    base: dict[int, dict[str, reduce.Aggregate]],
    head: dict[int, dict[str, reduce.Aggregate]],
    available: Mapping[tuple[str, str], Budget],
    *,
    seed: int,
) -> tuple[list[Verdict], list[str], list[str]]:
    measured_base = {index: _subjects(aggregates) for index, aggregates in base.items()}
    measured_head = {index: _subjects(aggregates) for index, aggregates in head.items()}
    base_names = {name for aggregates in measured_base.values() for name in aggregates}
    head_names = {name for aggregates in measured_head.values() for name in aggregates}
    removed = sorted(base_names - head_names)
    added = sorted(head_names - base_names)

    verdicts: list[Verdict] = []
    for name in sorted(base_names & head_names):
        before: list[float] = []
        after: list[float] = []
        excluded = 0
        for index in sorted(set(measured_base) & set(measured_head)):
            left, right = measured_base[index].get(name), measured_head[index].get(name)
            if left is None or right is None:
                continue
            if not reduce.qualifies(left) or not reduce.qualifies(right):
                excluded += 1
                continue
            before.append(left.median)
            after.append(right.median)

        budget = _budget_for(available, name, Metric.LATENCY.value)
        note = f'; {excluded} repetition(s) under the sample-quality minimum' if excluded else ''
        if len(before) < MINIMUM_REPETITIONS:
            verdicts.append(
                Verdict(
                    workload=name,
                    metric=Metric.LATENCY.value,
                    outcome=Outcome.NO_VERDICT,
                    detail=f'{len(before)} valid repetition(s), {MINIMUM_REPETITIONS} needed{note}',
                )
            )
            continue
        paired = stats.paired_ratio(before, after, seed=seed)
        verdicts.append(
            Verdict(
                workload=name,
                metric=Metric.LATENCY.value,
                outcome=budget_module.decide(budget, paired),
                detail=(
                    f'{paired.ratio:+.2%} [{paired.low:+.2%}, {paired.high:+.2%}] '
                    f'budget {budget.limit:.1%} n={paired.n}{note}'
                ),
            )
        )
    return verdicts, removed, added


def _numbers(payload: Mapping[str, object], section: str, where: str) -> dict[str, float]:
    values = require_object(payload.get(section, {}), f'{where}: {section}')
    return {name: require_number(value, f'{where}: {section}.{name}') for name, value in values.items()}


def _allocation_numbers(payload: Mapping[str, object], where: str) -> dict[str, dict[str, float]]:
    section = Metric.ALLOCATIONS.value
    values = require_object(payload.get(section, {}), f'{where}: {section}')
    counts: dict[str, dict[str, float]] = {}
    for name, value in values.items():
        fields = require_object(value, f'{where}: {section}.{name}')
        counts[name] = {
            field: require_number(fields.get(field), f'{where}: {section}.{name}.{field}')
            for field in ALLOCATION_FIELDS
        }
    return counts


def _curves(payload: Mapping[str, object], where: str) -> dict[str, list[float]]:
    section = Metric.SCALING.value
    values = require_object(payload.get(section, {}), f'{where}: {section}')
    curves: dict[str, list[float]] = {}
    for name, value in values.items():
        fields = require_object(value, f'{where}: {section}.{name}')
        sizes = require_array(fields.get('sizes'), f'{where}: {section}.{name}.sizes')
        costs = require_array(fields.get('costs'), f'{where}: {section}.{name}.costs')
        if len(sizes) != len(costs) or len(sizes) < 2:
            raise HarnessError(f'{where}: {section}.{name} needs at least two sizes, each with a cost')
        ordered = [require_number(cost, f'{where}: {section}.{name}.costs') for cost in costs]
        curves[name] = [later / earlier for earlier, later in pairwise(ordered)]
    return curves


def _exact(
    metric: str,
    base: Mapping[str, float],
    head: Mapping[str, float],
    available: Mapping[tuple[str, str], Budget],
) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for name in sorted(set(base) & set(head)):
        budget = _budget_for(available, name, metric)
        change = _change(base[name], head[name])
        verdicts.append(
            Verdict(
                workload=name,
                metric=metric,
                outcome=budget_module.decide_exact(budget, change),
                detail=f'{base[name]:g} -> {head[name]:g} ({change:+.2%}) budget {budget.limit:.1%}',
            )
        )
    return verdicts


def _allocations(
    before: Mapping[str, object],
    after: Mapping[str, object],
    base: Path,
    head: Path,
    available: Mapping[tuple[str, str], Budget],
) -> list[Verdict]:
    """One verdict per workload, decided by whichever of blocks and bytes moved worst."""
    counts_before = _allocation_numbers(before, str(base))
    counts_after = _allocation_numbers(after, str(head))
    verdicts: list[Verdict] = []
    for name in sorted(set(counts_before) & set(counts_after)):
        budget = _budget_for(available, name, Metric.ALLOCATIONS.value)
        changes = {field: _change(counts_before[name][field], counts_after[name][field]) for field in ALLOCATION_FIELDS}
        worst = max(changes, key=changes.__getitem__)
        verdicts.append(
            Verdict(
                workload=name,
                metric=Metric.ALLOCATIONS.value,
                outcome=budget_module.decide_exact(budget, changes[worst]),
                detail=(
                    f'{worst} {counts_before[name][worst]:g} -> {counts_after[name][worst]:g} '
                    f'({changes[worst]:+.2%}) budget {budget.limit:.1%}'
                ),
            )
        )
    return verdicts


def deterministic_verdicts(
    workload: str,
    metrics: Sequence[str],
    base: Mapping[str, object],
    head: Mapping[str, object],
    available: Mapping[tuple[str, str], Budget],
) -> tuple[Verdict, ...]:
    """Decide the deterministic evidence a comparative workload explicitly claims."""
    if len(metrics) != len(set(metrics)):
        raise HarnessError(f'{workload}: secondary deterministic metrics must not repeat')
    if Metric.LATENCY.value in metrics:
        raise HarnessError(f'{workload}: latency cannot be a secondary deterministic metric')

    verdicts: list[Verdict] = []
    for metric in metrics:
        if metric == Metric.ALLOCATIONS.value:
            counts_base = _allocation_numbers(base, 'base')
            counts_head = _allocation_numbers(head, 'head')
            allocation_before = counts_base.get(workload)
            allocation_after = counts_head.get(workload)
            if allocation_before is None or allocation_after is None:
                raise HarnessError(f'{workload}: allocations readings must be present on both base and head')
            budget = _budget_for(available, workload, Metric.ALLOCATIONS.value)
            changes = {field: _change(allocation_before[field], allocation_after[field]) for field in ALLOCATION_FIELDS}
            worst = max(changes, key=changes.__getitem__)
            verdicts.append(
                Verdict(workload, Metric.ALLOCATIONS.value, budget_module.decide_exact(budget, changes[worst]), worst)
            )
            work_base = _numbers(base, budget_module.WORK, 'base').get(workload)
            work_head = _numbers(head, budget_module.WORK, 'head').get(workload)
            if work_base is None or work_head is None:
                raise HarnessError(f'{workload}: allocations requires work readings on both base and head')
            work_budget = _budget_for(available, workload, budget_module.WORK)
            verdicts.append(
                Verdict(
                    workload,
                    budget_module.WORK,
                    budget_module.decide_exact(work_budget, _change(work_base, work_head)),
                    'work',
                )
            )
        elif metric == Metric.RETAINED.value:
            retained_before = _numbers(base, metric, 'base').get(workload)
            retained_after = _numbers(head, metric, 'head').get(workload)
            if retained_before is None or retained_after is None:
                raise HarnessError(f'{workload}: retained readings must be present on both base and head')
            budget = _budget_for(available, workload, metric)
            verdicts.append(
                Verdict(
                    workload,
                    metric,
                    budget_module.decide_exact(budget, _change(retained_before, retained_after)),
                    'retained',
                )
            )
        elif metric == Metric.SCALING.value:
            curve, _ = split_size(workload)
            scaling_before = _curves(base, 'base').get(curve)
            scaling_after = _curves(head, 'head').get(curve)
            if scaling_before is None or scaling_after is None:
                raise HarnessError(f'{workload}: scaling curve {curve} must be present on both base and head')
            if len(scaling_before) != len(scaling_after):
                raise HarnessError(f'{workload}: scaling curve {curve} has different size counts between base and head')
            budget = _budget_for(available, curve, metric)
            scaling_worst = max(_change(left, right) for left, right in zip(scaling_before, scaling_after, strict=True))
            verdicts.append(Verdict(curve, metric, budget_module.decide_exact(budget, scaling_worst), 'scaling'))
        else:
            raise HarnessError(f'{workload}: {metric!r} is not a deterministic secondary metric')
    return tuple(verdicts)


def _deterministic(base: Path, head: Path, available: Mapping[tuple[str, str], Budget]) -> list[Verdict]:
    before, after = read_json(base), read_json(head)
    verdicts: list[Verdict] = []
    for metric in (budget_module.WORK, Metric.RETAINED.value):
        verdicts += _exact(
            metric,
            _numbers(before, metric, str(base)),
            _numbers(after, metric, str(head)),
            available,
        )
    verdicts += _allocations(before, after, base, head, available)

    curves_before, curves_after = _curves(before, str(base)), _curves(after, str(head))
    for name in sorted(set(curves_before) & set(curves_after)):
        budget = _budget_for(available, name, Metric.SCALING.value)
        if len(curves_before[name]) != len(curves_after[name]):
            raise HarnessError(f'{name}: the two sides measured a different number of sizes')
        worst = max(
            _change(earlier, later) for earlier, later in zip(curves_before[name], curves_after[name], strict=True)
        )
        verdicts.append(
            Verdict(
                workload=name,
                metric=Metric.SCALING.value,
                outcome=budget_module.decide_exact(budget, worst),
                detail=f'worst size-to-size growth {worst:+.2%} budget {budget.limit:.1%}',
            )
        )
    return verdicts


def _status(verdicts: Sequence[Verdict], missing: Sequence[str]) -> int:
    outcomes = {verdict.outcome for verdict in verdicts}
    if missing or Outcome.FAIL in outcomes:
        return EXIT_REGRESSION
    if Outcome.INCONCLUSIVE in outcomes or Outcome.NO_VERDICT in outcomes:
        return EXIT_INCONCLUSIVE
    return EXIT_PASS


def _ordering(verdict: Verdict) -> tuple[str, str]:
    """Metric first, then workload, so a run's output is diffable against another's."""
    return (verdict.metric, verdict.workload)


def run(dataset: Path, budget_file: Path, *, expected: Sequence[str] = (), seed: int | None = None) -> int:
    """Gate `dataset` against `budget_file` and report to stdout."""
    available = budget_module.load(budget_file)
    metadata = read_json(dataset / ENVIRONMENT_FILE)
    chosen = require_integer(metadata.get('seed'), f'{dataset / ENVIRONMENT_FILE}: seed') if seed is None else seed

    base = _repetitions(dataset / BASE)
    head = _repetitions(dataset / HEAD)
    verdicts, removed, added = _latency(base, head, available, seed=chosen)
    verdicts += _deterministic(dataset / BASE / DETERMINISTIC_FILE, dataset / HEAD / DETERMINISTIC_FILE, available)

    gated = {verdict.workload for verdict in verdicts}
    missing = sorted(name for name in expected if name not in gated)

    for name in added:
        _ = sys.stdout.write(f'new         {name}: no base measurement, not gated\n')
    for name in removed:
        _ = sys.stdout.write(f'removed     {name}: no longer measured\n')
    for verdict in sorted(verdicts, key=_ordering):
        _ = sys.stdout.write(f'{verdict.outcome.value:<11} {verdict.metric:<12} {verdict.workload}: {verdict.detail}\n')
    for name in missing:
        _ = sys.stderr.write(f'{name} is expected by the inventory and has no result in either side\n')
    return _status(verdicts, missing)


def _arguments(argv: Sequence[str] | None) -> dict[str, object]:
    parser = argparse.ArgumentParser(prog='python -m benchmarks.harness.gate', description=USAGE)
    parser.add_argument('dataset', help='the directory python -m benchmarks.harness.pairs wrote')
    parser.add_argument('--budgets', required=True, help='the budget file every gated workload is measured against')
    parser.add_argument('--seed', type=int, help="override the dataset's bootstrap seed")
    parser.add_argument('--expect', action='append', help='a workload the run must carry a result for; repeatable')
    return dict(vars(parser.parse_args(argv)))


def main(argv: Sequence[str] | None = None) -> int:
    try:
        chosen = _arguments(argv)
        expected = chosen['expect']
        seed = chosen['seed']
        return run(
            Path(require_text(chosen['dataset'], 'DIR')),
            Path(require_text(chosen['budgets'], '--budgets')),
            expected=[require_text(name, '--expect') for name in require_array(expected, '--expect')]
            if expected is not None
            else (),
            seed=None if seed is None else require_integer(seed, '--seed'),
        )
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return EXIT_MISUSE


if __name__ == '__main__':
    raise SystemExit(main())
