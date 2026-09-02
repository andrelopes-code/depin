from collections.abc import Callable, Generator

import pytest

import benchmarks.comparison.adapters.dependency_injector as dependency_injector_adapter
import benchmarks.comparison.adapters.dishka as dishka_adapter
import benchmarks.comparison.adapters.wireup as wireup_adapter
from benchmarks.comparison.adapters.dependency_injector import ADAPTER, warm_chain
from benchmarks.comparison.contracts import Competitor, Equivalence
from benchmarks.comparison.shapes import Chain, chain, observation
from benchmarks.contracts import Observation
from benchmarks.harness import HarnessError
from benchmarks.workloads import WORKLOADS
from benchmarks.workloads.micro import CHAIN_DEPTH, HOT_GRAPH


class _TrackedResource:
    pass


def _tracked_chain_builder(log: list[str], expected_size: int) -> Callable[[int], Chain]:
    def build(size: int) -> Chain:
        if size != expected_size:
            raise HarnessError(f'expected chain depth {expected_size}, got {size}')

        def tracked() -> Generator[_TrackedResource, None, None]:
            log.append('opened')
            try:
                yield _TrackedResource()
            finally:
                log.append('closed')

        return Chain(nodes=(_TrackedResource,), factories=(tracked,), leaf=_TrackedResource, log=[])

    return build


def test_chain_constructs_a_typed_five_node_observation() -> None:
    shared = chain(5)

    value: object = shared.factories[0]()
    for factory in shared.factories[1:]:
        value = factory(value)

    assert type(value) is shared.leaf
    assert observation(shared, value) == Observation(
        result='Node4', constructed=('Node0', 'Node1', 'Node2', 'Node3', 'Node4'), closed=()
    )
    assert tuple(factory.__annotations__ for factory in shared.factories) == (
        {'return': shared.nodes[0]},
        {'upstream': shared.nodes[0], 'return': shared.nodes[1]},
        {'upstream': shared.nodes[1], 'return': shared.nodes[2]},
        {'upstream': shared.nodes[2], 'return': shared.nodes[3]},
        {'upstream': shared.nodes[3], 'return': shared.nodes[4]},
    )


def test_caller_clears_chain_log_between_observations() -> None:
    shared = chain(1)

    first = shared.factories[0]()
    assert observation(shared, first).constructed == ('Node0',)
    shared.log.clear()

    second = shared.factories[0]()
    assert observation(shared, second).constructed == ('Node0',)


def test_chain_creates_fresh_nodes_and_an_isolated_log() -> None:
    first = chain(3)
    second = chain(3)

    identical_nodes = tuple(
        first_node is second_node for first_node, second_node in zip(first.nodes, second.nodes, strict=True)
    )
    assert identical_nodes == (False, False, False)

    value: object = first.factories[0]()
    for factory in first.factories[1:]:
        value = factory(value)

    assert type(value) is first.leaf
    assert first.log == ['Node0', 'Node1', 'Node2']
    assert second.log == []


@pytest.mark.parametrize('size', [0, -1])
def test_chain_rejects_a_non_positive_size(size: int) -> None:
    with pytest.raises(HarnessError, match='chain size must be at least one'):
        _ = chain(size)


def test_dependency_injector_warm_singleton_matches_depin_and_uses_thread_safe_provider() -> None:
    workload = next(workload for workload in WORKLOADS if workload.name == 'resolve_cached_singleton')
    candidate = next(candidate for candidate in ADAPTER.candidates(WORKLOADS) if candidate.workload == workload.name)
    provider = warm_chain(1).leaf

    assert candidate.competitor.distribution == 'dependency-injector'
    assert candidate.competitor.version == '4.49.1'
    assert candidate.implementation is not None
    assert candidate.implementation.observe() == workload.subject.observe()
    assert type(provider).__name__ == 'ThreadSafeSingleton'

    prepared = candidate.implementation.prepare()
    assert prepared.close is not None
    first = prepared.call()
    prepared.close()
    second = prepared.call()
    prepared.close()
    assert first is not second


