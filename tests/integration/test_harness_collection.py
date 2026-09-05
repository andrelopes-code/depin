import json
from pathlib import Path

import pytest

from benchmarks.harness import HarnessError, gate, pairs, require_object
from benchmarks.workloads import scale

from .test_harness_gate import budget_file, latency_budget, work_budget

SEED = 20260902

REPORT_WRITER = """
import json, os, sys

side = os.path.basename(os.getcwd())
mean = 1e-6 if side == 'base' else 2e-6
json.dump(
    {
        'machine_info': {},
        'benchmarks': [
            {
                'name': 'probe',
                'fullname': 'benchmarks/test_probe.py::probe',
                'stats': {
                    'rounds': 5000,
                    'min': mean,
                    'median': mean,
                    'mean': mean,
                    'stddev': 0.0,
                    'iqr': 0.0,
                },
            }
        ],
    },
    open(sys.argv[1], 'w'),
)
"""

DETERMINISTIC_WRITER = """
import json, os, sys

side = os.path.basename(os.getcwd())
json.dump({'work': {'probe': 13 if side == 'base' else 14}}, open(sys.argv[1], 'w'))
"""


def test_a_collection_alternates_the_order_of_the_two_sides(tmp_path: Path) -> None:
    """Drift over the job falls on both revisions equally only when the order swaps."""
    base, head = tmp_path / 'base', tmp_path / 'head'
    base.mkdir()
    head.mkdir()
    out = tmp_path / 'data'

    pairs.collect(
        pairs.Side(pairs.BASE, base),
        pairs.Side(pairs.HEAD, head),
        out,
        repetitions=3,
        seed=SEED,
        latency_command=('-c', REPORT_WRITER, '{report}'),
        deterministic_command=('-c', DETERMINISTIC_WRITER, '{report}'),
    )

    first = [json.loads((out / 'base' / f'rep{index}.json').read_text())['first'] for index in range(3)]
    assert first == ['base', 'head', 'base']
    assert json.loads((out / 'head' / pairs.DETERMINISTIC_FILE).read_text())['work'] == {'probe': 14}
    assert json.loads((out / pairs.ENVIRONMENT_FILE).read_text())['repetitions'] == 3


def test_a_collection_gates_end_to_end(tmp_path: Path) -> None:
    base, head = tmp_path / 'base', tmp_path / 'head'
    base.mkdir()
    head.mkdir()
    out = tmp_path / 'data'
    pairs.collect(
        pairs.Side(pairs.BASE, base),
        pairs.Side(pairs.HEAD, head),
        out,
        repetitions=5,
        seed=SEED,
        latency_command=('-c', REPORT_WRITER, '{report}'),
        deterministic_command=('-c', DETERMINISTIC_WRITER, '{report}'),
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe'), work_budget('probe')])

    assert gate.main([str(out), '--budgets', str(budgets)]) == gate.EXIT_REGRESSION


def test_a_collection_refuses_a_revision_directory_that_does_not_exist(tmp_path: Path) -> None:
    assert (
        pairs.main(
            [
                '--base-dir',
                str(tmp_path / 'absent'),
                '--head-dir',
                str(tmp_path),
                '--out',
                str(tmp_path / 'data'),
            ]
        )
        == 2
    )


def test_a_collection_refuses_an_incomplete_command_line() -> None:
    assert pairs.main([]) == 2


def test_a_failing_measurement_process_stops_the_collection(tmp_path: Path) -> None:
    base, head = tmp_path / 'base', tmp_path / 'head'
    base.mkdir()
    head.mkdir()

    with pytest.raises(HarnessError, match='exited 1'):
        pairs.collect(
            pairs.Side(pairs.BASE, base),
            pairs.Side(pairs.HEAD, head),
            tmp_path / 'data',
            repetitions=1,
            seed=SEED,
            latency_command=('-c', 'raise SystemExit(1)', '{report}'),
            deterministic_command=('-c', 'pass', '{report}'),
        )


def test_the_deterministic_collector_reads_the_inventory_it_is_given(tmp_path: Path) -> None:
    measured = pairs.measure(scale.WORKLOADS[:1])

    assert measured['work'] == {}
    assert 'scale_freeze_graph_size' in require_object(measured['scaling'], 'the scaling section')
