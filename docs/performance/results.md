# Measured results

## Environment

| Property | Value |
| --- | --- |
| distributions.pydepin | 0.17.0 |
| distributions.pytest | 9.1.1 |
| distributions.pytest-benchmark | 5.3.0 |
| host.available_processors | 4 |
| host.cpu_model | Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| host.load_average | 2.43, 2.73, 2.47 |
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
| test_latency[build_the_graph_view-depin] | 5 | 179 | 4.280 ms | 3.1% |
| test_latency[call_through_an_inject_wrapper-depin] | 5 | 24213 | 5.570 µs | 7.9% |
| test_latency[call_through_an_inject_wrapper-direct] | 5 | 79473 | 119.030 ns | 3.3% |
| test_latency[explain_a_deep_chain-depin] | 5 | 120 | 6.584 ms | 2.9% |
| test_latency[explain_a_deep_chain_with_every_node_decorated-depin] | 5 | 120 | 16.584 ms | 3.2% |
| test_latency[explain_a_layered_dag-depin] | 5 | 149 | 4.961 ms | 3.8% |
| test_latency[explain_an_unbound_key_of_16-depin] | 5 | 125 | 7.357 ms | 2.1% |
| test_latency[explain_an_unbound_key_of_20-depin] | 5 | 131 | 7.432 ms | 2.5% |
| test_latency[export_a_large_graph_as_dot-depin] | 5 | 380 | 2.449 ms | 3.4% |
| test_latency[fastapi_application_startup-depin] | 5 | 324 | 2.445 ms | 3.5% |
| test_latency[fastapi_application_startup-direct] | 5 | 505 | 1.633 ms | 3.9% |
| test_latency[fastapi_async_resource_teardown-depin] | 5 | 1154 | 776.438 µs | 2.9% |
| test_latency[fastapi_async_resource_teardown-direct] | 5 | 1390 | 653.256 µs | 6.0% |
| test_latency[fastapi_cpu_light_endpoint-depin] | 5 | 1114 | 729.435 µs | 4.5% |
| test_latency[fastapi_cpu_light_endpoint-direct] | 5 | 1317 | 647.650 µs | 4.3% |
| test_latency[fastapi_endpoint_with_work-depin] | 5 | 931 | 1.005 ms | 4.1% |
| test_latency[fastapi_endpoint_with_work-direct] | 5 | 1063 | 882.937 µs | 5.7% |
| test_latency[fastapi_request_scoped_graph-depin] | 5 | 1137 | 779.516 µs | 4.2% |
| test_latency[fastapi_request_scoped_graph-direct] | 5 | 1001 | 654.946 µs | 5.7% |
| test_latency[fastapi_singletons_and_transients-depin] | 5 | 1210 | 760.037 µs | 4.7% |
| test_latency[fastapi_singletons_and_transients-direct] | 5 | 1075 | 654.150 µs | 4.4% |
| test_latency[freeze_a_chain_missing_a_provider_of_100-depin] | 5 | 120 | 10.960 ms | 4.2% |
| test_latency[freeze_a_chain_missing_a_provider_of_50-depin] | 5 | 120 | 9.175 ms | 1.7% |
| test_latency[freeze_a_chain_of_10-depin] | 5 | 1638 | 385.197 µs | 4.3% |
| test_latency[freeze_a_chain_of_100-depin] | 5 | 258 | 3.552 ms | 3.9% |
| test_latency[freeze_a_chain_of_1000-depin] | 5 | 120 | 35.862 ms | 5.5% |
| test_latency[freeze_a_decorated_chain_of_10-depin] | 5 | 934 | 928.047 µs | 2.5% |
| test_latency[freeze_a_decorated_chain_of_100-depin] | 5 | 120 | 8.659 ms | 3.2% |
| test_latency[freeze_a_decorated_chain_of_1000-depin] | 5 | 120 | 88.759 ms | 4.7% |
| test_latency[freeze_a_generic_key_chain_of_10-depin] | 5 | 860 | 694.034 µs | 8.9% |
| test_latency[freeze_a_generic_key_chain_of_100-depin] | 5 | 120 | 6.660 ms | 3.8% |
| test_latency[freeze_a_generic_key_chain_of_1000-depin] | 5 | 120 | 84.266 ms | 4.2% |
| test_latency[open_a_request_shaped_scope-depin] | 5 | 10459 | 26.723 µs | 6.9% |
| test_latency[open_a_request_shaped_scope-direct] | 5 | 181227 | 776.141 ns | 12.1% |
| test_latency[open_and_close_a_scope-depin] | 5 | 2806 | 325.633 µs | 4.2% |
| test_latency[open_and_close_a_scope-direct] | 5 | 93756 | 2.948 µs | 7.1% |
| test_latency[resolve_a_collection_of_10-depin] | 5 | 17504 | 18.164 µs | 4.1% |
| test_latency[resolve_a_collection_of_10-direct] | 5 | 49841 | 196.417 ns | 6.3% |
| test_latency[resolve_a_collection_of_100-depin] | 5 | 4968 | 133.030 µs | 1.9% |
| test_latency[resolve_a_collection_of_100-direct] | 5 | 43347 | 416.097 ns | 3.2% |
| test_latency[resolve_a_transient_chain-depin] | 5 | 9337 | 34.548 µs | 4.2% |
| test_latency[resolve_a_transient_chain-direct] | 5 | 134626 | 2.179 µs | 6.1% |
| test_latency[resolve_an_async_singleton-depin] | 5 | 17988 | 16.837 µs | 16.4% |
| test_latency[resolve_an_async_singleton-direct] | 5 | 31781 | 13.291 µs | 12.9% |
| test_latency[resolve_cached_singleton-depin] | 5 | 107969 | 1.759 µs | 4.9% |
| test_latency[resolve_cached_singleton-direct] | 5 | 43445 | 92.580 ns | 1.8% |
| test_latency[resolve_cached_singleton_through_an_alias-depin] | 5 | 34005 | 3.657 µs | 5.9% |
| test_latency[resolve_cached_singleton_through_an_alias-direct] | 5 | 101896 | 92.190 ns | 1.1% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-depin] | 5 | 112537 | 1.766 µs | 5.4% |
| test_latency[resolve_singleton_through_a_two_deep_decoration_chain-direct] | 5 | 102512 | 92.880 ns | 4.9% |
| test_latency[warmup_a_cold_singleton_graph-depin] | 5 | 120 | 11.956 ms | 4.1% |
| test_latency[warmup_a_cold_singleton_graph-direct] | 5 | 2961 | 262.731 µs | 7.5% |

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
| scale_explain_missing_key | 10 | 5.479 ms | — |
| scale_explain_missing_key | 12 | 5.503 ms | 1.00x |
| scale_explain_missing_key | 14 | 5.444 ms | 0.99x |
| scale_failing_freeze | 25 | 6.332 ms | — |
| scale_failing_freeze | 50 | 7.197 ms | 1.14x |
| scale_failing_freeze | 100 | 9.035 ms | 1.26x |
| scale_freeze_graph_size | 100 | 3.487 ms | — |
| scale_freeze_graph_size | 200 | 6.858 ms | 1.97x |
| scale_freeze_graph_size | 400 | 13.787 ms | 2.01x |
| scale_resolve_collection | 10 | 23.673 µs | — |
| scale_resolve_collection | 100 | 190.198 µs | 8.03x |
| scale_resolve_collection | 200 | 383.158 µs | 2.01x |
| scale_resolve_fan_out | 10 | 19.584 µs | — |
| scale_resolve_fan_out | 20 | 37.330 µs | 1.91x |
| scale_resolve_fan_out | 40 | 70.684 µs | 1.89x |
| scale_resolve_transient_depth | 10 | 19.068 µs | — |
| scale_resolve_transient_depth | 40 | 197.115 µs | 10.34x |
| scale_resolve_transient_depth | 160 | 764.523 µs | 3.88x |
| scale_scope_teardown | 10 | 102.169 µs | — |
| scale_scope_teardown | 20 | 184.875 µs | 1.81x |
| scale_scope_teardown | 40 | 351.049 µs | 1.90x |
