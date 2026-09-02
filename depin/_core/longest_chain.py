"""The longest chain reaching each parameter that no binding satisfies.

`depin._core.graph` needs one per missing key, to report them all from
`Container.freeze()`; `depin._core.render` needs the one for the key `explain()`
was asked about. Both once enumerated every simple path from every node. Solving
it as a longest-path dynamic program is exact on a directed acyclic graph, where
every path is simple, and wrong on a cyclic one, where the longest simple path is
NP-hard — so a cyclic graph keeps the enumerating walk. That case is reachable:
`build_plan` checks for a missing provider before it checks for a cycle, so a
graph carrying both reports the missing provider, and the chain it prints is
user-visible text that may not change.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from depin._core.diagnostics import DependencyGraph
from depin._core.spec import Ident, ProviderSpec


@dataclass(frozen=True, slots=True)
class Requirement:
    """Where an unsatisfied parameter is declared, and the deepest way to reach it.

    ``chain`` ends at ``owner``; the key itself is not part of it, because both
    callers append it themselves when they render the chain.
    """

    chain: tuple[Ident, ...]
    owner: Ident
    parameter: str


@dataclass(frozen=True, slots=True)
class _Edge:
    parameter: str
    ident: Ident
    reportable: bool


@dataclass(frozen=True, slots=True)
class _Node:
    ident: Ident
    edges: tuple[_Edge, ...]


def over_specs(specs: Sequence[ProviderSpec]) -> dict[Ident, Requirement]:
    """The chains `Container.freeze()` reports, keyed by the missing identity.

    A parameter carrying a default or admitting `None` is excused: `freeze()`
    may not fail over one. It is still traversed when a binding satisfies it,
    which is what keeps this and `over_graph` on one chain.

    Entries come in the order the keys are first required, walking the specs in
    declaration order, so the caller's stable sort by chain length is decided by
    that order where two chains are equally long.
    """
    return _longest(
        tuple(
            _Node(
                ident=(spec.key, spec.tag),
                edges=tuple(
                    _Edge(
                        parameter=param.name,
                        ident=(param.key, param.tag),
                        reportable=not param.has_default and not param.optional,
                    )
                    for param in spec.params
                ),
            )
            for spec in specs
        )
    )


def over_graph(graph: DependencyGraph) -> dict[Ident, Requirement]:
    """The chains `FrozenContainer.explain()` reports, keyed by the missing identity.

    Only a parameter that admits `None` without carrying a default is excused
    here, because `explain()` names the chain a defaulted parameter would need
    if it were required. Nodes are walked in the graph's own resolution order.
    """
    return _longest(
        tuple(
            _Node(
                ident=(node.key, node.tag),
                edges=tuple(
                    _Edge(
                        parameter=edge.parameter,
                        ident=(edge.key, edge.tag),
                        reportable=edge.has_default or not edge.optional,
                    )
                    for edge in node.dependencies
                ),
            )
            for node in graph.nodes
        )
    )


def _longest(nodes: tuple[_Node, ...]) -> dict[Ident, Requirement]:
    index = {node.ident: position for position, node in enumerate(nodes)}
    children = tuple(tuple(index[edge.ident] for edge in node.edges if edge.ident in index) for node in nodes)
    order = _topological(children)
    if order is None:
        return _enumerate_paths(nodes, index)
    return _dynamic(nodes, index, children, order)


def _topological(children: tuple[tuple[int, ...], ...]) -> tuple[int, ...] | None:
    """Kahn's algorithm, or `None` when the graph carries a cycle."""
    incoming = [0] * len(children)
    for targets in children:
        for target in targets:
            incoming[target] += 1
    ready = [position for position, count in enumerate(incoming) if count == 0]
    order: list[int] = []
    while ready:
        position = ready.pop()
        order.append(position)
        for target in children[position]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    return tuple(order) if len(order) == len(children) else None


def _depths(children: tuple[tuple[int, ...], ...], order: tuple[int, ...]) -> list[int]:
    """Nodes in the longest path ending at each node, counting the node itself."""
    depths = [1] * len(children)
    for position in order:
        for target in children[position]:
            depths[target] = max(depths[target], depths[position] + 1)
    return depths


