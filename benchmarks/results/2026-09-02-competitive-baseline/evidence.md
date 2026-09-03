# Competitive performance baseline evidence

The accepted comparison dataset is `comparison.json`; the matching null
calibration is `calibration.json`. Both were collected from source revision
`56c7dc1493565ab67a772c52ab28298a074c975d` against archived baseline
`4ad63e77bd21eefab15f1dde44c7e62460533da7`. The dataset records five installed
pins, five qualified repetitions, and the budget digest
`8142bcee8b717d86184c7c6daff05d5b521a26d0850d0d6f94c848d08cd17a6b`.

The null command used `--null --repetitions 5 --timeout-seconds 1500`; the real
command used `--repetitions 5 --timeout-seconds 4500`. Both used the archived
baseline, `benchmarks/budgets.toml`, and the locked comparison shell. The raw
temporary sources remain at `/tmp/tmp.UlAiP8fmyT/null` and
`/tmp/tmp.UlAiP8fmyT/real` for this execution.

The evaluator reported losses for `open_and_close_a_scope`,
`resolve_a_transient_chain`, and `resolve_cached_singleton`; it reported an
absolute failure for `construct_a_singleton_for_the_first_time`; it reported no
regressions or unstable workloads. Nineteen workloads had no equivalent
competitor. These per-workload outcomes are not an aggregate ranking.

Equivalence classifications are recorded beside every candidate in the dataset.
Only candidates classified as equivalent participate in leadership decisions;
direct Python remains present for the absolute-overhead decision.

Bounded profiles completed with exit status zero for the preliminary core gaps
`resolve_cached_singleton`, `resolve_a_transient_chain`, and
`open_and_close_a_scope`, and for `fastapi_cpu_light_endpoint`. Their raw reports
are `/tmp/task12-profile-cached.txt`, `/tmp/task12-profile-transient.txt`,
`/tmp/task12-profile-scope.txt`, and `/tmp/task12-profile-fastapi.txt`.

The follow-up owners remain the compiled-resolution runtime proposal, the
FastAPI minimum-overhead proposal, and the optional native-accelerator proposal.
