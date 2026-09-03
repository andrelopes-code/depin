# Competitive performance baseline evidence

The accepted comparison and calibration are
`benchmarks/results/2026-09-02-competitive-baseline/comparison.json` and
`benchmarks/results/2026-09-02-competitive-baseline/calibration.json`.
They were collected at `56c7dc1493565ab67a772c52ab28298a074c975d`; the later
publication commit intentionally does not change that measured revision.

Five qualified repetitions cover every expected comparison case. `accepted` is
true because collection ran from a clean tree; the evaluator treats a sample as
qualified unless its optional `qualified` field is explicitly false. The pins
object records all five installed distributions and their exact versions.

The evaluator found losses for warm cached singleton lookup, transient-chain
resolution, and scope open/close. The compiled-resolution runtime proposal owns
all three core gaps; the optional native-accelerator proposal is a later alternative.
The FastAPI minimum-overhead proposal owns the FastAPI residuals. Singleton cold
construction also failed its absolute target and belongs to compiled resolution.
There is no aggregate performance claim.

The cached-lookup seed evaluated as `loss`; after reverting it, the median fell
3.379% and the Dependency Injector ratio fell 3.820%, exceeding the 2.0%
allowance. Seed collection/evaluation exits were 0/3 and post-removal collection
exit was 0; the focused evaluator's 3 reflects the deliberately absent targets,
while the cached workload itself remained `loss` under competitive precedence.
