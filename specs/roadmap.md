# Roadmap to 1.0

`depin` released v0.20.0 and has accepted comparative and FastAPI performance
evidence.
The package remains pre-1.0: its public API may change in any pre-1.0 release.
The exact commit tagged `1.0.0` becomes the API-freeze baseline. Milestones do
not reserve intermediate version numbers.

The v1-readiness work at `59624cf` closed the identified lifecycle and
type-correctness findings. A new finding that affects the public contract moves
back to the front of this sequence.

The compiled-resolution experiments completed on 2026-09-08. They selected
generated functions for eligible shallow synchronous transient roots and dense
typed instructions for deep sync and async graphs. Universal shallow
instructions were rejected by the published work, allocation, and retained-
memory gates; the remaining interpreter paths are an explicit residual, not
unfinished expansion under the completed proposal.

The 2026-09-09 competitive rebaseline gives the transient chain a material point
margin but no core workload passes the strengthened leadership gate: transient
p99 confidence is insufficient. Cold singleton construction is competitively
timed but fails its absolute target, while warm cache and scoped-cycle gaps
remain attackable in Python. Leadership means at least a 25% p50 margin with
explicit p95 and p99 gates, not calibrated parity.

The 2026-09-10 post-release evidence compares the published v0.20.0 runtime with
the accepted v0.19.0 baseline. The primary CPU-light DI-attributable p50
objective passes at `-59.47% [-69.81%, -51.20%]`, and the generic p50 gate
passes all six FastAPI workloads. Application startup and the remaining p95 and
p99 criteria are not closed: their dedicated confidence-bound checks remain
inconclusive and require measurement in a dedicated environment. This result
closes endpoint compilation and lazy request scope as delivered v0.20 work; the
pending measurements do not reopen either design.

## Active sequence

1. Maintain comparative evidence under the accepted
   [competitive-performance leadership proposal](proposals/2026-09-02-competitive-performance-leadership-proposal.md).
   Keep the generated 2026-09-09 comparison page tied to its accepted dataset;
   the 2026-09-10 published-release comparison is supplemental evidence rather
   than a replacement dataset.
2. Measure FastAPI application startup and unresolved p95 and p99 criteria in a
   dedicated environment under the completed
   [FastAPI minimum-overhead proposal](proposals/2026-09-02-fastapi-minimum-overhead-proposal.md).
   This is an evidence task, not authorization to change runtime, budgets, or
   the completed endpoint-compilation and lazy-scope design.
3. Advance
   [declarative provider discovery](proposals/2026-09-05-declarative-provider-discovery-proposal.md),
   to design investigation. Compare the proposal's bounded mechanisms and
   invariants while keeping explicit package discovery, `@provide`, and
   `discover()` as hypotheses rather than accepted API or implementation, and
   do not present discovery as a performance fix.
4. Keep the optional native accelerator NO-GO under the
   [optional-native accelerator proposal](proposals/2026-09-02-optional-native-accelerator-proposal.md).
5. Complete the final public-API audit, stability commitment, comparison page,
   and package classifier; maintainers then decide whether to tag `1.0.0`.

## Evidence and operating references

- [Performance methodology](../docs/performance/methodology.md)
- [Reproducing performance results](../docs/performance/reproducing.md)
- [Competitive baseline](../docs/performance/comparison-baseline.md)
- [2026-09-09 competitive analysis](../benchmarks/results/2026-09-09-competitive-rebaseline/analysis.md)
- [2026-09-10 FastAPI post-release evidence](../benchmarks/results/2026-09-10-fastapi-minimum-overhead-hardening/report.md)
- [`benchmarks/results/`](../benchmarks/results/)

## Non-goals

- No aggregate winner claim across workloads.
- No runtime dependency in the core package.
- No lazy resolution, assisted injection, or implicit unbounded scanning.
- Declarative discovery stays inside an explicit application-selected boundary
  and completes before `freeze()`.
