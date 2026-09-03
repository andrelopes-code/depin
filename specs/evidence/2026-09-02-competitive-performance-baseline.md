# Competitive performance baseline evidence

The accepted v3 artifacts are
`benchmarks/results/2026-09-02-competitive-baseline/comparison.json` and
`benchmarks/results/2026-09-02-competitive-baseline/calibration.json`. They are
the only published dataset and calibration for this baseline. The generated
rendering is `docs/performance/comparison-baseline.md`; it makes no aggregate
ranking claim.

## Collection identity and protocol

Both source and harness revision are
`cd225b2e0250d8fce6e42975ebcf226a184b6389`. The archived baseline revision is
`4ad63e77bd21eefab15f1dde44c7e62460533da7`; its marker was checked before the
collector's archive preflight. The final publication revision is deliberately
later than the measured source revision.

The comparison and calibration have schema version 1. Calibration provenance
version 1 records the canonical null JSON digest and protocol fingerprint
`643844979a968bf143d3686a5f53bd842e0f71295e8f6f4873dbfd9116579405`.
The real dataset matches that fingerprint. The pinned CPU run records
`environment.host.available_processors = 1` (CPU 0), and all five repetitions
were accepted and qualified.

The exact installed pins are Dependency Injector 4.49.1, Dishka 1.10.1,
pydepin 0.17.1, svcs 26.1.0, and Wireup 2.12.0. The null dataset contains five
repetitions of 46 direct/depin target IDs; the real dataset contains five
repetitions of 56 target IDs, including implemented candidates.

The null command was `taskset -c 0 timeout 1560s python -m
benchmarks.harness.comparison collect --null --repetitions 5
--timeout-seconds 1500 --out /tmp/task12-v3.l6PIqv/null-pinned --baseline-dir
/tmp/task12-v3.l6PIqv/baseline --baseline-revision
4ad63e77bd21eefab15f1dde44c7e62460533da7 --budgets benchmarks/budgets.toml`.
Its supervised status file is 0. Calibration was written atomically to
`/tmp/task12-v3.l6PIqv/calibration-pinned.json` with status 0. The real command
was the same protocol without `--null`, with `--timeout-seconds 4500`, external
timeout 4560 seconds, and output `/tmp/task12-v3.l6PIqv/real-pinned`; its status
file is 0. The full real evaluator command used that comparison JSON, the
pinned calibration, and `benchmarks/budgets.toml`; it exited 1 for measured
failures, not malformed or unstable evidence.

## Measured outcomes and owners

The evaluator reports competitive losses for `resolve_cached_singleton`,
`resolve_a_transient_chain`, and `open_and_close_a_scope`; all three belong to
the compiled-resolution proposal. It reports an absolute failure for
`construct_a_singleton_for_the_first_time`, which is followed by the leadership
proposal. There are no regressions and no unstable workloads. The FastAPI
minimum-overhead proposal owns the FastAPI residuals, which have no equivalent
competitor in this dataset. No result is aggregated across workloads.

Raw accepted inputs and evaluator output remain at
`/tmp/task12-v3.l6PIqv/null-pinned/comparison.json`,
`/tmp/task12-v3.l6PIqv/real-pinned/comparison.json`,
`/tmp/task12-v3.l6PIqv/calibration-pinned.json`, and
`/tmp/task12-v3.l6PIqv/real-pinned.evaluate.{out,err,status}`.

## Seed proof

The final deliberate seed was applied in the temporary clone
`/tmp/task12-seed-v3c.9sWpLf/seed` at temporary commit
`2daaf7ceb82764a0ba44e5ef4c4b4c39048b0a25`. It used the provisioned Python,
`PYTHONPATH` set to that clone, `taskset -c 0`, the v3 baseline and calibration,
and the exact focused workload `resolve_cached_singleton` for five repetitions.
The collector exited 0, produced schema 1 accepted evidence with five sets of
six IDs, and had the same protocol fingerprint. Its focused evaluator exited 3
because all other target rows are absent; the cached workload verdict itself is
`loss`.

The seed median was 1.88406556845 microseconds versus 1.73703301698
microseconds in the valid post-removal v3b dataset at
`/tmp/task12-seed-v3.cPvvkW/removed-result-v2/comparison.json`: an 8.465%
slowdown. Its excess ratio to Dependency Injector was 1238.582677% versus
1118.966236%, a 119.616 percentage-point increase. Both exceed the calibrated
1.5% allowance. The post-removal runtime was byte-identical to the principal
worktree; its focused collector and evaluator exits were 0 and 3, respectively,
and its cached verdict was restored to the original unseeded `loss` by the
evaluator's competitive-loss precedence.
