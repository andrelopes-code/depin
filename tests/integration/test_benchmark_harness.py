"""The harness's own tests: the statistics, the budget rules, and the two CLIs.

These are the parts that gate a release. A gate that has never been shown to fail
is not known to work, so every verdict the rule can reach — pass, regression,
inconclusive, no verdict, malformed — is produced deliberately here from data
constructed to produce it.
"""

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from benchmarks import test_latency
from benchmarks.contracts import Metric, NoiseClass, Tier, Workload
from benchmarks.harness import (
    HarnessError,
    calibrate,
    environment,
    gate,
    is_object,
    memory,
    pairs,
    reduce,
    report,
    require_object,
    scaling,
    stats,
    unmeasured,
    work,
)
from benchmarks.harness import budgets as budget_module
from benchmarks.workloads import WORKLOADS, scale

ROOT = Path(__file__).resolve().parents[2]
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

ALLOCATION_PROBE = """
import json, sys

from benchmarks.harness import HarnessError, memory

def build():
    return [object() for _ in range(64)]

try:
    counted = memory.allocations_per_operation(build, operations=1)
    held = memory.retained(build)
except HarnessError as error:
    json.dump({'error': str(error)}, sys.stdout)
else:
    json.dump({'blocks': counted.blocks, 'size': counted.size, 'peak': counted.peak, 'retained': held}, sys.stdout)
"""


def _benchmark_report(entries: Sequence[dict[str, object]]) -> dict[str, object]:
    return {'machine_info': {}, 'commit_info': {}, 'benchmarks': list(entries)}


def _entry(name: str, *, mean: float = 1e-6, rounds: int = 5000) -> dict[str, object]:
    return {
        'name': name,
        'fullname': f'benchmarks/test_probe.py::{name}',
        'stats': {'rounds': rounds, 'min': mean, 'median': mean, 'mean': mean, 'stddev': 0.0, 'iqr': 0.0},
    }


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _budget_file(path: Path, entries: Sequence[str]) -> Path:
    _ = path.write_text('\n'.join(entries), encoding='utf-8')
    return path


def _latency_budget(workload: str, limit: float = 0.05, noise: str = 'low') -> str:
    return (
        '[[budget]]\n'
        f'workload = "{workload}"\n'
        'metric = "latency"\n'
        f'limit = {limit}\n'
        f'noise = "{noise}"\n'
        'justification = "paired null p99 of 1.7%, floored at the low class minimum"\n'
    )


def _work_budget(workload: str) -> str:
    return (
        '[[budget]]\n'
        f'workload = "{workload}"\n'
        'metric = "work"\n'
        'limit = 0.0\n'
        'noise = "low"\n'
        'justification = "a call count is deterministic and may not increase"\n'
    )


def _scaling_budget(workload: str, limit: float = 0.15) -> str:
    return (
        '[[budget]]\n'
        f'workload = "{workload}"\n'
        'metric = "scaling"\n'
        f'limit = {limit}\n'
        'noise = "low"\n'
        'justification = "a complexity-class test, not a timing one"\n'
    )


def _dataset(
    directory: Path,
    *,
    base: Sequence[dict[str, float]],
    head: Sequence[dict[str, float]],
    rounds: int = 5000,
    deterministic: dict[str, dict[str, object]] | None = None,
) -> Path:
    """Write a collection directory whose repetitions carry exactly the given medians."""
    for side, repetitions in (('base', base), ('head', head)):
        for index, medians in enumerate(repetitions):
            _write(
                directory / side / f'rep{index}.json',
                {
                    'repetition': index,
                    'first': 'base',
                    'aggregates': {
                        name: {
                            'rounds': rounds,
                            'minimum': median,
                            'median': median,
                            'mean': median,
                            'stddev': 0.0,
                            'iqr': 0.0,
                        }
                        for name, median in medians.items()
                    },
                },
            )
        payload = (deterministic or {}).get(side, {})
        _write(directory / side / pairs.DETERMINISTIC_FILE, payload)
    _write(directory / pairs.ENVIRONMENT_FILE, {'environment': environment.capture(), 'repetitions': 5, 'seed': SEED})
    return directory


def _flat(name: str, median: float, count: int = 5) -> list[dict[str, float]]:
    return [{name: median} for _ in range(count)]


def _probe(source: str, *, hash_seed: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, '-c', source],
        cwd=ROOT,
        env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT), 'PYTHONHASHSEED': hash_seed},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    decoded: object = json.loads(completed.stdout)
    assert is_object(decoded)
    return decoded


def test_a_known_paired_difference_is_recovered_exactly() -> None:
    """A constant 10% slowdown has no dispersion, so the interval collapses onto the point."""
    paired = stats.paired_ratio([1.0] * 6, [1.1] * 6, seed=SEED)

    assert paired.n == 6
    assert paired.ratio == pytest.approx(0.1)
    assert paired.low == pytest.approx(0.1)
    assert paired.high == pytest.approx(0.1)


