# FastAPI minimum-overhead post-release hardening

## Conclusion

The published `v0.20.0` runtime at `57bdea536936a482a358b4d87cff93ccb75272ba`
was compared with the accepted 2026-09-09 `v0.19.0` baseline at
`086adf98459773e3175f4723b2b64e3f47306e42`. After ten counterbalanced pairs,
none of the fifteen disputed criteria proves a formal runtime regression. Two
criteria now pass and thirteen remain statistically inconclusive. The causes
are classified as noise for ten criteria, environment for two, insufficient
sampling for three, and real formal regression for none.

The dedicated gate exits `3` only because required tail/contention criteria
remain inconclusive. The generic p50 gate passes all six FastAPI workloads;
startup passes narrowly at `+5.97%` against its `+6%` budget. The primary
CPU-light DI-attributable objective passes at `-59.47% [-69.81%, -51.20%]`,
clearing both the required `-25%` upper bound and the `-30%` stretch target. No
budget or runtime code was changed.

## Protocol and provenance

- Baseline: published `pydepin 0.19.0`, tag `v0.19.0`, revision `086adf9`.
- Head: published `pydepin 0.20.0`, tag `v0.20.0`, revision `57bdea5`.
- Harness revision used for the retained collection: `e28029a`.
- Ten independent paired repetitions, alternating base-first and head-first,
  with bootstrap seed `20260902`.
- Separate environments synchronized with `uv sync --locked
  --no-default-groups --group bench`; the recorded package set is FastAPI
  `0.141.1`, Starlette `1.6.0`, pytest `9.1.1`, and pytest-benchmark `5.3.0`.
- CPython `3.12.13`, Linux `6.8.0-138-generic`, Intel Xeon E5-2683 v4, affinity
  CPUs `0-3`, and unavailable governor telemetry.
- Load1 ranged from `3.71` to `7.11` in baseline processes and from `3.88` to
  `6.81` in head processes while four CPUs were available.

The normalized collection command and all required arguments are recorded in
[`raw-v4/source-manifest.json`](raw-v4/source-manifest.json). The reducer
validates its entry point, exact option inventory, revisions, target roots,
repetition count, runner SHA-256, and lockfile SHA-256 values. Every envelope's
`benchmark_report.sha256` is checked against the corresponding complete report
retained under [`raw-v4/reports`](raw-v4/reports/).

The retained [`raw-v4`](raw-v4/) envelopes/reports and reduced
[`evidence`](evidence/) bundle were produced directly by the corrected
collector and reducer, without hand-editing or a provenance bridge.

## Classification rule

- **Environment**: the equivalent direct control moved in the same direction
  and comparable magnitude, or was itself too unstable to attribute the depin
  result.
- **Noise**: doubling from five to ten pairs changed direction materially, or
  the pair signs were balanced around a point estimate inside the budget.
- **Insufficient sampling**: a potentially adverse direction persisted, but
  ten pairs still left the confidence interval crossing the budget.
- **Real regression**: the lower confidence bound exceeds the budget without a
  corresponding control movement. No criterion met this rule.

## The fifteen formal criteria

All intervals are 95% paired bootstrap intervals. Direct controls compare the
same FastAPI route without depin across the two published environments.

