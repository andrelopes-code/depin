# FastAPI minimum-overhead evidence report

Status: **INCONCLUSIVE**. The primary CPU-light DI-overhead claim passes:
-49.84% paired p50, 95% CI [-55.56%, -44.11%]. Both the <= -25% confidence
bound and <= -30% point target pass.

The measured revision is `bb10ef98d8d46b41563d2b6e42ee903b35d53fba`.
`5c1a00d` is an evidence-harness revision only and was not measured as runtime
or workload code.

Dedicated acceptance exit 3 is retained as INCONCLUSIVE. It is not relabeled
PASS and it establishes no proven required regression under the adjudication.
Fifteen tail/startup/contention observations remain inconclusive; their complete
raw controls, bootstrap intervals, and difference-of-differences are preserved
in `evidence-bridge-bb10/failed-criteria-analysis.json`.

Generic gate: all non-startup p50 latency workloads pass; startup is
inconclusive (+9.19% [+3.80%, +11.16%], budget +6%). Memory, allocation, work,
no-injection, and component evidence are retained in the sidecars and bridge.

Competitor/leadership evidence was measured using an immutable external archive
baseline at `086adf98459773e3175f4723b2b64e3f47306e42`, a clean detached
candidate source at `4f798bec90b5222427254a659052a94b511c3e00`, and external
locked environment/cache paths. The candidate revision packages evidence only;
it is not claimed as the measured FastAPI runtime/workload revision.

Leadership reports `resolve_a_transient_chain` as competitive;
`construct_a_singleton_for_the_first_time` and `open_and_close_a_scope` as
losses; `fastapi_async_resource_teardown` as unstable; and no equivalent
competitor for every other reported workload. The raw null and real
collections, calibration, archive provenance, and evaluator result are in
`comparison-bb10/`. The prior missing-marker attempt is retained as
`comparison-bb10/initial-marker-blocker.txt` rather than treated as the final
collection result.
