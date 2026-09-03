import os
from collections.abc import Callable, Generator
from importlib.metadata import PackageNotFoundError
from typing import Protocol

import pytest

import benchmarks.comparison.adapters.dependency_injector as dependency_injector_adapter
import benchmarks.comparison.adapters.dishka as dishka_adapter
import benchmarks.comparison.adapters.svcs as svcs_adapter
import benchmarks.comparison.adapters.wireup as wireup_adapter
from benchmarks.comparison.adapters.dependency_injector import ADAPTER, warm_chain
from benchmarks.comparison.contracts import Candidate, Competitor, Equivalence
from benchmarks.comparison.inventory import build
from benchmarks.comparison.shapes import Chain, chain, observation
from benchmarks.contracts import Cost, Implementation, Observation, Prepared, Workload
from benchmarks.harness import HarnessError, reduce
from benchmarks.workloads import WORKLOADS
from benchmarks.workloads.micro import CHAIN_DEPTH, HOT_GRAPH


class _TrackedResource:
    pass


class _RegistryCloseMarker:
    pass


class _RegistryWithCloseCallback(Protocol):
    def register_factory(
        self,
        svc_type: type[object],
        factory: Callable[..., object],
        *,
        on_registry_close: Callable[[], None],
    ) -> None: ...


def _register_close_callback(registry: _RegistryWithCloseCallback, callback: Callable[[], None]) -> None:
    registry.register_factory(_RegistryCloseMarker, _RegistryCloseMarker, on_registry_close=callback)


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


def test_wireup_singleton_prepare_warms_the_leaf_before_the_measured_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[str] = []
    monkeypatch.setattr(wireup_adapter, 'chain', _tracked_chain_builder(log, HOT_GRAPH))
    candidate = next(
        candidate
        for candidate in wireup_adapter.ADAPTER.candidates(WORKLOADS)
        if candidate.workload == 'resolve_cached_singleton'
    )

    assert candidate.implementation is not None
    prepared = candidate.implementation.prepare()
    close = prepared.close
    assert close is not None
    try:
        assert log == ['opened']
        _ = prepared.call()
        assert log == ['opened']
    finally:
        close()
        close()

    assert log == ['opened', 'closed']


