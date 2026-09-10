# Measured results

## Environment

| Property | Value |
| --- | --- |
| distributions.pydepin | 0.19.0 |
| distributions.pytest | 9.1.1 |
| distributions.pytest-benchmark | 5.3.0 |
| host.available_processors | 4 |
| host.cpu_model | Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| host.load_average | 2.94, 3.98, 3.64 |
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
| test_comparison[call_through_an_inject_wrapper-depin] | 5 | 40434 | 5.647 µs | 3.9% |
| test_comparison[call_through_an_inject_wrapper-direct] | 5 | 39756 | 118.460 ns | 3.5% |
| test_comparison[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 51758 | 6.660 µs | 2.4% |
| test_comparison[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 55356 | 174.785 ns | 4.5% |
| test_comparison[construct_a_singleton_for_the_first_time-dependency-injector-4.49.1] | 5 | 67097 | 5.593 µs | 4.8% |
| test_comparison[construct_a_singleton_for_the_first_time-depin] | 5 | 46597 | 5.749 µs | 8.3% |
| test_comparison[construct_a_singleton_for_the_first_time-direct] | 5 | 54801 | 297.703 ns | 49.9% |
| test_comparison[open_a_request_shaped_scope-depin] | 5 | 9933 | 28.556 µs | 5.5% |
| test_comparison[open_a_request_shaped_scope-direct] | 5 | 146306 | 867.003 ns | 1.1% |
| test_comparison[open_and_close_a_scope-depin] | 5 | 2895 | 192.545 µs | 3.6% |
| test_comparison[open_and_close_a_scope-direct] | 5 | 91634 | 3.033 µs | 5.7% |
| test_comparison[open_and_close_a_scope-dishka-1.10.1] | 5 | 1000 | 10.118 µs | 1.9% |
| test_comparison[open_and_close_a_scope-wireup-2.12.0] | 5 | 23545 | 9.364 µs | 6.7% |
| test_comparison[resolve_a_collection_of_10-depin] | 5 | 15880 | 18.645 µs | 3.3% |
| test_comparison[resolve_a_collection_of_10-direct] | 5 | 192604 | 196.039 ns | 2.7% |
| test_comparison[resolve_a_collection_of_100-depin] | 5 | 6340 | 137.340 µs | 4.3% |
| test_comparison[resolve_a_collection_of_100-direct] | 5 | 110363 | 408.149 ns | 6.2% |
| test_comparison[resolve_a_generic_key-depin] | 5 | 15890 | 6.082 µs | 8.2% |
| test_comparison[resolve_a_generic_key-direct] | 5 | 50126 | 92.570 ns | 2.6% |
| test_comparison[resolve_a_sync_resource_with_teardown-depin] | 5 | 8612 | 16.922 µs | 4.1% |
| test_comparison[resolve_a_sync_resource_with_teardown-direct] | 5 | 139374 | 1.532 µs | 1.8% |
| test_comparison[resolve_a_transient_chain-dependency-injector-4.49.1] | 5 | 1000 | 16.930 µs | 5.4% |
| test_comparison[resolve_a_transient_chain-depin] | 5 | 30365 | 4.455 µs | 4.4% |
| test_comparison[resolve_a_transient_chain-direct] | 5 | 170184 | 2.228 µs | 3.6% |
| test_comparison[resolve_a_transient_chain-dishka-1.10.1] | 5 | 1000 | 7.030 µs | 3.9% |
| test_comparison[resolve_a_transient_chain-wireup-2.12.0] | 5 | 37468 | 7.374 µs | 1.6% |
| test_comparison[resolve_an_async_singleton-depin] | 5 | 9878 | 16.809 µs | 1.3% |
| test_comparison[resolve_an_async_singleton-direct] | 5 | 32711 | 13.283 µs | 4.0% |
| test_comparison[resolve_cached_singleton-dependency-injector-4.49.1] | 5 | 65890 | 146.610 ns | 6.5% |
| test_comparison[resolve_cached_singleton-depin] | 5 | 109542 | 1.825 µs | 3.8% |
| test_comparison[resolve_cached_singleton-direct] | 5 | 1373 | 92.030 ns | 1.0% |
| test_comparison[resolve_cached_singleton-dishka-1.10.1] | 5 | 103724 | 904.023 ns | 10.1% |
| test_comparison[resolve_cached_singleton-svcs-26.2.0] | 5 | 50447 | 492.099 ns | 25.5% |
| test_comparison[resolve_cached_singleton-wireup-2.12.0] | 5 | 171526 | 278.250 ns | 4.7% |
| test_comparison[resolve_cached_singleton_through_an_alias-depin] | 5 | 7294 | 3.723 µs | 2.9% |
| test_comparison[resolve_cached_singleton_through_an_alias-direct] | 5 | 101072 | 92.330 ns | 4.6% |
| test_comparison[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 112664 | 1.864 µs | 2.7% |
| test_comparison[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 102554 | 92.280 ns | 5.1% |
| test_comparison[resolve_through_an_active_override-depin] | 5 | 87238 | 3.865 µs | 1.0% |
| test_comparison[resolve_through_an_active_override-direct] | 5 | 97505 | 96.680 ns | 7.1% |
| test_comparison[resolve_with_no_active_override-depin] | 5 | 157406 | 1.827 µs | 4.8% |
| test_comparison[resolve_with_no_active_override-direct] | 5 | 41725 | 92.510 ns | 0.7% |
| test_comparison[warmup_a_cold_singleton_graph-depin] | 5 | 1000 | 11.390 ms | 3.4% |
| test_comparison[warmup_a_cold_singleton_graph-direct] | 5 | 2000 | 270.025 µs | 4.7% |
| test_latency[build_the_graph_view-depin] | 5 | 473 | 4.205 ms | 6.9% |
| test_latency[call_through_an_inject_wrapper-depin] | 5 | 27863 | 5.658 µs | 2.3% |
| test_latency[call_through_an_inject_wrapper-direct] | 5 | 78648 | 119.090 ns | 7.0% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-depin] | 5 | 45857 | 6.726 µs | 2.9% |
| test_latency[call_through_an_inject_wrapper_with_explicit_arguments-direct] | 5 | 29934 | 167.220 ns | 4.1% |
| test_latency[construct_a_singleton_for_the_first_time-depin] | 5 | 26140 | 5.845 µs | 3.9% |
| test_latency[construct_a_singleton_for_the_first_time-direct] | 5 | 193200 | 296.472 ns | 4.2% |
| test_latency[explain_a_deep_chain-depin] | 5 | 310 | 6.532 ms | 7.1% |
| test_latency[explain_a_deep_chain_with_every_node_decorated-depin] | 5 | 119 | 16.623 ms | 22.1% |
| test_latency[explain_a_layered_dag-depin] | 5 | 400 | 4.978 ms | 6.9% |
| test_latency[explain_an_unbound_key_of_16-depin] | 5 | 270 | 12.686 ms | 17.8% |
| test_latency[explain_an_unbound_key_of_20-depin] | 5 | 271 | 12.583 ms | 40.1% |
| test_latency[export_a_large_graph_as_dot-depin] | 5 | 816 | 2.463 ms | 2.9% |
| test_latency[fastapi_async_resource_close-depin] | 5 | 1000 | 536.929 µs | 5.5% |
| test_latency[fastapi_endpoint_program_many_keys-depin] | 5 | 1000 | 490.876 µs | 3.2% |
| test_latency[fastapi_endpoint_program_one_key-depin] | 5 | 1063 | 483.836 µs | 6.2% |
| test_latency[fastapi_lazy_frame_activation_and_drain-depin] | 5 | 1000 | 523.906 µs | 4.1% |
| test_latency[fastapi_lazy_host_publication-depin] | 5 | 1068 | 452.788 µs | 6.5% |
| test_latency[fastapi_request_seed_read-depin] | 5 | 1000 | 547.376 µs | 6.7% |
| test_latency[freeze_a_chain_missing_a_provider_of_100-depin] | 5 | 180 | 16.308 ms | 23.9% |
| test_latency[freeze_a_chain_missing_a_provider_of_50-depin] | 5 | 218 | 14.298 ms | 19.1% |
| test_latency[freeze_a_chain_of_10-depin] | 5 | 1811 | 396.980 µs | 3.7% |
| test_latency[freeze_a_chain_of_100-depin] | 5 | 564 | 3.665 ms | 3.6% |
| test_latency[freeze_a_chain_of_1000-depin] | 5 | 56 | 36.805 ms | 3.9% |
| test_latency[freeze_a_decorated_chain_of_10-depin] | 5 | 1000 | 966.766 µs | 3.8% |
| test_latency[freeze_a_decorated_chain_of_100-depin] | 5 | 230 | 8.957 ms | 3.2% |
| test_latency[freeze_a_decorated_chain_of_1000-depin] | 5 | 23 | 92.162 ms | 7.4% |
| test_latency[freeze_a_generic_key_chain_of_10-depin] | 5 | 1000 | 711.151 µs | 2.8% |
| test_latency[freeze_a_generic_key_chain_of_100-depin] | 5 | 300 | 6.753 ms | 2.9% |
| test_latency[freeze_a_generic_key_chain_of_1000-depin] | 5 | 24 | 86.901 ms | 6.1% |
| test_latency[open_a_request_shaped_scope-depin] | 5 | 10827 | 27.956 µs | 4.7% |
| test_latency[open_a_request_shaped_scope-direct] | 5 | 63296 | 748.050 ns | 4.9% |
| test_latency[open_and_close_a_scope-depin] | 5 | 2396 | 192.986 µs | 4.8% |
| test_latency[open_and_close_a_scope-direct] | 5 | 76162 | 3.096 µs | 5.9% |
| test_latency[resolve_a_collection_of_10-depin] | 5 | 17551 | 18.635 µs | 3.0% |
| test_latency[resolve_a_collection_of_10-direct] | 5 | 49184 | 197.154 ns | 8.5% |
| test_latency[resolve_a_collection_of_100-depin] | 5 | 4848 | 137.001 µs | 5.4% |
| test_latency[resolve_a_collection_of_100-direct] | 5 | 85129 | 413.950 ns | 2.4% |
| test_latency[resolve_a_generic_key-depin] | 5 | 18374 | 5.913 µs | 5.9% |
| test_latency[resolve_a_generic_key-direct] | 5 | 100412 | 92.850 ns | 6.5% |
| test_latency[resolve_a_sync_resource_with_teardown-depin] | 5 | 8177 | 16.935 µs | 5.8% |
| test_latency[resolve_a_sync_resource_with_teardown-direct] | 5 | 130719 | 1.537 µs | 2.6% |
| test_latency[resolve_a_transient_chain-depin] | 5 | 46612 | 4.448 µs | 3.4% |
| test_latency[resolve_a_transient_chain-direct] | 5 | 132014 | 2.223 µs | 8.9% |
| test_latency[resolve_an_async_singleton-depin] | 5 | 16493 | 17.005 µs | 6.6% |
| test_latency[resolve_an_async_singleton-direct] | 5 | 24619 | 13.351 µs | 6.9% |
| test_latency[resolve_cached_singleton-depin] | 5 | 110853 | 1.844 µs | 8.1% |
| test_latency[resolve_cached_singleton-direct] | 5 | 102807 | 92.820 ns | 6.9% |
| test_latency[resolve_cached_singleton_through_an_alias-depin] | 5 | 73379 | 3.767 µs | 3.7% |
| test_latency[resolve_cached_singleton_through_an_alias-direct] | 5 | 100868 | 95.070 ns | 4.5% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 111882 | 1.839 µs | 6.0% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 103062 | 92.620 ns | 3.6% |
| test_latency[resolve_through_an_active_override-depin] | 5 | 64351 | 3.852 µs | 6.9% |
| test_latency[resolve_through_an_active_override-direct] | 5 | 97201 | 97.140 ns | 6.9% |
| test_latency[resolve_with_no_active_override-depin] | 5 | 141224 | 1.842 µs | 7.8% |
| test_latency[resolve_with_no_active_override-direct] | 5 | 105353 | 92.420 ns | 4.6% |
| test_latency[warmup_a_cold_singleton_graph-depin] | 5 | 168 | 11.511 ms | 5.8% |
| test_latency[warmup_a_cold_singleton_graph-direct] | 5 | 1000 | 279.645 µs | 7.1% |

## Application tier

Tail quantiles and CPU time are published for the application tier only. An end-to-end request has a tail a caller meets; a microbenchmark round is a calibrated loop, so its p99 describes the calibration rather than the operation. CPU is reported and not gated: process CPU on a shared runner carries the runner's noise, and the deterministic metrics already carry what can be gated exactly.

| Workload | Repetitions | Rounds | Median | p95 | p99 | CPU | Spread across repetitions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test_comparison[fastapi_application_startup-depin] | 5 | 1000 | 3.306 ms | 4.509 ms | 5.953 ms | 3.330 ms | 3.8% |
| test_comparison[fastapi_application_startup-direct] | 5 | 1000 | 2.179 ms | 3.089 ms | 4.817 ms | 2.130 ms | 3.5% |
| test_comparison[fastapi_async_resource_teardown-depin] | 5 | 1561 | 568.212 µs | 755.503 µs | 1.033 ms | 563.559 µs | 4.6% |
| test_comparison[fastapi_async_resource_teardown-direct] | 5 | 1999 | 461.176 µs | 589.766 µs | 907.490 µs | 464.108 µs | 5.5% |
| test_comparison[fastapi_cpu_light_endpoint-depin] | 5 | 1299 | 487.893 µs | 685.832 µs | 1.120 ms | 510.511 µs | 3.3% |
| test_comparison[fastapi_cpu_light_endpoint-direct] | 5 | 1315 | 460.633 µs | 668.572 µs | 998.510 µs | 462.132 µs | 3.2% |
| test_comparison[fastapi_endpoint_with_work-depin] | 5 | 1208 | 784.711 µs | 987.616 µs | 1.316 ms | 763.978 µs | 2.6% |
| test_comparison[fastapi_endpoint_with_work-direct] | 5 | 1383 | 697.593 µs | 921.797 µs | 1.397 ms | 672.743 µs | 2.3% |
| test_comparison[fastapi_no_injection-depin] | 5 | 1000 | 461.961 µs | 609.546 µs | 1.106 ms | 472.989 µs | 3.8% |
| test_comparison[fastapi_no_injection-direct] | 5 | 1779 | 446.278 µs | 640.910 µs | 1.049 ms | 441.643 µs | 3.1% |
| test_comparison[fastapi_request_scoped_graph-depin] | 5 | 1398 | 568.014 µs | 663.270 µs | 912.535 µs | 531.249 µs | 4.9% |
| test_comparison[fastapi_request_scoped_graph-direct] | 5 | 1948 | 462.519 µs | 658.301 µs | 1.037 ms | 462.491 µs | 5.3% |
| test_comparison[fastapi_singletons_and_transients-depin] | 5 | 1748 | 521.337 µs | 700.372 µs | 1.086 ms | 492.545 µs | 3.6% |
| test_comparison[fastapi_singletons_and_transients-direct] | 5 | 1799 | 464.664 µs | 555.404 µs | 754.573 µs | 481.126 µs | 2.6% |
| test_latency[fastapi_application_startup-depin] | 5 | 813 | 3.272 ms | 4.379 ms | 4.842 ms | 3.293 ms | 4.7% |
| test_latency[fastapi_application_startup-direct] | 5 | 1000 | 2.175 ms | 2.496 ms | 3.976 ms | 2.295 ms | 5.7% |
| test_latency[fastapi_async_resource_teardown-depin] | 5 | 1216 | 571.685 µs | 667.606 µs | 839.266 µs | 577.145 µs | 6.5% |
| test_latency[fastapi_async_resource_teardown-direct] | 5 | 1757 | 456.829 µs | 541.467 µs | 703.579 µs | 456.170 µs | 3.8% |
| test_latency[fastapi_cpu_light_endpoint-depin] | 5 | 1732 | 496.065 µs | 591.982 µs | 779.016 µs | 480.084 µs | 5.4% |
| test_latency[fastapi_cpu_light_endpoint-direct] | 5 | 1997 | 469.656 µs | 546.075 µs | 732.047 µs | 427.156 µs | 6.9% |
| test_latency[fastapi_endpoint_with_work-depin] | 5 | 1012 | 774.551 µs | 860.371 µs | 1.028 ms | 773.724 µs | 1.9% |
| test_latency[fastapi_endpoint_with_work-direct] | 5 | 1000 | 682.424 µs | 766.276 µs | 925.508 µs | 671.775 µs | 2.3% |
| test_latency[fastapi_no_injection-depin] | 5 | 1849 | 463.415 µs | 555.376 µs | 718.414 µs | 452.773 µs | 5.0% |
| test_latency[fastapi_no_injection-direct] | 5 | 1197 | 458.001 µs | 544.491 µs | 722.059 µs | 448.024 µs | 4.5% |
| test_latency[fastapi_request_scoped_graph-depin] | 5 | 1039 | 583.142 µs | 666.064 µs | 846.916 µs | 574.853 µs | 7.7% |
| test_latency[fastapi_request_scoped_graph-direct] | 5 | 1783 | 474.318 µs | 560.860 µs | 751.592 µs | 457.789 µs | 7.2% |
| test_latency[fastapi_singletons_and_transients-depin] | 5 | 1230 | 517.702 µs | 603.923 µs | 760.939 µs | 567.994 µs | 7.2% |
| test_latency[fastapi_singletons_and_transients-direct] | 5 | 1995 | 461.637 µs | 541.741 µs | 708.194 µs | 470.155 µs | 7.0% |

## Work

| Workload | Python calls per operation |
| --- | --- |
| allocations_of_a_cached_singleton_resolution | 8 |
| allocations_of_a_request_shaped_scope | 94 |
| allocations_of_a_scope_cycle | 363 |
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
| scale_async_teardown | 10 | 158.598 µs | — |
| scale_async_teardown | 20 | 249.958 µs | 1.58x |
| scale_async_teardown | 40 | 432.645 µs | 1.73x |
| scale_freeze_graph_size | 100 | 3.509 ms | — |
| scale_freeze_graph_size | 200 | 6.917 ms | 1.97x |
| scale_freeze_graph_size | 400 | 13.798 ms | 1.99x |
| scale_override_nesting | 8 | 2.272 µs | — |
| scale_override_nesting | 32 | 3.799 µs | 1.67x |
| scale_override_nesting | 128 | 10.074 µs | 2.65x |
| scale_resolve_collection | 10 | 23.932 µs | — |
| scale_resolve_collection | 100 | 194.640 µs | 8.13x |
| scale_resolve_collection | 200 | 403.076 µs | 2.07x |
| scale_resolve_fan_out | 10 | 19.194 µs | — |
| scale_resolve_fan_out | 20 | 37.719 µs | 1.97x |
| scale_resolve_fan_out | 40 | 72.969 µs | 1.93x |
| scale_resolve_transient_depth | 10 | 3.789 µs | — |
| scale_resolve_transient_depth | 40 | 10.432 µs | 2.75x |
| scale_resolve_transient_depth | 160 | 43.792 µs | 4.20x |
| scale_scope_teardown | 10 | 102.749 µs | — |
| scale_scope_teardown | 20 | 174.149 µs | 1.69x |
| scale_scope_teardown | 40 | 324.967 µs | 1.87x |

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
