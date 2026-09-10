"""Formal acceptance gate for the FastAPI minimum-overhead evidence."""

import argparse
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

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
from benchmarks.harness.budgets import Outcome

ATTRIBUTION_WORKLOAD = 'fastapi_cpu_light_endpoint'
TAIL_WORKLOADS = (
    'fastapi_cpu_light_endpoint',
    'fastapi_request_scoped_graph',
    'fastapi_singletons_and_transients',
    'fastapi_async_resource_teardown',
    'fastapi_endpoint_with_work',
    'fastapi_application_startup',
)
CHECK_NO_INJECTION = 'no_injection'
CHECK_RETAINED_MEMORY = 'retained_memory'
CHECK_PEAK_MEMORY = 'peak_memory'
CHECK_ALLOCATION = 'allocations'
CHECK_STARTUP = 'application_startup'
CHECK_CONTENTION = 'contention'
REQUIRED_CHECKS = (
    CHECK_NO_INJECTION,
    CHECK_RETAINED_MEMORY,
    CHECK_PEAK_MEMORY,
    CHECK_ALLOCATION,
    CHECK_STARTUP,
    CHECK_CONTENTION,
)
REPETITIONS = 5
TAIL_LIMIT = 0.05
ATTRIBUTION_LIMIT = -0.25
ATTRIBUTION_TARGET = -0.30
SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Verdict:
    """One explicit FastAPI acceptance criterion and its result."""

    criterion: str
    outcome: Outcome
    detail: str
    scope: str = 'paired'
    required: bool = True


@dataclass(frozen=True, slots=True)
class Acceptance:
    """The deterministic result of evaluating one FastAPI evidence bundle."""

    verdicts: tuple[Verdict, ...]
    head_only: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(verdict.outcome is Outcome.PASS for verdict in self.verdicts if verdict.required)


@dataclass(frozen=True, slots=True)
class _Pair:
    repetition: int
    base: reduce.Aggregate
    head: reduce.Aggregate


def _finite_positive(value: float, where: str) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise HarnessError(f'{where}: expected a finite positive number, found {value!r}')
    return value


def _side_repetitions(dataset: Path, side: str) -> dict[int, dict[str, reduce.Aggregate]]:
    directory = dataset / side
    paths = sorted(directory.glob('rep*.json'))
    found: dict[int, dict[str, reduce.Aggregate]] = {}
    for path in paths:
        payload = read_json(path)
        repetition = require_integer(payload.get('repetition'), f'{path}: repetition')
        if repetition in found:
            raise HarnessError(f'{path}: repetition {repetition} appears twice')
        first = require_text(payload.get('first'), f'{path}: first')
        expected = 'base' if repetition % 2 == 0 else 'head'
        if first != expected:
            raise HarnessError(f'{path}: repetition {repetition} must run {expected} first, found {first!r}')
        aggregates = require_object(payload.get('aggregates'), f'{path}: aggregates')
        found[repetition] = reduce.decode_all(aggregates, str(path))
    expected_indexes = set(range(REPETITIONS))
    if set(found) != expected_indexes:
        raise HarnessError(f'{directory}: requires exactly {REPETITIONS} repetitions numbered 0 through 4')
    return found


def _pairs(dataset: Path) -> tuple[dict[str, tuple[_Pair, ...]], int]:
    metadata = read_json(dataset / 'environment.json')
    seed = require_integer(metadata.get('seed'), f'{dataset / "environment.json"}: seed')
    base, head = _side_repetitions(dataset, 'base'), _side_repetitions(dataset, 'head')
    pairs: dict[str, tuple[_Pair, ...]] = {}
    for workload in TAIL_WORKLOADS:
        collected: list[_Pair] = []
        for repetition in range(REPETITIONS):
            before, after = base[repetition].get(workload), head[repetition].get(workload)
            if before is None or after is None:
                raise HarnessError(f'{workload}: missing from repetition {repetition} on base or head')
            if not reduce.qualifies(before) or not reduce.qualifies(after):
                raise HarnessError(f'{workload}: repetition {repetition} does not meet the sample-quality minimum')
            collected.append(_Pair(repetition, before, after))
        pairs[workload] = tuple(collected)
    return pairs, seed


