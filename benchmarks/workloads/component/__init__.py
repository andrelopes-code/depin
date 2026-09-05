"""Tier 2: representative graphs, startup, diagnostics, and error paths."""

from benchmarks.contracts import Workload
from benchmarks.workloads.component.diagnostics import (
    build_the_graph_view,
    explain_a_deep_chain,
    explain_a_deep_chain_with_every_node_decorated,
    explain_a_layered_dag,
    export_a_large_graph_as_dot,
)
from benchmarks.workloads.component.errors import explain_an_unbound_key, freeze_a_chain_missing_a_provider
from benchmarks.workloads.component.primitives import (
    FAILING_FREEZE_SIZES,
    UNBOUND_EXPLAIN_SIZES,
)
from benchmarks.workloads.component.primitives import (
    LARGE_GRAPH as LARGE_GRAPH,
)
from benchmarks.workloads.component.resolution import (
    freeze_a_chain,
    freeze_a_decorated_chain,
    freeze_a_generic_key_chain,
    warmup_a_cold_singleton_graph,
)
from benchmarks.workloads.component.scope import open_a_request_shaped_scope

WORKLOADS: tuple[Workload, ...] = (
    *(freeze_a_chain(size) for size in (10, 100, LARGE_GRAPH)),
    *(freeze_a_generic_key_chain(size) for size in (10, 100, LARGE_GRAPH)),
    *(freeze_a_decorated_chain(size) for size in (10, 100, LARGE_GRAPH)),
    warmup_a_cold_singleton_graph(),
    open_a_request_shaped_scope(),
    build_the_graph_view(),
    explain_a_deep_chain(),
    explain_a_deep_chain_with_every_node_decorated(),
    explain_a_layered_dag(),
    export_a_large_graph_as_dot(),
    *(freeze_a_chain_missing_a_provider(size) for size in FAILING_FREEZE_SIZES),
    *(explain_an_unbound_key(size) for size in UNBOUND_EXPLAIN_SIZES),
)
