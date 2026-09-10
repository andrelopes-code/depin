"""Formal acceptance gate for the FastAPI minimum-overhead evidence."""

import argparse
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

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
from benchmarks.harness.pairs import DEFAULT_SEED as PAIRS_DEFAULT_SEED

ATTRIBUTION_WORKLOAD = 'fastapi_cpu_light_endpoint'
BASELINE_REVISION = '086adf98459773e3175f4723b2b64e3f47306e42'
DEFAULT_SEED: Final = PAIRS_DEFAULT_SEED
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
COMPONENT_WORKLOADS = (
    'fastapi_lazy_host_publication',
    'fastapi_lazy_frame_activation_and_drain',
    'fastapi_endpoint_program_one_key',
    'fastapi_endpoint_program_many_keys',
    'fastapi_request_seed_read',
    'fastapi_async_resource_close',
)
REPETITIONS = 5
TAIL_LIMIT = 0.05
ATTRIBUTION_LIMIT = -0.25
ATTRIBUTION_TARGET = -0.30
SCHEMA_VERSION = 1
EXIT_PASS = 0
EXIT_REGRESSION = 1
EXIT_MISUSE = 2
EXIT_INCONCLUSIVE = 3


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
    if seed != DEFAULT_SEED:
        raise HarnessError(f'{dataset / "environment.json"}: seed must be the protocol constant {DEFAULT_SEED}')
    repetitions = require_integer(metadata.get('repetitions'), f'{dataset / "environment.json"}: repetitions')
    if repetitions != REPETITIONS:
        raise HarnessError(f'{dataset / "environment.json"}: repetitions must be exactly {REPETITIONS}')
    environment = require_object(metadata.get('environment'), f'{dataset / "environment.json"}: environment')
    interpreter = require_object(
        environment.get('interpreter'), f'{dataset / "environment.json"}: environment.interpreter'
    )
    for field in ('implementation', 'version', 'compiler'):
        _ = require_text(interpreter.get(field), f'{dataset / "environment.json"}: environment.interpreter.{field}')
    host = require_object(environment.get('host'), f'{dataset / "environment.json"}: environment.host')
    for field in ('system', 'release', 'machine'):
        _ = require_text(host.get(field), f'{dataset / "environment.json"}: environment.host.{field}')
    if (
        require_integer(
            host.get('available_processors'), f'{dataset / "environment.json"}: environment.host.available_processors'
        )
        < 1
    ):
        raise HarnessError(f'{dataset / "environment.json"}: environment.host.available_processors must be positive')
    distributions = require_object(
        environment.get('distributions'), f'{dataset / "environment.json"}: environment.distributions'
    )
    for package in ('pydepin', 'pytest', 'pytest-benchmark'):
        _ = require_text(
            distributions.get(package), f'{dataset / "environment.json"}: environment.distributions.{package}'
        )
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


def _attribution(
    path: Path, pairs: Sequence[_Pair], seed: int, evaluated_head_revision: str
) -> tuple[Verdict, Verdict]:
    payload = read_json(path)
    version = require_integer(payload.get('schema_version'), f'{path}: schema_version')
    if version != SCHEMA_VERSION:
        raise HarnessError(f'{path}: unsupported schema version {version}; expected {SCHEMA_VERSION}')
    if _revision(payload.get('baseline_revision'), f'{path}: baseline_revision') != BASELINE_REVISION:
        raise HarnessError(f'{path}: baseline_revision must be {BASELINE_REVISION}')
    if _revision(payload.get('head_revision'), f'{path}: head_revision') != evaluated_head_revision:
        raise HarnessError(f'{path}: head_revision does not match the evaluated head revision')
    workload = require_text(payload.get('workload'), f'{path}: workload')
    if workload != ATTRIBUTION_WORKLOAD:
        raise HarnessError(f'{path}: workload must be {ATTRIBUTION_WORKLOAD!r}, found {workload!r}')
    if require_text(payload.get('metric'), f'{path}: metric') != 'p50':
        raise HarnessError(f'{path}: metric must be p50')
    if require_text(payload.get('unit'), f'{path}: unit') != 'seconds per operation':
        raise HarnessError(f'{path}: unit must be seconds per operation')
    if require_text(payload.get('method'), f'{path}: method') != 'direct-request-p50':
        raise HarnessError(f'{path}: method must be direct-request-p50')
    if require_text(payload.get('scope'), f'{path}: scope') != 'paired':
        raise HarnessError(f'{path}: scope must be paired')
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


def _revision(value: object, where: str) -> str:
    revision = require_text(value, where)
    if re.fullmatch(r'[0-9a-f]{40}', revision) is None:
        raise HarnessError(f'{where}: expected a full lowercase Git SHA')
    return revision


