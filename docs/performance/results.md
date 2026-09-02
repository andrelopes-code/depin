# Measured results

## Environment

| Property | Value |
| --- | --- |
| distributions.pydepin | 0.17.1 |
| distributions.pytest | 9.1.1 |
| distributions.pytest-benchmark | 5.3.0 |
| host.available_processors | 4 |
| host.cpu_model | Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| host.load_average | 2.41, 2.91, 2.83 |
| host.machine | x86_64 |
| host.processor | x86_64 |
| host.processors | 4 |
| host.release | 6.8.0-138-generic |
| host.system | Linux |
| interpreter.compiler | Clang 22.1.3  |
| interpreter.free_threading | no |
| interpreter.hash_randomization | yes |
| interpreter.implementation | CPython |
| interpreter.recursion_limit | 1000 |
| interpreter.version | 3.12.13 |

## Latency

| Workload | Repetitions | Rounds | Median | Spread across repetitions |
| --- | --- | --- | --- | --- |
| test_latency[build_the_graph_view-depin] | 5 | 392 | 4.232 ms | 6.0% |
| test_latency[call_through_an_inject_wrapper-depin] | 5 | 40729 | 5.626 µs | 2.8% |
| test_latency[call_through_an_inject_wrapper-direct] | 5 | 76576 | 122.610 ns | 0.5% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 30824 | 6.720 µs | 6.1% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 197004 | 176.795 ns | 0.8% |
| test_latency[construct_a_singleton_for_the_first_time-depin] | 5 | 44223 | 5.417 µs | 5.9% |
| test_latency[construct_a_singleton_for_the_first_time-direct] | 5 | 36925 | 296.300 ns | 4.9% |
| test_latency[explain_a_deep_chain-depin] | 5 | 259 | 6.457 ms | 4.7% |
| test_latency[explain_a_deep_chain_with_every_node_decorated-depin] | 5 | 102 | 16.902 ms | 7.5% |
| test_latency[explain_a_layered_dag-depin] | 5 | 343 | 5.003 ms | 3.2% |
| test_latency[explain_an_unbound_key_of_16-depin] | 5 | 208 | 7.408 ms | 3.7% |
| test_latency[explain_an_unbound_key_of_20-depin] | 5 | 207 | 7.387 ms | 2.6% |
| test_latency[export_a_large_graph_as_dot-depin] | 5 | 743 | 2.452 ms | 5.3% |
| test_latency[freeze_a_chain_missing_a_provider_of_100-depin] | 5 | 144 | 11.115 ms | 4.9% |
| test_latency[freeze_a_chain_missing_a_provider_of_50-depin] | 5 | 172 | 9.183 ms | 4.3% |
| test_latency[freeze_a_chain_of_10-depin] | 5 | 1000 | 379.478 µs | 3.3% |
| test_latency[freeze_a_chain_of_100-depin] | 5 | 466 | 3.546 ms | 2.3% |
| test_latency[freeze_a_chain_of_1000-depin] | 5 | 46 | 35.834 ms | 6.1% |
| test_latency[freeze_a_decorated_chain_of_10-depin] | 5 | 1000 | 922.849 µs | 2.5% |
| test_latency[freeze_a_decorated_chain_of_100-depin] | 5 | 190 | 8.699 ms | 2.9% |
| test_latency[freeze_a_decorated_chain_of_1000-depin] | 5 | 19 | 90.192 ms | 3.4% |
| test_latency[freeze_a_generic_key_chain_of_10-depin] | 5 | 1000 | 686.537 µs | 2.6% |
| test_latency[freeze_a_generic_key_chain_of_100-depin] | 5 | 248 | 6.688 ms | 7.0% |
| test_latency[freeze_a_generic_key_chain_of_1000-depin] | 5 | 20 | 85.924 ms | 17.6% |
| test_latency[open_a_request_shaped_scope-depin] | 5 | 8348 | 27.704 µs | 2.1% |
| test_latency[open_a_request_shaped_scope-direct] | 5 | 180151 | 796.863 ns | 12.4% |
| test_latency[open_and_close_a_scope-depin] | 5 | 2588 | 326.873 µs | 4.9% |
| test_latency[open_and_close_a_scope-direct] | 5 | 88842 | 3.133 µs | 6.2% |
| test_latency[resolve_a_collection_of_10-depin] | 5 | 12440 | 18.729 µs | 1.4% |
| test_latency[resolve_a_collection_of_10-direct] | 5 | 193163 | 202.132 ns | 1.0% |
| test_latency[resolve_a_collection_of_100-depin] | 5 | 5980 | 133.175 µs | 2.4% |
| test_latency[resolve_a_collection_of_100-direct] | 5 | 47547 | 417.099 ns | 0.7% |
| test_latency[resolve_a_generic_key-depin] | 5 | 60321 | 5.931 µs | 2.3% |
| test_latency[resolve_a_generic_key-direct] | 5 | 101823 | 95.370 ns | 1.4% |
| test_latency[resolve_a_sync_resource_with_teardown-depin] | 5 | 10424 | 12.901 µs | 3.4% |
| test_latency[resolve_a_sync_resource_with_teardown-direct] | 5 | 149656 | 1.577 µs | 1.3% |
| test_latency[resolve_a_transient_chain-depin] | 5 | 9228 | 34.752 µs | 2.9% |
| test_latency[resolve_a_transient_chain-direct] | 5 | 165452 | 2.275 µs | 2.7% |
| test_latency[resolve_an_async_singleton-depin] | 5 | 17542 | 16.582 µs | 6.6% |
| test_latency[resolve_an_async_singleton-direct] | 5 | 21515 | 13.499 µs | 3.0% |
| test_latency[resolve_cached_singleton-depin] | 5 | 42635 | 1.817 µs | 1.9% |
| test_latency[resolve_cached_singleton-direct] | 5 | 102219 | 96.030 ns | 0.2% |
| test_latency[resolve_cached_singleton_through_an_alias-depin] | 5 | 71933 | 3.747 µs | 5.9% |
| test_latency[resolve_cached_singleton_through_an_alias-direct] | 5 | 102596 | 95.180 ns | 1.7% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 130839 | 1.781 µs | 4.6% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 102187 | 95.180 ns | 0.8% |
| test_latency[resolve_through_an_active_override-depin] | 5 | 91711 | 3.844 µs | 1.9% |
| test_latency[resolve_through_an_active_override-direct] | 5 | 96759 | 99.581 ns | 4.1% |
| test_latency[resolve_with_no_active_override-depin] | 5 | 119561 | 1.815 µs | 1.8% |
| test_latency[resolve_with_no_active_override-direct] | 5 | 23303 | 95.030 ns | 1.0% |
| test_latency[warmup_a_cold_singleton_graph-depin] | 5 | 142 | 11.945 ms | 5.3% |
| test_latency[warmup_a_cold_singleton_graph-direct] | 5 | 2981 | 262.381 µs | 10.1% |