def test_dependency_injector_transient_chain_matches_depin() -> None:
    workload = next(workload for workload in WORKLOADS if workload.name == 'resolve_a_transient_chain')
    candidate = next(candidate for candidate in ADAPTER.candidates(WORKLOADS) if candidate.workload == workload.name)

    assert candidate.competitor.distribution == 'dependency-injector'
    assert candidate.competitor.version == '4.49.1'
    assert candidate.implementation is not None
    assert candidate.implementation.observe() == workload.subject.observe()


def test_dependency_injector_cold_singleton_initializes_during_prepare(monkeypatch: pytest.MonkeyPatch) -> None:
    class RecordedSole:
        constructed = 0

        def __init__(self) -> None:
            type(self).constructed += 1

    monkeypatch.setattr(dependency_injector_adapter, 'Sole', RecordedSole)
    candidate = next(
        candidate
        for candidate in ADAPTER.candidates(WORKLOADS)
        if candidate.workload == 'construct_a_singleton_for_the_first_time'
    )

    assert candidate.implementation is not None
    prepared = candidate.implementation.prepare()
    assert RecordedSole.constructed == 1
    assert prepared.close is not None
    _ = prepared.call()
    assert RecordedSole.constructed == 2
    prepared.close()


def test_dependency_injector_candidates_cover_workloads_in_order_with_expected_families() -> None:
    candidates = ADAPTER.candidates(WORKLOADS)
    subjects = {workload.name: workload.subject for workload in WORKLOADS}
    by_name = {candidate.workload: candidate for candidate in candidates}

    assert tuple(candidate.workload for candidate in candidates) == tuple(workload.name for workload in WORKLOADS)
    assert all(candidate.competitor == Competitor('dependency-injector', '4.49.1') for candidate in candidates)
    assert tuple(candidate.workload for candidate in candidates if candidate.equivalence is Equivalence.EQUIVALENT) == (
        'resolve_cached_singleton',
        'resolve_a_transient_chain',
        'construct_a_singleton_for_the_first_time',
    )
    for name in ('resolve_cached_singleton', 'resolve_a_transient_chain', 'construct_a_singleton_for_the_first_time'):
        implementation = by_name[name].implementation
        assert implementation is not None
        assert implementation.observe() == subjects[name].observe()

    assert by_name['open_and_close_a_scope'].reason == (
        'provider overrides are substitutions, not nested scope frames with scoped caches'
    )
    assert by_name['freeze_a_chain_of_10'].reason == (
        'Dependency Injector has no separate frozen resolution plan or depin graph diagnostics operation'
    )
    assert by_name['allocations_of_a_cached_singleton_resolution'].reason == (
        'the measured allocation, retention, or scaling source has no equivalent Dependency Injector operation'
    )
    assert by_name['fastapi_cpu_light_endpoint'].reason == (
        'the FastAPI integration has different request lifecycle and dependency declaration semantics'
    )
    assert by_name['resolve_cached_singleton_through_an_alias'].reason == (
        'Dependency Injector delegates do not provide depin typed-key alias resolution'
    )
    assert by_name['resolve_a_collection_of_10'].reason == (
        'Dependency Injector has no depin collection binding and aggregation operation'
    )
    assert by_name['call_through_an_inject_wrapper'].reason == (
        'Dependency Injector wiring does not share depin injection wrapper calling semantics'
    )
    assert by_name['resolve_through_an_active_override'].reason == (
        'Dependency Injector provider overrides are not depin context-local override frames'
    )
    assert by_name['resolve_an_async_singleton'].reason == (
        'Dependency Injector async and resource providers have different resolution and teardown semantics'
    )
    assert by_name['resolve_a_generic_key'].reason == (
        'Dependency Injector providers are not resolved from depin parameterised generic keys'
    )
    assert by_name['resolve_singleton_through_a_two_deep_decoration_chain'].reason == (
        'Dependency Injector provider composition does not model depin decoration chains'
    )
    assert by_name['resolve_with_no_active_override'].reason == (
        'Dependency Injector provider overrides are not depin context-local override frames'
    )