def test_the_statistic_is_the_median_of_paired_log_ratios_not_a_ratio_of_means() -> None:
    """One extreme repetition moves a mean and does not move the median."""
    base = [1.0, 1.0, 1.0, 1.0, 1.0]
    head = [1.0, 1.0, 1.0, 1.0, 100.0]

    assert stats.paired_ratio(base, head, seed=SEED).ratio == pytest.approx(0.0)


def test_the_bootstrap_interval_is_reproducible_from_its_seed() -> None:
    """A verdict has to be re-derivable from the data that produced it, not merely re-runnable."""
    base = [1.0] * 5
    head = [1.0, 1.02, 1.05, 1.4, 3.0]

    first = stats.paired_ratio(base, head, seed=SEED)

    assert first == stats.paired_ratio(base, head, seed=SEED)
    assert first.low <= first.ratio <= first.high


def test_the_seed_drives_the_resampling_it_makes_reproducible() -> None:
    """Too few resamples to converge is where two seeds visibly disagree."""
    base = [1.0] * 5
    head = [1.0, 1.02, 1.05, 1.4, 3.0]

    one = stats.paired_ratio(base, head, seed=1, resamples=11)
    two = stats.paired_ratio(base, head, seed=2, resamples=11)

    assert one == stats.paired_ratio(base, head, seed=1, resamples=11)
    assert (one.low, one.high) != (two.low, two.high)


@pytest.mark.parametrize(
    ('base', 'head'),
    [
        ([1.0, 1.0], [1.0]),
        ([], []),
        ([1.0], [0.0]),
        ([-1.0], [1.0]),
    ],
)
def test_paired_ratio_refuses_data_it_cannot_pair(base: list[float], head: list[float]) -> None:
    with pytest.raises(HarnessError):
        _ = stats.paired_ratio(base, head, seed=SEED)


def test_paired_ratio_refuses_a_bootstrap_with_no_resamples() -> None:
    with pytest.raises(HarnessError):
        _ = stats.paired_ratio([1.0], [1.0], seed=SEED, resamples=0)


@pytest.mark.parametrize(
    ('outcome', 'paired'),
    [
        (budget_module.Outcome.FAIL, stats.Paired(ratio=0.30, low=0.20, high=0.40, n=5)),
        (budget_module.Outcome.INCONCLUSIVE, stats.Paired(ratio=0.08, low=0.01, high=0.15, n=5)),
        (budget_module.Outcome.PASS, stats.Paired(ratio=0.01, low=-0.02, high=0.04, n=5)),
        (budget_module.Outcome.PASS, stats.Paired(ratio=0.05, low=0.05, high=0.05, n=5)),
    ],
)
def test_the_decision_rule_fails_on_the_lower_bound_not_the_point(
    outcome: budget_module.Outcome, paired: stats.Paired
) -> None:
    budget = budget_module.Budget('probe', 'latency', 0.05, NoiseClass.LOW, 'measured')

    assert budget_module.decide(budget, paired) is outcome


def test_a_budget_below_its_noise_class_floor_is_refused(tmp_path: Path) -> None:
    """The rule that stops a failing pull request being made green by editing a number."""
    path = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe', limit=0.02)])

    with pytest.raises(HarnessError, match='below the low noise floor'):
        _ = budget_module.load(path)


@pytest.mark.parametrize(
    ('noise', 'limit'),
    [('low', 0.05), ('medium', 0.08), ('high', 0.15)],
)
def test_a_budget_at_its_floor_is_accepted(tmp_path: Path, noise: str, limit: float) -> None:
    path = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe', limit=limit, noise=noise)])

    assert budget_module.load(path)[('probe', 'latency')].limit == limit


def test_a_deterministic_metric_may_not_carry_a_non_zero_limit(tmp_path: Path) -> None:
    entry = _work_budget('probe').replace('limit = 0.0', 'limit = 0.01')
    path = _budget_file(tmp_path / 'budgets.toml', [entry])

    with pytest.raises(HarnessError, match='may not increase at all'):
        _ = budget_module.load(path)


def test_a_scaling_budget_may_not_exceed_its_ceiling(tmp_path: Path) -> None:
    path = _budget_file(tmp_path / 'budgets.toml', [_scaling_budget('probe', limit=0.40)])

    with pytest.raises(HarnessError, match='exceeds the scaling ceiling'):
        _ = budget_module.load(path)


@pytest.mark.parametrize(
    ('body', 'message'),
    [
        ('', 'expected an array'),
        ('budget = []\n', 'is empty'),
        ('[[budget]]\nworkload = "probe"\n', 'expected a non-empty string'),
        (
            '[[budget]]\nworkload = "p"\nmetric = "speed"\nlimit = 0.1\nnoise = "low"\njustification = "x"\n',
            'not a gated metric',
        ),
        (
            '[[budget]]\nworkload = "p"\nmetric = "latency"\nlimit = 0.1\nnoise = "quiet"\njustification = "x"\n',
            'not a noise class',
        ),
        (
            '[[budget]]\nworkload = "p"\nmetric = "latency"\nlimit = 0.1\nnoise = "low"\njustification = ""\n',
            'expected a non-empty string',
        ),
        ('this is not toml\n', 'is not TOML'),
    ],
)
def test_a_malformed_budget_file_is_refused(tmp_path: Path, body: str, message: str) -> None:
    path = _budget_file(tmp_path / 'budgets.toml', [body])

    with pytest.raises(HarnessError, match=message):
        _ = budget_module.load(path)


