"""Differential and complexity checks for `depin._core.longest_chain`.

`_reference_collect_missing` and `_reference_deepest_requirement` are verbatim
copies of the two walks the module replaced, kept here so every generated graph
can be checked against the chain the library used to report — contents and
tie-break included.
"""

import time
from collections.abc import Callable
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
# the two complexity cases measure two sizes three times each. Fifteen seconds is
# the same margin the other property modules take, and still catches the hung
# mutant the mutation gate's --timeout=2 targets.
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


CUBIC_GROWTH_LIMIT = 3.0
"""What doubling a chain may multiply the failing-freeze cost by.

Doubling the length doubles a linear walk and multiplies a cubic one by eight.
Measured over 200 and 400 providers: **1.80** as the repaired code stands, and
**5.91** with `benchmarks/seeds/scaling-restore-enumerating-walk.patch` applied.
Three sits between them with room on both sides.
"""

PATH_GROWTH_LIMIT = 2.0
"""What going from 16 to 24 nodes may multiply the missing-key walk's cost by.

The number of simple paths through a fan-in-2 DAG is Fibonacci in its size, so
those eight nodes multiply the path count by about eighteen. Measured: **1.00**
repaired, **33.84** seeded.
"""


def _growth(smaller: Callable[[], object], larger: Callable[[], object]) -> float:
    """How much more the larger case costs, as the best of three runs on each.

    A ratio rather than a budget, because a wall-clock budget states a host. The
    previous form of these two checks asserted half a second and a fifth of a
    second, and the seeded cubic walk came in at 0.42 s against the first of them
    — passing, on a host faster than the one the budget was written on. A ratio
    cancels the host and leaves the complexity class, which is what is being
    asserted. The best of three is kept because a scheduling hiccup can only
    lengthen a run.
    """
    return min(_elapsed(larger) for _ in range(3)) / min(_elapsed(smaller) for _ in range(3))


def _elapsed(operation: Callable[[], object]) -> float:
    started = time.perf_counter()
    _ = operation()
    return time.perf_counter() - started


def _failing_freeze(size: int) -> Callable[[], object]:
    """Freeze a chain of `size` providers whose deepest node needs an unbound key."""
    container = _bind_all(_chain_namespace(size), size)

    def attempt() -> object:
        try:
            return container.freeze()
        except MissingProviderError as failure:
            # Returned rather than raised: the caller times this, and an
            # exception crossing the timed region would be measured as one.
            return failure

    return attempt


def _explain_absent(size: int) -> Callable[[], str]:
    namespace = _layered_namespace(size)
    frozen = _bind_all(namespace, size).freeze()
    absent = namespace['Absent']
    assert isinstance(absent, type)
    return lambda: frozen.explain(absent)


def test_failing_freeze_does_not_grow_cubically_with_the_chain_length() -> None:
    """The chain the error names is found by a dynamic program, not by enumeration.

    The walk this replaced was cubic in the chain length. What pins that is the
    growth between two sizes rather than the cost at one: the path also carries
    `suggest_candidates` scanning `sys.modules`, a constant of about 11 ms here
    that has nothing to do with the graph, and a single-size budget measures the
    constant as much as the walk.
    """
    reported = _failing_freeze(200)()

    assert isinstance(reported, MissingProviderError)
    assert 'no provider for Missing' in str(reported)
    assert _growth(_failing_freeze(200), _failing_freeze(400)) < CUBIC_GROWTH_LIMIT


def test_explain_of_an_unbound_key_does_not_grow_with_the_path_count() -> None:
    """`explain()` reports the deepest chain without enumerating the paths to it.

    Same shape of assertion, and the same reason: the rendering shares the module
    scan, so the growth between two sizes is what isolates the walk.
    """
    assert 'no provider for Absent' in _explain_absent(24)()

    assert _growth(_explain_absent(16), _explain_absent(24)) < PATH_GROWTH_LIMIT
