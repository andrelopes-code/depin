"""Generative checks for the provider-graph validator."""

import inspect
from dataclasses import dataclass, replace
from types import GenericAlias

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from depin import Container, Scope
from depin._core.frozen import FrozenContainer
from depin._core.graph import INACTIVE_NOTE
from depin._core.spec import ResolutionPlan, fmt_key
from depin.errors import CaptiveDependencyError, CircularDependencyError, DepinError


@dataclass(frozen=True, slots=True)
class GraphCase:
    size: int
    edges: frozenset[tuple[int, int]]
    scopes: tuple[Scope, ...]
    registered: tuple[bool, ...]
    duplicates: frozenset[int]
    aliases: frozenset[int] = frozenset()
    optionals: frozenset[tuple[int, int]] = frozenset()
    collections: frozenset[int] = frozenset()
    generics: frozenset[int] = frozenset()
    decorations: frozenset[int] = frozenset()
    inactive: frozenset[int] = frozenset()
    checks: frozenset[int] = frozenset()


class _GenericMarker0: ...


class _GenericMarker1: ...


class _GenericMarker2: ...


class _GenericMarker3: ...


class _GenericMarker4: ...


class _GenericMarker5: ...


class _GenericMarker6: ...


class _GenericMarker7: ...


class _GenericContainer[T]:
    """Wraps a node's key in a parameterised generic, declared once for `GraphCase.generics`.

    `_materialize` builds each node's own class at runtime with `type(...)`, and
    subscripting a generic origin with a runtime-only type fails mypy's static
    check of the subscript ("Variable is not valid as a type"). Subscripting this
    container with one of the fixed, statically-known markers below sidesteps
    that: the resulting key is an ordinary canonical generic, just like `Repo[User]`.
    """


_GENERIC_KEYS: tuple[type[object], ...] = (
    _GenericContainer[_GenericMarker0],
    _GenericContainer[_GenericMarker1],
    _GenericContainer[_GenericMarker2],
    _GenericContainer[_GenericMarker3],
    _GenericContainer[_GenericMarker4],
    _GenericContainer[_GenericMarker5],
    _GenericContainer[_GenericMarker6],
    _GenericContainer[_GenericMarker7],
)


def _always_healthy(value: object) -> None:
    return None


