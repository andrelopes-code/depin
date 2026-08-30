"""Generative checks for the provider-graph validator."""

import inspect
from dataclasses import dataclass

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from depin import Container, Scope
from depin._core.graph import build_plan
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


@st.composite
def _arbitrary_graphs(draw: st.DrawFn) -> GraphCase:
    size = draw(st.integers(min_value=1, max_value=8))
    edges = draw(st.sets(st.tuples(st.integers(0, size - 1), st.integers(0, size - 1))))
    scopes = tuple(draw(st.lists(st.sampled_from(tuple(Scope)), min_size=size, max_size=size)))
    registered = tuple(draw(st.lists(st.booleans(), min_size=size, max_size=size)))
    registered_nodes = tuple(index for index, is_registered in enumerate(registered) if is_registered)
    duplicates = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    return GraphCase(size, frozenset(edges), scopes, registered, frozenset(duplicates))


@st.composite
def _acyclic_graphs(draw: st.DrawFn) -> GraphCase:
    size = draw(st.integers(min_value=1, max_value=8))
    candidates = tuple((owner, dependency) for owner in range(size) for dependency in range(owner))
    edges = draw(st.sets(st.sampled_from(candidates))) if candidates else frozenset[tuple[int, int]]()
    scopes = tuple(draw(st.lists(st.sampled_from(tuple(Scope)), min_size=size, max_size=size)))
    return GraphCase(size, frozenset(edges), scopes, (True,) * size, frozenset())


@st.composite
def _non_captive_graphs(draw: st.DrawFn) -> GraphCase:
    size = draw(st.integers(min_value=1, max_value=8))
    scopes = tuple(draw(st.lists(st.sampled_from(tuple(Scope)), min_size=size, max_size=size)))
    candidates = tuple(
        (owner, dependency)
        for owner in range(size)
        for dependency in range(size)
        if not (scopes[owner] in (Scope.SINGLETON, Scope.TRANSIENT) and scopes[dependency] is Scope.SCOPED)
    )
    edges = draw(st.sets(st.sampled_from(candidates)))
    registered = tuple(draw(st.lists(st.booleans(), min_size=size, max_size=size)))
    registered_nodes = tuple(index for index, is_registered in enumerate(registered) if is_registered)
    duplicates = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    return GraphCase(size, frozenset(edges), scopes, registered, frozenset(duplicates))


@settings(max_examples=200, deadline=None)
@given(_arbitrary_graphs())
def test_freeze_returns_a_topological_plan_or_a_depin_error(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        _ = container.freeze()
    except DepinError:
        return

    plan = build_plan(container.records())
    positions = {(spec.key, spec.tag): index for index, spec in enumerate(plan.order)}
    for spec in plan.order:
        for parameter in spec.params:
            assert positions[(parameter.key, parameter.tag)] < positions[(spec.key, spec.tag)]


@settings(max_examples=200, deadline=None)
@given(_arbitrary_graphs())
def test_graph_validation_never_leaks_a_non_depin_exception(case: GraphCase) -> None:
    try:
        _ = _materialize(case).freeze()
    except DepinError:
        return
    except Exception as error:
        pytest.fail(f'graph validation leaked {type(error).__name__}: {error}')


@settings(max_examples=200, deadline=None)
@given(_acyclic_graphs())
def test_an_acyclic_graph_never_reports_a_cycle(case: GraphCase) -> None:
    try:
        _ = _materialize(case).freeze()
    except CircularDependencyError as error:
        pytest.fail(f'acyclic graph reported a cycle: {error}')
    except DepinError:
        return


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
    try:
        _ = _materialize(case).freeze()
    except CaptiveDependencyError as error:
        pytest.fail(f'non-captive graph reported a captive dependency: {error}')
    except DepinError:
        return
