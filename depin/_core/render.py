"""Text renderings of a `DependencyGraph`: a resolution tree, Graphviz, and Mermaid."""

from depin._core.diagnostics import DependencyGraph, GraphNode
from depin._core.graph import format_missing, suggest_candidates
from depin._core.spec import ProviderKey, ProviderShape, fmt_key

type _Ident = tuple[ProviderKey, str | None]

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
    expanded: set[_Ident] = set()
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

    Picks the chain the way `depin._core.graph._collect_missing` picks it, so the
    line `explain` returns for a required-but-unbound key is the line `freeze()`
    would have raised had that parameter carried no default. It inherits that
    walk's cost on a dense graph; the roadmap routes that to Step 6.
    """
    best: tuple[tuple[ProviderKey, ...], ProviderKey, str] | None = None
    for root in graph.nodes:
        stack: list[tuple[GraphNode, tuple[_Ident, ...]]] = [(root, ((root.key, root.tag),))]
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
