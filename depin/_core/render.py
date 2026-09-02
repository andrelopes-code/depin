"""Text renderings of a `DependencyGraph`: a resolution tree, Graphviz, and Mermaid."""

from depin._core import longest_chain
from depin._core.diagnostics import DependencyGraph, GraphEdge, GraphNode
from depin._core.graph import INACTIVE_NOTE, format_missing, suggest_candidates
from depin._core.spec import Ident, ProviderKey, fmt_key


def annotation_parts(node: GraphNode) -> list[str]:
    """The scope, shape, async flag and tag fragments, in the order every renderer uses."""
    parts = [node.scope.value, node.shape.value]
    if node.needs_async:
        parts.append('async')
    if node.tag is not None:
        parts.append(f'tag={node.tag!r}')
    return parts


def render_tree(
    graph: DependencyGraph,
    key: ProviderKey,
    tag: str | None,
    inactive: frozenset[Ident],
) -> str:
    """The resolution tree below ``(key, tag)``, or the missing-provider line for it.

    ``inactive`` is the plan's set of keys a condition kept out; it decides whether the
    missing-provider line, when one is produced, carries the note that the key is registered
    but inactive rather than unbound outright.
    """
    root = graph.find(key, tag=tag)
    if root is None:
        return _render_absent(graph, key, tag, inactive)

    lines: list[str] = []
    expanded: set[Ident] = set()
    # Explicit stack rather than recursion: a chain of a thousand providers is a
    # supported graph, and CPython's recursion limit is well below that.
    stack: list[tuple[int, str, GraphNode | GraphEdge]] = [(0, '', root)]
    while stack:
        depth, label, target = stack.pop()
        indent = '  ' * depth
        if not isinstance(target, GraphNode):
            reason = 'default' if target.has_default else 'optional'
            lines.append(f'{indent}{label}{fmt_key(target.key)}  (unbound, {reason})')
            continue
        annotations = f'[{", ".join(annotation_parts(target))}]'
        ident = (target.key, target.tag)
        if ident in expanded:
            lines.append(f'{indent}{label}{fmt_key(target.key)}  {annotations}  (shown above)')
            continue
        expanded.add(ident)
        lines.append(f'{indent}{label}{fmt_key(target.key)}  {annotations}')
        for edge in reversed(target.dependencies):
            child = graph.find(edge.key, tag=edge.tag)
            stack.append((depth + 1, f'{edge.parameter}: ', edge if child is None else child))
    return '\n'.join(lines)


def _render_absent(
    graph: DependencyGraph,
    key: ProviderKey,
    tag: str | None,
    inactive: frozenset[Ident],
) -> str:
    is_inactive = (key, tag) in inactive
    required = _deepest_requirement(graph, key, tag)
    if required is not None:
        chain, owner, parameter = required
        return format_missing(key, chain, owner, parameter, inactive=is_inactive)
    suggestions = suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    note = INACTIVE_NOTE if is_inactive else ''
    return f'no provider for {fmt_key(key)} (tag={tag!r}){note}{extra}'


def _deepest_requirement(
    graph: DependencyGraph,
    key: ProviderKey,
    tag: str | None,
) -> tuple[tuple[ProviderKey, ...], ProviderKey, str] | None:
    """The longest chain reaching an unsatisfied parameter bound for ``(key, tag)``.

    Searches `graph.nodes`, the topological order; `depin._core.graph` searches
    specs in declaration order instead. The two orders can differ, and the two
    searches agree on what counts as missing only for the optional case: an
    unbound edge that is optional and carries no default is skipped by both,
    since neither would ever report it. They disagree on a defaulted edge —
    `freeze()` skips it outright, because a default satisfies the call and
    `freeze()` must never raise over it, while this one still reports it,
    because `explain()` names the chain a defaulted parameter would need if it
    were required, and the chain-consistency tests rely on that chain being
    reported the same way whether or not the parameter carries a default. Where
    both do report a chain, they agree on which one wins: the longest chain wins
    outright, and a tie — whether between two roots or between two siblings
    sharing one root — is broken the same way by both, because both go through
    `depin._core.longest_chain`, which reproduces the traversal order the
    enumerating walk decided ties by.
    """
    found = longest_chain.over_graph(graph).get((key, tag))
    if found is None:
        return None
    return (tuple(step[0] for step in found.chain), found.owner[0], found.parameter)


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
    """Escape for Mermaid's HTML-parsed label text, in an order safe from re-escaping.

    Mermaid parses node label text as HTML, which is why ``<br/>`` works as a
    separator; a raw ``<`` or ``>`` in a key would otherwise swallow the rest
    of the label. ``#`` goes first so the entities this function itself emits
    are never re-escaped.
    """
    text = text.replace('#', '#35;')
    text = text.replace('"', '#quot;')
    text = text.replace('<', '#lt;')
    return text.replace('>', '#gt;')
