# Comparative performance evidence

## resolve_cached_singleton

| Measure | Result |
| --- | --- |
| Claim | What does one resolution cost once the value is already built? |
| Status | loss |
| Noise allowance | 1.5% |
| Direct overhead | +1.646 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | equivalent | matches the singleton or transient provider lifecycle and construction shape | 139.751 ns | 1.736 µs | [+1105.05%, +1187.36%] |
| dishka-1.10.1 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 866.014 ns | 1.736 µs | [+95.31%, +108.89%] |
| wireup-2.12.0 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 262.901 ns | 1.736 µs | [+548.49%, +560.57%] |
| svcs-26.1.0 | partial | per-container caching has no singleton single-flight guarantee or nested lifetime contract | — | — | — |

## resolve_cached_singleton_through_an_alias

| Measure | Result |
| --- | --- |
| Claim | What does a second name for a binding add to a resolution? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.1% |
| Direct overhead | +3.421 µs |
| Absolute target | 1.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector delegates do not provide depin typed-key alias resolution | — | — | — |
| dishka-1.10.1 | incomparable | Dishka alias resolution does not demonstrate depin typed-key alias cache semantics | — | — | — |
| wireup-2.12.0 | incomparable | Wireup alias resolution does not demonstrate depin typed-key alias cache semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no depin typed-key alias resolution | — | — | — |

## resolve_singleton_through_a_two_deep_decoration_chain

| Measure | Result |
| --- | --- |
| Claim | What do two stacked decorators add to a resolution? |
| Status | no-equivalent-competitor |
| Noise allowance | 4.3% |
| Direct overhead | +1.640 µs |
| Absolute target | 1.500 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector provider composition does not model depin decoration chains | — | — | — |
| dishka-1.10.1 | incomparable | Dishka provider composition does not model depin decoration chains | — | — | — |
| wireup-2.12.0 | incomparable | Wireup provider composition does not model depin decoration chains | — | — | — |
| svcs-26.1.0 | incomparable | svcs registrations do not model depin decoration chains | — | — | — |

## resolve_a_collection_of_10

| Measure | Result |
| --- | --- |
| Claim | What does gathering a multi-binding into a list cost, by member count? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.7% |
| Direct overhead | +17.276 µs |
| Absolute target | 5.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector has no depin collection binding and aggregation operation | — | — | — |
| dishka-1.10.1 | incomparable | Dishka has no depin collection binding and aggregation operation | — | — | — |
| wireup-2.12.0 | incomparable | Wireup has no depin collection binding and aggregation operation | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no depin collection binding and aggregation operation | — | — | — |

## resolve_a_collection_of_100

| Measure | Result |
| --- | --- |
| Claim | What does gathering a multi-binding into a list cost, by member count? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.9% |
| Direct overhead | +130.562 µs |
| Absolute target | 50.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector has no depin collection binding and aggregation operation | — | — | — |
| dishka-1.10.1 | incomparable | Dishka has no depin collection binding and aggregation operation | — | — | — |
| wireup-2.12.0 | incomparable | Wireup has no depin collection binding and aggregation operation | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no depin collection binding and aggregation operation | — | — | — |

## resolve_a_transient_chain

| Measure | Result |
| --- | --- |
| Claim | What does depin add to constructing a dependency chain that is never cached? |
| Status | loss |
| Noise allowance | 1.1% |
| Direct overhead | +31.538 µs |
| Absolute target | 10.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | equivalent | matches the singleton or transient provider lifecycle and construction shape | 16.299 µs | 33.620 µs | [+88.04%, +113.94%] |
| dishka-1.10.1 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 7.065 µs | 33.620 µs | [+351.94%, +404.59%] |
| wireup-2.12.0 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 7.283 µs | 33.620 µs | [+338.72%, +379.63%] |
| svcs-26.1.0 | incomparable | svcs does not expose the depin provider operation this workload measures | — | — | — |

## open_and_close_a_scope

| Measure | Result |
| --- | --- |
| Claim | What does one scope cost, from entry to teardown? |
| Status | loss |
| Noise allowance | 2.3% |
| Direct overhead | +315.515 µs |
| Absolute target | 12.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | provider overrides are substitutions, not nested scope frames with scoped caches | — | — | — |
| dishka-1.10.1 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 10.369 µs | 318.499 µs | [+2924.54%, +3378.09%] |
| wireup-2.12.0 | equivalent | matches the singleton, transient, or request-scoped provider lifecycle and construction shape | 9.386 µs | 318.499 µs | [+3185.47%, +3417.89%] |
| svcs-26.1.0 | incomparable | svcs containers have no nested scope frames with scoped caches | — | — | — |

