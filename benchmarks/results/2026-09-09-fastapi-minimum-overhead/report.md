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

Competitor/leadership collection was not measured. The clean baseline checkout
lacked the required `.depin-baseline-revision` archive marker; the exact command
and error are recorded in `competitor-blocker.txt`.
