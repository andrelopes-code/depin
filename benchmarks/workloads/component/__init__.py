"""Tier 2: representative graphs, startup, diagnostics, and error paths."""

from benchmarks.contracts import Workload
from benchmarks.workloads.component.diagnostics import (
    _build_the_graph_view,
    _explain_a_deep_chain,
    _explain_a_deep_chain_with_every_node_decorated,
    _explain_a_layered_dag,
    _export_a_large_graph_as_dot,
)
from benchmarks.workloads.component.errors import _explain_an_unbound_key, _freeze_a_chain_missing_a_provider
from benchmarks.workloads.component.primitives import FAILING_FREEZE_SIZES, LARGE_GRAPH, UNBOUND_EXPLAIN_SIZES
from benchmarks.workloads.component.resolution import (
    _freeze_a_chain,
    _freeze_a_decorated_chain,
    _freeze_a_generic_key_chain,
    _warmup_a_cold_singleton_graph,
)
from benchmarks.workloads.component.scope import _open_a_request_shaped_scope

WORKLOADS: tuple[Workload, ...] = (
    *(_freeze_a_chain(size) for size in (10, 100, LARGE_GRAPH)),
    *(_freeze_a_generic_key_chain(size) for size in (10, 100, LARGE_GRAPH)),
    *(_freeze_a_decorated_chain(size) for size in (10, 100, LARGE_GRAPH)),
    _warmup_a_cold_singleton_graph(),
    _open_a_request_shaped_scope(),
    _build_the_graph_view(),
    _explain_a_deep_chain(),
    _explain_a_deep_chain_with_every_node_decorated(),
    _explain_a_layered_dag(),
    _export_a_large_graph_as_dot(),
    *(_freeze_a_chain_missing_a_provider(size) for size in FAILING_FREEZE_SIZES),
    *(_explain_an_unbound_key(size) for size in UNBOUND_EXPLAIN_SIZES),
)
