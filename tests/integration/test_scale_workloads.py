from collections.abc import Callable
from pathlib import Path

import pytest
from test_harness_reports import _aggregate_of

from benchmarks.contracts import Metric, Tier, Workload
from benchmarks.harness import HarnessError, pairs, reduce, scaling
from benchmarks.workloads import scale


def _smallest(curve: str) -> Workload:
    matching = [workload for workload in scale.WORKLOADS if pairs.split_size(workload.name)[0] == curve]
    assert matching
    return matching[0]


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
