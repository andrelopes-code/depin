# Competitive rebaseline and performance direction

Date: 2026-09-09  
Subject: `main` at `7207179`, measured through harness-only commits ending at
`25d48bc`  
Baseline revision: `4ad63e77bd21eefab15f1dde44c7e62460533da7`

## Method

The competitive run used five counterbalanced repetitions on one host and one
locked process environment. Its accepted pins are Dependency Injector 4.49.1,
Dishka 1.10.1, Wireup 2.12.0, svcs 26.2.0, and pydepin 0.18.0. The null run,
calibration, real run, and generated harness report are retained beside this
file. Candidate numbers count only when the adapter declared equivalent
lifetime, construction, cache, scope, teardown, async, override, and concurrency
semantics before timing.

The base/head run used the same host and five alternating independent processes.
It compares the accepted pre-compiled-runtime baseline with current `main`; it is
diagnostic evidence, not a substitute for competitors. The contention experiment
uses 200 counterbalanced waves of eight persistent worker threads. Barriers and
events force first-use contention without sleeps, and every wave validates
single-flight identity or per-request scope isolation before accepting its time.

## Competitive position

Times are the median across the five repetition-level percentiles. Ratios below
one favor `depin`.

| Workload | depin p50/p95/p99 | Fastest equivalent p50/p95/p99 | Ratio p50/p95/p99 | Classification |
| --- | ---: | ---: | ---: | --- |
| Warm cached singleton | 1.876/1.933/2.323 us | Dependency Injector 0.149/0.153/0.459 us | 12.553/12.661/5.057 | Gap attackable in Python |
| Transient chain | 4.566/4.685/15.177 us | Dishka 7.130/7.836/22.852 us | 0.640/0.598/0.664 | Competitive, no clear leadership |
| Cold singleton construction | 5.857/6.188/19.017 us | Dependency Injector 5.698/5.878/18.005 us | 1.028/1.053/1.056 | Competitive, no clear leadership |
| Enter, build, and close scoped graph | 193.141/283.507/369.969 us | Wireup 9.663/20.092/135.374 us | 19.988/14.110/2.733 | Gap attackable in Python |

The transient chain clears a material 25% margin in all three point estimates,
but the p99 95% confidence interval against Dishka is -58.27% to -7.45%. It does
not prove the required 20% tail margin and is therefore competitive without clear
leadership. No equivalent core workload currently proves leadership. Wireup is
pure Python and is 6.6 times faster on the warm p50 and 20 times faster on the
scope-cycle p50, so those gaps are not evidence that native code is necessary.

svcs remains partial for the warm cache: its per-container cache does not provide
the singleton single-flight and nested-lifetime contract. Its number cannot
establish leadership or defeat.

## Other measured dimensions

| Dimension | Current result | Interpretation |
| --- | --- | --- |
| Request-shaped scope entry/use/close | 26.720/40.252/55.171 us p50/p95/p99 | No equivalent external adapter; large direct-Python increment remains. |
| Sync resource resolution and teardown | 15.742/18.264/32.263 us | No equivalent adapter; current main is 21.72% slower than the accepted base and the gate is inconclusive. |
| Async singleton | 17.274/24.557/42.382 us | 3.632 us p50 above direct event-loop work; external resource semantics differ. |
| Override inactive/active | 1.865/1.930/2.284 us and 3.999/4.091/9.277 us | Context-local semantics have no eligible external equivalent; nesting growth remains inside its gate. |
| FastAPI CPU-light total | 525.6/710.5/930.5 us | Direct route p50 is 464.9 us; DI-attributable p50 is 60.7 us. Independent tail subtraction is not treated as attribution. |
| FastAPI async resource total | 614.3/919.3/1352.7 us | DI-attributable p50 is 150.6 us. |
| FastAPI request-scoped total | 592.4/1154.7/2570.2 us | DI-attributable p50 is 134.1 us. |
| FastAPI startup total | 2.693/4.741/6.199 ms | Direct startup p50 is 1.717 ms; DI-attributable p50 is 0.976 ms. |
| Freeze plain chain, 10/100/1,000 | 0.397/3.765/36.953 ms p50 | Approximately linear; 1,000-provider p95/p99 are 38.470/112.453 ms. |
| Freeze decorated 1,000 | 94.326/266.275/266.938 ms | No external semantic equivalent; retained as a declaration/startup guard. |
| Freeze generic-key 1,000 | 87.827/90.902/210.829 ms | No external semantic equivalent; retained as a declaration/startup guard. |
| Warm 1,000 cold singletons | 11.915/12.859/174.507 ms | p50 is 1.94% better than the accepted base; the long p99 remains diagnostic. |

FastAPI p95 and p99 totals are published, but percentile subtraction between
independent distributions is not DI attribution. Future gates pair the per-request
increment or compare total routes directly under the same counterbalanced order.

## Calls, allocations, and memory

