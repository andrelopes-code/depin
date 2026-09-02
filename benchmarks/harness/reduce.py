"""pytest-benchmark's round-level report, reduced to one aggregate per workload.

One report for the current suite is 21 MB, because the format stores every round
of every benchmark and the fastest cases run about 100,000 rounds. The published
raw data is what the statistics are computed from — one aggregate per repetition
per workload — and the round arrays stay transient artifacts of the job that
produced them.
"""

from dataclasses import dataclass
from pathlib import Path

from benchmarks.harness import (
    HarnessError,
    read_json,
    require_array,
    require_number,
    require_object,
    require_text,
)

MINIMUM_ROUNDS = 1000
MINIMUM_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class Aggregate:
    """One repetition's measurement of one workload, in seconds per round."""

    name: str
    rounds: int
    minimum: float
    median: float
    mean: float
    stddev: float
    iqr: float

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


def encode(aggregate: Aggregate) -> dict[str, object]:
    """The JSON form a reduced repetition is stored as."""
    return {
        'rounds': aggregate.rounds,
        'minimum': aggregate.minimum,
        'median': aggregate.median,
        'mean': aggregate.mean,
        'stddev': aggregate.stddev,
        'iqr': aggregate.iqr,
    }


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
    )


def decode_all(payload: dict[str, object], where: str) -> dict[str, Aggregate]:
    """Rebuild every aggregate in a stored mapping of workload name to measurement."""
    return {name: decode(name, value, where) for name, value in sorted(payload.items())}


def _entry(entry: object, where: str) -> Aggregate:
    fields = require_object(entry, where)
    name = require_text(fields.get('name'), f'{where}.name')
    stats = require_object(fields.get('stats'), f'{where}.stats')
    rounds = require_number(stats.get('rounds'), f'{where}.stats.rounds')
    return Aggregate(
        name=name,
        rounds=int(rounds),
        minimum=require_number(stats.get('min'), f'{where}.stats.min'),
        median=require_number(stats.get('median'), f'{where}.stats.median'),
        mean=require_number(stats.get('mean'), f'{where}.stats.mean'),
        stddev=require_number(stats.get('stddev'), f'{where}.stats.stddev'),
        iqr=require_number(stats.get('iqr'), f'{where}.stats.iqr'),
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
