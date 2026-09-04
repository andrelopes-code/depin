import pytest

from benchmarks.harness import HarnessError, stats

SEED = 20260902


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