def _provenance(path: Path, evaluated_head_revision: str) -> None:
    payload = read_json(path)
    if require_integer(payload.get('schema_version'), f'{path}: schema_version') != SCHEMA_VERSION:
        raise HarnessError(f'{path}: unsupported schema version')
    if _revision(payload.get('baseline_revision'), f'{path}: baseline_revision') != BASELINE_REVISION:
        raise HarnessError(f'{path}: baseline_revision must be {BASELINE_REVISION}')
    head = _revision(payload.get('head_revision'), f'{path}: head_revision')
    if head != _revision(evaluated_head_revision, 'evaluated head revision'):
        raise HarnessError(f'{path}: head_revision does not match the evaluated head revision')
    protocol = require_object(payload.get('protocol'), f'{path}: protocol')
    if require_text(protocol.get('collector'), f'{path}: protocol.collector') != 'benchmarks.harness.pairs':
        raise HarnessError(f'{path}: protocol.collector must be benchmarks.harness.pairs')
    if require_integer(protocol.get('repetitions'), f'{path}: protocol.repetitions') != REPETITIONS:
        raise HarnessError(f'{path}: protocol.repetitions must be exactly {REPETITIONS}')
    if require_integer(protocol.get('seed'), f'{path}: protocol.seed') != DEFAULT_SEED:
        raise HarnessError(f'{path}: protocol.seed must be {DEFAULT_SEED}')
    if protocol.get('locked_environments') is not True:
        raise HarnessError(f'{path}: protocol.locked_environments must be true')
    workloads = require_array(protocol.get('workloads'), f'{path}: protocol.workloads')
    if tuple(require_text(value, f'{path}: protocol.workloads') for value in workloads) != TAIL_WORKLOADS:
        raise HarnessError(f'{path}: protocol.workloads must exactly match the FastAPI paired inventory')
    environment = require_object(payload.get('environment'), f'{path}: environment')
    interpreter = require_object(environment.get('interpreter'), f'{path}: environment.interpreter')
    for field in ('implementation', 'version'):
        _ = require_text(interpreter.get(field), f'{path}: environment.interpreter.{field}')
    cpu = require_object(environment.get('cpu'), f'{path}: environment.cpu')
    _ = require_text(cpu.get('model'), f'{path}: environment.cpu.model')
    for field in ('kernel', 'governor'):
        _ = require_text(environment.get(field), f'{path}: environment.{field}')
    affinity = require_array(environment.get('affinity'), f'{path}: environment.affinity')
    if not affinity:
        raise HarnessError(f'{path}: environment.affinity must not be empty')
    for index, processor in enumerate(affinity):
        if require_integer(processor, f'{path}: environment.affinity[{index}]') < 0:
            raise HarnessError(f'{path}: environment.affinity[{index}] must be non-negative')
    packages = require_object(environment.get('packages'), f'{path}: environment.packages')
    for package in ('pydepin', 'pytest', 'pytest-benchmark', 'fastapi', 'starlette'):
        _ = require_text(packages.get(package), f'{path}: environment.packages.{package}')
    _ = _revision(environment.get('harness_revision'), f'{path}: environment.harness_revision')
    command = require_array(environment.get('collection_command'), f'{path}: environment.collection_command')
    if not command:
        raise HarnessError(f'{path}: environment.collection_command must not be empty')
    for index, argument in enumerate(command):
        _ = require_text(argument, f'{path}: environment.collection_command[{index}]')
    locked_environment = require_object(
        environment.get('locked_environment'), f'{path}: environment.locked_environment'
    )
    for side in ('base', 'head'):
        _ = require_text(locked_environment.get(side), f'{path}: environment.locked_environment.{side}')
    validations = require_array(payload.get('semantic_validation'), f'{path}: semantic_validation')
    proven: set[tuple[str, int]] = set()
    for index, value in enumerate(validations):
        validation = require_object(value, f'{path}: semantic_validation[{index}]')
        workload = require_text(validation.get('workload'), f'{path}: semantic_validation[{index}].workload')
        repetition = require_integer(validation.get('repetition'), f'{path}: semantic_validation[{index}].repetition')
        if (
            _revision(validation.get('base_revision'), f'{path}: semantic_validation[{index}].base_revision')
            != BASELINE_REVISION
        ):
            raise HarnessError(f'{path}: semantic_validation[{index}].base_revision does not match the baseline')
        if (
            _revision(validation.get('head_revision'), f'{path}: semantic_validation[{index}].head_revision')
            != evaluated_head_revision
        ):
            raise HarnessError(f'{path}: semantic_validation[{index}].head_revision does not match the evaluated head')
        if validation.get('response') != 'equivalent' or validation.get('lifecycle') != 'equivalent':
            raise HarnessError(f'{path}: {workload} lacks equivalent response and lifecycle validation')
        counts = require_object(validation.get('event_counts'), f'{path}: semantic_validation[{index}].event_counts')
        base_events = require_integer(counts.get('base'), f'{path}: semantic_validation[{index}].event_counts.base')
        head_events = require_integer(counts.get('head'), f'{path}: semantic_validation[{index}].event_counts.head')
        if base_events < 0 or head_events < 0 or base_events != head_events:
            raise HarnessError(f'{path}: semantic_validation[{index}].event_counts must be equal non-negative counts')
        if validation.get('teardown') != 'equivalent' or validation.get('deterministic') != 'passed':
            raise HarnessError(f'{path}: {workload} lacks teardown or deterministic validation')
        key = (workload, repetition)
        if key in proven:
            raise HarnessError(f'{path}: semantic_validation repeats {workload} repetition {repetition}')
        proven.add(key)
    expected = {(workload, repetition) for workload in TAIL_WORKLOADS for repetition in range(REPETITIONS)}
    if proven != expected or len(validations) != len(expected):
        raise HarnessError(f'{path}: semantic_validation must cover every FastAPI workload and repetition exactly once')


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
            verdicts.append(_regression_verdict(f'{workload}:{label}', base, head, TAIL_LIMIT))
    return tuple(verdicts)