def test_dishka_singleton_transient_and_scoped_observations_match_depin() -> None:
    candidates = {candidate.workload: candidate for candidate in dishka_adapter.ADAPTER.candidates(WORKLOADS)}
    subjects = {workload.name: workload.subject for workload in WORKLOADS}

    for name in ('resolve_cached_singleton', 'resolve_a_transient_chain', 'open_and_close_a_scope'):
        implementation = candidates[name].implementation
        assert implementation is not None
        assert implementation.observe() == subjects[name].observe()


def test_dishka_scoped_leaf_is_reused_within_one_request_scope() -> None:
    prepared = dishka_adapter.scoped_chain(1)
    try:
        with prepared.container() as request_container:
            first = request_container.get(prepared.shape.leaf)
            second = request_container.get(prepared.shape.leaf)
    finally:
        prepared.close()

    assert first is second


def test_dishka_candidates_cover_workloads_in_order_with_three_equivalent_shapes() -> None:
    candidates = dishka_adapter.ADAPTER.candidates(WORKLOADS)
    subjects = {workload.name: workload.subject for workload in WORKLOADS}
    by_name = {candidate.workload: candidate for candidate in candidates}

    assert tuple(candidate.workload for candidate in candidates) == tuple(workload.name for workload in WORKLOADS)
    assert all(candidate.competitor == Competitor('dishka', '1.10.1') for candidate in candidates)
    assert tuple(candidate.workload for candidate in candidates if candidate.equivalence is Equivalence.EQUIVALENT) == (
        'resolve_cached_singleton',
        'resolve_a_transient_chain',
        'open_and_close_a_scope',
    )
    for name in ('resolve_cached_singleton', 'resolve_a_transient_chain', 'open_and_close_a_scope'):
        implementation = by_name[name].implementation
        assert implementation is not None
        assert implementation.label == 'dishka-1.10.1'
        assert implementation.observe() == subjects[name].observe()

    assert all(candidate.reason for candidate in candidates if candidate.equivalence is not Equivalence.EQUIVALENT)


def test_dishka_prepared_calls_preserve_core_lifetimes_and_allow_repeated_cleanup() -> None:
    candidates = {candidate.workload: candidate for candidate in dishka_adapter.ADAPTER.candidates(WORKLOADS)}
    values: dict[str, tuple[object, object]] = {}

    for name in ('resolve_cached_singleton', 'resolve_a_transient_chain', 'open_and_close_a_scope'):
        implementation = candidates[name].implementation
        assert implementation is not None
        prepared = implementation.prepare()
        close = prepared.close
        assert close is not None
        try:
            values[name] = (prepared.call(), prepared.call())
        finally:
            close()
            close()

    assert values['resolve_cached_singleton'][0] is values['resolve_cached_singleton'][1]
    assert values['resolve_a_transient_chain'][0] is not values['resolve_a_transient_chain'][1]
    assert values['open_and_close_a_scope'][0] is not values['open_and_close_a_scope'][1]


def test_dishka_scoped_prepared_cycle_closes_a_real_request_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[str] = []
    monkeypatch.setattr(dishka_adapter, 'chain', _tracked_chain_builder(log, CHAIN_DEPTH))
    candidate = next(
        candidate
        for candidate in dishka_adapter.ADAPTER.candidates(WORKLOADS)
        if candidate.workload == 'open_and_close_a_scope'
    )
    assert candidate.implementation is not None
    prepared = candidate.implementation.prepare()
    close = prepared.close
    assert close is not None
    try:
        _ = prepared.call()
        _ = prepared.call()
    finally:
        close()
        close()

    assert log == ['opened', 'closed', 'opened', 'closed']


