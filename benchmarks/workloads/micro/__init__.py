"""Tier 1 workload inventory."""

from benchmarks.contracts import Workload

from .async_resolution import resolve_an_async_singleton
from .cache import (
    resolve_cached_singleton,
    resolve_cached_singleton_through_an_alias,
    resolve_singleton_through_a_two_deep_decoration_chain,
)
from .core import CHAIN_DEPTH as CHAIN_DEPTH
from .core import HOT_GRAPH as HOT_GRAPH
from .core import Sole as Sole
from .override import resolve_through_an_active_override, resolve_with_no_active_override
from .resolution import resolve_a_collection, resolve_a_generic_key, resolve_a_transient_chain
from .scope import (
    call_through_an_inject_wrapper,
    call_through_an_inject_wrapper_with_explicit_arguments,
    open_and_close_a_scope,
)
from .teardown import (
    construct_a_singleton_for_the_first_time,
    resolve_a_sync_resource_with_teardown,
)

WORKLOADS: tuple[Workload, ...] = (
    resolve_cached_singleton(),
    resolve_cached_singleton_through_an_alias(),
    resolve_singleton_through_a_two_deep_decoration_chain(),
    resolve_a_collection(10),
    resolve_a_collection(100),
    resolve_a_transient_chain(),
    open_and_close_a_scope(),
    call_through_an_inject_wrapper(),
    call_through_an_inject_wrapper_with_explicit_arguments(),
    resolve_an_async_singleton(),
    resolve_with_no_active_override(),
    resolve_through_an_active_override(),
    resolve_a_generic_key(),
    construct_a_singleton_for_the_first_time(),
    resolve_a_sync_resource_with_teardown(),
)