def _attribution(path: Path, pairs: Sequence[_Pair], seed: int) -> tuple[Verdict, Verdict]:
    payload = read_json(path)
    version = require_integer(payload.get('schema_version'), f'{path}: schema_version')
    if version != SCHEMA_VERSION:
        raise HarnessError(f'{path}: unsupported schema version {version}; expected {SCHEMA_VERSION}')
    workload = require_text(payload.get('workload'), f'{path}: workload')
    if workload != ATTRIBUTION_WORKLOAD:
        raise HarnessError(f'{path}: workload must be {ATTRIBUTION_WORKLOAD!r}, found {workload!r}')
    entries = require_array(payload.get('repetitions'), f'{path}: repetitions')
    if len(entries) != REPETITIONS:
        raise HarnessError(f'{path}: requires exactly {REPETITIONS} direct-baseline repetitions')
    direct: dict[int, tuple[float, float]] = {}
    for position, entry in enumerate(entries):
        fields = require_object(entry, f'{path}: repetitions[{position}]')
        repetition = require_integer(fields.get('repetition'), f'{path}: repetitions[{position}].repetition')
        if repetition in direct:
            raise HarnessError(f'{path}: repetition {repetition} appears twice')
        direct[repetition] = (
            _finite_positive(require_number(fields.get('base_direct_p50'), f'{path}: base_direct_p50'), str(path)),
            _finite_positive(require_number(fields.get('head_direct_p50'), f'{path}: head_direct_p50'), str(path)),
        )
    if set(direct) != set(range(REPETITIONS)):
        raise HarnessError(f'{path}: direct-baseline repetitions must be numbered 0 through 4')
    base_overhead: list[float] = []
    head_overhead: list[float] = []
    for pair in pairs:
        base_direct, head_direct = direct[pair.repetition]
        before = pair.base.median - base_direct
        after = pair.head.median - head_direct
        base_overhead.append(_finite_positive(before, f'{path}: repetition {pair.repetition} base attributable p50'))
        head_overhead.append(_finite_positive(after, f'{path}: repetition {pair.repetition} head attributable p50'))
    paired = stats.paired_ratio(base_overhead, head_overhead, seed=seed)
    detail = f'{paired.ratio:+.2%} [{paired.low:+.2%}, {paired.high:+.2%}] n={paired.n}'
    acceptance = Outcome.PASS if paired.high <= ATTRIBUTION_LIMIT else Outcome.FAIL
    stretch = Outcome.PASS if paired.ratio <= ATTRIBUTION_TARGET else Outcome.FAIL
    return (
        Verdict('cpu-light-attributable-p50', acceptance, f'{detail} upper bound must be <= {ATTRIBUTION_LIMIT:+.0%}'),
        Verdict(
            'cpu-light-attributable-p50-stretch',
            stretch,
            f'{detail} point target is <= {ATTRIBUTION_TARGET:+.0%}',
            required=False,
        ),
    )


def _tails(pairs: Mapping[str, Sequence[_Pair]]) -> tuple[Verdict, ...]:
    verdicts: list[Verdict] = []
    for workload in TAIL_WORKLOADS:
        for field, label in (('p95', 'p95-total'), ('p99', 'p99-total')):
            base: list[float] = []
            head: list[float] = []
            for pair in pairs[workload]:
                before = getattr(pair.base, field)
                after = getattr(pair.head, field)
                if before is None or after is None:
                    raise HarnessError(f'{workload}: {field} is missing from repetition {pair.repetition}')
                base.append(_finite_positive(before, f'{workload}: base {field}'))
                head.append(_finite_positive(after, f'{workload}: head {field}'))
            paired = stats.paired_ratio(base, head, seed=0)
            outcome = Outcome.PASS if paired.ratio <= TAIL_LIMIT else Outcome.FAIL
            verdicts.append(
                Verdict(
                    f'{workload}:{label}',
                    outcome,
                    f'{paired.ratio:+.2%} total-latency change must be <= {TAIL_LIMIT:+.0%} n={paired.n}',
                )
            )
    return tuple(verdicts)


