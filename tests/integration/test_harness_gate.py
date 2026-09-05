import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from benchmarks.contracts import NoiseClass
from benchmarks.harness import HarnessError, environment, gate, pairs, stats
from benchmarks.harness import budgets as budget_module

SEED = 20260902


def write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def budget_file(path: Path, entries: Sequence[str]) -> Path:
    _ = path.write_text('\n'.join(entries), encoding='utf-8')
    return path


def latency_budget(workload: str, limit: float = 0.05, noise: str = 'low') -> str:
    return (
        '[[budget]]\n'
        f'workload = "{workload}"\n'
        'metric = "latency"\n'
        f'limit = {limit}\n'
        f'noise = "{noise}"\n'
        'justification = "paired null p99 of 1.7%, floored at the low class minimum"\n'
    )


def work_budget(workload: str) -> str:
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


def make_dataset(
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
            write(
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
        write(directory / side / pairs.DETERMINISTIC_FILE, payload)
    write(directory / pairs.ENVIRONMENT_FILE, {'environment': environment.capture(), 'repetitions': 5, 'seed': SEED})
    return directory


def flat(name: str, median: float, count: int = 5) -> list[dict[str, float]]:
    return [{name: median} for _ in range(count)]


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
    path = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe', limit=0.02)])

    with pytest.raises(HarnessError, match='below the low noise floor'):
        _ = budget_module.load(path)


@pytest.mark.parametrize(
    ('noise', 'limit'),
    [('low', 0.05), ('medium', 0.08), ('high', 0.15)],
)
def test_a_budget_at_its_floor_is_accepted(tmp_path: Path, noise: str, limit: float) -> None:
    path = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe', limit=limit, noise=noise)])

    assert budget_module.load(path)[('probe', 'latency')].limit == limit


def test_a_deterministic_metric_may_not_carry_a_non_zero_limit(tmp_path: Path) -> None:
    entry = work_budget('probe').replace('limit = 0.0', 'limit = 0.01')
    path = budget_file(tmp_path / 'budgets.toml', [entry])

    with pytest.raises(HarnessError, match='may not increase at all'):
        _ = budget_module.load(path)


def test_a_scaling_budget_may_not_exceed_its_ceiling(tmp_path: Path) -> None:
    path = budget_file(tmp_path / 'budgets.toml', [_scaling_budget('probe', limit=0.40)])

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
    path = budget_file(tmp_path / 'budgets.toml', [body])

    with pytest.raises(HarnessError, match=message):
        _ = budget_module.load(path)


def test_two_budgets_for_one_workload_and_metric_are_refused(tmp_path: Path) -> None:
    path = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe'), latency_budget('probe')])

    with pytest.raises(HarnessError, match='two budgets for probe'):
        _ = budget_module.load(path)


def test_a_missing_budget_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match='cannot be read'):
        _ = budget_module.load(tmp_path / 'absent.toml')


def test_the_gate_passes_two_identical_sides(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path / 'data', base=flat('probe', 1e-6), head=flat('probe', 1e-6))
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_PASS


def test_the_gate_fails_a_regression_past_the_budget(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path / 'data', base=flat('probe', 1e-6), head=flat('probe', 1.3e-6))
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_REGRESSION


def test_the_gate_reports_inconclusive_when_only_the_point_estimate_clears_the_budget(tmp_path: Path) -> None:
    dataset = make_dataset(
        tmp_path / 'data',
        base=flat('probe', 1e-6),
        head=[{'probe': median} for median in (1.30e-6, 1.07e-6, 1.02e-6, 0.99e-6, 1.35e-6)],
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_INCONCLUSIVE


def test_too_few_valid_repetitions_is_no_verdict_rather_than_a_pass(tmp_path: Path) -> None:
    dataset = make_dataset(
        tmp_path / 'data',
        base=flat('probe', 1e-6, count=3),
        head=flat('probe', 1e-6, count=3),
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_INCONCLUSIVE


def test_a_repetition_below_the_sample_quality_minimum_is_excluded(tmp_path: Path) -> None:
    """Five repetitions that do not qualify are five repetitions the gate does not have."""
    dataset = make_dataset(tmp_path / 'data', base=flat('probe', 1e-6), head=flat('probe', 1e-6), rounds=10)
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_INCONCLUSIVE


def test_a_workload_measured_on_one_side_only_is_reported_and_not_gated(tmp_path: Path) -> None:
    dataset = make_dataset(
        tmp_path / 'data',
        base=[{'probe': 1e-6, 'gone': 1e-6} for _ in range(5)],
        head=[{'probe': 1e-6, 'fresh': 9e-6} for _ in range(5)],
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_PASS


def test_the_gate_budgets_the_depin_subject_and_not_the_baseline_beside_it(tmp_path: Path) -> None:
    """The direct baseline is timed for the ratio the report publishes, not for a budget.

    A gate over it would fail the build when hand-written Python got faster, which
    says nothing about `depin`.
    """
    dataset = make_dataset(
        tmp_path / 'data',
        base=[{'test_latency[probe-depin]': 2e-6, 'test_latency[probe-direct]': 1e-6} for _ in range(5)],
        head=[{'test_latency[probe-depin]': 2e-6, 'test_latency[probe-direct]': 0.5e-6} for _ in range(5)],
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_PASS
    assert gate.run(dataset, budgets, expected=['probe']) == gate.EXIT_PASS


def test_a_regression_in_the_depin_subject_of_a_parametrised_case_still_fails(tmp_path: Path) -> None:
    dataset = make_dataset(
        tmp_path / 'data',
        base=[{'test_latency[probe-depin]': 2e-6} for _ in range(5)],
        head=[{'test_latency[probe-depin]': 3e-6} for _ in range(5)],
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_REGRESSION


def test_a_shared_workload_without_a_budget_is_a_misuse(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path / 'data', base=flat('probe', 1e-6), head=flat('probe', 1e-6))
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('other')])

    assert gate.main([str(dataset), '--budgets', str(budgets)]) == gate.EXIT_MISUSE


def test_an_expected_workload_with_no_result_fails_the_gate(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path / 'data', base=flat('probe', 1e-6), head=flat('probe', 1e-6))
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe')])

    assert gate.run(dataset, budgets, expected=['probe', 'never_ran']) == gate.EXIT_REGRESSION


def test_a_call_count_that_grew_fails_the_work_gate(tmp_path: Path) -> None:
    dataset = make_dataset(
        tmp_path / 'data',
        base=flat('probe', 1e-6),
        head=flat('probe', 1e-6),
        deterministic={'base': {'work': {'probe': 13}}, 'head': {'work': {'probe': 14}}},
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe'), work_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_REGRESSION


def test_a_call_count_that_fell_passes_the_work_gate(tmp_path: Path) -> None:
    dataset = make_dataset(
        tmp_path / 'data',
        base=flat('probe', 1e-6),
        head=flat('probe', 1e-6),
        deterministic={'base': {'work': {'probe': 13}}, 'head': {'work': {'probe': 12}}},
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe'), work_budget('probe')])

    assert gate.run(dataset, budgets) == gate.EXIT_PASS


def test_a_complexity_change_fails_the_scaling_gate(tmp_path: Path) -> None:
    """The size-to-size ratio doubles while neither side's absolute cost is gated."""
    dataset = make_dataset(
        tmp_path / 'data',
        base=flat('probe', 1e-6),
        head=flat('probe', 1e-6),
        deterministic={
            'base': {'scaling': {'curve': {'sizes': [10, 20], 'costs': [1.0, 2.0]}}},
            'head': {'scaling': {'curve': {'sizes': [10, 20], 'costs': [1.0, 4.0]}}},
        },
    )
    budgets = budget_file(tmp_path / 'budgets.toml', [latency_budget('probe'), _scaling_budget('curve')])

    assert gate.run(dataset, budgets) == gate.EXIT_REGRESSION


def test_the_gate_refuses_a_dataset_with_no_repetitions(tmp_path: Path) -> None:
    dataset = tmp_path / 'data'
    write(dataset / pairs.ENVIRONMENT_FILE, {'environment': {}, 'repetitions': 5, 'seed': SEED})

    assert gate.main([str(dataset), '--budgets', str(tmp_path / 'absent.toml')]) == gate.EXIT_MISUSE
