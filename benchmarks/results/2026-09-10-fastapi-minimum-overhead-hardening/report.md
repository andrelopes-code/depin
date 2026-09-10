# FastAPI minimum-overhead post-release hardening

## Conclusion

The published `v0.20.0` runtime at `57bdea536936a482a358b4d87cff93ccb75272ba`
was compared with the accepted 2026-09-09 `v0.19.0` baseline at
`086adf98459773e3175f4723b2b64e3f47306e42`. The doubled, counterbalanced run
does not prove a runtime regression in any of the fifteen previously
inconclusive formal criteria. Eight are classified as environment, five as
noise, two as insufficient sampling, and none as a real formal regression.

The dedicated gate exits `3` because every one of the fifteen remains
statistically inconclusive, not because a lower confidence bound proves a
regression. The generic p50 gate passes five of six workloads and retains only
application startup as inconclusive. No budget was changed and no runtime code
was modified.

## Protocol and provenance

- Baseline: published `pydepin 0.19.0`, tag `v0.19.0`, revision `086adf9`.
- Head: published `pydepin 0.20.0`, tag `v0.20.0`, revision `57bdea5`.
- Harness revision used to collect and reduce: `22b93a3`.
- Ten independent paired repetitions, alternating base-first and head-first,
  with bootstrap seed `1847`.
- Separate environments synchronized with `uv sync --locked
  --no-default-groups --group bench`; the recorded package set is FastAPI
  `0.141.1`, Starlette `1.6.0`, pytest `9.1.1`, and pytest-benchmark `5.3.0`.
- CPython `3.12.13`, Linux `6.8.0-138-generic`, Intel Xeon E5-2683 v4, affinity
  CPUs `0-3`, and unavailable governor telemetry.
- Load1 ranged from `9.94` to `23.46` in baseline processes and from `10.09` to
  `18.64` in head processes while only four CPUs were available.

The exact collection command was:

```console
uv run --group bench python -m benchmarks.harness.fastapi_evidence collect \
  --out final-raw10 \
  --base-dir v0.19.0 --head-dir v0.20.0 \
  --base-python env-base/bin/python --head-python env-head/bin/python \
  --cache-root cache --repetitions 10
```

The retained [`raw-v4`](raw-v4/) envelopes and reduced [`evidence`](evidence/)
bundle were produced by that command and the reducer, without hand-editing or a
provenance bridge.

## Classification rule

- **Environment**: the equivalent direct control moved in the same direction
  and comparable magnitude, or was itself too unstable to attribute the depin
  result.
- **Noise**: doubling from five to ten pairs changed direction materially, or
  the pair signs were balanced around a point estimate inside the budget.
- **Insufficient sampling**: the direction remained favorable when the sample
  doubled, but ten pairs still left the confidence interval crossing the
  budget.
- **Real regression**: the lower confidence bound exceeds the budget without a
  corresponding control movement. No criterion met this rule.

## The fifteen formal criteria

All intervals are 95% paired bootstrap intervals. Direct controls compare the
same FastAPI route without depin across the two published environments.

