"""Tier 1 workload inventory."""

from benchmarks.contracts import Workload

from .async_resolution import _resolve_an_async_singleton
from .cache import (
    _resolve_cached_singleton,
    _resolve_cached_singleton_through_an_alias,
    _resolve_singleton_through_a_two_deep_decoration_chain,
)
from .core import CHAIN_DEPTH as CHAIN_DEPTH
from .core import HOT_GRAPH as HOT_GRAPH
from .core import Sole as Sole
from .override import _resolve_through_an_active_override, _resolve_with_no_active_override
from .resolution import _resolve_a_collection, _resolve_a_generic_key, _resolve_a_transient_chain
from .scope import (
    _call_through_an_inject_wrapper,
    _call_through_an_inject_wrapper_with_explicit_arguments,
    _open_and_close_a_scope,
)
from .teardown import (
    _construct_a_singleton_for_the_first_time,
    _resolve_a_sync_resource_with_teardown,
)

WORKLOADS: tuple[Workload, ...] = (
    _resolve_cached_singleton(),
    _resolve_cached_singleton_through_an_alias(),
    _resolve_singleton_through_a_two_deep_decoration_chain(),
    _resolve_a_collection(10),
    _resolve_a_collection(100),
    _resolve_a_transient_chain(),
    _open_and_close_a_scope(),
    _call_through_an_inject_wrapper(),
    _call_through_an_inject_wrapper_with_explicit_arguments(),
    _resolve_an_async_singleton(),
    _resolve_with_no_active_override(),
    _resolve_through_an_active_override(),
    _resolve_a_generic_key(),
    _construct_a_singleton_for_the_first_time(),
    _resolve_a_sync_resource_with_teardown(),
)