def test_wireup_scoped_prepared_cycle_closes_a_real_request_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    log: list[str] = []
    monkeypatch.setattr(wireup_adapter, 'chain', _tracked_chain_builder(log, CHAIN_DEPTH))
    candidate = next(
        candidate
        for candidate in wireup_adapter.ADAPTER.candidates(WORKLOADS)
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


def test_wireup_version_guard_rejects_a_missing_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(wireup_adapter, 'version', missing)

    with pytest.raises(HarnessError, match='wireup is not installed in the bench group'):
        wireup_adapter.require_installed_version()


def test_wireup_version_guard_rejects_a_different_distribution_version(monkeypatch: pytest.MonkeyPatch) -> None:
    def different_version(_: str) -> str:
        return '2.12.1'

    monkeypatch.setattr(wireup_adapter, 'version', different_version)

    with pytest.raises(HarnessError, match=r'wireup 2\.12\.1 is installed; 2\.12\.0 is required'):
        wireup_adapter.require_installed_version()


def test_svcs_container_caches_one_shared_chain_per_container_and_closes_it() -> None:
    candidate = next(
        candidate
        for candidate in svcs_adapter.ADAPTER.candidates(WORKLOADS)
        if candidate.workload == 'resolve_cached_singleton'
    )

    assert candidate.competitor == Competitor('svcs', '26.1.0')
    assert candidate.equivalence is Equivalence.PARTIAL
    assert candidate.implementation is not None
    assert candidate.implementation.label == 'svcs-26.1.0'
    assert candidate.reason == (
        'per-container caching has no singleton single-flight guarantee or nested lifetime contract'
    )

    prepared = candidate.implementation.prepare()
    close = prepared.close
    assert close is not None
    try:
        first = prepared.call()
        second = prepared.call()
    finally:
        close()
        close()

    assert first is second


def test_svcs_candidates_cover_workloads_in_order_with_one_partial_shape() -> None:
    candidates = svcs_adapter.ADAPTER.candidates(WORKLOADS)

    assert tuple(candidate.workload for candidate in candidates) == tuple(workload.name for workload in WORKLOADS)
    assert all(candidate.competitor == Competitor('svcs', '26.1.0') for candidate in candidates)
    assert tuple(candidate.workload for candidate in candidates if candidate.equivalence is Equivalence.PARTIAL) == (
        'resolve_cached_singleton',
    )
    assert all(candidate.reason for candidate in candidates if candidate.equivalence is not Equivalence.EQUIVALENT)


def test_svcs_partial_candidate_observes_the_subject_construction_order() -> None:
    workload = next(workload for workload in WORKLOADS if workload.name == 'resolve_cached_singleton')
    candidate = next(
        candidate for candidate in svcs_adapter.ADAPTER.candidates(WORKLOADS) if candidate.workload == workload.name
    )

    assert candidate.implementation is not None
    assert candidate.implementation.observe() == workload.subject.observe()


def test_svcs_closes_container_cache_and_registry_callback_once() -> None:
    close_log: list[str] = []

    def record_registry_close() -> None:
        close_log.append('registry')

    chain = svcs_adapter.warm_chain(1)
    _register_close_callback(chain.registry, record_registry_close)
    first = chain.container.get(chain.shape.leaf)
    chain.container.close()
    second = chain.container.get(chain.shape.leaf)

    prepared = Prepared(call=lambda: second, close=chain.close)
    close = prepared.close
    assert close is not None
    close()
    close()

    assert first is not second
    assert close_log == ['registry']


class Benchmark(Protocol):
    extra_info: dict[str, object]

    def __call__[T](self, function: Callable[[], T]) -> T: ...


_CASES: tuple[tuple[str, Workload, Implementation, Candidate | None], ...] = tuple(
    item
    for comparative in build()
    if comparative.target is not None
    for item in (
        (f'{comparative.workload.name}-depin', comparative.workload, comparative.workload.subject, None),
        *(
            (
                f'{comparative.workload.name}-{comparative.workload.baseline.label}',
                comparative.workload,
                comparative.workload.baseline,
                None,
            )
            for _ in (0,)
            if comparative.workload.baseline is not None
        ),
        *(
            (
                f'{comparative.workload.name}-{candidate.implementation.label}',
                comparative.workload,
                candidate.implementation,
                candidate,
            )
            for candidate in comparative.candidates
            if candidate.implementation is not None
        ),
    )
)


def _implementation_for_mode(name: str, workload: Workload, implementation: Implementation) -> Implementation:
    if os.environ.get('DEPIN_COMPARISON_NULL') == '1' and name.endswith('-direct'):
        return workload.subject
    return implementation


def _ordered_cases() -> tuple[tuple[str, Workload, Implementation, Candidate | None], ...]:
    cases = _CASES
    if os.environ.get('DEPIN_COMPARISON_NULL') == '1':
        cases = tuple(case for case in cases if case[3] is None and case[0].endswith(('-depin', '-direct')))
    if os.environ.get('DEPIN_COMPARISON_ORDER') == 'reverse':
        return tuple(reversed(cases))
    return cases


@pytest.mark.parametrize(
    ('workload', 'implementation', 'candidate'),
    [
        pytest.param(
            workload,
            _implementation_for_mode(name, workload, implementation),
            candidate,
            marks=pytest.mark.benchmark(min_rounds=reduce.MINIMUM_ROUNDS),
            id=name,
        )
        for name, workload, implementation, candidate in _ordered_cases()
    ],
)
def test_comparison(
    benchmark: Benchmark,
    workload: Workload,
    implementation: Implementation,
    candidate: Candidate | None,
) -> None:
    if (
        candidate is not None
        and candidate.equivalence is Equivalence.EQUIVALENT
        and implementation.observe() != workload.subject.observe()
    ):
        raise HarnessError(
            f'{workload.name}: {candidate.competitor.label} claims equivalence with a different observation'
        )
    prepared = implementation.prepare()
    try:
        outcome = benchmark(prepared.call)
    finally:
        if prepared.close is not None:
            prepared.close()
    benchmark.extra_info['equivalence'] = 'subject' if candidate is None else candidate.equivalence.value
    benchmark.extra_info['reason'] = 'depin subject' if candidate is None else candidate.reason
    benchmark.extra_info['tier'] = workload.tier.value
    if isinstance(outcome, Cost):
        benchmark.extra_info['cpu_nanoseconds'] = outcome.cpu_nanoseconds


def test_comparison_files_tier_and_cpu_for_cost_outcomes() -> None:
    class CapturingBenchmark:
        def __init__(self) -> None:
            self.extra_info: dict[str, object] = {}

        def __call__[T](self, function: Callable[[], T]) -> T:
            return function()

    workload = WORKLOADS[0]
    implementation = Implementation(
        'cost', lambda: Prepared(call=lambda: Cost(cpu_nanoseconds=17)), workload.subject.observe
    )
    benchmark = CapturingBenchmark()

    test_comparison(benchmark, workload, implementation, None)

    assert benchmark.extra_info['tier'] == workload.tier.value
    assert benchmark.extra_info['cpu_nanoseconds'] == 17


def test_null_mode_runs_the_direct_label_with_the_depin_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    workload = next(workload for workload in WORKLOADS if workload.baseline is not None)
    baseline = workload.baseline
    assert baseline is not None

    monkeypatch.setenv('DEPIN_COMPARISON_NULL', '1')

    assert _implementation_for_mode(f'{workload.name}-direct', workload, baseline) is workload.subject
    assert _implementation_for_mode(f'{workload.name}-depin', workload, workload.subject) is workload.subject

    monkeypatch.delenv('DEPIN_COMPARISON_NULL')

    assert _implementation_for_mode(f'{workload.name}-direct', workload, baseline) is baseline


def test_null_mode_excludes_candidate_cases_while_real_mode_keeps_them(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DEPIN_COMPARISON_NULL', '1')

    null_cases = _ordered_cases()

    assert null_cases
    assert all(candidate is None for _, _, _, candidate in null_cases)
    assert all(name.endswith(('-depin', '-direct')) for name, _, _, _ in null_cases)

    monkeypatch.delenv('DEPIN_COMPARISON_NULL')

    assert any(candidate is not None for _, _, _, candidate in _ordered_cases())
