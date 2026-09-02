"""Differential and complexity checks for `depin._core.longest_chain`.

`_reference_collect_missing` and `_reference_deepest_requirement` are verbatim
copies of the two walks the module replaced, kept here so every generated graph
can be checked against the chain the library used to report — contents and
tie-break included.
"""

import time
from dataclasses import dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from depin import Container, DependencyGraph, GraphEdge, GraphNode, Registry, Scope
from depin._core import longest_chain
from depin._core.graph import build_plan
from depin._core.spec import Ident, ParamSpec, ProviderKey, ProviderShape, ProviderSpec
from depin.errors import MissingProviderError

# Hypothesis-driven property module; its slowest case runs under a second, and
# the two complexity cases assert half-second and fifth-of-a-second budgets of
# their own. Fifteen seconds is the same margin the other property modules take,
# and still catches the hung mutant the mutation gate's --timeout=2 targets.
pytestmark = pytest.mark.timeout(15)

type _Reference = dict[Ident, tuple[tuple[ProviderSpec, ...], ProviderSpec, str]]


def _reference_collect_missing(
    root: ProviderSpec,
    by_key: dict[Ident, ProviderSpec],
    chain: tuple[ProviderSpec, ...],
    missing: _Reference,
) -> None:
    stack: list[tuple[ProviderSpec, tuple[ProviderSpec, ...]]] = [(root, chain)]
    while stack:
        spec, current_chain = stack.pop()
        chain_specs = {id(c) for c in current_chain}
        for param in spec.params:
            dep = by_key.get((param.key, param.tag))
            if dep is None:
                if param.has_default or param.optional:
                    continue
                ident = (param.key, param.tag)
                if ident not in missing or len(current_chain) > len(missing[ident][0]):
                    missing[ident] = (current_chain, spec, param.name)
                continue
            if id(dep) in chain_specs:
                continue
            stack.append((dep, (*current_chain, dep)))


def _reference_deepest_requirement(
    graph: DependencyGraph,
    key: ProviderKey,
    tag: str | None,
) -> tuple[tuple[ProviderKey, ...], ProviderKey, str] | None:
    best: tuple[tuple[ProviderKey, ...], ProviderKey, str] | None = None
    for root in graph.nodes:
        stack: list[tuple[GraphNode, tuple[Ident, ...]]] = [(root, ((root.key, root.tag),))]
        while stack:
            node, chain = stack.pop()
            for edge in node.dependencies:
                child = graph.find(edge.key, tag=edge.tag)
                if child is None:
                    if edge.optional and not edge.has_default:
                        continue
                    if (edge.key, edge.tag) == (key, tag) and (best is None or len(chain) > len(best[0])):
                        best = (tuple(ident[0] for ident in chain), node.key, edge.parameter)
                    continue
                if (child.key, child.tag) in chain:
                    continue
                stack.append((child, (*chain, (child.key, child.tag))))
    return best


@dataclass(frozen=True, slots=True)
class _Param:
    name: str
    key: str
    tag: str | None
    has_default: bool
    optional: bool


@dataclass(frozen=True, slots=True)
class _Case:
    tags: tuple[str | None, ...]
    params: tuple[tuple[_Param, ...], ...]


_TAGS: tuple[str | None, ...] = (None, 'a')
_UNBOUND: tuple[str, ...] = ('m0', 'm1')


@st.composite
def _cases(draw: st.DrawFn, *, acyclic: bool) -> _Case:
    """Random provider graphs over string keys, two tags and two unbound keys.

    ``acyclic`` restricts every edge to a lower-numbered node, which forces the
    dynamic program; the free form reaches the enumerating walk instead, since a
    node may name itself or any node after it.
    """
    size = draw(st.integers(min_value=1, max_value=7))
    tags = tuple(draw(st.sampled_from(_TAGS)) for _ in range(size))
    rows: list[tuple[_Param, ...]] = []
    for position in range(size):
        reachable = position if acyclic else size
        targets = [f'k{other}' for other in range(reachable)] + list(_UNBOUND)
        count = draw(st.integers(min_value=0, max_value=3))
        rows.append(
            tuple(
                _Param(
                    name=f'p{offset}',
                    key=draw(st.sampled_from(targets)),
                    tag=draw(st.sampled_from(_TAGS)),
                    has_default=draw(st.booleans()),
                    optional=draw(st.booleans()),
                )
                for offset in range(count)
            )
        )
    return _Case(tags=tags, params=tuple(rows))


def _specs(case: _Case) -> tuple[ProviderSpec, ...]:
    return tuple(
        ProviderSpec(
            key=f'k{position}',
            tag=case.tags[position],
            source=None,
            scope=Scope.SINGLETON,
            shape=ProviderShape.CLASS,
            needs_async=False,
            params=tuple(
                ParamSpec(
                    name=param.name,
                    key=param.key,
                    tag=param.tag,
                    has_default=param.has_default,
                    default=None,
                    optional=param.optional,
                )
                for param in case.params[position]
            ),
        )
        for position in range(len(case.tags))
    )


def _graph(case: _Case) -> DependencyGraph:
    bound = {(spec.key, spec.tag) for spec in _specs(case)}
    return DependencyGraph(
        tuple(
            GraphNode(
                key=spec.key,
                tag=spec.tag,
                scope=spec.scope,
                shape=spec.shape,
                needs_async=spec.needs_async,
                dependencies=tuple(
                    GraphEdge(
                        parameter=param.name,
                        key=param.key,
                        tag=param.tag,
                        satisfied=(param.key, param.tag) in bound,
                        optional=param.optional,
                        has_default=param.has_default,
                    )
                    for param in spec.params
                ),
            )
            for spec in _specs(case)
        )
    )