## call_through_an_inject_wrapper

| Measure | Result |
| --- | --- |
| Claim | What does calling a function whose dependency depin supplies cost? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.6% |
| Direct overhead | +5.317 µs |
| Absolute target | 1.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector wiring does not share depin injection wrapper calling semantics | — | — | — |
| dishka-1.10.1 | incomparable | Dishka injection does not share depin injection wrapper calling semantics | — | — | — |
| wireup-2.12.0 | incomparable | Wireup injection does not share depin injection wrapper calling semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no depin injection wrapper calling semantics | — | — | — |

## call_through_an_inject_wrapper_with_explicit_arguments

| Measure | Result |
| --- | --- |
| Claim | What does an argument the caller supplies add to an injected call? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.2% |
| Direct overhead | +6.362 µs |
| Absolute target | 1.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector wiring does not share depin injection wrapper calling semantics | — | — | — |
| dishka-1.10.1 | incomparable | Dishka injection does not share depin injection wrapper calling semantics | — | — | — |
| wireup-2.12.0 | incomparable | Wireup injection does not share depin injection wrapper calling semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no depin injection wrapper calling semantics | — | — | — |

## resolve_an_async_singleton

| Measure | Result |
| --- | --- |
| Claim | What does depin add to driving one coroutine through an event loop? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.7% |
| Direct overhead | +3.345 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector async and resource providers have different resolution and teardown semantics | — | — | — |
| dishka-1.10.1 | incomparable | Dishka async and resource providers have different resolution and teardown semantics | — | — | — |
| wireup-2.12.0 | incomparable | Wireup async and resource providers have different resolution and teardown semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs async factories and cleanup do not share depin resolution and teardown semantics | — | — | — |

## resolve_with_no_active_override

| Measure | Result |
| --- | --- |
| Claim | What does the override check cost on a resolution nothing has overridden? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.3% |
| Direct overhead | +1.610 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector provider overrides are not depin context-local override frames | — | — | — |
| dishka-1.10.1 | incomparable | Dishka provider substitution is not a depin context-local override frame | — | — | — |
| wireup-2.12.0 | incomparable | Wireup provider substitution is not a depin context-local override frame | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no depin context-local override frames | — | — | — |

## resolve_through_an_active_override

| Measure | Result |
| --- | --- |
| Claim | What does a resolution cost while an override for that key is installed? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.4% |
| Direct overhead | +3.535 µs |
| Absolute target | 1.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector provider overrides are not depin context-local override frames | — | — | — |
| dishka-1.10.1 | incomparable | Dishka provider substitution is not a depin context-local override frame | — | — | — |
| wireup-2.12.0 | incomparable | Wireup provider substitution is not a depin context-local override frame | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no depin context-local override frames | — | — | — |

## resolve_a_generic_key

| Measure | Result |
| --- | --- |
| Claim | What does a parameterised generic key cost at resolution time? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.2% |
| Direct overhead | +5.563 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector providers are not resolved from depin parameterised generic keys | — | — | — |
| dishka-1.10.1 | incomparable | Dishka providers are not resolved from depin parameterised generic keys | — | — | — |
| wireup-2.12.0 | incomparable | Wireup providers are not resolved from depin parameterised generic keys | — | — | — |
| svcs-26.1.0 | incomparable | svcs services are not resolved from depin parameterised generic keys | — | — | — |

## construct_a_singleton_for_the_first_time

| Measure | Result |
| --- | --- |
| Claim | What does the first resolution of a singleton cost, before anything is cached? |
| Status | absolute-failure |
| Noise allowance | 2.0% |
| Direct overhead | +4.951 µs |
| Absolute target | 500.000 ns |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | equivalent | matches the singleton or transient provider lifecycle and construction shape | 5.312 µs | 5.228 µs | [-7.44%, +0.72%] |
| dishka-1.10.1 | incomparable | Dishka does not expose the depin provider operation this workload measures | — | — | — |
| wireup-2.12.0 | incomparable | Wireup does not expose the depin provider operation this workload measures | — | — | — |
| svcs-26.1.0 | incomparable | svcs does not expose the depin provider operation this workload measures | — | — | — |

## resolve_a_sync_resource_with_teardown