def _change(base: float, head: float, criterion: str) -> float:
    _finite_positive(base, f'{criterion}: base')
    _finite_positive(head, f'{criterion}: head')
    return head / base - 1.0


def _series(value: object, where: str) -> list[float]:
    readings = require_array(value, where)
    if len(readings) != REPETITIONS:
        raise HarnessError(f'{where}: requires exactly {REPETITIONS} paired observations')
    return [
        _finite_positive(require_number(reading, f'{where}[{index}]'), where) for index, reading in enumerate(readings)
    ]


def _regression_verdict(
    criterion: str, base: Sequence[float], head: Sequence[float], limit: float, scope: str = 'paired'
) -> Verdict:
    paired = stats.paired_ratio(base, head, seed=DEFAULT_SEED)
    if paired.low > limit:
        outcome = Outcome.FAIL
    elif paired.high <= limit:
        outcome = Outcome.PASS
    else:
        outcome = Outcome.INCONCLUSIVE
    return Verdict(
        criterion,
        outcome,
        f'{paired.ratio:+.2%} [{paired.low:+.2%}, {paired.high:+.2%}] budget {limit:+.2%} n={paired.n}',
        scope,
    )


def _typed_check(
    fields: Mapping[str, object], path: Path, criterion: str, expected: tuple[str, str, str, str, str]
) -> Verdict:
    for field, value in zip(('workload', 'metric', 'unit', 'method', 'scope'), expected, strict=True):
        if require_text(fields.get(field), f'{path}: {criterion}.{field}') != value:
            raise HarnessError(f'{path}: {criterion}.{field} must be {value!r}')
    limit = require_number(fields.get('limit'), f'{path}: {criterion}.limit')
    if not math.isfinite(limit) or limit < 0.0:
        raise HarnessError(f'{path}: {criterion}.limit must be finite and non-negative')
    before, after = (
        (
            _series(fields.get('direct'), f'{path}: {criterion}.direct'),
            _series(fields.get('depin'), f'{path}: {criterion}.depin'),
        )
        if criterion == CHECK_NO_INJECTION
        else (
            _series(fields.get('base'), f'{path}: {criterion}.base'),
            _series(fields.get('head'), f'{path}: {criterion}.head'),
        )
    )
    if criterion == CHECK_ALLOCATION:
        changes = [_change(left, right, criterion) for left, right in zip(before, after, strict=True)]
        worst = max(changes)
        return Verdict(
            criterion,
            Outcome.PASS if worst <= limit else Outcome.FAIL,
            f'worst paired change {worst:+.2%} budget {limit:+.2%} n={len(changes)}',
            expected[4],
        )
    return _regression_verdict(criterion, before, after, limit, expected[4])