def test_two_budgets_for_one_workload_and_metric_are_refused(tmp_path: Path) -> None:
    path = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe'), _latency_budget('probe')])

    with pytest.raises(HarnessError, match='two budgets for probe'):
        _ = budget_module.load(path)


def test_a_missing_budget_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match='cannot be read'):
        _ = budget_module.load(tmp_path / 'absent.toml')


def test_a_report_reduces_to_one_aggregate_per_workload(tmp_path: Path) -> None:
    path = _write(tmp_path / 'report.json', _benchmark_report([_entry('one'), _entry('two', mean=2e-6)]))

    reduced = reduce.load(path)

    assert sorted(reduced) == ['one', 'two']
    assert reduced['two'].mean == 2e-6
    assert reduced['two'].measured == pytest.approx(2e-6 * 5000)


MALFORMED_REPORTS: list[tuple[object, str]] = [
    ([1, 2, 3], 'expected a JSON object'),
    ({'machine_info': {}}, 'expected an array'),
    ({'benchmarks': {}}, 'expected an array'),
    ({'benchmarks': []}, 'is empty'),
    ({'benchmarks': [{'name': 'one'}]}, 'stats'),
    ({'benchmarks': [{'stats': {}}]}, 'name'),
]


@pytest.mark.parametrize(('payload', 'message'), MALFORMED_REPORTS)
def test_a_malformed_report_is_refused(tmp_path: Path, payload: object, message: str) -> None:
    path = _write(tmp_path / 'report.json', payload)

    with pytest.raises(HarnessError, match=message):
        _ = reduce.load(path)


def test_an_unreadable_report_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match='cannot be read'):
        _ = reduce.load(tmp_path / 'absent.json')


def test_a_report_that_is_not_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / 'report.json'
    _ = path.write_text('{', encoding='utf-8')

    with pytest.raises(HarnessError, match='is not JSON'):
        _ = reduce.load(path)


def test_two_benchmarks_under_one_name_are_refused(tmp_path: Path) -> None:
    path = _write(tmp_path / 'report.json', _benchmark_report([_entry('one'), _entry('one')]))

    with pytest.raises(HarnessError, match='two benchmarks named one'):
        _ = reduce.load(path)


@pytest.mark.parametrize(
    ('rounds', 'mean', 'expected'),
    [(1000, 1e-9, True), (999, 1e-9, False), (10, 0.05, True), (10, 0.04, False)],
)
def test_sample_quality_needs_a_thousand_rounds_or_half_a_second(rounds: int, mean: float, expected: bool) -> None:
    aggregate = reduce.Aggregate('probe', rounds, mean, mean, mean, 0.0, 0.0)

    assert reduce.qualifies(aggregate) is expected


def _outer() -> int:
    return _inner() + _inner()


def _inner() -> int:
    return 1


def test_python_calls_are_counted_per_operation() -> None:
    assert work.calls_per_operation(_outer, operations=100) == 3


def test_a_workload_whose_call_count_varies_is_reported_rather_than_averaged() -> None:
    counter = {'calls': 0}

    def alternating() -> None:
        counter['calls'] += 1
        if counter['calls'] % 2 == 0:
            _ = _inner()

    with pytest.raises(HarnessError, match='does not divide evenly'):
        _ = work.calls_per_operation(alternating, operations=3)


def test_counting_calls_needs_at_least_one_operation() -> None:
    with pytest.raises(HarnessError, match='at least one'):
        _ = work.calls_per_operation(_outer, operations=0)


def test_allocations_are_measured_under_a_fixed_hash_seed() -> None:
    measured = _probe(ALLOCATION_PROBE, hash_seed=memory.HASH_SEED)

    assert 'error' not in measured
    assert isinstance(measured['blocks'], int)
    assert measured['blocks'] > 0
    assert isinstance(measured['retained'], int)
    assert measured['retained'] > 0


def test_allocation_measurement_refuses_a_randomised_hash_seed() -> None:
    """The seed cannot be set after start, so the guard is the only place this is catchable."""
    measured = _probe(ALLOCATION_PROBE, hash_seed='1')

    assert 'PYTHONHASHSEED' in str(measured['error'])


def test_a_curve_measures_every_size_it_is_given() -> None:
    def build(size: int) -> Callable[[], object]:
        data = list(range(size))
        return lambda: sum(data)

    costs = scaling.curve(build, (16, 32), repeats=1, minimum_seconds=0.001)

    assert sorted(costs) == [16, 32]
    assert all(cost > 0.0 for cost in costs.values())


