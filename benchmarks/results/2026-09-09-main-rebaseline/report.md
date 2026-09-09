# Measured results

## Environment

| Property | Value |
| --- | --- |
| distributions.pydepin | 0.18.0 |
| distributions.pytest | 9.1.1 |
| distributions.pytest-benchmark | 5.3.0 |
| host.available_processors | 4 |
| host.cpu_model | Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| host.load_average | 2.44, 3.53, 4.17 |
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
| test_comparison[call_through_an_inject_wrapper-depin] | 5 | 40837 | 5.790 µs | 1.8% |
| test_comparison[call_through_an_inject_wrapper-direct] | 5 | 79682 | 122.890 ns | 1.0% |
| test_comparison[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 28624 | 6.794 µs | 3.8% |
| test_comparison[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 26484 | 178.248 ns | 1.9% |
| test_comparison[construct_a_singleton_for_the_first_time-dependency-injector-4.49.1] | 5 | 68952 | 5.678 µs | 1.1% |
| test_comparison[construct_a_singleton_for_the_first_time-depin] | 5 | 40503 | 5.768 µs | 5.5% |
| test_comparison[construct_a_singleton_for_the_first_time-direct] | 5 | 82042 | 295.250 ns | 2.0% |
| test_comparison[open_a_request_shaped_scope-depin] | 5 | 9613 | 26.812 µs | 3.3% |
| test_comparison[open_a_request_shaped_scope-direct] | 5 | 183790 | 872.009 ns | 12.9% |
| test_comparison[open_and_close_a_scope-depin] | 5 | 1661 | 196.246 µs | 4.1% |
| test_comparison[open_and_close_a_scope-direct] | 5 | 75002 | 3.086 µs | 2.7% |
| test_comparison[open_and_close_a_scope-dishka-1.10.1] | 5 | 1000 | 10.154 µs | 5.1% |
| test_comparison[open_and_close_a_scope-wireup-2.12.0] | 5 | 34391 | 9.520 µs | 6.3% |
| test_comparison[resolve_a_collection_of_10-depin] | 5 | 25320 | 19.074 µs | 2.0% |
| test_comparison[resolve_a_collection_of_10-direct] | 5 | 194744 | 202.879 ns | 4.5% |
| test_comparison[resolve_a_collection_of_100-depin] | 5 | 5808 | 137.279 µs | 1.9% |
| test_comparison[resolve_a_collection_of_100-direct] | 5 | 116686 | 419.552 ns | 1.6% |
| test_comparison[resolve_a_generic_key-depin] | 5 | 57304 | 6.042 µs | 2.6% |
| test_comparison[resolve_a_generic_key-direct] | 5 | 99463 | 96.131 ns | 2.5% |
| test_comparison[resolve_a_sync_resource_with_teardown-depin] | 5 | 8647 | 15.973 µs | 5.2% |
| test_comparison[resolve_a_sync_resource_with_teardown-direct] | 5 | 135649 | 1.581 µs | 3.6% |
| test_comparison[resolve_a_transient_chain-dependency-injector-4.49.1] | 5 | 1000 | 16.983 µs | 5.7% |
| test_comparison[resolve_a_transient_chain-depin] | 5 | 46383 | 4.509 µs | 4.1% |
| test_comparison[resolve_a_transient_chain-direct] | 5 | 166889 | 2.252 µs | 1.6% |
| test_comparison[resolve_a_transient_chain-dishka-1.10.1] | 5 | 1000 | 7.172 µs | 4.0% |
| test_comparison[resolve_a_transient_chain-wireup-2.12.0] | 5 | 34020 | 7.478 µs | 1.8% |
| test_comparison[resolve_an_async_singleton-depin] | 5 | 9229 | 17.321 µs | 3.7% |
| test_comparison[resolve_an_async_singleton-direct] | 5 | 32468 | 13.617 µs | 2.4% |
| test_comparison[resolve_cached_singleton-dependency-injector-4.49.1] | 5 | 62446 | 146.960 ns | 73.2% |
| test_comparison[resolve_cached_singleton-depin] | 5 | 107713 | 1.872 µs | 1.3% |
| test_comparison[resolve_cached_singleton-direct] | 5 | 102239 | 95.690 ns | 1.2% |
| test_comparison[resolve_cached_singleton-dishka-1.10.1] | 5 | 111982 | 895.991 ns | 2.9% |
| test_comparison[resolve_cached_singleton-svcs-26.2.0] | 5 | 50772 | 487.300 ns | 26.2% |
| test_comparison[resolve_cached_singleton-wireup-2.12.0] | 5 | 172951 | 278.850 ns | 2.1% |
| test_comparison[resolve_cached_singleton_through_an_alias-depin] | 5 | 59162 | 3.850 µs | 4.7% |
| test_comparison[resolve_cached_singleton_through_an_alias-direct] | 5 | 102470 | 95.650 ns | 1.3% |
| test_comparison[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 105708 | 1.886 µs | 3.2% |
| test_comparison[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 100120 | 95.300 ns | 1.4% |
| test_comparison[resolve_through_an_active_override-depin] | 5 | 85978 | 3.993 µs | 1.1% |
| test_comparison[resolve_through_an_active_override-direct] | 5 | 97762 | 100.460 ns | 2.1% |
| test_comparison[resolve_with_no_active_override-depin] | 5 | 150151 | 1.876 µs | 1.7% |
| test_comparison[resolve_with_no_active_override-direct] | 5 | 50567 | 95.510 ns | 1.7% |
| test_comparison[warmup_a_cold_singleton_graph-depin] | 5 | 1000 | 11.462 ms | 2.8% |
| test_comparison[warmup_a_cold_singleton_graph-direct] | 5 | 1000 | 282.260 µs | 9.1% |
| test_latency[build_the_graph_view-depin] | 5 | 473 | 4.374 ms | 4.9% |
| test_latency[call_through_an_inject_wrapper-depin] | 5 | 56757 | 5.762 µs | 2.6% |
| test_latency[call_through_an_inject_wrapper-direct] | 5 | 77108 | 123.940 ns | 0.9% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 31344 | 6.798 µs | 4.0% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 56600 | 172.830 ns | 0.7% |
| test_latency[construct_a_singleton_for_the_first_time-depin] | 5 | 27146 | 5.851 µs | 10.5% |
| test_latency[construct_a_singleton_for_the_first_time-direct] | 5 | 117042 | 302.296 ns | 35.3% |
| test_latency[explain_a_deep_chain-depin] | 5 | 310 | 6.669 ms | 1.9% |
| test_latency[explain_a_deep_chain_with_every_node_decorated-depin] | 5 | 119 | 18.666 ms | 11.1% |
| test_latency[explain_a_layered_dag-depin] | 5 | 400 | 5.071 ms | 9.4% |
| test_latency[explain_an_unbound_key_of_16-depin] | 5 | 270 | 13.023 ms | 16.5% |
| test_latency[explain_an_unbound_key_of_20-depin] | 5 | 271 | 13.216 ms | 10.2% |
| test_latency[export_a_large_graph_as_dot-depin] | 5 | 816 | 2.472 ms | 9.6% |
| test_latency[freeze_a_chain_missing_a_provider_of_100-depin] | 5 | 180 | 16.351 ms | 13.3% |
| test_latency[freeze_a_chain_missing_a_provider_of_50-depin] | 5 | 218 | 14.800 ms | 12.1% |
| test_latency[freeze_a_chain_of_10-depin] | 5 | 1721 | 396.963 µs | 3.5% |
| test_latency[freeze_a_chain_of_100-depin] | 5 | 564 | 3.765 ms | 3.4% |
| test_latency[freeze_a_chain_of_1000-depin] | 5 | 56 | 36.953 ms | 10.3% |
| test_latency[freeze_a_decorated_chain_of_10-depin] | 5 | 1000 | 983.032 µs | 4.6% |
| test_latency[freeze_a_decorated_chain_of_100-depin] | 5 | 230 | 9.167 ms | 7.8% |
| test_latency[freeze_a_decorated_chain_of_1000-depin] | 5 | 23 | 94.326 ms | 9.1% |
| test_latency[freeze_a_generic_key_chain_of_10-depin] | 5 | 1000 | 735.694 µs | 7.8% |
| test_latency[freeze_a_generic_key_chain_of_100-depin] | 5 | 300 | 6.861 ms | 6.3% |
| test_latency[freeze_a_generic_key_chain_of_1000-depin] | 5 | 24 | 87.827 ms | 12.4% |
| test_latency[open_a_request_shaped_scope-depin] | 5 | 11506 | 27.025 µs | 3.0% |
| test_latency[open_a_request_shaped_scope-direct] | 5 | 63784 | 774.137 ns | 1.5% |
| test_latency[open_and_close_a_scope-depin] | 5 | 2896 | 195.866 µs | 7.8% |
| test_latency[open_and_close_a_scope-direct] | 5 | 86588 | 3.152 µs | 3.5% |
| test_latency[resolve_a_collection_of_10-depin] | 5 | 21962 | 19.449 µs | 2.9% |
| test_latency[resolve_a_collection_of_10-direct] | 5 | 26280 | 204.687 ns | 4.1% |
| test_latency[resolve_a_collection_of_100-depin] | 5 | 5365 | 138.285 µs | 1.1% |
| test_latency[resolve_a_collection_of_100-direct] | 5 | 93739 | 423.251 ns | 2.6% |
| test_latency[resolve_a_generic_key-depin] | 5 | 60515 | 6.131 µs | 11.9% |
| test_latency[resolve_a_generic_key-direct] | 5 | 55304 | 94.990 ns | 28.5% |
| test_latency[resolve_a_sync_resource_with_teardown-depin] | 5 | 1000 | 15.962 µs | 2.2% |
| test_latency[resolve_a_sync_resource_with_teardown-direct] | 5 | 152952 | 1.561 µs | 5.3% |
| test_latency[resolve_a_transient_chain-depin] | 5 | 28216 | 4.611 µs | 3.7% |
| test_latency[resolve_a_transient_chain-direct] | 5 | 174642 | 2.259 µs | 1.8% |
| test_latency[resolve_an_async_singleton-depin] | 5 | 19262 | 17.417 µs | 19.5% |
| test_latency[resolve_an_async_singleton-direct] | 5 | 24199 | 13.614 µs | 7.2% |
| test_latency[resolve_cached_singleton-depin] | 5 | 107632 | 1.894 µs | 3.3% |
| test_latency[resolve_cached_singleton-direct] | 5 | 101927 | 95.380 ns | 0.7% |
| test_latency[resolve_cached_singleton_through_an_alias-depin] | 5 | 69430 | 3.862 µs | 4.8% |
| test_latency[resolve_cached_singleton_through_an_alias-direct] | 5 | 102083 | 95.820 ns | 1.4% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 121419 | 1.880 µs | 1.6% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 101896 | 95.420 ns | 1.4% |
| test_latency[resolve_through_an_active_override-depin] | 5 | 100463 | 3.976 µs | 4.8% |
| test_latency[resolve_through_an_active_override-direct] | 5 | 59390 | 99.660 ns | 4.9% |
| test_latency[resolve_with_no_active_override-depin] | 5 | 147667 | 1.864 µs | 9.8% |
| test_latency[resolve_with_no_active_override-direct] | 5 | 99404 | 95.130 ns | 9.3% |
| test_latency[warmup_a_cold_singleton_graph-depin] | 5 | 168 | 11.915 ms | 4.9% |
| test_latency[warmup_a_cold_singleton_graph-direct] | 5 | 1000 | 286.243 µs | 12.4% |

## Application tier

Tail quantiles and CPU time are published for the application tier only. An end-to-end request has a tail a caller meets; a microbenchmark round is a calibrated loop, so its p99 describes the calibration rather than the operation. CPU is reported and not gated: process CPU on a shared runner carries the runner's noise, and the deterministic metrics already carry what can be gated exactly.

| Workload | Repetitions | Rounds | Median | p95 | p99 | CPU | Spread across repetitions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test_comparison[fastapi_application_startup-depin] | 5 | 1000 | 2.558 ms | 2.888 ms | 4.100 ms | 2.486 ms | 5.1% |
| test_comparison[fastapi_application_startup-direct] | 5 | 1000 | 1.652 ms | 1.984 ms | 3.276 ms | 1.665 ms | 8.1% |
| test_comparison[fastapi_async_resource_teardown-depin] | 5 | 1619 | 595.343 µs | 681.464 µs | 864.656 µs | 567.618 µs | 4.7% |
| test_comparison[fastapi_async_resource_teardown-direct] | 5 | 1267 | 458.428 µs | 528.000 µs | 699.950 µs | 431.619 µs | 4.5% |
| test_comparison[fastapi_cpu_light_endpoint-depin] | 5 | 1425 | 536.728 µs | 618.396 µs | 768.508 µs | 528.902 µs | 4.8% |
| test_comparison[fastapi_cpu_light_endpoint-direct] | 5 | 1294 | 454.161 µs | 516.532 µs | 685.015 µs | 457.621 µs | 6.1% |
| test_comparison[fastapi_endpoint_with_work-depin] | 5 | 1196 | 814.397 µs | 923.975 µs | 1.083 ms | 835.514 µs | 5.2% |
| test_comparison[fastapi_endpoint_with_work-direct] | 5 | 1321 | 692.867 µs | 787.804 µs | 946.784 µs | 680.425 µs | 4.1% |
| test_comparison[fastapi_request_scoped_graph-depin] | 5 | 1482 | 581.381 µs | 651.442 µs | 844.397 µs | 607.767 µs | 8.2% |
| test_comparison[fastapi_request_scoped_graph-direct] | 5 | 1826 | 464.012 µs | 529.853 µs | 697.516 µs | 445.803 µs | 6.6% |
| test_comparison[fastapi_singletons_and_transients-depin] | 5 | 1170 | 563.456 µs | 667.846 µs | 834.396 µs | 549.613 µs | 5.1% |
| test_comparison[fastapi_singletons_and_transients-direct] | 5 | 1264 | 461.347 µs | 546.495 µs | 728.907 µs | 445.469 µs | 5.0% |
| test_latency[fastapi_application_startup-depin] | 5 | 813 | 2.573 ms | 3.194 ms | 4.442 ms | 2.575 ms | 5.1% |
| test_latency[fastapi_application_startup-direct] | 5 | 1000 | 1.641 ms | 2.017 ms | 3.465 ms | 1.652 ms | 6.5% |
| test_latency[fastapi_async_resource_teardown-depin] | 5 | 1472 | 592.195 µs | 665.504 µs | 893.961 µs | 594.107 µs | 8.8% |
| test_latency[fastapi_async_resource_teardown-direct] | 5 | 1093 | 463.673 µs | 576.371 µs | 838.952 µs | 449.398 µs | 7.8% |
| test_latency[fastapi_cpu_light_endpoint-depin] | 5 | 1301 | 545.338 µs | 627.349 µs | 811.929 µs | 563.897 µs | 5.3% |
| test_latency[fastapi_cpu_light_endpoint-direct] | 5 | 1257 | 468.543 µs | 536.225 µs | 726.691 µs | 458.628 µs | 7.2% |
| test_latency[fastapi_endpoint_with_work-depin] | 5 | 1000 | 812.275 µs | 1.043 ms | 1.347 ms | 826.729 µs | 5.5% |
| test_latency[fastapi_endpoint_with_work-direct] | 5 | 1368 | 696.973 µs | 851.463 µs | 1.091 ms | 695.525 µs | 4.5% |
| test_latency[fastapi_request_scoped_graph-depin] | 5 | 1488 | 596.500 µs | 682.414 µs | 876.346 µs | 589.455 µs | 6.0% |
| test_latency[fastapi_request_scoped_graph-direct] | 5 | 1000 | 468.294 µs | 587.306 µs | 838.465 µs | 458.294 µs | 7.7% |
| test_latency[fastapi_singletons_and_transients-depin] | 5 | 1699 | 583.025 µs | 774.002 µs | 921.807 µs | 574.783 µs | 13.3% |
| test_latency[fastapi_singletons_and_transients-direct] | 5 | 1954 | 470.239 µs | 548.694 µs | 747.118 µs | 459.980 µs | 8.4% |

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
| retained_by_a_frozen_container_of_100 | 35032 |
| retained_by_a_frozen_container_of_1000 | 326776 |
| retained_by_a_warm_singleton_cache_of_1000 | 397560 |
| retained_by_an_open_scope_of_20 | 10624 |

## Scaling

| Curve | Size | Cost per operation | Growth over the previous size |
| --- | --- | --- | --- |
| scale_async_teardown | 10 | 168.503 µs | — |
| scale_async_teardown | 20 | 266.858 µs | 1.58x |
| scale_async_teardown | 40 | 462.338 µs | 1.73x |
| scale_freeze_graph_size | 100 | 3.646 ms | — |
| scale_freeze_graph_size | 200 | 7.332 ms | 2.01x |
| scale_freeze_graph_size | 400 | 14.731 ms | 2.01x |
| scale_override_nesting | 8 | 2.287 µs | — |
| scale_override_nesting | 32 | 3.920 µs | 1.71x |
| scale_override_nesting | 128 | 10.625 µs | 2.71x |
| scale_resolve_collection | 10 | 23.362 µs | — |
| scale_resolve_collection | 100 | 186.009 µs | 7.96x |
| scale_resolve_collection | 200 | 373.398 µs | 2.01x |
| scale_resolve_fan_out | 10 | 18.893 µs | — |
| scale_resolve_fan_out | 20 | 37.006 µs | 1.96x |
| scale_resolve_fan_out | 40 | 71.384 µs | 1.93x |
| scale_resolve_transient_depth | 10 | 3.935 µs | — |
| scale_resolve_transient_depth | 40 | 10.792 µs | 2.74x |
| scale_resolve_transient_depth | 160 | 45.476 µs | 4.21x |
| scale_scope_teardown | 10 | 103.108 µs | — |
| scale_scope_teardown | 20 | 182.288 µs | 1.77x |
| scale_scope_teardown | 40 | 342.659 µs | 1.88x |

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
| Long-running allocation and retention drift. | Retention here is a point-in-time reading. Drift is only visible over a soak, and how much runner time a soak may consume in a blocking pull-request gate is a budget decision rather than a methodological one. | A scheduled job with its own time budget, not a check on the pull-request path. |
