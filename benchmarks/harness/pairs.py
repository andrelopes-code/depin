"""Collect a paired dataset: R counterbalanced repetitions of two revisions.

    python -m benchmarks.harness.pairs --base-dir PATH --head-dir PATH --repetitions N --out DIR

Each repetition measures both revisions in independent processes, and the order
within a repetition alternates, so a systematic drift over the job — thermal
behaviour, frequency scaling, a noisy neighbour — falls on both sides equally
instead of on whichever ran second.

What lands in `DIR` is the reduced per-repetition aggregates, never the round-level
report: one round-level report for the current suite is 21 MB, and the statistics
are computed from the aggregates anyway.

    DIR/environment.json                the metadata every published number depends on
    DIR/<side>/rep<i>.json              one reduced aggregate per workload per repetition
    DIR/<side>/deterministic.json       work, allocation and scaling measurements

The deterministic measurements need neither pairing nor repetition, because they
carry no noise; they are collected here so a job has one collection step and one
verdict step. They are gathered by re-running this module inside each revision, in
worker mode:

    python -m benchmarks.harness.pairs --deterministic FILE

which measures the inventory of the tree it is running in. Nothing here knows about
escalation: the command is deterministic given its inputs, so a re-run at double
`--repetitions` is an ordinary second collection.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from benchmarks.contracts import Metric, Workload
from benchmarks.harness import (
    HarnessError,
    memory,
    read_json,
    reduce,
    require_integer,
    require_text,
    scaling,
    work,
    write_json,
)
from benchmarks.harness import environment as environment_module

USAGE = 'python -m benchmarks.harness.pairs --base-dir PATH --head-dir PATH --repetitions N --out DIR'
BASE = 'base'
HEAD = 'head'
DEFAULT_REPETITIONS = 5
DEFAULT_SEED = 20260902
REPORT_PLACEHOLDER = '{report}'
ENVIRONMENT_FILE = 'environment.json'
DETERMINISTIC_FILE = 'deterministic.json'
# pytest-benchmark stops a workload once it has spent `--benchmark-max-time`,
# and its calibration occasionally lands far under that: one repetition of
# `build_the_graph_view` ran 16 rounds where its four siblings ran 183 to 232,
# and `reduce.qualifies` then excluded it, leaving the workload without the five
# valid pairs a verdict needs. A rounds floor removes that failure mode at the
# collection step rather than escalating it into a second measurement. 120 is
# the count that carries `reduce.MINIMUM_SECONDS` for the slowest workload the
# calibration has been observed to under-sample.
MINIMUM_LATENCY_ROUNDS = 120
LATENCY_COMMAND = (
    '-m',
    'pytest',
    'benchmarks',
    '--benchmark-only',
    '-q',
    f'--benchmark-min-rounds={MINIMUM_LATENCY_ROUNDS}',
    '--benchmark-json={report}',
)
DETERMINISTIC_COMMAND = ('-m', 'benchmarks.harness.pairs', '--deterministic', '{report}')


@dataclass(frozen=True, slots=True)
class Side:
    """One revision under comparison: the name it is filed under, and where it lives."""

    name: str
    directory: Path


def _run(side: Side, template: Sequence[str], report: Path) -> None:
    # `str.replace`, not `str.format`: an argument can be a whole program, and a
    # program is full of braces `format` would read as fields of its own.
    argv = [sys.executable, *(part.replace(REPORT_PLACEHOLDER, str(report)) for part in template)]
    child = os.environ | {'PYTHONHASHSEED': memory.HASH_SEED, 'PYTHONPATH': str(side.directory)}
    completed = subprocess.run(argv, cwd=side.directory, env=child, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise HarnessError(
            f'{side.name}: {" ".join(argv)} exited {completed.returncode}\n{completed.stdout}{completed.stderr}'
        )


def _measure_latency(side: Side, template: Sequence[str]) -> dict[str, reduce.Aggregate]:
    with tempfile.TemporaryDirectory() as scratch:
        report = Path(scratch) / 'report.json'
        _run(side, template, report)
        return reduce.load(report)


def _measure_deterministic(side: Side, template: Sequence[str]) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as scratch:
        report = Path(scratch) / DETERMINISTIC_FILE
        _run(side, template, report)
        return read_json(report)


def split_size(name: str) -> tuple[str, int]:
    """Split `<curve>_<size>` into the curve it belongs to and the size it measures."""
    curve, separator, size = name.rpartition('_')
    if not separator or not curve or not size.isdigit():
        raise HarnessError(f'{name}: a scaling workload is named <curve>_<size>, and its size decides its position')
    return curve, int(size)


def _inventory() -> tuple[Workload, ...]:
    from benchmarks.workloads import WORKLOADS

    return WORKLOADS


def measure(workloads: Sequence[Workload]) -> dict[str, object]:
    """Measure every deterministic metric the inventory declares.

    A workload declaring `ALLOCATIONS` yields both an allocation reading and a call
    count, because the two are counts of the same callable and the second is free
    once the first has been set up. A workload declaring `SCALING` contributes one
    point to the curve its name is parameterised into. `LATENCY` workloads are
    skipped: they are driven by the timing shell, and a curve must not be timed as
    if it were one operation.

    Every measurement uses one operation, so the harness never divides a total that
    a workload did not spend uniformly.
    """
    calls: dict[str, object] = {}
    allocations: dict[str, object] = {}
    retained: dict[str, object] = {}
    curves: dict[str, dict[int, float]] = {}

    for workload in workloads:
        metric = workload.claim.metric
        if metric is Metric.LATENCY:
            continue
        prepared = workload.subject.prepare()
        try:
            if metric is Metric.ALLOCATIONS:
                calls[workload.name] = work.calls_per_operation(prepared.call, operations=1)
                allocation = memory.allocations_per_operation(prepared.call, operations=1)
                allocations[workload.name] = {
                    'blocks': allocation.blocks,
                    'size': allocation.size,
                    'peak': allocation.peak,
                }
            elif metric is Metric.RETAINED:
                retained[workload.name] = memory.retained(prepared.call)
            else:
                curve, size = split_size(workload.name)
                curves.setdefault(curve, {})[size] = scaling.cost(prepared.call)
        finally:
            if prepared.close is not None:
                prepared.close()

    return {
        'work': calls,
        'allocations': allocations,
        'retained': retained,
        'scaling': {
            name: {'sizes': sorted(points), 'costs': [points[size] for size in sorted(points)]}
            for name, points in curves.items()
        },
    }


def collect(
    base: Side,
    head: Side,
    out: Path,
    *,
    repetitions: int,
    seed: int,
    latency_command: Sequence[str] = LATENCY_COMMAND,
    deterministic_command: Sequence[str] = DETERMINISTIC_COMMAND,
) -> None:
    """Run the paired protocol and write the dataset.

    Raises:
        HarnessError: `repetitions` is below one, a revision directory does not
            exist, or a measurement process failed.
    """
    if repetitions < 1:
        raise HarnessError(f'{repetitions} repetitions; the protocol needs at least one')
    for side in (base, head):
        if not side.directory.is_dir():
            raise HarnessError(f'{side.name}: {side.directory} is not a directory')

    for index in range(repetitions):
        order = (base, head) if index % 2 == 0 else (head, base)
        for side in order:
            aggregates = _measure_latency(side, latency_command)
            write_json(
                out / side.name / f'rep{index}.json',
                {
                    'repetition': index,
                    'first': order[0].name,
                    'aggregates': {name: reduce.encode(value) for name, value in aggregates.items()},
                },
            )

    for side in (base, head):
        write_json(out / side.name / DETERMINISTIC_FILE, _measure_deterministic(side, deterministic_command))

    write_json(
        out / ENVIRONMENT_FILE,
        {'environment': environment_module.capture(), 'repetitions': repetitions, 'seed': seed},
    )


def _optional_path(value: object, flag: str) -> Path | None:
    if value is None:
        return None
    return Path(require_text(value, flag))


def _arguments(argv: Sequence[str] | None) -> dict[str, object]:
    parser = argparse.ArgumentParser(prog='python -m benchmarks.harness.pairs', description=USAGE)
    parser.add_argument('--base-dir', help='the revision the head is compared against')
    parser.add_argument('--head-dir', help='the revision under test')
    parser.add_argument('--out', help='the directory the dataset is written to')
    parser.add_argument('--repetitions', type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--deterministic', help="worker mode: measure this tree's deterministic metrics into this file")
    return dict(vars(parser.parse_args(argv)))


def main(argv: Sequence[str] | None = None) -> int:
    try:
        chosen = _arguments(argv)
        worker = _optional_path(chosen['deterministic'], '--deterministic')
        if worker is not None:
            write_json(worker, measure(_inventory()))
            return 0
        base_dir = _optional_path(chosen['base_dir'], '--base-dir')
        head_dir = _optional_path(chosen['head_dir'], '--head-dir')
        out = _optional_path(chosen['out'], '--out')
        if base_dir is None or head_dir is None or out is None:
            raise HarnessError(f'--base-dir, --head-dir and --out are all required\n{USAGE}')
        collect(
            Side(BASE, base_dir),
            Side(HEAD, head_dir),
            out,
            repetitions=require_integer(chosen['repetitions'], '--repetitions'),
            seed=require_integer(chosen['seed'], '--seed'),
        )
    except HarnessError as error:
        _ = sys.stderr.write(f'{error}\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