def test_a_linear_curve_reads_as_linear_and_a_quadratic_one_does_not() -> None:
    """`steps` is a pure function of the costs, so the complexity test needs no clock."""
    linear = scaling.steps({10: 1.0, 20: 2.0, 40: 4.0}, exponent=1.0)
    quadratic = scaling.steps({10: 1.0, 20: 4.0}, exponent=1.0)

    assert [step.excess for step in linear] == pytest.approx([0.0, 0.0])
    assert quadratic[0].excess == pytest.approx(1.0)
    assert (quadratic[0].smaller, quadratic[0].larger) == (10, 20)


@pytest.mark.parametrize('sizes', [(), (0,), (10, 10), (20, 10)])
def test_a_curve_refuses_sizes_it_cannot_grow_along(sizes: tuple[int, ...]) -> None:
    with pytest.raises(HarnessError):
        _ = scaling.curve(lambda size: lambda: size, sizes, repeats=1, minimum_seconds=0.001)


@pytest.mark.parametrize('costs', [{10: 1.0}, {10: 0.0, 20: 1.0}])
def test_a_complexity_comparison_refuses_data_it_cannot_compare(costs: dict[int, float]) -> None:
    with pytest.raises(HarnessError):
        _ = scaling.steps(costs, exponent=1.0)


def test_the_environment_is_recorded_as_json(tmp_path: Path) -> None:
    captured = environment.capture()
    _ = _write(tmp_path / 'environment.json', captured)

    assert sorted(captured) == ['distributions', 'host', 'interpreter']
    assert isinstance(captured['interpreter'], dict)


def test_the_gate_passes_two_identical_sides(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / 'data', base=_flat('probe', 1e-6), head=_flat('probe', 1e-6))
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_PASS


def test_the_gate_fails_a_regression_past_the_budget(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / 'data', base=_flat('probe', 1e-6), head=_flat('probe', 1.3e-6))
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_REGRESSION


def test_the_gate_reports_inconclusive_when_only_the_point_estimate_clears_the_budget(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / 'data',
        base=_flat('probe', 1e-6),
        head=[{'probe': median} for median in (1.30e-6, 1.07e-6, 1.02e-6, 0.99e-6, 1.35e-6)],
    )
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_INCONCLUSIVE


def test_too_few_valid_repetitions_is_no_verdict_rather_than_a_pass(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / 'data',
        base=_flat('probe', 1e-6, count=3),
        head=_flat('probe', 1e-6, count=3),
    )
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_INCONCLUSIVE


def test_a_repetition_below_the_sample_quality_minimum_is_excluded(tmp_path: Path) -> None:
    """Five repetitions that do not qualify are five repetitions the gate does not have."""
    dataset = _dataset(tmp_path / 'data', base=_flat('probe', 1e-6), head=_flat('probe', 1e-6), rounds=10)
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_INCONCLUSIVE


def test_a_workload_measured_on_one_side_only_is_reported_and_not_gated(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / 'data',
        base=[{'probe': 1e-6, 'gone': 1e-6} for _ in range(5)],
        head=[{'probe': 1e-6, 'fresh': 9e-6} for _ in range(5)],
    )
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_PASS


def test_the_gate_budgets_the_depin_subject_and_not_the_baseline_beside_it(tmp_path: Path) -> None:
    """The direct baseline is timed for the ratio the report publishes, not for a budget.

    A gate over it would fail the build when hand-written Python got faster, which
    says nothing about `depin`.
    """
    dataset = _dataset(
        tmp_path / 'data',
        base=[{'test_latency[probe-depin]': 2e-6, 'test_latency[probe-direct]': 1e-6} for _ in range(5)],
        head=[{'test_latency[probe-depin]': 2e-6, 'test_latency[probe-direct]': 0.5e-6} for _ in range(5)],
    )
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_PASS
    assert gate.run(dataset, budgets, expected=['probe']) == gate.EXIT_PASS


def test_a_regression_in_the_depin_subject_of_a_parametrised_case_still_fails(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / 'data',
        base=[{'test_latency[probe-depin]': 2e-6} for _ in range(5)],
        head=[{'test_latency[probe-depin]': 3e-6} for _ in range(5)],
    )
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_REGRESSION


def test_a_shared_workload_without_a_budget_is_a_misuse(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / 'data', base=_flat('probe', 1e-6), head=_flat('probe', 1e-6))
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('other')])

    assert gate.main([str(dataset), '--budgets', str(budgets)]) == gate.EXIT_MISUSE


def test_an_expected_workload_with_no_result_fails_the_gate(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / 'data', base=_flat('probe', 1e-6), head=_flat('probe', 1e-6))
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe')])

    assert gate.run(dataset, budgets, expected=['probe', 'never_ran']) == gate.EXIT_REGRESSION


def test_a_call_count_that_grew_fails_the_work_gate(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / 'data',
        base=_flat('probe', 1e-6),
        head=_flat('probe', 1e-6),
        deterministic={'base': {'work': {'probe': 13}}, 'head': {'work': {'probe': 14}}},
    )
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe'), _work_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_REGRESSION


