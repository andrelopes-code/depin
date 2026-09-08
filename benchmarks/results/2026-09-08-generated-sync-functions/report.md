# Measured results

## Environment

| Property | Value |
| --- | --- |
| distributions.pydepin | 0.18.0 |
| distributions.pytest | 9.1.1 |
| distributions.pytest-benchmark | 5.3.0 |
| host.available_processors | 4 |
| host.cpu_model | Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| host.load_average | 6.12, 6.27, 5.35 |
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
| test_comparison[call_through_an_inject_wrapper-depin] | 5 | 40935 | 5.793 µs | 9.6% |
| test_comparison[call_through_an_inject_wrapper-direct] | 5 | 78983 | 122.360 ns | 0.8% |
| test_comparison[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 45451 | 6.844 µs | 6.2% |
| test_comparison[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 48924 | 178.034 ns | 0.7% |
| test_comparison[construct_a_singleton_for_the_first_time-dependency-injector-4.49.1] | 5 | 1000 | 5.813 µs | 13.5% |
| test_comparison[construct_a_singleton_for_the_first_time-depin] | 5 | 38429 | 5.783 µs | 7.9% |
| test_comparison[construct_a_singleton_for_the_first_time-direct] | 5 | 82285 | 297.550 ns | 3.3% |
| test_comparison[open_a_request_shaped_scope-depin] | 5 | 8028 | 26.508 µs | 3.1% |
| test_comparison[open_a_request_shaped_scope-direct] | 5 | 179533 | 875.036 ns | 4.6% |
| test_comparison[open_and_close_a_scope-depin] | 5 | 2952 | 191.705 µs | 3.3% |
| test_comparison[open_and_close_a_scope-direct] | 5 | 73363 | 3.149 µs | 3.9% |
| test_comparison[open_and_close_a_scope-dishka-1.10.1] | 5 | 1000 | 10.300 µs | 4.0% |
| test_comparison[open_and_close_a_scope-wireup-2.12.0] | 5 | 23993 | 9.785 µs | 2.4% |
| test_comparison[resolve_a_collection_of_10-depin] | 5 | 27152 | 19.338 µs | 1.2% |
| test_comparison[resolve_a_collection_of_10-direct] | 5 | 194592 | 202.000 ns | 2.1% |
| test_comparison[resolve_a_collection_of_100-depin] | 5 | 5679 | 137.564 µs | 1.0% |
| test_comparison[resolve_a_collection_of_100-direct] | 5 | 2534 | 418.452 ns | 3.8% |
| test_comparison[resolve_a_generic_key-depin] | 5 | 58453 | 5.977 µs | 1.6% |
| test_comparison[resolve_a_generic_key-direct] | 5 | 101328 | 95.670 ns | 1.1% |
| test_comparison[resolve_a_sync_resource_with_teardown-depin] | 5 | 1000 | 15.943 µs | 7.7% |
| test_comparison[resolve_a_sync_resource_with_teardown-direct] | 5 | 142207 | 1.570 µs | 1.9% |
| test_comparison[resolve_a_transient_chain-dependency-injector-4.49.1] | 5 | 4787 | 17.009 µs | 1.4% |
| test_comparison[resolve_a_transient_chain-depin] | 5 | 46754 | 4.618 µs | 2.0% |
| test_comparison[resolve_a_transient_chain-direct] | 5 | 162575 | 2.267 µs | 2.5% |
| test_comparison[resolve_a_transient_chain-dishka-1.10.1] | 5 | 1000 | 7.167 µs | 2.2% |
| test_comparison[resolve_a_transient_chain-wireup-2.12.0] | 5 | 16349 | 7.465 µs | 3.9% |
| test_comparison[resolve_an_async_singleton-depin] | 5 | 16492 | 17.591 µs | 3.5% |
| test_comparison[resolve_an_async_singleton-direct] | 5 | 1000 | 13.704 µs | 5.7% |
| test_comparison[resolve_cached_singleton-dependency-injector-4.49.1] | 5 | 64696 | 147.220 ns | 8.8% |
| test_comparison[resolve_cached_singleton-depin] | 5 | 90810 | 1.830 µs | 4.2% |
| test_comparison[resolve_cached_singleton-direct] | 5 | 101990 | 95.110 ns | 1.3% |
| test_comparison[resolve_cached_singleton-dishka-1.10.1] | 5 | 96600 | 891.974 ns | 1.6% |
| test_comparison[resolve_cached_singleton-svcs-26.1.0] | 5 | 168068 | 606.989 ns | 20.5% |
| test_comparison[resolve_cached_singleton-wireup-2.12.0] | 5 | 172474 | 279.301 ns | 1.3% |
| test_comparison[resolve_cached_singleton_through_an_alias-depin] | 5 | 65356 | 3.858 µs | 5.2% |
| test_comparison[resolve_cached_singleton_through_an_alias-direct] | 5 | 102282 | 95.240 ns | 1.3% |
| test_comparison[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 34589 | 1.831 µs | 4.5% |
| test_comparison[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 102387 | 95.320 ns | 1.5% |
| test_comparison[resolve_through_an_active_override-depin] | 5 | 54098 | 4.010 µs | 3.2% |
| test_comparison[resolve_through_an_active_override-direct] | 5 | 98320 | 99.530 ns | 2.0% |
| test_comparison[resolve_with_no_active_override-depin] | 5 | 159034 | 1.833 µs | 2.5% |
| test_comparison[resolve_with_no_active_override-direct] | 5 | 100980 | 94.720 ns | 1.4% |
| test_comparison[warmup_a_cold_singleton_graph-depin] | 5 | 1000 | 12.023 ms | 14.8% |
| test_comparison[warmup_a_cold_singleton_graph-direct] | 5 | 1000 | 261.581 µs | 4.8% |
| test_latency[build_the_graph_view-depin] | 5 | 473 | 4.204 ms | 4.5% |
| test_latency[call_through_an_inject_wrapper-depin] | 5 | 54717 | 5.807 µs | 4.9% |
| test_latency[call_through_an_inject_wrapper-direct] | 5 | 79146 | 122.850 ns | 0.4% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 46808 | 6.888 µs | 4.5% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 55522 | 172.880 ns | 1.1% |
| test_latency[construct_a_singleton_for_the_first_time-depin] | 5 | 50718 | 5.954 µs | 6.1% |
| test_latency[construct_a_singleton_for_the_first_time-direct] | 5 | 158302 | 302.060 ns | 5.0% |
| test_latency[explain_a_deep_chain-depin] | 5 | 310 | 6.630 ms | 4.4% |
| test_latency[explain_a_deep_chain_with_every_node_decorated-depin] | 5 | 119 | 18.028 ms | 14.9% |
| test_latency[explain_a_layered_dag-depin] | 5 | 400 | 5.064 ms | 2.8% |
| test_latency[explain_an_unbound_key_of_16-depin] | 5 | 270 | 9.959 ms | 27.8% |
| test_latency[explain_an_unbound_key_of_20-depin] | 5 | 271 | 10.020 ms | 37.8% |
| test_latency[export_a_large_graph_as_dot-depin] | 5 | 816 | 2.481 ms | 5.6% |
| test_latency[freeze_a_chain_missing_a_provider_of_100-depin] | 5 | 180 | 14.325 ms | 27.1% |
| test_latency[freeze_a_chain_missing_a_provider_of_50-depin] | 5 | 218 | 12.163 ms | 32.3% |
| test_latency[freeze_a_chain_of_10-depin] | 5 | 1688 | 399.435 µs | 3.5% |
| test_latency[freeze_a_chain_of_100-depin] | 5 | 564 | 3.784 ms | 5.1% |
| test_latency[freeze_a_chain_of_1000-depin] | 5 | 56 | 38.058 ms | 5.5% |
| test_latency[freeze_a_decorated_chain_of_10-depin] | 5 | 1000 | 988.281 µs | 5.8% |
| test_latency[freeze_a_decorated_chain_of_100-depin] | 5 | 230 | 9.279 ms | 10.3% |
| test_latency[freeze_a_decorated_chain_of_1000-depin] | 5 | 23 | 94.683 ms | 14.3% |
| test_latency[freeze_a_generic_key_chain_of_10-depin] | 5 | 1000 | 722.031 µs | 3.0% |
| test_latency[freeze_a_generic_key_chain_of_100-depin] | 5 | 300 | 6.989 ms | 10.6% |
| test_latency[freeze_a_generic_key_chain_of_1000-depin] | 5 | 24 | 90.744 ms | 19.8% |
| test_latency[open_a_request_shaped_scope-depin] | 5 | 10482 | 27.028 µs | 2.7% |
| test_latency[open_a_request_shaped_scope-direct] | 5 | 33281 | 783.999 ns | 3.7% |
| test_latency[open_and_close_a_scope-depin] | 5 | 2606 | 198.070 µs | 3.7% |
| test_latency[open_and_close_a_scope-direct] | 5 | 74483 | 3.179 µs | 5.5% |
| test_latency[resolve_a_collection_of_10-depin] | 5 | 29502 | 19.257 µs | 2.8% |
| test_latency[resolve_a_collection_of_10-direct] | 5 | 176275 | 205.399 ns | 4.5% |
| test_latency[resolve_a_collection_of_100-depin] | 5 | 5385 | 137.972 µs | 2.1% |
| test_latency[resolve_a_collection_of_100-direct] | 5 | 84969 | 421.397 ns | 32.6% |
| test_latency[resolve_a_generic_key-depin] | 5 | 57127 | 5.985 µs | 1.8% |
| test_latency[resolve_a_generic_key-direct] | 5 | 101266 | 95.410 ns | 3.7% |
| test_latency[resolve_a_sync_resource_with_teardown-depin] | 5 | 10492 | 16.309 µs | 5.0% |
| test_latency[resolve_a_sync_resource_with_teardown-direct] | 5 | 140253 | 1.587 µs | 5.8% |
| test_latency[resolve_a_transient_chain-depin] | 5 | 28860 | 4.687 µs | 3.3% |
| test_latency[resolve_a_transient_chain-direct] | 5 | 164365 | 2.285 µs | 2.9% |
| test_latency[resolve_an_async_singleton-depin] | 5 | 15037 | 17.405 µs | 3.8% |
| test_latency[resolve_an_async_singleton-direct] | 5 | 24149 | 13.672 µs | 2.7% |
| test_latency[resolve_cached_singleton-depin] | 5 | 125992 | 1.837 µs | 4.9% |
| test_latency[resolve_cached_singleton-direct] | 5 | 76588 | 95.340 ns | 7.1% |
| test_latency[resolve_cached_singleton_through_an_alias-depin] | 5 | 72229 | 3.849 µs | 4.6% |
| test_latency[resolve_cached_singleton_through_an_alias-direct] | 5 | 102271 | 95.190 ns | 5.5% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 110315 | 1.831 µs | 1.1% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 101740 | 94.920 ns | 0.9% |
| test_latency[resolve_through_an_active_override-depin] | 5 | 83942 | 4.022 µs | 3.0% |
| test_latency[resolve_through_an_active_override-direct] | 5 | 95814 | 99.720 ns | 0.8% |
| test_latency[resolve_with_no_active_override-depin] | 5 | 145392 | 1.839 µs | 2.7% |
| test_latency[resolve_with_no_active_override-direct] | 5 | 37276 | 95.130 ns | 0.7% |
| test_latency[warmup_a_cold_singleton_graph-depin] | 5 | 168 | 11.768 ms | 20.5% |
| test_latency[warmup_a_cold_singleton_graph-direct] | 5 | 2278 | 275.042 µs | 8.9% |

## Application tier

Tail quantiles and CPU time are published for the application tier only. An end-to-end request has a tail a caller meets; a microbenchmark round is a calibrated loop, so its p99 describes the calibration rather than the operation. CPU is reported and not gated: process CPU on a shared runner carries the runner's noise, and the deterministic metrics already carry what can be gated exactly.

| Workload | Repetitions | Rounds | Median | p95 | p99 | CPU | Spread across repetitions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test_comparison[fastapi_application_startup-depin] | 5 | 1000 | 2.673 ms | 4.853 ms | 7.306 ms | 2.578 ms | 4.2% |
| test_comparison[fastapi_application_startup-direct] | 5 | 1000 | 1.715 ms | 4.079 ms | 5.518 ms | 1.640 ms | 9.7% |
| test_comparison[fastapi_async_resource_teardown-depin] | 5 | 1124 | 794.058 µs | 1.083 ms | 3.258 ms | 801.806 µs | 2.5% |
| test_comparison[fastapi_async_resource_teardown-direct] | 5 | 1359 | 667.429 µs | 865.567 µs | 1.160 ms | 673.238 µs | 2.4% |
| test_comparison[fastapi_cpu_light_endpoint-depin] | 5 | 1086 | 742.173 µs | 848.280 µs | 1.012 ms | 769.701 µs | 4.5% |
| test_comparison[fastapi_cpu_light_endpoint-direct] | 5 | 1000 | 663.538 µs | 756.310 µs | 913.477 µs | 658.994 µs | 4.0% |
| test_comparison[fastapi_endpoint_with_work-depin] | 5 | 1000 | 1.010 ms | 1.314 ms | 3.305 ms | 1.008 ms | 3.3% |
| test_comparison[fastapi_endpoint_with_work-direct] | 5 | 1052 | 890.193 µs | 1.330 ms | 3.644 ms | 922.851 µs | 1.8% |
| test_comparison[fastapi_request_scoped_graph-depin] | 5 | 1000 | 793.648 µs | 893.803 µs | 1.084 ms | 783.846 µs | 4.1% |
| test_comparison[fastapi_request_scoped_graph-direct] | 5 | 1402 | 668.487 µs | 1.211 ms | 3.340 ms | 689.181 µs | 3.6% |
| test_comparison[fastapi_singletons_and_transients-depin] | 5 | 1000 | 770.643 µs | 1.415 ms | 3.028 ms | 752.610 µs | 6.1% |
| test_comparison[fastapi_singletons_and_transients-direct] | 5 | 1000 | 667.724 µs | 928.425 µs | 3.438 ms | 657.664 µs | 3.2% |
| test_latency[fastapi_application_startup-depin] | 5 | 813 | 2.576 ms | 3.374 ms | 5.647 ms | 2.605 ms | 7.7% |
| test_latency[fastapi_application_startup-direct] | 5 | 1000 | 1.635 ms | 2.119 ms | 3.590 ms | 1.647 ms | 12.0% |
| test_latency[fastapi_async_resource_teardown-depin] | 5 | 1055 | 792.325 µs | 1.018 ms | 1.264 ms | 817.203 µs | 4.5% |
| test_latency[fastapi_async_resource_teardown-direct] | 5 | 1389 | 663.880 µs | 848.952 µs | 1.131 ms | 675.174 µs | 3.6% |
| test_latency[fastapi_cpu_light_endpoint-depin] | 5 | 1265 | 745.614 µs | 877.477 µs | 1.046 ms | 741.048 µs | 2.5% |
| test_latency[fastapi_cpu_light_endpoint-direct] | 5 | 1281 | 660.400 µs | 943.795 µs | 1.372 ms | 658.175 µs | 3.4% |
| test_latency[fastapi_endpoint_with_work-depin] | 5 | 1000 | 1.007 ms | 1.244 ms | 1.503 ms | 1.026 ms | 5.4% |
| test_latency[fastapi_endpoint_with_work-direct] | 5 | 1082 | 886.934 µs | 1.128 ms | 1.590 ms | 912.195 µs | 4.0% |
| test_latency[fastapi_request_scoped_graph-depin] | 5 | 1000 | 805.928 µs | 1.096 ms | 1.468 ms | 810.525 µs | 3.7% |
| test_latency[fastapi_request_scoped_graph-direct] | 5 | 1414 | 677.973 µs | 905.775 µs | 1.454 ms | 716.735 µs | 5.7% |
| test_latency[fastapi_singletons_and_transients-depin] | 5 | 1000 | 778.279 µs | 938.634 µs | 1.209 ms | 754.025 µs | 5.3% |
| test_latency[fastapi_singletons_and_transients-direct] | 5 | 1404 | 668.075 µs | 886.421 µs | 1.110 ms | 672.302 µs | 4.8% |

## Work

| Workload | Python calls per operation |
| --- | --- |
| allocations_of_a_cached_singleton_resolution | 8 |
| allocations_of_a_request_shaped_scope | 88 |
| allocations_of_a_scope_cycle | 358 |
| allocations_of_a_transient_chain | 28 |
| allocations_of_an_inject_call | 28 |

## Allocations

| Workload | Blocks per operation | Bytes per operation | Peak bytes |
| --- | --- | --- | --- |
| allocations_of_a_cached_singleton_resolution | 13 | 1168 | 2056 |
| allocations_of_a_request_shaped_scope | 27 | 2360 | 4480 |
| allocations_of_a_scope_cycle | 75 | 6176 | 14552 |
| allocations_of_a_transient_chain | 12 | 1224 | 2008 |
| allocations_of_an_inject_call | 17 | 1360 | 2064 |

## Retained memory

| Workload | Bytes held |
| --- | --- |
| retained_by_a_frozen_container_of_100 | 35096 |
| retained_by_a_frozen_container_of_1000 | 326528 |
| retained_by_a_warm_singleton_cache_of_1000 | 397560 |
| retained_by_an_open_scope_of_20 | 10624 |

## Scaling

| Curve | Size | Cost per operation | Growth over the previous size |
| --- | --- | --- | --- |
| scale_async_teardown | 10 | 163.096 µs | — |
| scale_async_teardown | 20 | 265.523 µs | 1.63x |
| scale_async_teardown | 40 | 469.006 µs | 1.77x |
| scale_freeze_graph_size | 100 | 3.607 ms | — |
| scale_freeze_graph_size | 200 | 7.218 ms | 2.00x |
| scale_freeze_graph_size | 400 | 14.177 ms | 1.96x |
| scale_override_nesting | 8 | 2.248 µs | — |
| scale_override_nesting | 32 | 3.890 µs | 1.73x |
| scale_override_nesting | 128 | 10.884 µs | 2.80x |
| scale_resolve_collection | 10 | 23.514 µs | — |
| scale_resolve_collection | 100 | 197.802 µs | 8.41x |
| scale_resolve_collection | 200 | 410.802 µs | 2.08x |
| scale_resolve_fan_out | 10 | 18.842 µs | — |
| scale_resolve_fan_out | 20 | 36.380 µs | 1.93x |
| scale_resolve_fan_out | 40 | 75.119 µs | 2.06x |
| scale_resolve_transient_depth | 10 | 4.057 µs | — |
| scale_resolve_transient_depth | 40 | 11.424 µs | 2.82x |
| scale_resolve_transient_depth | 160 | 46.291 µs | 4.05x |
| scale_scope_teardown | 10 | 101.022 µs | — |
| scale_scope_teardown | 20 | 186.439 µs | 1.85x |
| scale_scope_teardown | 40 | 347.777 µs | 1.87x |

## Retired measurements

Measured once, no longer measured. A workload withdrawn without a record is indistinguishable from one that was never written.

| Workload | What it claimed | Why it was retired | What covers the path now |
| --- | --- | --- | --- |
| scale_failing_freeze | The complexity class of the failing-freeze path, as the growth ratio between graph sizes. | The path is dominated by a constant that does not depend on graph size: `suggest_candidates` scans `sys.modules` when the error is built. Measured on the pull-request runner with both sides on identical code, the curve read 7.095, 7.021 and 7.026 ms at sizes 25, 50 and 100 — flat across a fourfold range — and the difference between the two identical revisions reached +23.61% against a 15% budget. The scan also depends on how many modules each process loaded, which is not a property of the revision under test. The curve was valid before the walk it watched was repaired; the repair is what left the constant in charge. | `tests/unit/test_longest_chain.py::test_failing_freeze_does_not_grow_cubically_with_the_chain_length`, which compares 200 providers against 400 — the sizes at which the walk overtakes the constant — and reads 1.80 repaired against 5.91 with the cubic walk restored. It replaced a half-second wall-clock budget that the same seeded walk passed at 0.42 s, on a host faster than the one that budget was written on. The fixed-size latency workloads `freeze_a_chain_missing_a_provider_of_50` and `_of_100` cover the path as well. |
| scale_explain_missing_key | The complexity class of the missing-key walk, as the growth ratio between graph sizes. | The same constant, reached through `render`. The published reference-host dataset already recorded the curve as flat — 5.479, 5.503 and 5.444 ms at sizes 10, 12 and 14, growth 1.00x and 0.99x — while the number of simple paths through those graphs grows Fibonacci in the size. A curve that does not move where the quantity it claims to track quadruples is not measuring that quantity. | `tests/unit/test_longest_chain.py::test_explain_of_an_unbound_key_does_not_grow_with_the_path_count`, which compares a 16-node fan-in-2 DAG against a 24-node one — eighteen times the simple paths — and reads 1.00 repaired against 24.94 with the enumerating walk restored. The fixed-size latency workloads `explain_an_unbound_key_of_16` and `_of_20` cover the path as well. |

## Refused measurements

Asked for by the performance proposal and not measured here, with what an honest measurement would need in its place.

| Case | Why it is refused | What it would need |
| --- | --- | --- |
| Concurrent requests, active scopes, and singleton first-use contention. | Timed sleeps are forbidden here, so contention has to be created with explicit synchronisation — a barrier, a reduced switch interval — and a benchmark built that way measures the synchronisation as much as it measures the lock. The invariants themselves are already tested for correctness under free-threading in `tests/unit/test_free_threading.py`, where the guarantee rather than the number is what matters. | A design of its own, alongside the free-threading work that owns what the public surface commits to under concurrency. Routed to Step 8. |
| Long-running allocation and retention drift. | Retention here is a point-in-time reading. Drift is only visible over a soak, and how much runner time a soak may consume in a blocking pull-request gate is a budget decision rather than a methodological one. | A scheduled job with its own time budget, not a check on the pull-request path. |
