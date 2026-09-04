from pathlib import Path

import pytest
from test_harness_gate import _budget_file, _dataset

from benchmarks.contracts import Metric, NoiseClass
from benchmarks.harness import HarnessError, calibrate
from benchmarks.harness import budgets as budget_module


def _null_collection(directory: Path) -> Path:
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