def test_a_call_count_that_fell_passes_the_work_gate(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / 'data',
        base=_flat('probe', 1e-6),
        head=_flat('probe', 1e-6),
        deterministic={'base': {'work': {'probe': 13}}, 'head': {'work': {'probe': 12}}},
    )
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe'), _work_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_PASS


def test_a_complexity_change_fails_the_scaling_gate(tmp_path: Path) -> None:
    """The size-to-size ratio doubles while neither side's absolute cost is gated."""
    dataset = _dataset(
        tmp_path / 'data',
        base=_flat('probe', 1e-6),
        head=_flat('probe', 1e-6),
        deterministic={
            'base': {'scaling': {'curve': {'sizes': [10, 20], 'costs': [1.0, 2.0]}}},
            'head': {'scaling': {'curve': {'sizes': [10, 20], 'costs': [1.0, 4.0]}}},
        },
    )
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe'), _scaling_budget('curve')])

    assert gate.run(dataset, budgets) == gate.EXIT_REGRESSION


def test_the_gate_refuses_a_dataset_with_no_repetitions(tmp_path: Path) -> None:
    dataset = tmp_path / 'data'
    _write(dataset / pairs.ENVIRONMENT_FILE, {'environment': {}, 'repetitions': 5, 'seed': SEED})

    assert gate.main([str(dataset), '--budgets', str(tmp_path / 'absent.toml')]) == gate.EXIT_MISUSE


def test_the_report_renders_the_same_markdown_from_the_same_data(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / 'data',
        base=_flat('probe', 1e-6),
        head=_flat('probe', 2e-6),
        deterministic={
            'base': {},
            'head': {
                'work': {'probe': 13},
                'allocations': {'probe': {'blocks': 4, 'size': 320, 'peak': 4096}},
                'retained': {'probe': 1024},
                'scaling': {'curve': {'sizes': [10, 20], 'costs': [1e-6, 2e-6]}},
            },
        },
    )

    rendered = report.render(dataset)

    assert rendered == report.render(dataset)
    assert '## Latency' in rendered
    assert '## Work' in rendered
    assert '## Allocations' in rendered
    assert '## Retained memory' in rendered
    assert '## Scaling' in rendered
    assert '2.000 µs' in rendered
    assert str(tmp_path) not in rendered


def test_the_report_refuses_a_dataset_it_cannot_read(tmp_path: Path) -> None:
    assert report.main([str(tmp_path / 'absent')]) == 2


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
    budgets = _budget_file(tmp_path / 'budgets.toml', [_latency_budget('probe'), _work_budget('probe')])

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


@pytest.mark.parametrize('name', ['unparameterised', 'curve_', '_10', 'curve_big'])
def test_a_scaling_workload_must_be_parameterised_by_size(name: str) -> None:
    with pytest.raises(HarnessError):
        _ = pairs.split_size(name)


def test_every_tier_four_workload_declares_a_scaling_metric() -> None:
    assert scale.WORKLOADS
    assert {workload.claim.metric for workload in scale.WORKLOADS} == {Metric.SCALING}
    assert {workload.tier for workload in scale.WORKLOADS} == {Tier.SCALING}


def test_every_tier_four_workload_carries_a_complete_claim() -> None:
    for workload in scale.WORKLOADS:
        claim = workload.claim
        assert all(
            text for text in (claim.question, claim.work, claim.included, claim.excluded, claim.semantics, claim.shape)
        )
        assert claim.valid
        assert claim.invalid


def test_every_tier_four_workload_is_named_for_its_curve_and_size() -> None:
    for workload in scale.WORKLOADS:
        curve, size = pairs.split_size(workload.name)
        assert curve.startswith('scale_')
        assert size > 0


def _smallest(curve: str) -> Workload:
    matching = [workload for workload in scale.WORKLOADS if pairs.split_size(workload.name)[0] == curve]
    assert matching
    return matching[0]


@pytest.mark.parametrize(
    'curve',
    [
        'scale_resolve_transient_depth',
        'scale_resolve_fan_out',
        'scale_resolve_collection',
        'scale_scope_teardown',
        'scale_async_teardown',
    ],
)
def test_the_subject_and_its_direct_baseline_do_the_same_work(curve: str) -> None:
    workload = _smallest(curve)
    baseline = workload.baseline

    assert baseline is not None
    assert workload.subject.observe() == baseline.observe()


@pytest.mark.parametrize('curve', ['scale_freeze_graph_size', 'scale_override_nesting'])
def test_a_workload_without_a_baseline_says_why_in_its_claim(curve: str) -> None:
    workload = _smallest(curve)

    assert workload.baseline is None
    assert 'no direct baseline' in workload.claim.work


def test_a_scaling_workload_prepares_a_callable_that_can_be_measured() -> None:
    for curve in ('scale_freeze_graph_size', 'scale_override_nesting', 'scale_async_teardown'):
        prepared = _smallest(curve).subject.prepare()
        try:
            assert prepared.call() is not None
        finally:
            if prepared.close is not None:
                prepared.close()


