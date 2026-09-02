"""pytest-benchmark's round-level report, reduced to one aggregate per workload.

One report for the current suite is 21 MB, because the format stores every round
of every benchmark and the fastest cases run about 100,000 rounds. The published
raw data is what the statistics are computed from — one aggregate per repetition
per workload — and the round arrays stay transient artifacts of the job that
produced them.

The round arrays are read before they are discarded, which is where the tail
quantiles come from: `pytest-benchmark` reports a median and an interquartile
range, and a p95 or p99 exists only in the data.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from benchmarks.harness import (
    HarnessError,
    quantile,
    read_json,
    require_array,
    require_number,
    require_object,
    require_text,
)

SUBJECT_LABEL = 'depin'
MINIMUM_ROUNDS = 1000
MINIMUM_SECONDS = 0.5

HOST_MARGIN = 4.0
"""How much faster than the reference host a workload may run and still qualify.

`rounds_for` derives a rounds floor from a cost measured on the reference host and
applies it wherever the suite runs, which is mostly a shared runner. The runner is
not uniformly slower: `build_the_graph_view` measured 5.9 ms on the reference host
and 3.4 ms on the runner, so a floor derived without margin would have bought
0.29 s of a rule that asks for 0.5. Four is past twice that observed ratio.
"""


@dataclass(frozen=True, slots=True)
class Aggregate:
    """One repetition's measurement of one workload, in seconds per round.

    ``p95`` and ``p99`` are computed from the round array the report carries.
    ``cpu`` is nanoseconds of process CPU for one operation, present only where
    the workload's callable returns a `benchmarks.contracts.Cost`. ``tier`` is the
    workload's tier, carried so a publication step can separate the tiers without
    importing the inventory — the inventory pulls in a web framework, and this
    package is standard library only.
    """

    name: str
    rounds: int
    minimum: float
    median: float
    mean: float
    stddev: float
    iqr: float
    p95: float | None = None
    p99: float | None = None
    cpu: float | None = None
    tier: str | None = None

    @property
    def measured(self) -> float:
        """Seconds of timed work this repetition accumulated."""
        return self.mean * self.rounds


def qualifies(aggregate: Aggregate) -> bool:
    """Whether the repetition is allowed to contribute to a verdict.

    A workload that accumulated neither 1000 rounds nor half a second of measured
    time has not been sampled enough for its median to mean anything, and averaging
    it in would import its dispersion into the paired statistic. Such a repetition
    is recorded and excluded; a workload left with too few of them is reported as
    having no verdict rather than as passing.
    """
    return aggregate.rounds >= MINIMUM_ROUNDS or aggregate.measured >= MINIMUM_SECONDS


def rounds_for(median: float) -> int:
    """The rounds floor that keeps a workload of this cost qualifying, wherever it runs.

    `qualifies` is satisfied by either branch of its rule, so the cheapest floor
    that carries it is the smaller of the two: the round count itself, or the
    rounds a half second of this workload takes, widened by `HOST_MARGIN` for the
    host the floor is applied on rather than measured on.

    A fixed count cannot do this. 120 rounds is half a second of a 4.2 ms
    operation, six seconds of a 50 ms one, and a thousandth of a second of a
    microsecond one — so one number is simultaneously a floor that does not bind
    and a floor that overruns.

    Raises:
        HarnessError: `median` is not finite and positive. A cost of zero would
            make the floor unbounded, which is a malformed dataset rather than a
            workload that needs every round available.

    Example:
        ```pycon
        >>> from benchmarks.harness.reduce import rounds_for
        >>> rounds_for(0.0059)
        339
        >>> rounds_for(1e-6)
        1000

        ```
    """
    if not math.isfinite(median) or median <= 0.0:
        raise HarnessError(f'a median of {median!r}; a cost must be finite and positive to derive rounds from')
    return min(MINIMUM_ROUNDS, math.ceil(HOST_MARGIN * MINIMUM_SECONDS / median))


def subject_of(name: str) -> str | None:
    """The workload a benchmark case measured, or `None` when it did not measure `depin`.

    The timing shell parametrises one case per implementation, with the id
    `<workload>-<label>`, so `test_latency[resolve_cached_singleton-depin]` is the
    `depin` subject of `resolve_cached_singleton` and the `-direct` case beside it
    is the baseline it is published against. The baseline is measured for the ratio
    the report prints, not for a budget: what a gate protects is `depin`'s own cost.

    A case name carrying no parameter is its own workload, so a report produced by
    a shell that does not parametrise is still gated.

    Example:
        ```pycon
        >>> from benchmarks.harness.reduce import subject_of
        >>> subject_of('test_latency[resolve_cached_singleton-depin]')
        'resolve_cached_singleton'
        >>> subject_of('test_latency[resolve_cached_singleton-direct]') is None
        True

        ```
    """
    if not name.endswith(']') or '[' not in name:
        return name
    inside = name[name.index('[') + 1 : -1]
    workload, separator, label = inside.rpartition('-')
    if not separator:
        return inside
    return workload if label == SUBJECT_LABEL else None


def encode(aggregate: Aggregate) -> dict[str, object]:
    """The JSON form a reduced repetition is stored as.

    The optional fields are written only when they were measured, so a dataset
    never records a `null` a reader would have to tell apart from a zero.
    """
    stored: dict[str, object] = {
        'rounds': aggregate.rounds,
        'minimum': aggregate.minimum,
        'median': aggregate.median,
        'mean': aggregate.mean,
        'stddev': aggregate.stddev,
        'iqr': aggregate.iqr,
    }
    for field, value in (('p95', aggregate.p95), ('p99', aggregate.p99), ('cpu', aggregate.cpu)):
        if value is not None:
            stored[field] = value
    if aggregate.tier is not None:
        stored['tier'] = aggregate.tier
    return stored


def _optional_number(value: object, where: str) -> float | None:
    return None if value is None else require_number(value, where)


def _optional_text(value: object, where: str) -> str | None:
    return None if value is None else require_text(value, where)


def decode(name: str, value: object, where: str) -> Aggregate:
    """Rebuild an `Aggregate` from the form `encode` wrote."""
    fields = require_object(value, f'{where}: {name}')
    rounds = require_number(fields.get('rounds'), f'{where}: {name}.rounds')
    return Aggregate(
        name=name,
        rounds=int(rounds),
        minimum=require_number(fields.get('minimum'), f'{where}: {name}.minimum'),
        median=require_number(fields.get('median'), f'{where}: {name}.median'),
        mean=require_number(fields.get('mean'), f'{where}: {name}.mean'),
        stddev=require_number(fields.get('stddev'), f'{where}: {name}.stddev'),
        iqr=require_number(fields.get('iqr'), f'{where}: {name}.iqr'),
        p95=_optional_number(fields.get('p95'), f'{where}: {name}.p95'),
        p99=_optional_number(fields.get('p99'), f'{where}: {name}.p99'),
        cpu=_optional_number(fields.get('cpu'), f'{where}: {name}.cpu'),
        tier=_optional_text(fields.get('tier'), f'{where}: {name}.tier'),
    )


def decode_all(payload: dict[str, object], where: str) -> dict[str, Aggregate]:
    """Rebuild every aggregate in a stored mapping of workload name to measurement."""
    return {name: decode(name, value, where) for name, value in sorted(payload.items())}


def _rounds(entry: dict[str, object], where: str) -> list[float] | None:
    data = entry.get('data')
    if data is None:
        return None
    return sorted(require_number(round_, f'{where}.data') for round_ in require_array(data, f'{where}.data'))


def _extra(entry: dict[str, object], where: str) -> dict[str, object]:
    return require_object(entry.get('extra_info', {}), f'{where}.extra_info')


def _entry(entry: object, where: str) -> Aggregate:
    fields = require_object(entry, where)
    name = require_text(fields.get('name'), f'{where}.name')
    stats = require_object(fields.get('stats'), f'{where}.stats')
    rounds = require_number(stats.get('rounds'), f'{where}.stats.rounds')
    ordered = _rounds(stats, f'{where}.stats')
    extra = _extra(fields, where)
    cpu = extra.get('cpu_nanoseconds')
    tier = extra.get('tier')
    return Aggregate(
        name=name,
        rounds=int(rounds),
        minimum=require_number(stats.get('min'), f'{where}.stats.min'),
        median=require_number(stats.get('median'), f'{where}.stats.median'),
        mean=require_number(stats.get('mean'), f'{where}.stats.mean'),
        stddev=require_number(stats.get('stddev'), f'{where}.stats.stddev'),
        iqr=require_number(stats.get('iqr'), f'{where}.stats.iqr'),
        p95=None if ordered is None else quantile(ordered, 0.95),
        p99=None if ordered is None else quantile(ordered, 0.99),
        cpu=None if cpu is None else require_number(cpu, f'{where}.extra_info.cpu_nanoseconds'),
        tier=None if tier is None else require_text(tier, f'{where}.extra_info.tier'),
    )


def load(path: Path) -> dict[str, Aggregate]:
    """Reduce a `--benchmark-json` report to one aggregate per workload.

    Workloads are keyed by the benchmark's `name`, which carries the parameter
    suffix, so `freeze_a_chain[100]` and `freeze_a_chain[1000]` stay distinct. Two
    entries under one name make the report ambiguous and are rejected rather than
    silently collapsed.

    Raises:
        HarnessError: the file is unreadable, is not a JSON object, carries no
            `benchmarks` array, carries an empty one, or carries an entry missing
            a name or one of the statistics a verdict is formed from.
    """
    payload = read_json(path)
    entries = require_array(payload.get('benchmarks'), f'{path}: "benchmarks"')
    if not entries:
        raise HarnessError(f'{path}: "benchmarks" is empty; the run measured nothing')

    reduced: dict[str, Aggregate] = {}
    for index, entry in enumerate(entries):
        aggregate = _entry(entry, f'{path}: benchmarks[{index}]')
        if aggregate.name in reduced:
            raise HarnessError(f'{path}: two benchmarks named {aggregate.name}; the report is ambiguous')
        reduced[aggregate.name] = aggregate
    return reduced
