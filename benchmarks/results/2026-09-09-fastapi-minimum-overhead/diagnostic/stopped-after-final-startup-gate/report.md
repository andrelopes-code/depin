# Measured results

## Environment

| Property | Value |
| --- | --- |
| distributions.pydepin | 0.19.0 |
| distributions.pytest | 9.1.1 |
| distributions.pytest-benchmark | 5.3.0 |
| host.available_processors | 4 |
| host.cpu_model | Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| host.load_average | 4.2, 3.31, 2.99 |
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
| test_comparison[call_through_an_inject_wrapper-depin] | 5 | 41048 | 5.798 µs | 2.4% |
| test_comparison[call_through_an_inject_wrapper-direct] | 5 | 77937 | 122.640 ns | 2.2% |
| test_comparison[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 50396 | 6.802 µs | 5.2% |
| test_comparison[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 195847 | 178.794 ns | 1.0% |
| test_comparison[construct_a_singleton_for_the_first_time-dependency-injector-4.49.1] | 5 | 68729 | 5.713 µs | 3.8% |
| test_comparison[construct_a_singleton_for_the_first_time-depin] | 5 | 22652 | 6.021 µs | 5.8% |
| test_comparison[construct_a_singleton_for_the_first_time-direct] | 5 | 86207 | 295.426 ns | 2.4% |
| test_comparison[open_a_request_shaped_scope-depin] | 5 | 9739 | 27.835 µs | 3.1% |
| test_comparison[open_a_request_shaped_scope-direct] | 5 | 179372 | 871.019 ns | 13.9% |
| test_comparison[open_and_close_a_scope-depin] | 5 | 2918 | 197.182 µs | 3.2% |
| test_comparison[open_and_close_a_scope-direct] | 5 | 79454 | 3.182 µs | 6.8% |
| test_comparison[open_and_close_a_scope-dishka-1.10.1] | 5 | 1000 | 10.205 µs | 5.4% |
| test_comparison[open_and_close_a_scope-wireup-2.12.0] | 5 | 21984 | 9.716 µs | 2.9% |
| test_comparison[resolve_a_collection_of_10-depin] | 5 | 27665 | 19.056 µs | 5.7% |
| test_comparison[resolve_a_collection_of_10-direct] | 5 | 191499 | 201.112 ns | 2.1% |
| test_comparison[resolve_a_collection_of_100-depin] | 5 | 5618 | 135.994 µs | 2.2% |
| test_comparison[resolve_a_collection_of_100-direct] | 5 | 62590 | 414.799 ns | 4.5% |
| test_comparison[resolve_a_generic_key-depin] | 5 | 59197 | 6.121 µs | 2.9% |
| test_comparison[resolve_a_generic_key-direct] | 5 | 101379 | 95.900 ns | 2.6% |
| test_comparison[resolve_a_sync_resource_with_teardown-depin] | 5 | 7510 | 16.276 µs | 3.2% |
| test_comparison[resolve_a_sync_resource_with_teardown-direct] | 5 | 138065 | 1.572 µs | 3.0% |
| test_comparison[resolve_a_transient_chain-dependency-injector-4.49.1] | 5 | 5122 | 16.990 µs | 2.2% |
| test_comparison[resolve_a_transient_chain-depin] | 5 | 41726 | 4.543 µs | 5.3% |
| test_comparison[resolve_a_transient_chain-direct] | 5 | 160617 | 2.257 µs | 5.8% |
| test_comparison[resolve_a_transient_chain-dishka-1.10.1] | 5 | 1000 | 7.139 µs | 5.4% |
| test_comparison[resolve_a_transient_chain-wireup-2.12.0] | 5 | 28182 | 7.416 µs | 5.0% |
| test_comparison[resolve_an_async_singleton-depin] | 5 | 13776 | 17.273 µs | 9.3% |
| test_comparison[resolve_an_async_singleton-direct] | 5 | 22746 | 13.394 µs | 5.6% |
| test_comparison[resolve_cached_singleton-dependency-injector-4.49.1] | 5 | 35040 | 146.420 ns | 2.7% |
| test_comparison[resolve_cached_singleton-depin] | 5 | 105486 | 1.864 µs | 5.1% |
| test_comparison[resolve_cached_singleton-direct] | 5 | 100645 | 95.030 ns | 2.2% |
| test_comparison[resolve_cached_singleton-dishka-1.10.1] | 5 | 92260 | 889.006 ns | 3.4% |
| test_comparison[resolve_cached_singleton-svcs-26.2.0] | 5 | 52885 | 487.974 ns | 2.3% |
| test_comparison[resolve_cached_singleton-wireup-2.12.0] | 5 | 159262 | 282.950 ns | 5.1% |
| test_comparison[resolve_cached_singleton_through_an_alias-depin] | 5 | 60057 | 3.882 µs | 9.8% |
| test_comparison[resolve_cached_singleton_through_an_alias-direct] | 5 | 52969 | 95.740 ns | 1.8% |
| test_comparison[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 123305 | 1.840 µs | 2.3% |
| test_comparison[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 102764 | 95.170 ns | 3.2% |
| test_comparison[resolve_through_an_active_override-depin] | 5 | 77731 | 3.966 µs | 3.6% |
| test_comparison[resolve_through_an_active_override-direct] | 5 | 96806 | 99.400 ns | 2.3% |
| test_comparison[resolve_with_no_active_override-depin] | 5 | 134681 | 1.840 µs | 4.0% |
| test_comparison[resolve_with_no_active_override-direct] | 5 | 94608 | 95.980 ns | 1.9% |
| test_comparison[warmup_a_cold_singleton_graph-depin] | 5 | 1000 | 11.873 ms | 5.1% |
| test_comparison[warmup_a_cold_singleton_graph-direct] | 5 | 2150 | 270.484 µs | 4.7% |
| test_latency[build_the_graph_view-depin] | 5 | 473 | 4.332 ms | 5.0% |
| test_latency[call_through_an_inject_wrapper-depin] | 5 | 51785 | 5.788 µs | 2.7% |
| test_latency[call_through_an_inject_wrapper-direct] | 5 | 76471 | 122.380 ns | 1.3% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 51089 | 6.818 µs | 1.8% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 55464 | 173.930 ns | 7.6% |
| test_latency[construct_a_singleton_for_the_first_time-depin] | 5 | 49085 | 6.027 µs | 3.6% |
| test_latency[construct_a_singleton_for_the_first_time-direct] | 5 | 187441 | 303.413 ns | 4.7% |
| test_latency[explain_a_deep_chain-depin] | 5 | 310 | 6.758 ms | 3.9% |
| test_latency[explain_a_deep_chain_with_every_node_decorated-depin] | 5 | 119 | 17.245 ms | 2.9% |
| test_latency[explain_a_layered_dag-depin] | 5 | 400 | 5.084 ms | 1.7% |
| test_latency[explain_an_unbound_key_of_16-depin] | 5 | 270 | 10.490 ms | 3.0% |
| test_latency[explain_an_unbound_key_of_20-depin] | 5 | 271 | 10.478 ms | 3.4% |
| test_latency[export_a_large_graph_as_dot-depin] | 5 | 816 | 2.459 ms | 4.3% |
| test_latency[fastapi_async_resource_close-depin] | 5 | 1000 | 766.970 µs | 3.1% |
| test_latency[fastapi_endpoint_program_many_keys-depin] | 5 | 1000 | 728.261 µs | 1.4% |
| test_latency[fastapi_endpoint_program_one_key-depin] | 5 | 1000 | 720.946 µs | 3.4% |
| test_latency[fastapi_lazy_frame_activation_and_drain-depin] | 5 | 1000 | 756.929 µs | 4.7% |
| test_latency[fastapi_lazy_host_publication-depin] | 5 | 1000 | 689.985 µs | 6.1% |
| test_latency[fastapi_request_seed_read-depin] | 5 | 1000 | 780.840 µs | 4.0% |
| test_latency[freeze_a_chain_missing_a_provider_of_100-depin] | 5 | 180 | 14.073 ms | 3.1% |
| test_latency[freeze_a_chain_missing_a_provider_of_50-depin] | 5 | 218 | 12.315 ms | 2.1% |
| test_latency[freeze_a_chain_of_10-depin] | 5 | 1757 | 405.200 µs | 2.3% |
| test_latency[freeze_a_chain_of_100-depin] | 5 | 564 | 3.781 ms | 1.8% |
| test_latency[freeze_a_chain_of_1000-depin] | 5 | 56 | 37.106 ms | 6.2% |
| test_latency[freeze_a_decorated_chain_of_10-depin] | 5 | 1000 | 1.004 ms | 7.7% |
| test_latency[freeze_a_decorated_chain_of_100-depin] | 5 | 230 | 9.307 ms | 3.2% |
| test_latency[freeze_a_decorated_chain_of_1000-depin] | 5 | 23 | 93.733 ms | 3.2% |
| test_latency[freeze_a_generic_key_chain_of_10-depin] | 5 | 1000 | 743.627 µs | 3.0% |
| test_latency[freeze_a_generic_key_chain_of_100-depin] | 5 | 300 | 7.040 ms | 5.1% |
| test_latency[freeze_a_generic_key_chain_of_1000-depin] | 5 | 24 | 89.066 ms | 13.4% |
| test_latency[open_a_request_shaped_scope-depin] | 5 | 11545 | 28.160 µs | 4.8% |
| test_latency[open_a_request_shaped_scope-direct] | 5 | 47491 | 784.149 ns | 4.9% |
| test_latency[open_and_close_a_scope-depin] | 5 | 1000 | 203.829 µs | 9.8% |
| test_latency[open_and_close_a_scope-direct] | 5 | 33744 | 3.110 µs | 11.8% |
| test_latency[resolve_a_collection_of_10-depin] | 5 | 28678 | 19.253 µs | 3.8% |
| test_latency[resolve_a_collection_of_10-direct] | 5 | 16381 | 202.639 ns | 1.0% |
| test_latency[resolve_a_collection_of_100-depin] | 5 | 5957 | 138.237 µs | 4.0% |
| test_latency[resolve_a_collection_of_100-direct] | 5 | 2022 | 423.125 ns | 5.2% |
| test_latency[resolve_a_generic_key-depin] | 5 | 36844 | 6.007 µs | 3.4% |
| test_latency[resolve_a_generic_key-direct] | 5 | 59369 | 95.820 ns | 16.0% |
| test_latency[resolve_a_sync_resource_with_teardown-depin] | 5 | 1000 | 16.339 µs | 7.2% |
| test_latency[resolve_a_sync_resource_with_teardown-direct] | 5 | 148944 | 1.565 µs | 3.0% |
| test_latency[resolve_a_transient_chain-depin] | 5 | 37971 | 4.599 µs | 3.1% |
| test_latency[resolve_a_transient_chain-direct] | 5 | 173521 | 2.238 µs | 6.2% |
| test_latency[resolve_an_async_singleton-depin] | 5 | 16154 | 17.032 µs | 6.1% |
| test_latency[resolve_an_async_singleton-direct] | 5 | 22523 | 13.481 µs | 4.6% |
| test_latency[resolve_cached_singleton-depin] | 5 | 122460 | 1.867 µs | 2.1% |
| test_latency[resolve_cached_singleton-direct] | 5 | 101001 | 94.970 ns | 3.8% |
| test_latency[resolve_cached_singleton_through_an_alias-depin] | 5 | 65596 | 3.832 µs | 12.8% |
| test_latency[resolve_cached_singleton_through_an_alias-direct] | 5 | 39905 | 95.370 ns | 1.2% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 116891 | 1.846 µs | 1.6% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 101720 | 95.370 ns | 1.7% |
| test_latency[resolve_through_an_active_override-depin] | 5 | 96359 | 3.975 µs | 4.1% |
| test_latency[resolve_through_an_active_override-direct] | 5 | 91025 | 99.890 ns | 4.8% |
| test_latency[resolve_with_no_active_override-depin] | 5 | 136334 | 1.863 µs | 4.4% |
| test_latency[resolve_with_no_active_override-direct] | 5 | 98961 | 95.090 ns | 2.1% |
| test_latency[warmup_a_cold_singleton_graph-depin] | 5 | 168 | 12.026 ms | 3.5% |
| test_latency[warmup_a_cold_singleton_graph-direct] | 5 | 2286 | 285.658 µs | 5.9% |

## Application tier

Tail quantiles and CPU time are published for the application tier only. An end-to-end request has a tail a caller meets; a microbenchmark round is a calibrated loop, so its p99 describes the calibration rather than the operation. CPU is reported and not gated: process CPU on a shared runner carries the runner's noise, and the deterministic metrics already carry what can be gated exactly.

| Workload | Repetitions | Rounds | Median | p95 | p99 | CPU | Spread across repetitions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test_comparison[fastapi_application_startup-depin] | 5 | 1000 | 3.346 ms | 3.701 ms | 5.176 ms | 3.356 ms | 2.1% |
| test_comparison[fastapi_application_startup-direct] | 5 | 1000 | 2.267 ms | 2.610 ms | 4.025 ms | 2.257 ms | 4.5% |
| test_comparison[fastapi_async_resource_teardown-depin] | 5 | 1124 | 802.873 µs | 884.806 µs | 1.069 ms | 832.870 µs | 3.7% |
| test_comparison[fastapi_async_resource_teardown-direct] | 5 | 1432 | 685.276 µs | 767.162 µs | 940.155 µs | 677.772 µs | 4.7% |
| test_comparison[fastapi_cpu_light_endpoint-depin] | 5 | 1000 | 730.586 µs | 813.176 µs | 967.607 µs | 709.741 µs | 5.0% |
| test_comparison[fastapi_cpu_light_endpoint-direct] | 5 | 1339 | 678.097 µs | 765.847 µs | 928.100 µs | 694.350 µs | 4.3% |
| test_comparison[fastapi_endpoint_with_work-depin] | 5 | 1000 | 1.012 ms | 1.120 ms | 1.278 ms | 994.329 µs | 1.2% |
| test_comparison[fastapi_endpoint_with_work-direct] | 5 | 1000 | 915.385 µs | 998.384 µs | 1.178 ms | 896.007 µs | 3.5% |
| test_comparison[fastapi_no_injection-depin] | 5 | 1069 | 696.559 µs | 778.104 µs | 928.213 µs | 717.839 µs | 3.0% |
| test_comparison[fastapi_no_injection-direct] | 5 | 1448 | 676.670 µs | 764.477 µs | 913.867 µs | 662.443 µs | 2.8% |
| test_comparison[fastapi_request_scoped_graph-depin] | 5 | 1179 | 782.788 µs | 879.527 µs | 1.042 ms | 771.925 µs | 2.4% |
| test_comparison[fastapi_request_scoped_graph-direct] | 5 | 1165 | 685.032 µs | 761.184 µs | 919.358 µs | 698.989 µs | 2.3% |
| test_comparison[fastapi_singletons_and_transients-depin] | 5 | 1200 | 742.640 µs | 845.231 µs | 1.003 ms | 727.798 µs | 4.3% |
| test_comparison[fastapi_singletons_and_transients-direct] | 5 | 1099 | 680.185 µs | 776.949 µs | 922.148 µs | 674.346 µs | 4.3% |
| test_latency[fastapi_application_startup-depin] | 5 | 813 | 3.371 ms | 3.725 ms | 4.974 ms | 3.499 ms | 2.5% |
| test_latency[fastapi_application_startup-direct] | 5 | 1000 | 2.236 ms | 2.611 ms | 4.116 ms | 2.347 ms | 5.5% |
| test_latency[fastapi_async_resource_teardown-depin] | 5 | 1130 | 796.672 µs | 870.026 µs | 1.068 ms | 809.417 µs | 3.7% |
| test_latency[fastapi_async_resource_teardown-direct] | 5 | 1403 | 673.817 µs | 746.481 µs | 918.231 µs | 678.542 µs | 3.3% |
| test_latency[fastapi_cpu_light_endpoint-depin] | 5 | 1342 | 724.500 µs | 800.700 µs | 972.238 µs | 700.925 µs | 2.2% |
| test_latency[fastapi_cpu_light_endpoint-direct] | 5 | 1370 | 682.081 µs | 758.098 µs | 918.793 µs | 659.569 µs | 4.0% |
| test_latency[fastapi_endpoint_with_work-depin] | 5 | 1000 | 1.008 ms | 1.102 ms | 1.289 ms | 1.012 ms | 2.0% |
| test_latency[fastapi_endpoint_with_work-direct] | 5 | 1008 | 913.403 µs | 1.005 ms | 1.178 ms | 905.710 µs | 1.4% |
| test_latency[fastapi_no_injection-depin] | 5 | 1324 | 696.036 µs | 774.407 µs | 933.998 µs | 700.626 µs | 4.1% |
| test_latency[fastapi_no_injection-direct] | 5 | 1336 | 681.730 µs | 762.292 µs | 943.207 µs | 666.795 µs | 3.7% |
| test_latency[fastapi_request_scoped_graph-depin] | 5 | 1000 | 789.445 µs | 877.900 µs | 1.047 ms | 805.113 µs | 3.5% |
| test_latency[fastapi_request_scoped_graph-direct] | 5 | 1329 | 687.165 µs | 770.088 µs | 934.779 µs | 682.597 µs | 3.5% |
| test_latency[fastapi_singletons_and_transients-depin] | 5 | 1277 | 746.831 µs | 830.456 µs | 1.010 ms | 733.012 µs | 3.1% |
| test_latency[fastapi_singletons_and_transients-direct] | 5 | 1222 | 687.011 µs | 761.253 µs | 941.079 µs | 643.126 µs | 3.9% |

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
| allocations_of_a_request_shaped_scope | 27 | 2360 | 4504 |
| allocations_of_a_scope_cycle | 75 | 6176 | 14576 |
| allocations_of_a_transient_chain | 12 | 1224 | 2008 |
| allocations_of_an_inject_call | 17 | 1360 | 2064 |

## Retained memory

| Workload | Bytes held |
| --- | --- |
| retained_by_a_frozen_container_of_100 | 35032 |
| retained_by_a_frozen_container_of_1000 | 326776 |
| retained_by_a_warm_singleton_cache_of_1000 | 397560 |
| retained_by_an_open_scope_of_20 | 10648 |

## Scaling

| Curve | Size | Cost per operation | Growth over the previous size |
| --- | --- | --- | --- |
| scale_async_teardown | 10 | 167.239 µs | — |
| scale_async_teardown | 20 | 272.755 µs | 1.63x |
| scale_async_teardown | 40 | 471.896 µs | 1.73x |
| scale_freeze_graph_size | 100 | 3.642 ms | — |
| scale_freeze_graph_size | 200 | 7.266 ms | 2.00x |
| scale_freeze_graph_size | 400 | 14.370 ms | 1.98x |
| scale_override_nesting | 8 | 2.404 µs | — |
| scale_override_nesting | 32 | 4.101 µs | 1.71x |
| scale_override_nesting | 128 | 10.840 µs | 2.64x |
| scale_resolve_collection | 10 | 24.130 µs | — |
| scale_resolve_collection | 100 | 194.454 µs | 8.06x |
| scale_resolve_collection | 200 | 397.847 µs | 2.05x |
| scale_resolve_fan_out | 10 | 22.057 µs | — |
| scale_resolve_fan_out | 20 | 37.314 µs | 1.69x |
| scale_resolve_fan_out | 40 | 74.604 µs | 2.00x |
| scale_resolve_transient_depth | 10 | 3.816 µs | — |
| scale_resolve_transient_depth | 40 | 10.592 µs | 2.78x |
| scale_resolve_transient_depth | 160 | 43.484 µs | 4.11x |
| scale_scope_teardown | 10 | 106.057 µs | — |
| scale_scope_teardown | 20 | 185.499 µs | 1.75x |
| scale_scope_teardown | 40 | 346.794 µs | 1.87x |

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
| fastapi_no_injection | The installed no-injection route exists only in the FastAPI optimization head; the accepted dataset predates it, so an archived baseline cannot supply a paired observation. It remains a head-only diagnostic and is reported separately rather than silently treated as paired evidence. | A five-repetition head-only diagnostic collection alongside the next accepted paired FastAPI run. |
| fastapi_lazy_host_publication | The accepted dataset predates the lazy FastAPI host-publication component diagnostic. | A dedicated component collection in a new accepted FastAPI evidence dataset. |
| fastapi_lazy_frame_activation_and_drain | The accepted dataset predates the lazy FastAPI frame-activation component diagnostic. | A dedicated component collection in a new accepted FastAPI evidence dataset. |
| fastapi_endpoint_program_one_key | The accepted dataset predates the one-key compiled FastAPI endpoint-program diagnostic. | A dedicated component collection in a new accepted FastAPI evidence dataset. |
| fastapi_endpoint_program_many_keys | The accepted dataset predates the multi-key compiled FastAPI endpoint-program diagnostic. | A dedicated component collection in a new accepted FastAPI evidence dataset. |
| fastapi_request_seed_read | The accepted dataset predates the lazy FastAPI request-seed component diagnostic. | A dedicated component collection in a new accepted FastAPI evidence dataset. |
| fastapi_async_resource_close | The accepted dataset predates the async FastAPI resource-close component diagnostic. | A dedicated component collection in a new accepted FastAPI evidence dataset. |
| Long-running allocation and retention drift. | Retention here is a point-in-time reading. Drift is only visible over a soak, and how much runner time a soak may consume in a blocking pull-request gate is a budget decision rather than a methodological one. | A scheduled job with its own time budget, not a check on the pull-request path. |

REPORT_EXIT=0
