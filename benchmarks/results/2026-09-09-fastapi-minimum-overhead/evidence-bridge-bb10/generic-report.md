# Measured results

## Environment

| Property | Value |
| --- | --- |
| bootstrap.inner | {'bytecode': 'disabled', 'hash_seed': '0', 'pythonpath': 'removed', 'user_site': 'disabled'} |
| bootstrap.outer | isolated-python-I |
| distributions.pydepin | 0.19.0 |
| distributions.pytest | 9.1.1 |
| distributions.pytest-benchmark | 5.3.0 |
| host.available_processors | 4 |
| host.cpu_model | Intel(R) Xeon(R) CPU E5-2683 v4 @ 2.10GHz |
| host.load_average | 6.81, 3.61, 2.7 |
| host.machine | x86_64 |
| host.processor | x86_64 |
| host.processors | 4 |
| host.release | 6.8.0-138-generic |
| host.system | Linux |
| interpreter.compiler | Clang 22.1.3  |
| interpreter.free_threading | no |
| interpreter.hash_randomization | no |
| interpreter.implementation | CPython |
| interpreter.recursion_limit | 1000 |
| interpreter.version | 3.12.13 |

## Latency

| Workload | Repetitions | Rounds | Median | Spread across repetitions |
| --- | --- | --- | --- | --- |
| fastapi_application_startup | 5 | 813 | 2.712 ms | 8.1% |
| fastapi_async_resource_teardown | 5 | 1073 | 736.987 µs | 5.2% |
| fastapi_cpu_light_endpoint | 5 | 1347 | 669.909 µs | 6.7% |
| fastapi_endpoint_with_work | 5 | 1000 | 939.706 µs | 9.6% |
| fastapi_request_scoped_graph | 5 | 1331 | 725.566 µs | 6.1% |
| fastapi_singletons_and_transients | 5 | 1368 | 681.563 µs | 10.0% |

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
