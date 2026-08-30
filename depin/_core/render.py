"""Text renderings of a `DependencyGraph`: a resolution tree, Graphviz, and Mermaid."""

from depin._core.diagnostics import DependencyGraph, GraphNode
from depin._core.graph import format_missing, suggest_candidates
from depin._core.spec import Ident, ProviderKey, ProviderShape, fmt_key

_SHAPE_NAMES: dict[ProviderShape, str] = {
    ProviderShape.CLASS: 'class',
    ProviderShape.FUNCTION: 'function',
    ProviderShape.ASYNC_FUNCTION: 'async function',
    ProviderShape.GENERATOR: 'generator',
    ProviderShape.ASYNC_GENERATOR: 'async generator',
    ProviderShape.CONTEXT_MANAGER: 'context manager',
    ProviderShape.ASYNC_CONTEXT_MANAGER: 'async context manager',
    ProviderShape.VALUE: 'value',
    ProviderShape.FRAME: 'frame',
}


def annotation_parts(node: GraphNode) -> list[str]:
    """The scope, shape, async flag and tag fragments, in the order every renderer uses."""
    parts = [node.scope.value, _SHAPE_NAMES[node.shape]]
    if node.needs_async:
        parts.append('async')
    if node.tag is not None:
        parts.append(f'tag={node.tag!r}')
    return parts


def render_tree(graph: DependencyGraph, key: ProviderKey, tag: str | None) -> str:
    """The resolution tree below ``(key, tag)``, or the missing-provider line for it."""
    root = graph.find(key, tag)
    if root is None:
        return _render_absent(graph, key, tag)

    lines: list[str] = []
    expanded: set[Ident] = set()
    # Explicit stack rather than recursion: a chain of a thousand providers is a
    # supported graph, and CPython's recursion limit is well below that.
    stack: list[tuple[int, str, GraphNode | ProviderKey]] = [(0, '', root)]
    while stack:
        depth, label, target = stack.pop()
        indent = '  ' * depth
        if not isinstance(target, GraphNode):
            lines.append(f'{indent}{label}{fmt_key(target)}  (unbound, default)')
            continue
        annotations = f'[{", ".join(annotation_parts(target))}]'
        ident = (target.key, target.tag)
        if ident in expanded:
            lines.append(f'{indent}{label}{fmt_key(target.key)}  {annotations}  (shown above)')
            continue
        expanded.add(ident)
        lines.append(f'{indent}{label}{fmt_key(target.key)}  {annotations}')
        for edge in reversed(target.dependencies):
            child = graph.find(edge.key, edge.tag)
            stack.append((depth + 1, f'{edge.parameter}: ', edge.key if child is None else child))
    return '\n'.join(lines)


def _render_absent(graph: DependencyGraph, key: ProviderKey, tag: str | None) -> str:
    required = _deepest_requirement(graph, key, tag)
    if required is not None:
        chain, owner, parameter = required
        return format_missing(key, chain, owner, parameter)
    suggestions = suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    return f'no provider for {fmt_key(key)} (tag={tag!r}){extra}'


def _deepest_requirement(
    graph: DependencyGraph,
    key: ProviderKey,
    tag: str | None,
) -> tuple[tuple[ProviderKey, ...], ProviderKey, str] | None:
    """The longest chain reaching an unsatisfied parameter bound for ``(key, tag)``.

    Walks `graph.nodes`, the topological order; `depin._core.graph._collect_missing`
    walks specs in declaration order instead. The two orders can differ, but the
    two walks still agree on which chain wins: the longest chain wins outright, and
    a tie is only reachable between two roots where neither depends on the other —
    an ordering the toposort preserves from declaration order. It inherits that
    walk's cost on a dense graph; the roadmap routes that to Step 6.
    """
    best: tuple[tuple[ProviderKey, ...], ProviderKey, str] | None = None
    for root in graph.nodes:
        stack: list[tuple[GraphNode, tuple[Ident, ...]]] = [(root, ((root.key, root.tag),))]
        while stack:
            node, chain = stack.pop()
            for edge in node.dependencies:
                child = graph.find(edge.key, edge.tag)
                if child is None:
                    if (edge.key, edge.tag) == (key, tag) and (best is None or len(chain) > len(best[0])):
                        best = (tuple(ident[0] for ident in chain), node.key, edge.parameter)
                    continue
                if (child.key, child.tag) in chain:
                    continue
                stack.append((child, (*chain, (child.key, child.tag))))
    return best


def render_dot(graph: DependencyGraph) -> str:
    """The graph as a Graphviz ``digraph`` document."""
    bound, unbound = _identifiers(graph)
    lines = ['digraph depin {', '  rankdir=LR;']
    for node in graph.nodes:
        label = f'{_dot_escape(fmt_key(node.key))}\\n{_dot_escape(", ".join(annotation_parts(node)))}'
        lines.append(f'  {bound[(node.key, node.tag)]} [label="{label}", shape=box];')
    for ident, name in unbound.items():
        lines.append(f'  {name} [label="{_dot_escape(fmt_key(ident[0]))}\\nunbound", shape=box, style=dashed];')
    for node in graph.nodes:
        source = bound[(node.key, node.tag)]
        for edge in node.dependencies:
            ident = (edge.key, edge.tag)
            if ident in bound:
                lines.append(f'  {source} -> {bound[ident]} [label="{edge.parameter}"];')
            else:
                lines.append(f'  {source} -> {unbound[ident]} [label="{edge.parameter}", style=dashed];')
    lines.append('}')
    return '\n'.join(lines)


def render_mermaid(graph: DependencyGraph) -> str:
    """The graph as a Mermaid ``graph LR`` document."""
    bound, unbound = _identifiers(graph)
    lines = ['graph LR']
    for node in graph.nodes:
        label = f'{_mermaid_escape(fmt_key(node.key))}<br/>{_mermaid_escape(", ".join(annotation_parts(node)))}'
        lines.append(f'  {bound[(node.key, node.tag)]}["{label}"]')
    for ident, name in unbound.items():
        lines.append(f'  {name}["{_mermaid_escape(fmt_key(ident[0]))}<br/>unbound"]')
    for node in graph.nodes:
        source = bound[(node.key, node.tag)]
        for edge in node.dependencies:
            ident = (edge.key, edge.tag)
            if ident in bound:
                lines.append(f'  {source} -->|{edge.parameter}| {bound[ident]}')
            else:
                lines.append(f'  {source} -.->|{edge.parameter}| {unbound[ident]}')
    return '\n'.join(lines)


def _identifiers(graph: DependencyGraph) -> tuple[dict[Ident, str], dict[Ident, str]]:
    """Stable identifiers: ``n<plan index>`` for a bound node, ``u<n>`` for an unbound target.

    An index keeps a key containing a quote or a bracket out of the identifier
    position in both formats, and both dictionaries are built in walk order, so
    iterating them is deterministic.
    """
    bound = {(node.key, node.tag): f'n{index}' for index, node in enumerate(graph.nodes)}
    unbound: dict[Ident, str] = {}
    for node in graph.nodes:
        for edge in node.dependencies:
            ident = (edge.key, edge.tag)
            if ident in bound or ident in unbound:
                continue
            unbound[ident] = f'u{len(unbound)}'
    return bound, unbound


def _dot_escape(text: str) -> str:
    return text.replace('\\', '\\\\').replace('"', '\\"')


def _mermaid_escape(text: str) -> str:
    return text.replace('"', '#quot;')
