# Comparative performance evidence

## FastAPI minimum-overhead status

The 2026-09-09 FastAPI optimization diagnostic is not published as accepted
performance evidence. Its first counterbalanced CPU-light pair measured a
108.542-microsecond depin-over-direct p50 increment, above the 45.525-microsecond
maximum required for a 25% reduction from the accepted 60.7-microsecond
baseline. The incomplete raw pair and diagnosis are retained in
`benchmarks/results/2026-09-09-fastapi-minimum-overhead/`; no leadership or
tail-performance claim is made from that partial collection.

## resolve_cached_singleton

| Measure | Result |
| --- | --- |
| Claim | What does one resolution cost once the value is already built? |
| Status | loss |
| Noise allowance | 2.4% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +1.781 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | equivalent | matches the singleton or transient provider lifecycle and construction shape | 149.450 ns | 1.876 µs | [+1149.99%, +1193.26%] | [+1160.32%, +1177.21%] | [+373.47%, +685.01%] |
| dishka-1.10.1 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 896.049 ns | 1.876 µs | [+104.23%, +112.21%] | [+101.02%, +107.55%] | [+94.18%, +133.82%] |
| wireup-2.12.0 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 284.601 ns | 1.876 µs | [+553.68%, +568.56%] | [+565.64%, +580.02%] | [+148.28%, +501.46%] |
| svcs-26.2.0 | partial | per-container caching has no singleton single-flight guarantee or nested lifetime contract | — | — | — | — | — |

## resolve_cached_singleton_through_an_alias

| Measure | Result |
| --- | --- |
| Claim | What does a second name for a binding add to a resolution? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.7% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +3.823 µs |
| Absolute target | 1.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector delegates do not provide depin typed-key alias resolution | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka alias resolution does not demonstrate depin typed-key alias cache semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup alias resolution does not demonstrate depin typed-key alias cache semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no depin typed-key alias resolution | — | — | — | — | — |

## resolve_singleton_through_a_two_deep_decoration_chain

| Measure | Result |
| --- | --- |
| Claim | What do two stacked decorators add to a resolution? |
| Status | no-equivalent-competitor |
| Noise allowance | 3.3% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +1.809 µs |
| Absolute target | 1.500 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector provider composition does not model depin decoration chains | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka provider composition does not model depin decoration chains | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup provider composition does not model depin decoration chains | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs registrations do not model depin decoration chains | — | — | — | — | — |

## resolve_a_collection_of_10

| Measure | Result |
| --- | --- |
| Claim | What does gathering a multi-binding into a list cost, by member count? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.6% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +19.184 µs |
| Absolute target | 5.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector has no depin collection binding and aggregation operation | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka has no depin collection binding and aggregation operation | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup has no depin collection binding and aggregation operation | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no depin collection binding and aggregation operation | — | — | — | — | — |

## resolve_a_collection_of_100

| Measure | Result |
| --- | --- |
| Claim | What does gathering a multi-binding into a list cost, by member count? |
| Status | no-equivalent-competitor |
| Noise allowance | 0.9% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +137.114 µs |
| Absolute target | 50.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector has no depin collection binding and aggregation operation | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka has no depin collection binding and aggregation operation | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup has no depin collection binding and aggregation operation | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no depin collection binding and aggregation operation | — | — | — | — | — |

## resolve_a_transient_chain

| Measure | Result |
| --- | --- |
| Claim | What does depin add to constructing a dependency chain that is never cached? |
| Status | competitive |
| Noise allowance | 2.4% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +2.322 µs |
| Absolute target | 10.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | equivalent | matches the singleton or transient provider lifecycle and construction shape | 17.373 µs | 4.566 µs | [-74.14%, -73.26%] | [-84.38%, -74.15%] | [-69.96%, -53.62%] |
| dishka-1.10.1 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 7.130 µs | 4.566 µs | [-36.97%, -33.33%] | [-42.19%, -38.71%] | [-58.27%, -7.45%] |
| wireup-2.12.0 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 7.460 µs | 4.566 µs | [-39.97%, -37.30%] | [-65.17%, -52.67%] | [-58.91%, -20.64%] |
| svcs-26.2.0 | incomparable | svcs does not expose the depin provider operation this workload measures | — | — | — | — | — |

