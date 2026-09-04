"""Component workloads for graph diagnostics."""

from benchmarks.contracts import Observation, Tier, Workload
from benchmarks.graphs import build_chain, build_decorated_chain, build_layered_dag
from benchmarks.workloads.component.primitives import (
    LARGE_GRAPH,
    LAYERED_GRAPH,
    _diagnostic_claim,
    _explain_workload,
)
from benchmarks.workloads.shell import Session, implementation


def _build_the_graph_view() -> Workload:
    def setup() -> Session:
        container, _ = build_chain(LARGE_GRAPH)
        frozen = container.freeze()

        def observe() -> Observation:
            view = frozen.graph()
            edges = sum(len(node.dependencies) for node in view.nodes)
            return Observation(result=f'{len(view.nodes)} nodes, {edges} edges', constructed=(), closed=())

        return Session(call=frozen.graph, observe=observe)

    return Workload(
        name='build_the_graph_view',
        tier=Tier.COMPONENT,
        claim=_diagnostic_claim(
            question='What does the public graph view over a validated plan cost?',
            work=f'Build the node and edge view of a {LARGE_GRAPH}-provider graph.',
            shape=f'A linear chain of {LARGE_GRAPH} providers.',
            valid=('The diagnostic cost of the graph view, published apart from resolution.',),
            invalid=('Not a cost any resolution pays: the view is built only when it is asked for.',),
        ),
        subject=implementation('depin', setup),
    )


def _explain_a_deep_chain() -> Workload:
    return _explain_workload(
        'explain_a_deep_chain',
        lambda: build_chain(LARGE_GRAPH),
        _diagnostic_claim(
            question='What does rendering a resolution tree cost over a chain nothing is reached twice in?',
            work=f'Render the resolution tree below the leaf of a {LARGE_GRAPH}-provider chain.',
            shape=f'A linear chain of {LARGE_GRAPH} providers, so every node is reached exactly once.',
            valid=('The cost of rendering a tree with one line per node and no repeated subtree.',),
            invalid=(
                'Not evidence about the subtree-elision guard: the baseline counted 0 occurrences of '
                '"(shown above)" over this shape, so removing the guard could not change this result. '
                '`explain_a_layered_dag` is the workload that covers it.',
            ),
        ),
    )


def _explain_a_deep_chain_with_every_node_decorated() -> Workload:
    return _explain_workload(
        'explain_a_deep_chain_with_every_node_decorated',
        lambda: build_decorated_chain(LARGE_GRAPH),
        _diagnostic_claim(
            question='What does a decorator over every node add to rendering a resolution tree?',
            work=f'Render the resolution tree below the leaf of a decorated {LARGE_GRAPH}-provider chain.',
            shape='`explain_a_deep_chain`, with one pass-through decorator over every node.',
            valid=('The cost of rendering a decoration chain, read against `explain_a_deep_chain`.',),
            invalid=('Not evidence about the elision guard: this shape reaches no node twice either.',),
        ),
    )


def _explain_a_layered_dag() -> Workload:
    return _explain_workload(
        'explain_a_layered_dag',
        lambda: build_layered_dag(LAYERED_GRAPH),
        _diagnostic_claim(
            question='What does rendering a resolution tree cost when subtrees repeat?',
            work=f'Render the resolution tree below the deepest node of a {LAYERED_GRAPH}-node layered DAG.',
            shape=(
                f'{LAYERED_GRAPH} providers where node i depends on both i-1 and i-2, so all but two nodes are '
                'reached twice and the second visit is elided.'
            ),
            valid=(
                'The cost of rendering a tree whose subtrees repeat, and the only coverage the subtree-elision '
                'guard has: this shape elides 498 subtrees where `explain_a_deep_chain` elides none, so '
                'removing the guard is detectable here and nowhere else.',
            ),
            invalid=(
                'Not comparable with `explain_a_deep_chain` as a size-for-size pair: the two render a similar '
                'number of lines from a different number of nodes.',
            ),
        ),
    )


def _export_a_large_graph_as_dot() -> Workload:
    def setup() -> Session:
        container, _ = build_chain(LARGE_GRAPH)
        graph = container.freeze().graph()
        return Session(
            call=graph.dot,
            observe=lambda: Observation(
                result=f'lines={len(graph.dot().splitlines())}',
                constructed=(),
                closed=(),
            ),
        )

    return Workload(
        name='export_a_large_graph_as_dot',
        tier=Tier.COMPONENT,
        claim=_diagnostic_claim(
            question='What does exporting a graph to Graphviz cost?',
            work=f'Render a {LARGE_GRAPH}-provider graph as a dot document.',
            shape=f'A linear chain of {LARGE_GRAPH} providers.',
            valid=('The export cost, and the quietest workload in the suite to gate against.',),
            invalid=('Not a cost any resolution pays: the export runs only when it is asked for.',),
        ),
        subject=implementation('depin', setup),
    )