def _assert_over_specs_agrees(case: _Case) -> None:
    specs = _specs(case)
    by_key = {(spec.key, spec.tag): spec for spec in specs}
    reference: _Reference = {}
    for root in specs:
        _reference_collect_missing(root, by_key, (root,), reference)

    expected = [
        (ident, tuple((step.key, step.tag) for step in chain), (owner.key, owner.tag), name)
        for ident, (chain, owner, name) in reference.items()
    ]
    produced = [
        (ident, found.chain, found.owner, found.parameter) for ident, found in longest_chain.over_specs(specs).items()
    ]

    assert produced == expected


@settings(max_examples=200, deadline=None)
@given(_cases(acyclic=True))
def test_over_specs_on_a_dag_reports_what_the_replaced_walk_reported(case: _Case) -> None:
    """The dynamic program's own branch: every missing key, chain, owner and order.

    The comparison is over lists rather than dicts, so the insertion order that
    `freeze()`'s stable sort by chain length preserves is pinned as well as the
    entries themselves.
    """
    _assert_over_specs_agrees(case)


@settings(max_examples=200, deadline=None)
@given(_cases(acyclic=False))
def test_over_specs_on_a_cyclic_graph_reports_what_the_replaced_walk_reported(case: _Case) -> None:
    """The fallback branch, which no polynomial algorithm may replace."""
    _assert_over_specs_agrees(case)


@settings(max_examples=200, deadline=None)
@given(_cases(acyclic=False))
def test_over_graph_reports_what_the_replaced_walk_reported(case: _Case) -> None:
    """The chain `explain()` prints for an unbound key, against the old walk.

    Asked about every key any node names plus keys no node names at all, so the
    "nothing requires it" answer is compared too.
    """
    graph = _graph(case)
    found = longest_chain.over_graph(graph)
    targets = [(edge.key, edge.tag) for node in graph.nodes for edge in node.dependencies]
    targets += [(key, tag) for key in ('k0', *_UNBOUND, 'absent') for tag in _TAGS]

    for key, tag in targets:
        entry = found.get((key, tag))
        produced = None if entry is None else (tuple(step[0] for step in entry.chain), entry.owner[0], entry.parameter)

        assert produced == _reference_deepest_requirement(graph, key, tag)


class _CycleGone: ...


class _CycleHead:
    def __init__(self, tail: '_CycleTail') -> None: ...


class _CycleTail:
    def __init__(self, head: _CycleHead, gone: _CycleGone) -> None: ...


def test_a_cycle_beside_a_missing_provider_keeps_its_reported_chain() -> None:
    """The exact text the enumerating fallback produces, pinned.

    `build_plan` checks for a missing provider before it checks for a cycle, so
    this graph reaches the fallback rather than the dynamic program, and its
    chain is one no polynomial algorithm reproduces.
    """
    records = Registry().bind(_CycleHead).bind(_CycleTail).records()

    with pytest.raises(MissingProviderError) as raised:
        _ = build_plan(records)

    assert 'required by _CycleTail.gone' in str(raised.value)
    assert 'resolution chain: _CycleHead -> _CycleTail -> _CycleGone' in str(raised.value)


def _bind_all(namespace: dict[str, object], size: int) -> Container:
    container = Container()
    for position in range(size):
        built = namespace[f'N{position}']
        assert isinstance(built, type)
        container = container.bind(built)
    return container


def _chain_namespace(size: int) -> dict[str, object]:
    """A linear chain of ``size`` providers whose deepest node needs an unbound key."""
    source = ['class Missing: ...', 'class N0:\n    def __init__(self, dep: Missing) -> None: ...']
    source += [
        f'class N{position}:\n    def __init__(self, dep: N{position - 1}) -> None: ...' for position in range(1, size)
    ]
    namespace: dict[str, object] = {}
    exec('\n'.join(source), namespace)
    return namespace


def _layered_namespace(size: int) -> dict[str, object]:
    """A fan-in-2 DAG: node ``i`` depends on ``i - 1`` and ``i - 2``, plus an unbound key."""
    source = ['class N0: ...', 'class N1:\n    def __init__(self, a: N0) -> None: ...']
    source += [
        f'class N{position}:\n    def __init__(self, a: N{position - 1}, b: N{position - 2}) -> None: ...'
        for position in range(2, size)
    ]
    source.append('class Absent: ...')
    namespace: dict[str, object] = {}
    exec('\n'.join(source), namespace)
    return namespace


def test_failing_freeze_is_not_cubic_in_the_chain_length() -> None:
    """400 providers deep, reported well inside half a second.

    The enumerating walk took 1.4 s on the host this was written on and grew as
    the cube of the chain length. The budget states a complexity class, not a
    timing: it leaves the dynamic program two orders of magnitude of headroom
    for a shared runner while staying under what the walk it replaced reached.
    """
    container = _bind_all(_chain_namespace(400), 400)

    start = time.perf_counter()
    with pytest.raises(MissingProviderError, match='no provider for Missing'):
        _ = container.freeze()
    elapsed = time.perf_counter() - start

    assert elapsed < 0.5


def test_explain_of_an_unbound_key_is_not_exponential_in_the_path_count() -> None:
    """A 24-node fan-in-2 DAG carries Fibonacci-many simple paths.

    The enumerating walk took 0.36 s on the host this was written on and roughly
    tripled every four nodes. Same budget rationale as the freeze case.
    """
    namespace = _layered_namespace(24)
    frozen = _bind_all(namespace, 24).freeze()
    absent = namespace['Absent']
    assert isinstance(absent, type)

    start = time.perf_counter()
    reported = frozen.explain(absent)
    elapsed = time.perf_counter() - start

    assert 'no provider for Absent' in reported
    assert elapsed < 0.2