The compiled transient program reduced its deterministic Python calls from 202
to 28, allocated bytes from 4,968 to 1,224, and peak bytes from 5,752 to 2,008.
That is the causal evidence behind the competitive transient win.

| Operation | Python calls | Blocks / bytes / peak |
| --- | ---: | ---: |
| Warm cached singleton | 8 | 13 / 1,168 / 2,056 |
| Request-shaped scope | 88 | 27 / 2,360 / 4,480 |
| Scoped cycle | 358 | 75 / 6,176 / 14,552 |
| Transient chain | 28 | 12 / 1,224 / 2,008 |
| Inject call | 28 | 17 / 1,360 / 2,064 |

Retained memory is 35,032 bytes for 100 frozen providers, 326,776 bytes for
1,000 frozen providers, 397,560 bytes for 1,000 warmed singletons, and 10,624
bytes for one open 20-provider scope. The changes against the accepted base are
+1.34%, +0.24%, 0.00%, and +1.07%; every retained-memory gate passes. Every
allocation, call-count, and scaling gate also passes.

## Contention

| Eight-worker wave | depin p50/p95/p99 | Direct p50/p95/p99 | depin overhead p50/p95/p99 |
| --- | ---: | ---: | ---: |
| Warm cached singleton | 593/2,043/3,685 us | 550/1,319/2,897 us | 43/724/787 us |
| Singleton first use | 1,524/4,996/7,504 us | 1,021/3,920/5,477 us | 503/1,077/2,027 us |
| Independent request scopes | 1,166/3,491/4,515 us | 712/2,239/3,782 us | 454/1,252/733 us |

These totals include deliberately equivalent thread scheduling and
synchronization. The paired increment is the DI-attributable reading. The p95
cost is material, but the experiment does not isolate a native-resident segment:
thread wake-up, Python providers, `ContextVar` state, and native/Python crossings
would remain.

## Exhaustive workload classification

Each timed or deterministic workload belongs to exactly one category. Names on
one row share the stated classification; diagnostic metrics are named explicitly
rather than silently omitted.

| Classification | Workloads |
| --- | --- |
| Proven leadership | None. |
| Competitive, no clear leadership | `resolve_a_transient_chain`; `construct_a_singleton_for_the_first_time` (its competitive timing still fails the absolute direct-overhead target) |
| Gap attackable in Python | `resolve_cached_singleton`; `open_and_close_a_scope`; `open_a_request_shaped_scope`; `resolve_cached_singleton_through_an_alias`; `resolve_singleton_through_a_two_deep_decoration_chain`; `resolve_a_collection_of_10`; `resolve_a_collection_of_100`; `resolve_a_generic_key`; `call_through_an_inject_wrapper`; `call_through_an_inject_wrapper_with_explicit_arguments`; `resolve_a_sync_resource_with_teardown`; `resolve_an_async_singleton`; `resolve_with_no_active_override`; `resolve_through_an_active_override`; `warmup_a_cold_singleton_graph`; `explain_an_unbound_key_of_16`; `explain_an_unbound_key_of_20`; `freeze_a_chain_missing_a_provider_of_50`; `freeze_a_chain_missing_a_provider_of_100`; contention profiles `cached_singleton`, `singleton_first_use`, and `request_scopes` |
| Candidate for native execution | None. The entry threshold is not met. |
| FastAPI integration overhead | `fastapi_application_startup`; `fastapi_async_resource_teardown`; `fastapi_cpu_light_endpoint`; `fastapi_endpoint_with_work`; `fastapi_request_scoped_graph`; `fastapi_singletons_and_transients` |
| Incomparable because semantics differ | `build_the_graph_view`; `explain_a_deep_chain`; `explain_a_deep_chain_with_every_node_decorated`; `explain_a_layered_dag`; `export_a_large_graph_as_dot`; all nine valid-freeze workloads at 10/100/1,000 providers; work/allocation diagnostics for cache, request scope, scope cycle, transient chain, and inject; retained-memory diagnostics for frozen 100/1,000, warm cache 1,000, and open scope 20; scaling curves for async teardown, freeze, override nesting, collection, fan-out, transient depth, and scope teardown |

The base/head latency gate exposes three real current-main regressions that this
rebaseline does not hide or fix: `explain_an_unbound_key_of_16` (+59.43%),
`explain_an_unbound_key_of_20` (+61.53%), and
`freeze_a_chain_missing_a_provider_of_50` (+46.37%). The size-100 failing freeze,
plain freeze 100, cold singleton, and sync resource teardown are inconclusive at
five repetitions. This session deliberately records them instead of implementing
another runtime optimization.

## Direction

The next performance proposal is the FastAPI minimum-overhead proposal, limited
to endpoint compilation and lazy request scope. Compiled resolution is complete;
provider discovery is not a response to any measured runtime gap; native remains
NO-GO. A native experiment may be reconsidered only after the FastAPI result and
only if profiles attribute a qualifying residual to an end-to-end execution
program that can remain native across multiple providers.