| Criterion | Formal result | depin change | direct control | Classification | Evidence |
| --- | --- | ---: | ---: | --- | --- |
| CPU-light p95 | inconclusive | -6.64% [-56.38%, +17.32%] | -3.46% [-22.56%, +53.92%] | noise | Only 4/10 pairs increased and both subject and control are centered below zero. |
| CPU-light p99 | inconclusive | -12.40% [-40.07%, +41.98%] | -20.91% [-47.63%, +135.44%] | environment | The direct control moved further in the same direction with substantially wider uncertainty. |
| Request-scoped p95 | inconclusive | -1.60% [-9.50%, +17.62%] | -1.64% [-25.99%, +42.85%] | noise | The five-pair point `+17.62%` reversed after doubling; only 4/10 subject pairs increased. |
| Request-scoped p99 | inconclusive | -5.49% [-25.81%, +21.84%] | -0.39% [-48.51%, +42.64%] | noise | The five-pair point `+21.84%` reversed after doubling and pair signs are near-balanced. |
| Singletons/transients p95 | inconclusive | -1.33% [-16.30%, +15.02%] | -5.03% [-18.52%, +3.23%] | noise | The five-pair point `+10.61%` reversed; signs split 5/5. |
| Singletons/transients p99 | inconclusive | +13.03% [-23.48%, +33.82%] | -6.82% [-46.32%, +13.19%] | insufficient sampling | The adverse point persisted from `+26.78%`, but its lower bound remains well below the budget. |
| Async teardown p95 | pass | -1.41% [-35.27%, +4.61%] | +7.50% [-25.36%, +35.16%] | noise | Doubling resolved the upper bound below `+5%`; only 4/10 subject pairs increased. |
| Async teardown p99 | inconclusive | -1.65% [-33.64%, +41.55%] | +9.18% [-34.80%, +87.99%] | noise | The five-pair point `+28.91%` reversed and signs split 5/5. |
| Endpoint-with-work p95 | inconclusive | +0.61% [-11.81%, +24.35%] | -2.18% [-12.16%, +39.81%] | noise | The five-pair point `+9.73%` contracted inside budget and signs split 5/5. |
| Endpoint-with-work p99 | inconclusive | +25.40% [-9.48%, +47.95%] | -2.39% [-30.18%, +66.90%] | insufficient sampling | The adverse point persisted from `+36.58%`, but ten pairs do not establish its lower bound. |
| Startup p95 | inconclusive | +2.14% [-19.99%, +20.98%] | -4.91% [-30.68%, +15.29%] | noise | The five-pair point `-9.59%` changed direction but remains inside budget; signs are near-balanced. |
| Startup p99 | inconclusive | -0.47% [-20.98%, +72.57%] | +0.58% [-27.37%, +10.83%] | noise | Both points are effectively zero and signs split 5/5 despite broad subject tails. |
| Application startup p50 | inconclusive | +5.97% [+4.33%, +8.89%] | -1.78% [-5.82%, +3.52%] | insufficient sampling | The point is `0.03` percentage points inside budget while the interval straddles `+6%`; the attributable absolute increase is disclosed below. |
| Contention p99 | inconclusive | -23.66% [-70.96%, +35.10%] | +31.85% [-53.91%, +84.55%] | environment | Subject direction reversed when doubled and the direct synchronized-wave control remains highly unstable. |
| No-injection p50 | pass | +2.57% [+2.02%, +3.29%] | head-only null control | noise | Doubling bounds the small head-only effect safely below the `+5%` allowance; the prior inconclusivity was sampling noise around an acceptable effect. |

## Startup margin

Generic startup p50 passes by only `0.03` percentage points, while the dedicated
confidence-bound rule remains inconclusive. The direct path is stable at
`-1.78% [-5.82%, +3.52%]`, and the absolute p50
difference-of-differences is `+153.3 µs [+141.5, +212.1 µs]`. Minimum startup
confirms the floor: depin moved `+7.96% [+5.86%, +9.45%]`, direct moved `-1.88%
[-5.11%, +2.99%]`, and their difference-of-differences is `+195.3 µs [+169.3,
+224.9 µs]`.

This establishes a real startup cost, but not a formal regression beyond the
declared budget: the formal lower bound is `+4.33%`, below `+6%`, and the
generic point estimator passes. A focused profile of 1,000 three-route builds
placed about `0.478 ms` per build in `install`, predominantly route planning.
The cost is therefore recorded as a release trade-off and the narrow gate is
classified as insufficient sampling; endpoint compilation and lazy request
scope were not reopened without a formal budget regression.

## Measurement-system correction

The correction is limited to the evidence system:

1. Released comparisons normalize only the `pydepin` subject version, require
   `packages.pydepin` and `distributions.pydepin` to agree, and continue to
   require every other stable environment field to match.
2. Collection, reduction, provenance, and acceptance support a contiguous,
   counterbalanced repetition count of at least five, including the prescribed
   doubled rerun.
3. The real collector records CPU, kernel, governor, affinity, packages, the
   full normalized collection command, target revisions/lock digests, and the
   runner digest.
4. Complete pytest-benchmark reports are retained beside the raw envelopes and
   verified by SHA-256 during reduction.
5. A non-positive noisy head attribution makes the formal log-ratio
   inconclusive; a non-positive accepted baseline attribution remains invalid.
6. The generated report renders scalar and array provenance fields emitted by
   the real collector.

The stored dedicated and generic outputs are
[`fastapi-acceptance.txt`](fastapi-acceptance.txt) and
[`generic-gate.txt`](generic-gate.txt). No file in `benchmarks/budgets.toml` was
edited.

## Independent review

The single independent review found no critical issues and recomputed all
twelve tail/control intervals exactly. Its two important findings—an incomplete
projected collection command and absent retained benchmark reports—were fixed
and exercised by five RED/GREEN cases before this final collection. Two minor
recommendations were adjudicated: conflicting subject-version sources are now
rejected; generating the authored classification narrative was deferred because
the reviewer independently matched every displayed statistic to the retained
raw data and a new report generator would exceed this bounded correction.