def test_dishka_root_cleanup_closes_a_real_app_resource_once(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[str] = []
    monkeypatch.setattr(dishka_adapter, 'chain', _tracked_chain_builder(log, HOT_GRAPH))
    candidate = next(
        candidate
        for candidate in dishka_adapter.ADAPTER.candidates(WORKLOADS)
        if candidate.workload == 'resolve_cached_singleton'
    )
    assert candidate.implementation is not None
    prepared = candidate.implementation.prepare()
    close = prepared.close
    assert close is not None

    _ = prepared.call()
    close()
    close()

    assert log == ['opened', 'closed']


def test_wireup_singleton_transient_and_scoped_observations_match_depin() -> None:
    candidates = {candidate.workload: candidate for candidate in wireup_adapter.ADAPTER.candidates(WORKLOADS)}
    subjects = {workload.name: workload.subject for workload in WORKLOADS}

    for name in ('resolve_cached_singleton', 'resolve_a_transient_chain', 'open_and_close_a_scope'):
        implementation = candidates[name].implementation
        assert implementation is not None
        assert implementation.observe() == subjects[name].observe()


def test_wireup_prepared_calls_preserve_core_lifetimes_and_allow_repeated_cleanup() -> None:
    candidates = {candidate.workload: candidate for candidate in wireup_adapter.ADAPTER.candidates(WORKLOADS)}
    values: dict[str, tuple[object, object]] = {}

    for name in ('resolve_cached_singleton', 'resolve_a_transient_chain', 'open_and_close_a_scope'):
        implementation = candidates[name].implementation
        assert implementation is not None
        prepared = implementation.prepare()
        close = prepared.close
        assert close is not None
        try:
            values[name] = (prepared.call(), prepared.call())
        finally:
            close()
            close()

    assert values['resolve_cached_singleton'][0] is values['resolve_cached_singleton'][1]
    assert values['resolve_a_transient_chain'][0] is not values['resolve_a_transient_chain'][1]
    assert values['open_and_close_a_scope'][0] is not values['open_and_close_a_scope'][1]


def test_wireup_uses_root_get_for_singletons_and_scopes_for_other_lifetimes() -> None:
    singleton = wireup_adapter.warm_chain(1)
    try:
        singleton_first = singleton.container.get(singleton.shape.leaf)
        singleton_second = singleton.container.get(singleton.shape.leaf)
    finally:
        singleton.close()
        singleton.close()

    transient = wireup_adapter.transient_chain(1)
    try:
        with transient.container.enter_scope() as transient_scope:
            transient_first = transient_scope.get(transient.shape.leaf)
            transient_second = transient_scope.get(transient.shape.leaf)
    finally:
        transient.close()
        transient.close()

    scoped_chain = wireup_adapter.scoped_chain(1)
    try:
        with scoped_chain.container.enter_scope() as request:
            scoped_first = request.get(scoped_chain.shape.leaf)
            scoped_second = request.get(scoped_chain.shape.leaf)
    finally:
        scoped_chain.close()
        scoped_chain.close()

    assert singleton_first is singleton_second
    assert transient_first is not transient_second
    assert scoped_first is scoped_second


def test_wireup_candidates_cover_workloads_in_order_with_three_equivalent_shapes() -> None:
    candidates = wireup_adapter.ADAPTER.candidates(WORKLOADS)
    subjects = {workload.name: workload.subject for workload in WORKLOADS}
    by_name = {candidate.workload: candidate for candidate in candidates}

    assert tuple(candidate.workload for candidate in candidates) == tuple(workload.name for workload in WORKLOADS)
    assert all(candidate.competitor == Competitor('wireup', '2.12.0') for candidate in candidates)
    assert tuple(candidate.workload for candidate in candidates if candidate.equivalence is Equivalence.EQUIVALENT) == (
        'resolve_cached_singleton',
        'resolve_a_transient_chain',
        'open_and_close_a_scope',
    )
    for name in ('resolve_cached_singleton', 'resolve_a_transient_chain', 'open_and_close_a_scope'):
        implementation = by_name[name].implementation
        assert implementation is not None
        assert implementation.label == 'wireup-2.12.0'
        assert implementation.observe() == subjects[name].observe()

    assert all(candidate.reason for candidate in candidates if candidate.equivalence is not Equivalence.EQUIVALENT)