## Application tier

Tail quantiles and CPU time are published for the application tier only. An end-to-end request has a tail a caller meets; a microbenchmark round is a calibrated loop, so its p99 describes the calibration rather than the operation. CPU is reported and not gated: process CPU on a shared runner carries the runner's noise, and the deterministic metrics already carry what can be gated exactly.

| Workload | Repetitions | Rounds | Median | p95 | p99 | CPU | Spread across repetitions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test_latency[fastapi_application_startup-depin] | 5 | 751 | 2.462 ms | 2.816 ms | 3.977 ms | 2.347 ms | 2.6% |
| test_latency[fastapi_application_startup-direct] | 5 | 1000 | 1.611 ms | 1.907 ms | 3.047 ms | 1.554 ms | 4.6% |
| test_latency[fastapi_async_resource_teardown-depin] | 5 | 1281 | 758.806 µs | 852.651 µs | 1.014 ms | 760.685 µs | 5.8% |
| test_latency[fastapi_async_resource_teardown-direct] | 5 | 1486 | 642.123 µs | 709.753 µs | 869.443 µs | 640.911 µs | 2.4% |
| test_latency[fastapi_cpu_light_endpoint-depin] | 5 | 1127 | 726.118 µs | 824.394 µs | 968.206 µs | 744.329 µs | 4.8% |
| test_latency[fastapi_cpu_light_endpoint-direct] | 5 | 1340 | 646.634 µs | 733.901 µs | 885.088 µs | 634.950 µs | 3.5% |
| test_latency[fastapi_endpoint_with_work-depin] | 5 | 1000 | 970.261 µs | 1.073 ms | 1.234 ms | 985.039 µs | 1.2% |
| test_latency[fastapi_endpoint_with_work-direct] | 5 | 1000 | 867.000 µs | 963.845 µs | 1.119 ms | 854.845 µs | 2.9% |
| test_latency[fastapi_request_scoped_graph-depin] | 5 | 1000 | 763.957 µs | 867.273 µs | 1.017 ms | 746.031 µs | 3.3% |
| test_latency[fastapi_request_scoped_graph-direct] | 5 | 1425 | 648.046 µs | 739.813 µs | 889.659 µs | 642.627 µs | 4.7% |
| test_latency[fastapi_singletons_and_transients-depin] | 5 | 1288 | 736.115 µs | 857.765 µs | 999.305 µs | 729.399 µs | 4.5% |
| test_latency[fastapi_singletons_and_transients-direct] | 5 | 1376 | 642.044 µs | 728.115 µs | 884.272 µs | 657.609 µs | 3.6% |

## Work

| Workload | Python calls per operation |
| --- | --- |
| allocations_of_a_cached_singleton_resolution | 9 |
| allocations_of_a_request_shaped_scope | 105 |
| allocations_of_a_scope_cycle | 396 |
| allocations_of_a_transient_chain | 202 |
| allocations_of_an_inject_call | 29 |

## Allocations