## open_and_close_a_scope

| Measure | Result |
| --- | --- |
| Claim | What does one scope cost, from entry to teardown? |
| Status | loss |
| Noise allowance | 2.4% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +189.805 µs |
| Absolute target | 12.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | provider overrides are substitutions, not nested scope frames with scoped caches | — | — | — | — | — |
| dishka-1.10.1 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 10.374 µs | 193.141 µs | [+1601.06%, +1896.95%] | [+1823.28%, +2329.04%] | [+1092.45%, +2389.32%] |
| wireup-2.12.0 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 9.663 µs | 193.141 µs | [+1788.45%, +2107.39%] | [+1069.22%, +1580.76%] | [+111.32%, +915.97%] |
| svcs-26.2.0 | incomparable | svcs containers have no nested scope frames with scoped caches | — | — | — | — | — |

## call_through_an_inject_wrapper

| Measure | Result |
| --- | --- |
| Claim | What does calling a function whose dependency depin supplies cost? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.7% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +5.706 µs |
| Absolute target | 1.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector wiring does not share depin injection wrapper calling semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka injection does not share depin injection wrapper calling semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup injection does not share depin injection wrapper calling semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no depin injection wrapper calling semantics | — | — | — | — | — |

## call_through_an_inject_wrapper_with_explicit_arguments

| Measure | Result |
| --- | --- |
| Claim | What does an argument the caller supplies add to an injected call? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.8% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +6.657 µs |
| Absolute target | 1.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector wiring does not share depin injection wrapper calling semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka injection does not share depin injection wrapper calling semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup injection does not share depin injection wrapper calling semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no depin injection wrapper calling semantics | — | — | — | — | — |

## resolve_an_async_singleton

| Measure | Result |
| --- | --- |
| Claim | What does depin add to driving one coroutine through an event loop? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.0% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +3.632 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector async and resource providers have different resolution and teardown semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka async and resource providers have different resolution and teardown semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup async and resource providers have different resolution and teardown semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs async factories and cleanup do not share depin resolution and teardown semantics | — | — | — | — | — |

## resolve_with_no_active_override

| Measure | Result |
| --- | --- |
| Claim | What does the override check cost on a resolution nothing has overridden? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.9% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +1.770 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector provider overrides are not depin context-local override frames | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka provider substitution is not a depin context-local override frame | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup provider substitution is not a depin context-local override frame | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no depin context-local override frames | — | — | — | — | — |

## resolve_through_an_active_override

| Measure | Result |
| --- | --- |
| Claim | What does a resolution cost while an override for that key is installed? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.0% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +3.899 µs |
| Absolute target | 1.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector provider overrides are not depin context-local override frames | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka provider substitution is not a depin context-local override frame | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup provider substitution is not a depin context-local override frame | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no depin context-local override frames | — | — | — | — | — |

## resolve_a_generic_key

| Measure | Result |
| --- | --- |
| Claim | What does a parameterised generic key cost at resolution time? |
| Status | no-equivalent-competitor |
| Noise allowance | 4.0% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +5.948 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector providers are not resolved from depin parameterised generic keys | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka providers are not resolved from depin parameterised generic keys | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup providers are not resolved from depin parameterised generic keys | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs services are not resolved from depin parameterised generic keys | — | — | — | — | — |

## construct_a_singleton_for_the_first_time

| Measure | Result |
| --- | --- |
| Claim | What does the first resolution of a singleton cost, before anything is cached? |
| Status | absolute-failure |
| Noise allowance | 4.3% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +5.559 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | equivalent | matches the singleton or transient provider lifecycle and construction shape | 5.698 µs | 5.857 µs | [+1.46%, +3.72%] | [+1.97%, +6.15%] | [-16.19%, +18.66%] |
| dishka-1.10.1 | incomparable | Dishka does not expose the depin provider operation this workload measures | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup does not expose the depin provider operation this workload measures | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs does not expose the depin provider operation this workload measures | — | — | — | — | — |

