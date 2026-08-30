"""Generative checks for the provider-graph validator."""

import inspect
from dataclasses import dataclass

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from depin import Container, Scope
from depin._core.frozen import FrozenContainer
from depin._core.spec import ResolutionPlan, fmt_key
from depin.errors import CaptiveDependencyError, CircularDependencyError, DepinError


@dataclass(frozen=True, slots=True)
class GraphCase:
    size: int
    edges: frozenset[tuple[int, int]]
    scopes: tuple[Scope, ...]
    registered: tuple[bool, ...]
    duplicates: frozenset[int]


def _set_dynamic_attribute(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def _frozen_plan(container: FrozenContainer) -> ResolutionPlan:
    plan = object.__getattribute__(container, '_plan')
    if isinstance(plan, ResolutionPlan):
        return plan
    raise AssertionError('FrozenContainer did not retain a ResolutionPlan')


def _materialize(case: GraphCase) -> Container:
    nodes = tuple(type(f'GraphNode{index}', (), {}) for index in range(case.size))
    for owner, node in enumerate(nodes):
        parameters = [inspect.Parameter('self', inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        annotations: dict[str, object] = {}
        for dependency in sorted(dependency for edge_owner, dependency in case.edges if edge_owner == owner):
            name = f'dependency_{dependency}'
            parameters.append(
                inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=nodes[dependency])
            )
            annotations[name] = nodes[dependency]

        def initialize(self: object, **values: object) -> None:
            return None

        _set_dynamic_attribute(initialize, '__annotations__', annotations)
        _set_dynamic_attribute(initialize, '__signature__', inspect.Signature(parameters))
        _set_dynamic_attribute(node, '__init__', initialize)

    container = Container()
    for index, node in enumerate(nodes):
        if case.registered[index]:
            _ = container.bind(node, scope=case.scopes[index])
            if index in case.duplicates:
                _ = container.bind(node, scope=case.scopes[index])
    return container


def _freeze_result(case: GraphCase) -> str:
    try:
        frozen = _materialize(case).freeze()
    except CircularDependencyError as error:
        return f'circular:{error}'
    except CaptiveDependencyError as error:
        return f'captive:{error}'
    except DepinError as error:
        return f'depin:{error}'
    except BaseException as error:
        return f'unexpected:{type(error).__name__}:{error}'
    else:
        plan = _frozen_plan(frozen)
        positions = {(spec.key, spec.tag): index for index, spec in enumerate(plan.order)}
        ordered = all(
            positions[(parameter.key, parameter.tag)] < positions[(spec.key, spec.tag)]
            for spec in plan.order
            for parameter in spec.params
        )
        return 'ordered' if ordered else 'out-of-order'


@st.composite
def _graphs(draw: st.DrawFn) -> GraphCase:
    size = draw(st.integers(min_value=1, max_value=8))
    edges = draw(st.sets(st.tuples(st.integers(0, size - 1), st.integers(0, size - 1))))
    scopes = tuple(draw(st.lists(st.sampled_from(tuple(Scope)), min_size=size, max_size=size)))
    registered = tuple(draw(st.lists(st.booleans(), min_size=size, max_size=size)))
    registered_nodes = tuple(index for index, is_registered in enumerate(registered) if is_registered)
    duplicates = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    return GraphCase(size, frozenset(edges), scopes, registered, frozenset(duplicates))


def _has_singleton_to_scoped_path(case: GraphCase) -> bool:
    dependencies = tuple(
        tuple(dependency for owner, dependency in case.edges if owner == node) for node in range(case.size)
    )
    for root, scope in enumerate(case.scopes):
        if scope is not Scope.SINGLETON:
            continue
        visited = {root}
        pending = [root]
        while pending:
            owner = pending.pop()
            for dependency in dependencies[owner]:
                if dependency in visited:
                    continue
                if case.scopes[dependency] is Scope.SCOPED:
                    return True
                visited.add(dependency)
                pending.append(dependency)
    return False


@st.composite
def _acyclic_graphs(draw: st.DrawFn) -> GraphCase:
    size = draw(st.integers(min_value=1, max_value=8))
    candidates = tuple((owner, dependency) for owner in range(size) for dependency in range(owner))
    edges = draw(st.sets(st.sampled_from(candidates))) if candidates else frozenset[tuple[int, int]]()
    scopes = tuple(draw(st.lists(st.sampled_from(tuple(Scope)), min_size=size, max_size=size)))
    return GraphCase(size, frozenset(edges), scopes, (True,) * size, frozenset())


@st.composite
def _non_captive_graphs(draw: st.DrawFn) -> GraphCase:
    return draw(_graphs().filter(lambda case: not _has_singleton_to_scoped_path(case)))


def test_a_cyclic_missing_graph_is_bounded_during_validation() -> None:
    safe_missing = GraphCase(
        size=3,
        edges=frozenset({(2, 1), (1, 0)}),
        scopes=(Scope.SINGLETON,) * 3,
        registered=(False, True, True),
        duplicates=frozenset(),
    )
    with pytest.raises(DepinError):
        _ = _materialize(safe_missing).freeze()

    cyclic_missing = GraphCase(
        size=3,
        edges=frozenset({(0, 1), (1, 0), (1, 2)}),
        scopes=(Scope.SINGLETON,) * 3,
        registered=(True, True, False),
        duplicates=frozenset(),
    )
    assert _freeze_result(cyclic_missing).startswith('depin:')


def test_singleton_to_scoped_reachability_follows_transient_edges_and_handles_cycles() -> None:
    captive = GraphCase(
        size=4,
        edges=frozenset({(0, 1), (1, 2), (2, 1)}),
        scopes=(Scope.SINGLETON, Scope.TRANSIENT, Scope.SCOPED, Scope.TRANSIENT),
        registered=(True,) * 4,
        duplicates=frozenset(),
    )
    non_captive = GraphCase(
        size=3,
        edges=frozenset({(1, 2)}),
        scopes=(Scope.SINGLETON, Scope.TRANSIENT, Scope.SCOPED),
        registered=(True,) * 3,
        duplicates=frozenset(),
    )

    assert _has_singleton_to_scoped_path(captive)
    assert not _has_singleton_to_scoped_path(non_captive)


@settings(max_examples=200, deadline=None)
@given(_graphs())
def test_freeze_returns_a_topological_plan_or_a_depin_error(case: GraphCase) -> None:
    result = _freeze_result(case)
    assert result == 'ordered' or result.startswith(('depin:', 'circular:', 'captive:')), result


@settings(max_examples=200, deadline=None)
@given(_graphs())
def test_graph_validation_never_leaks_a_non_depin_exception(case: GraphCase) -> None:
    result = _freeze_result(case)
    assert not result.startswith('unexpected:'), result


@settings(max_examples=200, deadline=None)
@given(_acyclic_graphs())
def test_an_acyclic_graph_never_reports_a_cycle(case: GraphCase) -> None:
    result = _freeze_result(case)
    assert not result.startswith('circular:'), result


@example(
    GraphCase(
        size=3,
        edges=frozenset({(1, 2)}),
        scopes=(Scope.SINGLETON, Scope.TRANSIENT, Scope.SCOPED),
        registered=(True, True, True),
        duplicates=frozenset(),
    )
)
@example(
    GraphCase(
        size=2,
        edges=frozenset({(1, 0)}),
        scopes=(Scope.SINGLETON, Scope.SINGLETON),
        registered=(True, True),
        duplicates=frozenset(),
    )
)
@settings(max_examples=200, deadline=None)
@given(_non_captive_graphs())
def test_a_graph_without_a_singleton_to_scoped_path_is_not_captive(case: GraphCase) -> None:
    result = _freeze_result(case)
    assert not result.startswith('captive:'), result


@given(case=_graphs())
def test_every_planned_provider_appears_as_exactly_one_node(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        frozen = container.freeze()
    except DepinError:
        return
    graph = frozen.graph()
    idents = [(node.key, node.tag) for node in graph.nodes]
    assert len(idents) == len(set(idents))
    assert len(idents) == len(_frozen_plan(frozen).order)


@example(
    case=GraphCase(
        size=2,
        edges=frozenset({(1, 0)}),
        scopes=(Scope.SINGLETON, Scope.SINGLETON),
        registered=(True, True),
        duplicates=frozenset(),
    )
)
@given(case=_graphs())
def test_every_edge_either_indexes_a_node_or_is_unsatisfied(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        graph = container.freeze().graph()
    except DepinError:
        return
    for node in graph.nodes:
        for edge in node.dependencies:
            assert edge.satisfied is (graph.find(edge.key, tag=edge.tag) is not None)


@given(case=_graphs())
def test_each_export_declares_one_entry_per_node(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        graph = container.freeze().graph()
    except DepinError:
        return
    # An unbound dot node ends `style=dashed];`, never `shape=box];`, so that
    # count is exact; an unbound mermaid node still opens with `["`, so that
    # count only lower-bounds the node total.
    assert graph.dot().count('shape=box];') == len(graph.nodes)
    assert graph.mermaid().count('["') >= len(graph.nodes)


@example(
    case=GraphCase(
        size=2,
        edges=frozenset({(1, 0)}),
        scopes=(Scope.SINGLETON, Scope.SINGLETON),
        registered=(True, True),
        duplicates=frozenset(),
    )
)
@given(case=_graphs())
def test_explain_names_every_key_reachable_from_its_root(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        frozen = container.freeze()
    except DepinError:
        return
    graph = frozen.graph()
    for root in graph.roots:
        text = frozen.explain(root.key, tag=root.tag)
        reachable: set[tuple[object, str | None]] = set()
        pending = [root]
        while pending:
            node = pending.pop()
            if (node.key, node.tag) in reachable:
                continue
            reachable.add((node.key, node.tag))
            for edge in node.dependencies:
                child = graph.find(edge.key, tag=edge.tag)
                if child is not None:
                    pending.append(child)
        for key, _tag in reachable:
            assert fmt_key(key) in text