def _change(base: float, head: float, criterion: str) -> float:
    _finite_positive(base, f'{criterion}: base')
    _finite_positive(head, f'{criterion}: head')
    return head / base - 1.0


def _sidecars(path: Path) -> tuple[Verdict, ...]:
    payload = read_json(path)
    version = require_integer(payload.get('schema_version'), f'{path}: schema_version')
    if version != SCHEMA_VERSION:
        raise HarnessError(f'{path}: unsupported schema version {version}; expected {SCHEMA_VERSION}')
    entries = require_array(payload.get('checks'), f'{path}: checks')
    parsed: dict[str, Verdict] = {}
    head_only: set[str] = set()
    for position, entry in enumerate(entries):
        fields = require_object(entry, f'{path}: checks[{position}]')
        criterion = require_text(fields.get('criterion'), f'{path}: checks[{position}].criterion')
        if criterion in parsed:
            raise HarnessError(f'{path}: criterion {criterion!r} appears twice')
        scope = require_text(fields.get('scope'), f'{path}: checks[{position}].scope')
        if scope not in {'paired', 'head-only'}:
            raise HarnessError(f'{path}: {criterion}: scope must be paired or head-only')
        if scope == 'head-only':
            head_only.add(criterion)
        limit = require_number(fields.get('limit'), f'{path}: {criterion}.limit')
        if not math.isfinite(limit) or limit < 0.0:
            raise HarnessError(f'{path}: {criterion}.limit must be finite and non-negative')
        change = _change(
            require_number(fields.get('base'), f'{path}: {criterion}.base'),
            require_number(fields.get('head'), f'{path}: {criterion}.head'),
            criterion,
        )
        parsed[criterion] = Verdict(
            criterion,
            Outcome.PASS if change <= limit else Outcome.FAIL,
            f'{change:+.2%} budget {limit:+.2%}',
            scope=scope,
        )
    for criterion in REQUIRED_CHECKS:
        if criterion not in parsed:
            scope = 'head-only' if criterion == CHECK_NO_INJECTION else 'paired'
            parsed[criterion] = Verdict(
                criterion, Outcome.NO_VERDICT, 'required sidecar evidence is missing', scope=scope
            )
    if not any(criterion.startswith('component:') for criterion in head_only):
        parsed['components'] = Verdict(
            'components', Outcome.NO_VERDICT, 'head-only component sidecar evidence is missing', scope='head-only'
        )
    return tuple(parsed[criterion] for criterion in sorted(parsed))


def evaluate(dataset: Path, attribution: Path, sidecars: Path) -> Acceptance:
    """Evaluate the fixed FastAPI acceptance criteria from collected evidence."""
    pairs, seed = _pairs(dataset)
    verdicts = (*_attribution(attribution, pairs[ATTRIBUTION_WORKLOAD], seed), *_tails(pairs), *_sidecars(sidecars))
    ordered = tuple(sorted(verdicts, key=lambda verdict: verdict.criterion))
    head_only = tuple(sorted(verdict.criterion for verdict in ordered if verdict.scope == 'head-only'))
    return Acceptance(ordered, head_only)


def run(dataset: Path, attribution: Path, sidecars: Path) -> int:
    """Print the acceptance verdict and return its shell status."""
    acceptance = evaluate(dataset, attribution, sidecars)
    for verdict in acceptance.verdicts:
        marker = 'required' if verdict.required else 'target'
        print(f'{verdict.outcome.value:12} {marker:8} {verdict.scope:9} {verdict.criterion}: {verdict.detail}')
    return 0 if acceptance.passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the FastAPI acceptance evaluator as a command-line program."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--attribution', type=Path, required=True)
    parser.add_argument('--sidecars', type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        return run(arguments.dataset, arguments.attribution, arguments.sidecars)
    except HarnessError as error:
        print(f'misuse: {error}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