| Criterion | depin change | direct control | Classification | Evidence |
| --- | ---: | ---: | --- | --- |
| CPU-light p95 | -2.91% [-48.76%, +31.00%] | -10.72% [-21.35%, +45.29%] | noise | The first five pairs read +19.55%; doubling reversed the point estimate and the signs split 5/5. |
| CPU-light p99 | -5.82% [-33.71%, +33.80%] | -6.01% [-31.31%, +31.71%] | environment | Subject and direct control moved almost identically. |
| Request-scoped p95 | -10.16% [-27.93%, +18.23%] | -12.93% [-33.05%, +108.36%] | environment | The direct control has the same direction and a much wider upper tail. |
| Request-scoped p99 | -6.21% [-18.21%, +17.25%] | -9.26% [-31.95%, +23.77%] | environment | Both point estimates improved and both intervals cross the budget. |
| Singletons/transients p95 | +15.72% [-46.23%, +54.97%] | +9.55% [-34.67%, +71.92%] | environment | The direct route carries the same positive shift and greater uncertainty. |
| Singletons/transients p99 | +4.34% [-41.32%, +38.05%] | +11.45% [-24.51%, +79.91%] | noise | The subject moved from -11.73% at five pairs to +4.34% at ten, with signs split 5/5. |
| Async teardown p95 | -2.81% [-9.69%, +29.16%] | +5.81% [-18.27%, +63.86%] | noise | The point is inside budget, only 4/10 pairs increased, and the control is noisier. |
| Async teardown p99 | +4.38% [-18.01%, +21.56%] | +0.39% [-11.55%, +53.30%] | noise | The point remains inside budget with near-balanced signs and no stable control shift. |
| Endpoint-with-work p95 | -21.06% [-39.18%, +27.87%] | +3.23% [-33.21%, +17.82%] | insufficient sampling | The favorable direction persisted from -17.78% at five pairs, but ten pairs do not bound the tail. |
| Endpoint-with-work p99 | -16.63% [-26.56%, +16.71%] | -5.15% [-10.81%, +9.10%] | insufficient sampling | The favorable direction persisted from -26.56%; its upper bound still crosses +5%. |
| Startup p95 | +22.34% [-1.33%, +58.25%] | +34.80% [+7.80%, +65.18%] | environment | The direct control has a proven, larger regression on the loaded host. |
| Startup p99 | +23.54% [+1.10%, +50.73%] | +39.66% [-7.09%, +86.37%] | environment | Eight of ten pairs increased on both paths; the direct point is larger. |
| Application startup p50 | +17.77% [+2.75%, +35.47%] | +11.26% [+0.93%, +32.85%] | environment | Direct startup moved with the subject; the absolute difference-of-differences is +696.9 µs [-329.6, +1213.1 µs]. |
| Contention p99 | -17.34% [-61.48%, +113.60%] | +138.42% [-40.35%, +754.56%] | environment | The direct synchronized-wave control is substantially less stable than the subject. |
| No-injection p50 | +2.51% [-2.34%, +9.85%] | head-only null control | noise | The point moved from -2.34% at five pairs to +2.51% at ten; only 6/10 pairs increased. |

## Startup margin

The formal startup p50 remains an environment classification: both subject and
direct paths moved, the paired difference-of-differences includes zero, and the
head startup repetitions have `94.6%` spread. It is therefore not a formal
runtime regression.

There is nevertheless a reproducible non-gating floor cost that must not be
hidden. Minimum startup moved `+7.01% [+5.46%, +9.13%]` for depin while the
direct minimum moved `+0.20% [-1.34%, +3.25%]`; the minimum
difference-of-differences is `+164.3 µs [+96.8, +204.2 µs]`. A focused profile
of 1,000 three-route builds placed about `0.478 ms` per build in `install`,
predominantly route planning. Minimum latency is not the formal p50 estimator,
and the p50 attribution interval does not establish a regression, so this
signal is recorded as a startup trade-off rather than used to reopen endpoint
compilation or lazy request scope.

The CPU-light attribution objective is also conservatively inconclusive in the
new run: three of ten head repetitions have a non-positive observed overhead
after subtracting the independently measured direct p50. That value is a noisy
difference, not a physical duration, so the evaluator now reports that its
log-ratio is undefined instead of misclassifying valid evidence as malformed.

## Measurement-system correction

The correction is limited to the evidence system:

1. Released comparisons normalize only the `pydepin` subject version while
   continuing to require every other stable environment field to match.
2. Collection, reduction, provenance, and acceptance support a contiguous,
   counterbalanced repetition count of at least five, including the prescribed
   doubled rerun.
3. The real collector records CPU, kernel, governor, affinity, and package
   provenance; reduction records subject versions, harness revision, collection
   command, and locked-environment fingerprints.
4. A non-positive noisy head attribution makes the formal log-ratio
   inconclusive; a non-positive accepted baseline attribution remains invalid.
5. The generated report renders scalar and array provenance fields emitted by
   the real collector.

The stored dedicated and generic outputs are
[`fastapi-acceptance.txt`](fastapi-acceptance.txt) and
[`generic-gate.txt`](generic-gate.txt). No file in `benchmarks/budgets.toml` was
edited.