def _ranks(children: tuple[tuple[int, ...], ...], depths: list[int]) -> tuple[list[int], list[int]]:
    """One deepest path per node, and the order the walk this replaced found them in.

    Every deepest path ending at a node of depth ``d`` passes through a node of
    depth ``i`` at each position ``i``, so the paths of one depth are extensions
    of the paths of the depth below it. Ranking each depth by the order the walk
    reached it therefore ranks the next depth too: within a node, the walk pushed
    children in parameter order onto a LIFO stack and so took the last of them
    first. Ranks are comparable within a depth, never across two.
    """
    parents = [-1] * len(children)
    ranks = [-1] * len(children)
    current = [position for position, depth in enumerate(depths) if depth == 1]
    for rank, position in enumerate(current):
        ranks[position] = rank
    assigned = len(current)
    depth = 1
    while current:
        depth += 1
        following: list[int] = []
        for position in current:
            for target in reversed(children[position]):
                if depths[target] == depth and ranks[target] < 0:
                    ranks[target] = assigned
                    assigned += 1
                    parents[target] = position
                    following.append(target)
        current = following
    return parents, ranks


def _chain(position: int, parents: list[int], nodes: tuple[_Node, ...]) -> tuple[Ident, ...]:
    walk: list[Ident] = []
    while position >= 0:
        walk.append(nodes[position].ident)
        position = parents[position]
    walk.reverse()
    return tuple(walk)


def _encounters(
    nodes: tuple[_Node, ...], index: dict[Ident, int], children: tuple[tuple[int, ...], ...]
) -> list[Ident]:
    """The unsatisfied identities, in the order the walk this replaced first met them."""
    visited = [False] * len(nodes)
    seen: set[Ident] = set()
    encountered: list[Ident] = []
    for root in range(len(nodes)):
        stack = [root]
        while stack:
            position = stack.pop()
            if visited[position]:
                continue
            visited[position] = True
            for edge in nodes[position].edges:
                if edge.ident in index or not edge.reportable or edge.ident in seen:
                    continue
                seen.add(edge.ident)
                encountered.append(edge.ident)
            stack.extend(children[position])
    return encountered


def _dynamic(
    nodes: tuple[_Node, ...],
    index: dict[Ident, int],
    children: tuple[tuple[int, ...], ...],
    order: tuple[int, ...],
) -> dict[Ident, Requirement]:
    depths = _depths(children, order)
    parents, ranks = _ranks(children, depths)
    declared: dict[Ident, tuple[int, int]] = {}
    for position, node in enumerate(nodes):
        for offset, edge in enumerate(node.edges):
            if edge.ident in index or not edge.reportable:
                continue
            standing = declared.get(edge.ident)
            if standing is None or (depths[position], -ranks[position]) > (depths[standing[0]], -ranks[standing[0]]):
                declared[edge.ident] = (position, offset)
    return {
        ident: Requirement(
            chain=_chain(declared[ident][0], parents, nodes),
            owner=nodes[declared[ident][0]].ident,
            parameter=nodes[declared[ident][0]].edges[declared[ident][1]].parameter,
        )
        for ident in _encounters(nodes, index, children)
    }


def _enumerate_paths(nodes: tuple[_Node, ...], index: dict[Ident, int]) -> dict[Ident, Requirement]:
    """Every simple path from every node. Exponential, and exact on a cyclic graph."""
    found: dict[Ident, Requirement] = {}
    for root in range(len(nodes)):
        stack: list[tuple[int, tuple[int, ...]]] = [(root, (root,))]
        while stack:
            position, chain = stack.pop()
            walked = set(chain)
            node = nodes[position]
            for edge in node.edges:
                target = index.get(edge.ident)
                if target is None:
                    if not edge.reportable:
                        continue
                    standing = found.get(edge.ident)
                    if standing is None or len(chain) > len(standing.chain):
                        found[edge.ident] = Requirement(
                            chain=tuple(nodes[step].ident for step in chain),
                            owner=node.ident,
                            parameter=edge.parameter,
                        )
                    continue
                if target in walked:
                    continue
                stack.append((target, (*chain, target)))
    return found