def _set_dynamic_attribute(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def _frozen_plan(container: FrozenContainer) -> ResolutionPlan:
    plan = object.__getattribute__(container, '_plan')
    if isinstance(plan, ResolutionPlan):
        return plan
    raise AssertionError('FrozenContainer did not retain a ResolutionPlan')


def _bind_consumer(container: Container, name: str, key: object) -> None:
    """Bind a fresh singleton depending on `key`, so a generated alias or collection sits on a real path."""
    parameters = [
        inspect.Parameter('self', inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter('value', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=key),
    ]

    def initialize(self: object, **values: object) -> None:
        return None

    _set_dynamic_attribute(initialize, '__annotations__', {'value': key})
    _set_dynamic_attribute(initialize, '__signature__', inspect.Signature(parameters))
    consumer = type(name, (), {})
    _set_dynamic_attribute(consumer, '__init__', initialize)
    _ = container.bind(consumer)


def _bind_decorator(container: Container, name: str, key: type[object]) -> None:
    """Decorate `key` with a generated class taking the undecorated value as its one parameter."""
    parameters = [
        inspect.Parameter('self', inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter('inner', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=key),
    ]

    def initialize(self: object, **values: object) -> None:
        return None

    _set_dynamic_attribute(initialize, '__annotations__', {'inner': key})
    _set_dynamic_attribute(initialize, '__signature__', inspect.Signature(parameters))
    wrapper = type(name, (), {})
    _set_dynamic_attribute(wrapper, '__init__', initialize)
    _ = container.decorate(key, wrapper)


def _materialize(case: GraphCase) -> Container:
    nodes = tuple(type(f'GraphNode{index}', (), {}) for index in range(case.size))
    # A node in `case.generics` is registered and referenced by a parameterised
    # generic key instead of its own class — see `_GenericContainer`.
    keys: tuple[type[object], ...] = tuple(
        _GENERIC_KEYS[index] if index in case.generics else node for index, node in enumerate(nodes)
    )
    for owner, node in enumerate(nodes):
        parameters = [inspect.Parameter('self', inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        annotations: dict[str, object] = {}
        for dependency in sorted(dependency for edge_owner, dependency in case.edges if edge_owner == owner):
            name = f'dependency_{dependency}'
            annotation: object = keys[dependency] | None if (owner, dependency) in case.optionals else keys[dependency]
            parameters.append(inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation))
            annotations[name] = annotation

        def initialize(self: object, **values: object) -> None:
            return None

        _set_dynamic_attribute(initialize, '__annotations__', annotations)
        _set_dynamic_attribute(initialize, '__signature__', inspect.Signature(parameters))
        _set_dynamic_attribute(node, '__init__', initialize)

    container = Container()
    for index, node in enumerate(nodes):
        if case.registered[index]:
            provides = keys[index] if index in case.generics else None
            check = _always_healthy if index in case.checks else None
            _ = container.bind(node, scope=case.scopes[index], provides=provides, check=check)
            if index in case.duplicates:
                _ = container.bind(node, scope=case.scopes[index], provides=provides, check=check)
    for index in case.aliases:
        alias_key = type(f'GraphAlias{index}', (), {})
        _ = container.alias(alias_key, to=keys[index])
        _bind_consumer(container, f'GraphAliasConsumer{index}', alias_key)
    for index in case.collections:
        element = type(f'GraphCollectionElement{index}', (), {})
        _ = container.collect(element, [keys[index]])
        _bind_consumer(container, f'GraphCollectionConsumer{index}', GenericAlias(list, (element,)))
    for index in case.decorations:
        _bind_decorator(container, f'GraphDecorator{index}', keys[index])
    for index in case.inactive:
        _ = container.bind(type(f'GraphInactive{index}', (), {}), provides=keys[index], when=False)
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
        ordered = True
        for spec in plan.order:
            for parameter in spec.params:
                ident = (parameter.key, parameter.tag)
                # An unbound optional or defaulted parameter has no entry in `positions`:
                # nothing provides it, so it constrains no ordering. Any other absence is
                # a bug the invariant must still catch, via the KeyError the lookup below raises.
                if ident not in positions and (parameter.optional or parameter.has_default):
                    continue
                if positions[ident] >= positions[(spec.key, spec.tag)]:
                    ordered = False
        return 'ordered' if ordered else 'out-of-order'


@st.composite
def _graphs(draw: st.DrawFn) -> GraphCase:
    size = draw(st.integers(min_value=1, max_value=8))
    edges = draw(st.sets(st.tuples(st.integers(0, size - 1), st.integers(0, size - 1))))
    scopes = tuple(draw(st.lists(st.sampled_from(tuple(Scope)), min_size=size, max_size=size)))
    registered = tuple(draw(st.lists(st.booleans(), min_size=size, max_size=size)))
    registered_nodes = tuple(index for index, is_registered in enumerate(registered) if is_registered)
    duplicates = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    aliases = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    optionals = draw(st.sets(st.sampled_from(tuple(edges)))) if edges else frozenset[tuple[int, int]]()
    collections = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    generics = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    decorations = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    unregistered = tuple(index for index, is_registered in enumerate(registered) if not is_registered)
    inactive = draw(st.sets(st.sampled_from(unregistered))) if unregistered else frozenset[int]()
    checks = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    return GraphCase(
        size,
        frozenset(edges),
        scopes,
        registered,
        frozenset(duplicates),
        frozenset(aliases),
        frozenset(optionals),
        frozenset(collections),
        frozenset(generics),
        frozenset(decorations),
        frozenset(inactive),
        frozenset(checks),
    )


def _reaches_scoped(dependencies: tuple[tuple[int, ...], ...], scopes: tuple[Scope, ...], start: int) -> bool:
    visited = {start}
    pending = [start]
    while pending:
        owner = pending.pop()
        for dependency in dependencies[owner]:
            if dependency in visited:
                continue
            if scopes[dependency] is Scope.SCOPED:
                return True
            visited.add(dependency)
            pending.append(dependency)
    return False


def _has_singleton_to_scoped_path(case: GraphCase) -> bool:
    """Whether some singleton in the materialized graph transitively captures a scoped provider.

    Beyond `case.edges`, `_materialize` adds a singleton consumer for every generated
    alias and collection, each reaching straight into `nodes[index]`. Those synthetic
    roots are folded in here as `virtual_roots`, so the filter still matches what gets
    built.
    """
    dependencies = tuple(
        tuple(dependency for owner, dependency in case.edges if owner == node) for node in range(case.size)
    )
    for root, scope in enumerate(case.scopes):
        if scope is Scope.SINGLETON and _reaches_scoped(dependencies, case.scopes, root):
            return True
    virtual_roots = set(case.aliases) | set(case.collections)
    for index in virtual_roots:
        if case.scopes[index] is Scope.SCOPED or _reaches_scoped(dependencies, case.scopes, index):
            return True
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


@settings(deadline=None)
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
@settings(deadline=None)
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


@settings(deadline=None)
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
@settings(deadline=None)
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


@settings(deadline=None)
@given(_graphs())
def test_an_inactive_binding_leaves_the_plan_as_if_it_were_never_written(case: GraphCase) -> None:
    """A `when=False` binding must produce exactly the plan that omitting it produces.

    Only the note naming the key as inactive may differ, which is the one thing
    an omitted binding cannot say.
    """
    with_inactive = _freeze_result(case).replace(INACTIVE_NOTE, '')
    without = _freeze_result(replace(case, inactive=frozenset()))
    assert with_inactive == without


@settings(deadline=None)
@given(_graphs())
def test_declaring_a_check_changes_nothing_about_the_plan(case: GraphCase) -> None:
    """A check is a value the plan carries, not a rule it applies."""
    assert _freeze_result(case) == _freeze_result(replace(case, checks=frozenset()))


@settings(deadline=None)
@given(case=_graphs())
def test_checks_reports_exactly_the_specs_the_plan_marked_checked(case: GraphCase) -> None:
    """A check is neither lost nor invented by validation, decoration, or the async pass."""
    container = _materialize(case)
    try:
        frozen = container.freeze()
    except DepinError:
        return
    plan = _frozen_plan(frozen)
    expected = {(spec.key, spec.tag) for spec in plan.order if spec.check is not None}
    actual = {(check.key, check.tag) for check in frozen.checks()}
    assert actual == expected
