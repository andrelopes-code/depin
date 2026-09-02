"""The budget file, the floors a budget may not go under, and the decision rule.

A uniform threshold cannot be right: per-benchmark dispersion spans 0.9% to 7.0%,
so one number is simultaneously too loose for the quiet workloads and too tight
for the noisy one. Budgets are therefore per workload, derived from that
workload's measured paired null:

    limit = max(class floor, 2 x measured paired null p99)

Two rules make the file evidence rather than configuration. A budget carries the
measurement that justifies it, and a budget below its noise class floor is
refused — which is what stops a failing pull request being made green by editing
a number.
"""

import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from benchmarks.contracts import Metric, NoiseClass
from benchmarks.harness import HarnessError, require_array, require_number, require_object, require_text
from benchmarks.harness.stats import Paired

CLASS_FLOORS: dict[NoiseClass, float] = {
    NoiseClass.LOW: 0.05,
    NoiseClass.MEDIUM: 0.08,
    NoiseClass.HIGH: 0.15,
}

WORK = 'work'
EXACT_METRICS = frozenset({WORK, Metric.ALLOCATIONS.value})
METRIC_CEILINGS: dict[str, float] = {Metric.RETAINED.value: 0.02, Metric.SCALING.value: 0.15}
METRICS = frozenset({Metric.LATENCY.value}) | EXACT_METRICS | frozenset(METRIC_CEILINGS)


class Outcome(Enum):
    """What the gate concluded about one workload under one metric."""

    PASS = 'pass'
    FAIL = 'fail'
    INCONCLUSIVE = 'inconclusive'
    NO_VERDICT = 'no-verdict'


@dataclass(frozen=True, slots=True)
class Budget:
    """How much a workload is allowed to move, and the measurement that allows it."""

    workload: str
    metric: str
    limit: float
    noise: NoiseClass
    justification: str


def _noise(value: object, where: str) -> NoiseClass:
    text = require_text(value, where)
    try:
        return NoiseClass(text)
    except ValueError as error:
        classes = ', '.join(sorted(member.value for member in NoiseClass))
        raise HarnessError(f'{where}: {text!r} is not a noise class; expected one of {classes}') from error


def _check_limit(budget: Budget, where: str) -> None:
    """Refuse a limit the evidence does not support.

    Latency carries a floor because a budget under its workload's own noise band
    fails on noise. The deterministic metrics carry the opposite constraint: work
    and allocation counts may not increase at all, and retained memory and scaling
    ratios carry a ceiling, so neither can be widened into meaninglessness.
    """
    if budget.limit < 0.0:
        raise HarnessError(f'{where}: a limit of {budget.limit} is negative')
    if budget.metric == Metric.LATENCY.value:
        floor = CLASS_FLOORS[budget.noise]
        if budget.limit < floor:
            raise HarnessError(
                f'{where}: a limit of {budget.limit:.1%} is below the {budget.noise.value} noise floor of {floor:.0%}; '
                'a budget under its own workload band fails on noise, so the floor is not negotiable'
            )
        return
    if budget.metric in EXACT_METRICS and budget.limit != 0.0:
        raise HarnessError(
            f'{where}: {budget.metric} is deterministic and may not increase at all, so its limit must be 0, '
            f'not {budget.limit}'
        )
    ceiling = METRIC_CEILINGS.get(budget.metric)
    if ceiling is not None and budget.limit > ceiling:
        raise HarnessError(
            f'{where}: a limit of {budget.limit:.1%} exceeds the {budget.metric} ceiling of {ceiling:.0%}'
        )


def _budget(entry: object, where: str) -> Budget:
    fields = require_object(entry, where)
    workload = require_text(fields.get('workload'), f'{where}.workload')
    metric = require_text(fields.get('metric'), f'{where}.metric')
    if metric not in METRICS:
        raise HarnessError(
            f'{where}.metric: {metric!r} is not a gated metric; expected one of {", ".join(sorted(METRICS))}'
        )
    budget = Budget(
        workload=workload,
        metric=metric,
        limit=require_number(fields.get('limit'), f'{where}.limit'),
        noise=_noise(fields.get('noise'), f'{where}.noise'),
        justification=require_text(fields.get('justification'), f'{where}.justification'),
    )
    _check_limit(budget, where)
    return budget


def load(path: Path) -> dict[tuple[str, str], Budget]:
    """Read the budget file, keyed by workload and metric.

    Raises:
        HarnessError: the file is unreadable or is not TOML; it carries no
            `budget` array; an entry is missing a field, names a metric or noise
            class that does not exist, repeats a workload and metric, or states a
            limit its metric does not allow.
    """
    try:
        contents = path.read_text(encoding='utf-8')
    except OSError as error:
        raise HarnessError(f'{path}: cannot be read ({error})') from error
    try:
        document = dict(tomllib.loads(contents))
    except tomllib.TOMLDecodeError as error:
        raise HarnessError(f'{path}: is not TOML ({error})') from error

    entries = require_array(document.get('budget'), f'{path}: "budget"')
    if not entries:
        raise HarnessError(f'{path}: "budget" is empty; nothing would be gated')

    loaded: dict[tuple[str, str], Budget] = {}
    for index, entry in enumerate(entries):
        budget = _budget(entry, f'{path}: budget[{index}]')
        key = (budget.workload, budget.metric)
        if key in loaded:
            raise HarnessError(f'{path}: two budgets for {budget.workload} under {budget.metric}')
        loaded[key] = budget
    return loaded


def decide(budget: Budget, paired: Paired) -> Outcome:
    """The latency rule: fail on the interval, not on the point estimate.

    Failing only once the *lower* bound clears the budget is deliberately
    conservative. On a shared runner a blocking gate that cries wolf is turned off
    within a month, and the deterministic gates carry the sensitivity this rule
    gives up.
    """
    if paired.low > budget.limit:
        return Outcome.FAIL
    if paired.ratio > budget.limit:
        return Outcome.INCONCLUSIVE
    return Outcome.PASS


def decide_exact(budget: Budget, change: float) -> Outcome:
    """The deterministic rule: a count carries no interval, so the point estimate decides."""
    return Outcome.FAIL if change > budget.limit else Outcome.PASS