| Workload | Blocks per operation | Bytes per operation | Peak bytes |
| --- | --- | --- | --- |
| allocations_of_a_cached_singleton_resolution | 13 | 1168 | 2056 |
| allocations_of_a_request_shaped_scope | 27 | 2360 | 4360 |
| allocations_of_a_scope_cycle | 76 | 6240 | 14496 |
| allocations_of_a_transient_chain | 53 | 4968 | 5752 |
| allocations_of_an_inject_call | 17 | 1360 | 2064 |

## Retained memory

| Workload | Bytes held |
| --- | --- |
| retained_by_a_frozen_container_of_100 | 34568 |
| retained_by_a_frozen_container_of_1000 | 326000 |
| retained_by_a_warm_singleton_cache_of_1000 | 397560 |
| retained_by_an_open_scope_of_20 | 10512 |

## Scaling

| Curve | Size | Cost per operation | Growth over the previous size |
| --- | --- | --- | --- |
| scale_async_teardown | 10 | 171.166 µs | — |
| scale_async_teardown | 20 | 270.509 µs | 1.58x |
| scale_async_teardown | 40 | 467.681 µs | 1.73x |
| scale_freeze_graph_size | 100 | 3.557 ms | — |
| scale_freeze_graph_size | 200 | 7.099 ms | 2.00x |
| scale_freeze_graph_size | 400 | 14.159 ms | 1.99x |
| scale_override_nesting | 8 | 2.299 µs | — |
| scale_override_nesting | 32 | 3.932 µs | 1.71x |
| scale_override_nesting | 128 | 10.834 µs | 2.76x |
| scale_resolve_collection | 10 | 23.939 µs | — |
| scale_resolve_collection | 100 | 191.340 µs | 7.99x |
| scale_resolve_collection | 200 | 380.021 µs | 1.99x |
| scale_resolve_fan_out | 10 | 18.662 µs | — |
| scale_resolve_fan_out | 20 | 37.439 µs | 2.01x |
| scale_resolve_fan_out | 40 | 71.075 µs | 1.90x |
| scale_resolve_transient_depth | 10 | 19.710 µs | — |
| scale_resolve_transient_depth | 40 | 203.929 µs | 10.35x |
| scale_resolve_transient_depth | 160 | 768.570 µs | 3.77x |
| scale_scope_teardown | 10 | 101.862 µs | — |
| scale_scope_teardown | 20 | 191.945 µs | 1.88x |
| scale_scope_teardown | 40 | 372.958 µs | 1.94x |

## Retired measurements

Measured once, no longer measured. A workload withdrawn without a record is indistinguishable from one that was never written.

| Workload | What it claimed | Why it was retired | What covers the path now |
| --- | --- | --- | --- |
| scale_failing_freeze | The complexity class of the failing-freeze path, as the growth ratio between graph sizes. | The path is dominated by a constant that does not depend on graph size: `suggest_candidates` scans `sys.modules` when the error is built. Measured on the pull-request runner with both sides on identical code, the curve read 7.095, 7.021 and 7.026 ms at sizes 25, 50 and 100 — flat across a fourfold range — and the difference between the two identical revisions reached +23.61% against a 15% budget. The scan also depends on how many modules each process loaded, which is not a property of the revision under test. The curve was valid before the walk it watched was repaired; the repair is what left the constant in charge. | `tests/unit/test_longest_chain.py::test_failing_freeze_is_not_cubic_in_the_chain_length`, which asserts a complexity class over 400 providers on a budget two orders of magnitude above the constant, and the fixed-size latency workloads `freeze_a_chain_missing_a_provider_of_50` and `_of_100`. |
| scale_explain_missing_key | The complexity class of the missing-key walk, as the growth ratio between graph sizes. | The same constant, reached through `render`. The published reference-host dataset already recorded the curve as flat — 5.479, 5.503 and 5.444 ms at sizes 10, 12 and 14, growth 1.00x and 0.99x — while the number of simple paths through those graphs grows Fibonacci in the size. A curve that does not move where the quantity it claims to track quadruples is not measuring that quantity. | `tests/unit/test_longest_chain.py::test_explain_of_an_unbound_key_is_not_exponential_in_the_path_count`, over a 24-node fan-in-2 DAG, and the fixed-size latency workloads `explain_an_unbound_key_of_16` and `_of_20`. |

## Refused measurements

Asked for by the performance proposal and not measured here, with what an honest measurement would need in its place.

| Case | Why it is refused | What it would need |
| --- | --- | --- |
| Concurrent requests, active scopes, and singleton first-use contention. | Timed sleeps are forbidden here, so contention has to be created with explicit synchronisation — a barrier, a reduced switch interval — and a benchmark built that way measures the synchronisation as much as it measures the lock. The invariants themselves are already tested for correctness under free-threading in `tests/unit/test_free_threading.py`, where the guarantee rather than the number is what matters. | A design of its own, alongside the free-threading work that owns what the public surface commits to under concurrency. Routed to Step 8. |
| Long-running allocation and retention drift. | Retention here is a point-in-time reading. Drift is only visible over a soak, and how much runner time a soak may consume in a blocking pull-request gate is a budget decision rather than a methodological one. | A scheduled job with its own time budget, not a check on the pull-request path. |
