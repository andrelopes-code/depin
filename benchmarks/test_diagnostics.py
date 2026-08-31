"""Diagnostics over a large graph: the view, the tree, and the exports."""

from collections.abc import Callable
from typing import Protocol

from benchmarks.graphs import build_chain, build_decorated_chain


class Benchmark(Protocol):
    """The subset of pytest-benchmark's fixture these cases use.

    Declared locally so the benchmarks do not depend on the plugin shipping
    accurate type information.
    """

    def __call__[T](self, function: Callable[[], T]) -> T: ...


def test_build_the_graph_view(benchmark: Benchmark) -> None:
    container, _ = build_chain(1000)
    frozen = container.freeze()
    _ = benchmark(frozen.graph)


def test_explain_a_deep_chain(benchmark: Benchmark) -> None:
    container, leaf = build_chain(1000)
    frozen = container.freeze()

    def explain() -> str:
        return frozen.explain(leaf)

    _ = benchmark(explain)


def test_export_a_large_graph_as_dot(benchmark: Benchmark) -> None:
    container, _ = build_chain(1000)
    graph = container.freeze().graph()
    _ = benchmark(graph.dot)


def test_explain_a_deep_chain_with_every_node_decorated(benchmark: Benchmark) -> None:
    """`test_explain_a_deep_chain`, with one decorator over every node, so the
    cost of rendering a decoration chain is visible against the plain-chain
    baseline."""
    container, leaf = build_decorated_chain(1000)
    frozen = container.freeze()

    def explain() -> str:
        return frozen.explain(leaf)

    _ = benchmark(explain)