| Measure | Result |
| --- | --- |
| Claim | What does one resource with a teardown cost, from open to drain? |
| Status | no-equivalent-competitor |
| Noise allowance | 3.0% |
| Direct overhead | +11.393 µs |
| Absolute target | 3.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector async and resource providers have different resolution and teardown semantics | — | — | — |
| dishka-1.10.1 | incomparable | Dishka async and resource providers have different resolution and teardown semantics | — | — | — |
| wireup-2.12.0 | incomparable | Wireup async and resource providers have different resolution and teardown semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs async factories and cleanup do not share depin resolution and teardown semantics | — | — | — |

## warmup_a_cold_singleton_graph

| Measure | Result |
| --- | --- |
| Claim | What does building every singleton in a graph cost at startup? |
| Status | no-equivalent-competitor |
| Noise allowance | 0.7% |
| Direct overhead | +11.163 ms |
| Absolute target | 500.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | Dependency Injector has no separate frozen resolution plan or depin graph diagnostics operation | — | — | — |
| dishka-1.10.1 | incomparable | Dishka has no separate frozen resolution plan or depin graph diagnostics operation | — | — | — |
| wireup-2.12.0 | incomparable | Wireup has no separate frozen resolution plan or depin graph diagnostics operation | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no separate frozen resolution plan or depin graph diagnostics operation | — | — | — |

## open_a_request_shaped_scope

| Measure | Result |
| --- | --- |
| Claim | What does one request cost an integration that opens a scope, seeds it, and resolves? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.5% |
| Direct overhead | +25.442 µs |
| Absolute target | 3.500 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | provider overrides are substitutions, not nested scope frames with scoped caches | — | — | — |
| dishka-1.10.1 | incomparable | Dishka does not expose the depin provider operation this workload measures | — | — | — |
| wireup-2.12.0 | incomparable | Wireup does not expose the depin provider operation this workload measures | — | — | — |
| svcs-26.1.0 | incomparable | svcs containers have no nested scope frames with scoped caches | — | — | — |

## fastapi_cpu_light_endpoint

| Measure | Result |
| --- | --- |
| Claim | On the cheapest possible endpoint, how much of a request does depin account for? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.1% |
| Direct overhead | +74.590 µs |
| Absolute target | 12.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — |

## fastapi_request_scoped_graph

| Measure | Result |
| --- | --- |
| Claim | What does a request-scoped service graph cost inside a real request? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.9% |
| Direct overhead | +112.301 µs |
| Absolute target | 16.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | provider overrides are substitutions, not nested scope frames with scoped caches | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — |

## fastapi_singletons_and_transients

| Measure | Result |
| --- | --- |
| Claim | What does mixing cached singletons with transient request services cost? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.5% |
| Direct overhead | +81.266 µs |
| Absolute target | 16.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — |

## fastapi_async_resource_teardown

| Measure | Result |
| --- | --- |
| Claim | What does an async resource with deterministic teardown cost inside a request? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.7% |
| Direct overhead | +116.657 µs |
| Absolute target | 18.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — |

## fastapi_endpoint_with_work

| Measure | Result |
| --- | --- |
| Claim | At what amount of application work does the resolution cost stop mattering? |
| Status | no-equivalent-competitor |
| Noise allowance | 1.8% |
| Direct overhead | +110.258 µs |
| Absolute target | 12.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — |

## fastapi_application_startup

| Measure | Result |
| --- | --- |
| Claim | What does wiring the application through depin add to process startup? |
| Status | no-equivalent-competitor |
| Noise allowance | 2.2% |
| Direct overhead | +792.477 µs |
| Absolute target | 30.000 µs |
| Secondary verdict | — |

| Candidate | Classification | Reason | Candidate median | depin median | 95% CI vs depin |
| --- | --- | --- | --- | --- | --- |
| dependency-injector-4.49.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| dishka-1.10.1 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| wireup-2.12.0 | incomparable | the FastAPI integration has different request lifecycle and dependency declaration semantics | — | — | — |
| svcs-26.1.0 | incomparable | svcs has no FastAPI integration with depin request lifecycle and declaration semantics | — | — | — |

## Provenance

| Property | Value |
| --- | --- |
| Source revision | cd225b2e0250d8fce6e42975ebcf226a184b6389 |
| Harness revision | cd225b2e0250d8fce6e42975ebcf226a184b6389 |
| Dependency versions | dependency-injector 4.49.1, dishka 1.10.1, pydepin 0.17.1, svcs 26.1.0, wireup 2.12.0 |
| Host | Linux x86_64 Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| Collection command | python -m pytest benchmarks/test_comparison.py --benchmark-only -q --benchmark-json={report} |
