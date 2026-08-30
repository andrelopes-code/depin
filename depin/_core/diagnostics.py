"""The immutable, navigable view of a validated `ResolutionPlan`."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import override

from depin._core.scope import Scope
from depin._core.spec import Ident, ProviderKey, ProviderShape, ProviderSpec, ResolutionPlan, fmt_key
from depin.errors import MissingProviderError


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """One provider parameter and the binding identity it resolves to.

    ``satisfied`` is false only for a parameter that carries a default and that
    no binding provides. `Container.freeze()` rejects every other unsatisfied
    parameter, so a frozen graph holds no other kind.

    Example:
        ```pycon
        >>> from depin import Container
        >>> class Config: ...
        >>> class Service:
        ...     def __init__(self, config: Config) -> None: ...
        >>> di = Container().bind(Config).bind(Service).freeze()
        >>> edge = di.graph().node(Service).dependencies[0]
        >>> edge.parameter, edge.satisfied
        ('config', True)

        ```
    """

    parameter: str
    key: ProviderKey
    tag: str | None
    satisfied: bool


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One provider in the validated graph.

    ``dependencies`` is in the provider's own parameter order, which is what
    makes every rendering of the graph reproducible.

    Example:
        ```pycon
        >>> from depin import Container, ProviderShape
        >>> class Config: ...
        >>> di = Container().bind(Config).freeze()
        >>> node = di.graph().node(Config)
        >>> node.scope.value, node.shape is ProviderShape.CLASS
        ('singleton', True)

        ```
    """

    key: ProviderKey
    tag: str | None
    scope: Scope
    shape: ProviderShape
    needs_async: bool
    dependencies: tuple[GraphEdge, ...]


class DependencyGraph:
    """The validated dependency graph, as data.

    Returned by `FrozenContainer.graph()`. Nodes come in resolution order: a
    node never precedes one it depends on. The view describes the plan
    `Container.freeze()` validated, so an active `FrozenContainer.override`
    does not change it.

    Example:
        ```pycon
        >>> from depin import Container
        >>> class Config: ...
        >>> class Service:
        ...     def __init__(self, config: Config) -> None: ...
        >>> di = Container().bind(Config).bind(Service).freeze()
        >>> print(di.graph().mermaid())
        graph LR
          n0["Config<br/>singleton, class"]
          n1["Service<br/>singleton, class"]
          n1 -->|config| n0

        ```
    """

    __slots__ = ('_index', '_nodes')

    def __init__(self, nodes: tuple[GraphNode, ...]) -> None:
        self._nodes = nodes
        self._index: Mapping[Ident, GraphNode] = {(node.key, node.tag): node for node in nodes}

    @property
    def nodes(self) -> tuple[GraphNode, ...]:
        """Every provider in the graph, in resolution order."""
        return self._nodes

    @property
    def roots(self) -> tuple[GraphNode, ...]:
        """The nodes no other node depends on, in resolution order."""
        depended = {(edge.key, edge.tag) for node in self._nodes for edge in node.dependencies if edge.satisfied}
        return tuple(node for node in self._nodes if (node.key, node.tag) not in depended)

    def node(self, key: ProviderKey, *, tag: str | None = None) -> GraphNode:
        """Return the node bound under ``key`` and ``tag``.

        Raises:
            MissingProviderError: Nothing is bound under that key and tag. Use
                `find` to ask without raising.
        """
        found = self.find(key, tag=tag)
        if found is None:
            raise MissingProviderError(f'no provider for {fmt_key(key)} (tag={tag!r})')
        return found

    def find(self, key: ProviderKey, *, tag: str | None = None) -> GraphNode | None:
        """Return the node bound under ``key`` and ``tag``, or None when nothing is."""
        return self._index.get((key, tag))

    def dot(self) -> str:
        """Render the graph as a Graphviz ``digraph`` document."""
        # Deferred: depin._core.render imports DependencyGraph from this module,
        # so a module-level import here would be circular.
        from depin._core import render

        return render.render_dot(self)

    def mermaid(self) -> str:
        """Render the graph as a Mermaid ``graph LR`` document."""
        from depin._core import render

        return render.render_mermaid(self)

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DependencyGraph):
            return NotImplemented
        return self._nodes == other._nodes

    @override
    def __hash__(self) -> int:
        return hash(self._nodes)

    @override
    def __repr__(self) -> str:
        return f'DependencyGraph({len(self._nodes)} nodes)'


def build_graph(plan: ResolutionPlan) -> DependencyGraph:
    """Project a validated plan into the public view."""
    return DependencyGraph(tuple(_node_for(spec, plan) for spec in plan.order))


def _node_for(spec: ProviderSpec, plan: ResolutionPlan) -> GraphNode:
    edges = tuple(
        GraphEdge(
            parameter=param.name,
            key=param.key,
            tag=param.tag,
            satisfied=(param.key, param.tag) in plan.by_key,
        )
        for param in spec.params
    )
    return GraphNode(
        key=spec.key,
        tag=spec.tag,
        scope=spec.scope,
        shape=spec.shape,
        needs_async=spec.needs_async,
        dependencies=edges,
    )