def _sidecars(path: Path, pairs: Mapping[str, Sequence[_Pair]]) -> tuple[Verdict, ...]:
    payload = read_json(path)
    version = require_integer(payload.get('schema_version'), f'{path}: schema_version')
    if version != SCHEMA_VERSION:
        raise HarnessError(f'{path}: unsupported schema version {version}; expected {SCHEMA_VERSION}')
    specifications = {
        CHECK_NO_INJECTION: ('fastapi_no_injection', 'latency', 'seconds per operation', 'direct-null', 'head-only'),
        CHECK_RETAINED_MEMORY: (ATTRIBUTION_WORKLOAD, 'retained', 'bytes', 'tracemalloc-retained', 'paired'),
        CHECK_PEAK_MEMORY: (ATTRIBUTION_WORKLOAD, 'peak-memory', 'bytes', 'tracemalloc-peak', 'paired'),
        CHECK_ALLOCATION: (
            ATTRIBUTION_WORKLOAD,
            'allocations',
            'allocation-count',
            'tracemalloc-allocation-count',
            'paired',
        ),
        CHECK_CONTENTION: ('request_scopes', 'p99_seconds', 'seconds', 'synchronized-wave', 'paired'),
    }
    verdicts = [
        _typed_check(require_object(payload.get(criterion), f'{path}: {criterion}'), path, criterion, expected)
        for criterion, expected in specifications.items()
    ]
    startup = require_object(payload.get(CHECK_STARTUP), f'{path}: {CHECK_STARTUP}')
    expected_startup = ('fastapi_application_startup', 'latency', 'seconds per operation', 'paired-total-p50', 'paired')
    for field, value in zip(('workload', 'metric', 'unit', 'method', 'scope'), expected_startup, strict=True):
        if require_text(startup.get(field), f'{path}: {CHECK_STARTUP}.{field}') != value:
            raise HarnessError(f'{path}: {CHECK_STARTUP}.{field} must be {value!r}')
    limit = require_number(startup.get('limit'), f'{path}: {CHECK_STARTUP}.limit')
    verdicts.append(
        _regression_verdict(
            CHECK_STARTUP,
            [pair.base.median for pair in pairs['fastapi_application_startup']],
            [pair.head.median for pair in pairs['fastapi_application_startup']],
            limit,
        )
    )
    entries = require_array(payload.get('components'), f'{path}: components')
    components: set[str] = set()
    for index, entry in enumerate(entries):
        fields = require_object(entry, f'{path}: components[{index}]')
        workload = require_text(fields.get('workload'), f'{path}: components[{index}].workload')
        if workload in components:
            raise HarnessError(f'{path}: component {workload!r} appears twice')
        for field, value in zip(
            ('metric', 'unit', 'method', 'scope'),
            ('latency', 'seconds per operation', 'component-observation', 'head-only'),
            strict=True,
        ):
            if require_text(fields.get(field), f'{path}: components[{index}].{field}') != value:
                raise HarnessError(f'{path}: component {workload}.{field} must be {value!r}')
        if fields.get('validated') is not True:
            raise HarnessError(f'{path}: component {workload} must carry validated true')
        components.add(workload)
        verdicts.append(Verdict(f'component:{workload}', Outcome.PASS, 'validated component observation', 'head-only'))
    if components != set(COMPONENT_WORKLOADS):
        raise HarnessError(f'{path}: components must exactly match the FastAPI component inventory')
    return tuple(verdicts)


def evaluate(
    dataset: Path, attribution: Path, sidecars: Path, provenance: Path, *, evaluated_head_revision: str
) -> Acceptance:
    """Evaluate the fixed FastAPI acceptance criteria from collected evidence."""
    _provenance(provenance, evaluated_head_revision)
    pairs, seed = _pairs(dataset)
    verdicts = (
        *_attribution(attribution, pairs[ATTRIBUTION_WORKLOAD], seed, evaluated_head_revision),
        *_tails(pairs),
        *_sidecars(sidecars, pairs),
    )
    ordered = tuple(sorted(verdicts, key=lambda verdict: verdict.criterion))
    head_only = tuple(sorted(verdict.criterion for verdict in ordered if verdict.scope == 'head-only'))
    return Acceptance(ordered, head_only)


def run(dataset: Path, attribution: Path, sidecars: Path, provenance: Path, *, evaluated_head_revision: str) -> int:
    """Print the acceptance verdict and return its shell status."""
    acceptance = evaluate(dataset, attribution, sidecars, provenance, evaluated_head_revision=evaluated_head_revision)
    for verdict in acceptance.verdicts:
        marker = 'required' if verdict.required else 'target'
        print(f'{verdict.outcome.value:12} {marker:8} {verdict.scope:9} {verdict.criterion}: {verdict.detail}')
    outcomes = {verdict.outcome for verdict in acceptance.verdicts if verdict.required}
    if Outcome.FAIL in outcomes:
        return EXIT_REGRESSION
    if Outcome.INCONCLUSIVE in outcomes or Outcome.NO_VERDICT in outcomes:
        return EXIT_INCONCLUSIVE
    return EXIT_PASS


def main(argv: Sequence[str] | None = None) -> int:
    """Run the FastAPI acceptance evaluator as a command-line program."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--attribution', type=Path, required=True)
    parser.add_argument('--sidecars', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, required=True)
    parser.add_argument('--head-revision', required=True)
    arguments = parser.parse_args(argv)
    try:
        return run(
            arguments.dataset,
            arguments.attribution,
            arguments.sidecars,
            arguments.provenance,
            evaluated_head_revision=arguments.head_revision,
        )
    except HarnessError as error:
        print(f'misuse: {error}')
        return EXIT_MISUSE


if __name__ == '__main__':
    raise SystemExit(main())
