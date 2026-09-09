# Roadmap to 1.0

`depin` released v0.18.0 and has an accepted competitive performance baseline.
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
margin but no workload passes the strengthened leadership gate: transient p99
confidence is insufficient. Cold singleton construction is competitively timed
but fails its absolute target; warm cache and scoped-cycle gaps remain attackable
in Python; FastAPI contributes 60.7 to 150.6 microseconds at p50 on the measured
request shapes; and the native entry threshold is not met. Leadership now means
at least a 25% p50 margin with explicit p95 and p99 gates, not calibrated parity.

## Active sequence

1. Maintain comparative evidence under the accepted
   [competitive-performance leadership proposal](proposals/2026-09-02-competitive-performance-leadership-proposal.md).
2. Execute endpoint compilation and lazy request scope under the
   [FastAPI minimum-overhead proposal](proposals/2026-09-02-fastapi-minimum-overhead-proposal.md),
   the single next performance proposal.
3. Investigate
   [declarative provider discovery](proposals/2026-09-05-declarative-provider-discovery-proposal.md),
   keeping explicit package discovery as a hypothesis rather than an accepted
   API or mechanism and not presenting discovery as a performance fix.
4. Keep the optional native accelerator NO-GO under the
   [optional-native accelerator proposal](proposals/2026-09-02-optional-native-accelerator-proposal.md).
5. Complete the final public-API audit, stability commitment, comparison page,
   and package classifier; maintainers then decide whether to tag `1.0.0`.

## Evidence and operating references

- [Performance methodology](../docs/performance/methodology.md)
- [Reproducing performance results](../docs/performance/reproducing.md)
- [Competitive baseline](../docs/performance/comparison-baseline.md)
- [2026-09-09 competitive analysis](../benchmarks/results/2026-09-09-competitive-rebaseline/analysis.md)
- [`benchmarks/results/`](../benchmarks/results/)

## Non-goals

- No aggregate winner claim across workloads.
- No runtime dependency in the core package.
- No lazy resolution, assisted injection, or implicit unbounded scanning.
- Declarative discovery stays inside an explicit application-selected boundary
  and completes before `freeze()`.