def test_the_cold_resolution_depth_cliff_is_where_the_baseline_measured_it() -> None:
    """Pinned, not repaired: making resolution iterative is Step 8's change, not Step 7's.

    The probe runs in a fresh interpreter at module level, because the answer is a
    frame budget divided by the frames a resolution consumes per provider — measured
    under pytest it would pin the runner's stack depth instead.
    """
    assert scale.deepest_resolvable_chain() == {'singleton': scale.DEPTH_CLIFF, 'transient': scale.DEPTH_CLIFF}


def test_freeze_accepts_and_warmup_survives_a_graph_a_cold_resolve_cannot(tmp_path: Path) -> None:
    """The cliff's consequence: `freeze()` admits a graph the runtime cannot resolve cold."""
    del tmp_path
    from benchmarks.graphs import build_chain

    container, leaf = build_chain(1000)
    frozen = container.freeze()

    assert frozen.warmup().constructed
    assert frozen.resolve(leaf) is not None


@pytest.mark.parametrize('median', [1e-8, 1e-6, 1e-4, 3.4e-3, 5.9e-3, 8.9e-2])
def test_the_derived_rounds_floor_makes_a_repetition_of_that_cost_qualify(median: float) -> None:
    """The floor exists to satisfy `qualifies`, so it has to satisfy it at every scale."""
    floored = reduce.Aggregate(
        name='probe',
        rounds=reduce.rounds_for(median),
        minimum=median,
        median=median,
        mean=median,
        stddev=0.0,
        iqr=0.0,
    )

    assert reduce.qualifies(floored)


@pytest.mark.parametrize('median', [1e-6, 1e-4, 3.4e-3, 5.9e-3, 8.9e-2])
def test_the_derived_rounds_floor_survives_a_host_faster_by_its_stated_margin(median: float) -> None:
    """A floor derived on the reference host is applied on the runner, which is not always slower.

    This is the failure the fixed count produced: `build_the_graph_view` was
    floored at 120 rounds from a 5.9 ms reference cost and ran 3.4 ms on the
    runner, which bought 0.408 s of a rule that asks for half a second.
    """
    faster = median / reduce.HOST_MARGIN
    floored = reduce.Aggregate(
        name='probe',
        rounds=reduce.rounds_for(median),
        minimum=faster,
        median=faster,
        mean=faster,
        stddev=0.0,
        iqr=0.0,
    )

    assert reduce.qualifies(floored)


def test_a_fixed_rounds_floor_does_not_carry_the_rule_at_every_cost() -> None:
    """The defect the derivation replaces, stated as a test rather than as a comment."""
    fixed = 120
    slow, fast = 5.9e-3 / 1.7, 1.4e-5

    assert not reduce.qualifies(_aggregate_of(rounds=fixed, mean=slow))
    assert not reduce.qualifies(_aggregate_of(rounds=fixed, mean=fast))
    assert reduce.qualifies(_aggregate_of(rounds=reduce.rounds_for(slow), mean=slow))
    assert reduce.qualifies(_aggregate_of(rounds=reduce.rounds_for(fast), mean=fast))


@pytest.mark.parametrize('median', [0.0, -1.0, float('inf'), float('nan')])
def test_a_rounds_floor_cannot_be_derived_from_a_cost_that_is_not_one(median: float) -> None:
    with pytest.raises(HarnessError, match='finite and positive'):
        _ = reduce.rounds_for(median)


def test_a_case_the_published_dataset_does_not_cover_falls_back_to_the_round_count() -> None:
    """A workload added since the dataset was published still has to be measurable."""
    assert test_latency.floor('a_workload_no_dataset_has_ever_carried-depin') == reduce.MINIMUM_ROUNDS


def test_a_published_case_takes_its_floor_from_the_cost_the_dataset_recorded() -> None:
    published = dict(sorted(test_latency._PUBLISHED.items()))  # pyright: ignore[reportPrivateUsage]

    assert published, 'the accepted dataset carries no latency case to derive a floor from'
    for case, median in published.items():
        assert test_latency.floor(case) == reduce.rounds_for(median)


def _aggregate_of(*, rounds: int, mean: float) -> reduce.Aggregate:
    return reduce.Aggregate(name='probe', rounds=rounds, minimum=mean, median=mean, mean=mean, stddev=0.0, iqr=0.0)


def test_the_tail_quantiles_are_computed_from_the_round_array(tmp_path: Path) -> None:
    """pytest-benchmark reports a median and an interquartile range; a p99 exists only in the data."""
    entry = _entry('probe')
    require_object(entry['stats'], 'stats')['data'] = [float(value) for value in range(1, 101)]

    reduced = reduce.load(_write(tmp_path / 'report.json', _benchmark_report([entry])))['probe']

    assert reduced.p95 == pytest.approx(95.05)
    assert reduced.p99 == pytest.approx(99.01)


def test_an_entry_with_no_round_array_carries_no_quantiles(tmp_path: Path) -> None:
    reduced = reduce.load(_write(tmp_path / 'report.json', _benchmark_report([_entry('probe')])))['probe']

    assert reduced.p95 is None
    assert reduced.p99 is None