## resolve_a_sync_resource_with_teardown

| Measure | Result |
| --- | --- |
| Claim | What does one resource with a teardown cost, from open to drain? |
| Status | no-equivalent-competitor |
| Noise allowance | 4.5% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +14.175 µs |
| Absolute target | 3.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector async and resource providers have different resolution and teardown semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka async and resource providers have different resolution and teardown semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup async and resource providers have different resolution and teardown semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs async factories and cleanup do not share depin resolution and teardown semantics | — | — | — | — | — |

## warmup_a_cold_singleton_graph

| Measure | Result |
| --- | --- |
| Claim | What does building every singleton in a graph cost at startup? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.8% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +11.748 ms |
| Absolute target | 500.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector has no separate frozen resolution plan or depin graph diagnostics operation | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka has no separate frozen resolution plan or depin graph diagnostics operation | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup has no separate frozen resolution plan or depin graph diagnostics operation | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no separate frozen resolution plan or depin graph diagnostics operation | — | — | — | — | — |

## open_a_request_shaped_scope

| Measure | Result |
| --- | --- |
| Claim | What does one request cost an integration that opens a scope, seeds it, and resolves? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.0% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +25.847 µs |
| Absolute target | 3.500 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | provider overrides are substitutions, not nested scope frames with scoped caches | — | — | — | — | — |
| dishka-1.10.1 | incomparable | Dishka does not expose the depin provider operation this workload measures | — | — | — | — | — |
| wireup-2.12.0 | incomparable | Wireup does not expose the depin provider operation this workload measures | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs containers have no nested scope frames with scoped caches | — | — | — | — | — |

## fastapi_cpu_light_endpoint

| Measure | Result |
| --- | --- |
| Claim | On the cheapest possible endpoint, how much of a request does depin account for? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.5% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +81.555 µs |
| Absolute target | 12.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — | — | — |

## fastapi_request_scoped_graph

| Measure | Result |
| --- | --- |
| Claim | What does a request-scoped service graph cost inside a real request? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.8% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +122.907 µs |
| Absolute target | 16.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | provider overrides are substitutions, not nested scope frames with scoped caches | — | — | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — | — | — |

## fastapi_singletons_and_transients

| Measure | Result |
| --- | --- |
| Claim | What does mixing cached singletons with transient request services cost? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.6% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +95.159 µs |
| Absolute target | 16.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — | — | — |

## fastapi_async_resource_teardown

| Measure | Result |
| --- | --- |
| Claim | What does an async resource with deterministic teardown cost inside a request? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.6% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +139.588 µs |
| Absolute target | 18.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — | — | — |

## fastapi_endpoint_with_work

| Measure | Result |
| --- | --- |
| Claim | At what amount of application work does the resolution cost stop mattering? |
| Status | no-equivalent-competitor |
| Noise allowance | 0.8% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +133.365 µs |
| Absolute target | 12.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — | — | — |

## fastapi_application_startup

| Measure | Result |
| --- | --- |
| Claim | What does wiring the application through depin add to process startup? |
| Status | no-equivalent-competitor |
| Noise allowance | 0.8% |
| Material p50 margin | 25.0% |
| Material p95/p99 margin | 20.0% |
| Direct overhead | +913.036 µs |
| Absolute target | 30.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | p50 95% CI vs depin | p95 95% CI vs depin | p99 95% CI vs depin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — | — | — |
| svcs-26.2.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — | — | — |

## Provenance

| Property | Value |
| --- | --- |
| Source revision | 4ea1475bd0110b2b7824431d80672eda10059fba |
| Harness revision | 4ea1475bd0110b2b7824431d80672eda10059fba |
| Dependency versions | dependency-injector 4.49.1, dishka 1.10.1, pydepin 0.18.0, svcs 26.2.0, wireup 2.12.0 |
| Host | Linux x86_64 Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| Collection command | python -m pytest benchmarks/test_comparison.py --benchmark-only -q --benchmark-json={report} |
