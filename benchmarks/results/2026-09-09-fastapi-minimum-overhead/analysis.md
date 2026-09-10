# FastAPI minimum-overhead analysis

Measured runtime/workload revision: `bb10ef98d8d46b41563d2b6e42ee903b35d53fba`.
Evidence-harness revision: `5c1a00d`; later commits changed evidence validation
and projection only, not `depin` or measured workloads.

The paired CPU-light DI-attributable p50 change is **-49.84%**, with a 95%
bootstrap interval of **[-55.56%, -44.11%]**. The upper-bound <= -25%
acceptance objective passes, as does the <= -30% point target.

Allocation (-2.63%), retained memory (-0.38%), peak memory (-8.48%), work,
no-injection (+2.55%), and all six component observations pass their stated
checks. Generic p50 latency gates pass except startup, which is inconclusive at
+9.19% [+3.80%, +11.16%] against +6% under the generic lower-bound rule.

The dedicated evaluator exits 3 and is retained as **INCONCLUSIVE**, not PASS:
there are 0 proven required regressions under the parent adjudication. Fifteen
tail/startup/contention criteria remain inconclusive. Their point estimates
include startup p50 +9.19% (median direct/depin difference-of-differences
+221.3 us), startup p95 +23.31%, startup p99 +15.29%, CPU-light p99 +23.65%,
request-scoped p95 +7.98%, request-scoped p99 +27.00%, and contention +6.85%.
The raw paired bootstrap analysis records direct and depin controls separately;
tail and contention intervals are broad and do not establish attribution.

See `evidence-bridge-bb10/failed-criteria-analysis.json` for every repetition,
bootstrap interval, selector, and absolute delta. The v4 raw reports are under
`raw-v4-bb10/`; provenance annotations are under `evidence-bridge-bb10/`.

## Competitor evidence

Competitive evidence was collected from clean external sources and locked
external environments. The immutable archive baseline is
`086adf98459773e3175f4723b2b64e3f47306e42`; the clean candidate source used
for this packaging-only comparison is
`4f798bec90b5222427254a659052a94b511c3e00`. The latter is not claimed as the
measured FastAPI runtime/workload revision.

Leadership classifies `resolve_a_transient_chain` as competitive,
`construct_a_singleton_for_the_first_time` and `open_and_close_a_scope` as
losses, and `fastapi_async_resource_teardown` as unstable. All remaining
reported workloads have no equivalent competitor. The null calibration, real
collection, archive-validation provenance, and evaluator output are retained
under `comparison-bb10/`. The earlier missing-marker failure is retained there
as `initial-marker-blocker.txt` for diagnosis only.