def test_the_cpu_reading_and_the_tier_are_read_from_extra_info(tmp_path: Path) -> None:
    entry = _entry('probe')
    entry['extra_info'] = {'cpu_nanoseconds': 4321, 'tier': Tier.APPLICATION.value}

    reduced = reduce.load(_write(tmp_path / 'report.json', _benchmark_report([entry])))['probe']

    assert reduced.cpu == 4321
    assert reduced.tier == Tier.APPLICATION.value


def test_an_aggregate_carrying_no_optional_reading_stores_none_of_them() -> None:
    stored = reduce.encode(_aggregate_of(rounds=10, mean=1e-6))

    assert set(stored) == {'rounds', 'minimum', 'median', 'mean', 'stddev', 'iqr'}


def test_every_reading_survives_the_round_trip_the_dataset_is_stored_through() -> None:
    measured = reduce.Aggregate(
        name='probe',
        rounds=10,
        minimum=1e-6,
        median=2e-6,
        mean=3e-6,
        stddev=4e-6,
        iqr=5e-6,
        p95=6e-6,
        p99=7e-6,
        cpu=8.0,
        tier=Tier.APPLICATION.value,
    )

    assert reduce.decode('probe', reduce.encode(measured), 'round trip') == measured


def test_the_published_page_separates_the_application_tier_and_gives_it_quantiles(tmp_path: Path) -> None:
    dataset = tmp_path / 'dataset'
    _write(dataset / pairs.ENVIRONMENT_FILE, {'environment': environment.capture(), 'repetitions': 1, 'seed': SEED})
    _write(
        dataset / 'rep0.json',
        {
            'repetition': 0,
            'first': 'head',
            'aggregates': {
                'test_latency[an_endpoint-depin]': {
                    'rounds': 1000,
                    'minimum': 1e-3,
                    'median': 1e-3,
                    'mean': 1e-3,
                    'stddev': 0.0,
                    'iqr': 0.0,
                    'p95': 2e-3,
                    'p99': 3e-3,
                    'cpu': 900000.0,
                    'tier': Tier.APPLICATION.value,
                },
                'test_latency[a_lookup-depin]': {
                    'rounds': 1000,
                    'minimum': 1e-6,
                    'median': 1e-6,
                    'mean': 1e-6,
                    'stddev': 0.0,
                    'iqr': 0.0,
                    'p95': 2e-6,
                    'p99': 3e-6,
                    'tier': Tier.ISOLATED.value,
                },
            },
        },
    )

    rendered = report.render(dataset)
    latency, application = rendered.split('## Application tier')

    assert 'a_lookup' in latency
    assert 'an_endpoint' not in latency
    assert 'an_endpoint' in application
    assert '3.000 ms' in application
    assert '900.000 µs' in application


def test_the_published_page_states_every_retired_and_refused_measurement(tmp_path: Path) -> None:
    _write(tmp_path / pairs.ENVIRONMENT_FILE, {'environment': environment.capture(), 'repetitions': 1, 'seed': SEED})

    rendered = report.render(tmp_path)

    for retirement in unmeasured.RETIRED:
        assert retirement.workload in rendered
        assert retirement.covered_by in rendered
    for refusal in unmeasured.REFUSED:
        assert refusal.case in rendered
        assert refusal.needed in rendered


def test_no_retired_workload_is_still_in_the_inventory() -> None:
    """Retirement is a decision, and a decision that the tree quietly reverses is not one."""
    declared = {workload.name for workload in WORKLOADS} | {
        pairs.split_size(workload.name)[0] for workload in WORKLOADS if workload.claim.metric is Metric.SCALING
    }

    for retirement in unmeasured.RETIRED:
        assert retirement.workload not in declared


def test_no_retired_workload_still_carries_a_budget() -> None:
    available = budget_module.load(ROOT / 'benchmarks' / 'budgets.toml')
    retired = {retirement.workload for retirement in unmeasured.RETIRED}

    assert not {workload for workload, _ in available} & retired


@pytest.mark.parametrize(
    ('p99', 'noise', 'limit'),
    [
        (0.0, NoiseClass.LOW, 0.05),
        (0.0192, NoiseClass.LOW, 0.05),
        (0.0299, NoiseClass.LOW, 0.06),
        (0.0438, NoiseClass.MEDIUM, 0.09),
        (0.0528, NoiseClass.MEDIUM, 0.11),
        (0.0601, NoiseClass.HIGH, 0.15),
        (0.1000, NoiseClass.HIGH, 0.20),
    ],
)
def test_a_budget_is_twice_its_measured_null_p99_floored_by_the_band_it_falls_in(
    p99: float,
    noise: NoiseClass,
    limit: float,
) -> None:
    assert calibrate.derive(p99) == (noise, limit)


def test_a_dispersion_cannot_be_negative() -> None:
    with pytest.raises(HarnessError, match='cannot be negative'):
        _ = calibrate.derive(-0.01)


def test_identical_runs_produce_no_excursion_at_all() -> None:
    """The null of the null: ten measurements of the same number differ by nothing."""
    assert set(calibrate.excursions([1e-6] * 10)) == {0.0}


def test_the_trial_count_is_every_split_of_the_runs_times_the_orderings() -> None:
    """Exchangeability is what makes ten runs carry 1512 trials rather than five."""
    assert len(calibrate.excursions([1e-6 + index * 1e-9 for index in range(10)])) == 252 * calibrate.SPLITS


def test_a_calibration_is_reproducible_from_its_seed() -> None:
    runs = [1e-6 + index * 1e-9 for index in range(10)]

    assert calibrate.excursions(runs) == calibrate.excursions(runs)
    assert calibrate.excursions(runs, seed=1) != calibrate.excursions(runs)


@pytest.mark.parametrize(
    ('runs', 'message'),
    [([1e-6, 1e-6, 1e-6], 'at least four'), ([1e-6, 0.0, 1e-6, 1e-6], 'finite and positive')],
)
def test_a_calibration_refuses_data_it_cannot_split(runs: list[float], message: str) -> None:
    with pytest.raises(HarnessError, match=message):
        _ = calibrate.excursions(runs)


def test_a_calibration_needs_at_least_one_ordering_per_split() -> None:
    with pytest.raises(HarnessError, match='at least one is needed per split'):
        _ = calibrate.excursions([1e-6] * 10, orderings=0)


def _null_collection(directory: Path) -> Path:
    """Five repetitions of two sides carrying the same code, which is what a calibration reads."""
    medians = [1.00e-6, 1.02e-6, 0.99e-6, 1.01e-6, 1.03e-6]
    _dataset(
        directory,
        base=[{'test_latency[probe-depin]': median} for median in medians],
        head=[{'test_latency[probe-depin]': median} for median in reversed(medians)],
        deterministic={
            'base': {'work': {'probe': 13}, 'scaling': {'scale_probe': {'sizes': [1, 2], 'costs': [1.0, 2.0]}}},
            'head': {'work': {'probe': 13}, 'scaling': {'scale_probe': {'sizes': [1, 2], 'costs': [1.0, 2.0]}}},
        },
    )
    return directory


def test_a_calibration_covers_only_the_depin_subject(tmp_path: Path) -> None:
    calibrated = calibrate.calibrate(_null_collection(tmp_path / 'null'))

    assert [entry.workload for entry in calibrated] == ['probe']
    assert calibrated[0].trials == 252 * calibrate.SPLITS


def test_the_generated_budget_file_is_one_the_gate_accepts(tmp_path: Path) -> None:
    """The output is the file, not a suggestion for one: a budget is generated, never typed."""
    generated = tmp_path / 'budgets.toml'
    _ = generated.write_text(calibrate.render(_null_collection(tmp_path / 'null')), encoding='utf-8')

    available = budget_module.load(generated)

    assert available[('probe', Metric.LATENCY.value)].limit >= budget_module.CLASS_FLOORS[NoiseClass.LOW]
    assert available[('probe', budget_module.WORK)].limit == 0.0
    assert available[('scale_probe', Metric.SCALING.value)].limit == 0.15


def test_a_generated_budget_carries_the_measurement_that_justifies_it(tmp_path: Path) -> None:
    available = budget_module.load(
        _budget_file(tmp_path / 'budgets.toml', [calibrate.render(_null_collection(tmp_path / 'null'))])
    )

    assert 'paired null p99' in available[('probe', Metric.LATENCY.value)].justification


def test_the_calibration_summary_names_every_workload_it_measured(tmp_path: Path) -> None:
    printed = calibrate.summary(calibrate.calibrate(_null_collection(tmp_path / 'null')))

    assert printed.startswith('probe')
    assert 'p99' in printed


def test_calibrating_a_collection_with_one_side_missing_is_refused(tmp_path: Path) -> None:
    (tmp_path / 'base').mkdir(parents=True)

    with pytest.raises(HarnessError, match='a null collection measures both sides'):
        _ = calibrate.calibrate(tmp_path)


def test_the_calibration_command_writes_a_budget_file_to_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert calibrate.main([str(_null_collection(tmp_path / 'null'))]) == 0
    assert '[[budget]]' in capsys.readouterr().out


def test_the_calibration_command_reports_a_collection_it_cannot_read(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert calibrate.main([str(tmp_path / 'absent')]) == 2
    assert 'null collection' in capsys.readouterr().err


def test_competitive_cached_lookup_seed_applies_only_to_the_cached_resolution_path() -> None:
    patch = ROOT / 'benchmarks' / 'seeds' / 'competitive-cached-lookup.patch'
    rendered = patch.read_text(encoding='utf-8')

    checked = subprocess.run(
        ('git', 'apply', '--check', str(patch)), cwd=ROOT, capture_output=True, text=True, check=False
    )

    assert checked.returncode == 0, checked.stderr
    changed = [line.removeprefix('+++ b/') for line in rendered.splitlines() if line.startswith('+++ b/')]
    assert changed == ['depin/_core/frozen.py']
    assert '+                self._warm_cached_lookup_probe = {cache_id: cached}' in rendered
    assert '+                _ = self._warm_cached_lookup_probe[cache_id]' in rendered
