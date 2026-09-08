# Roadmap to 1.0

`depin` released v0.18.0 and has an accepted competitive performance baseline.
The package remains pre-1.0: its public API may change in any pre-1.0 release.
The exact commit tagged `1.0.0` becomes the API-freeze baseline. Milestones do
not reserve intermediate version numbers.

The v1-readiness work at `59624cf` closed the identified lifecycle and
type-correctness findings. A new finding that affects the public contract moves
back to the front of this sequence.

## Active sequence

1. Maintain comparative evidence under the accepted
   [competitive-performance leadership proposal](proposals/2026-09-02-competitive-performance-leadership-proposal.md).
2. Continue bounded compiled-Python experiments under the
   [compiled-resolution runtime proposal](proposals/2026-09-02-compiled-resolution-runtime-proposal.md),
   with freeze-time composition of closures for synchronous transient chains
   selected next after the 2026-09-04 cached-runtime experiment's NO-GO.
3. Investigate
   [declarative provider discovery](proposals/2026-09-05-declarative-provider-discovery-proposal.md),
   keeping explicit package discovery as a hypothesis rather than an accepted
   API or mechanism.
4. Recalibrate FastAPI application performance under the
   [FastAPI minimum-overhead proposal](proposals/2026-09-02-fastapi-minimum-overhead-proposal.md).
5. Keep the optional native accelerator NO-GO under the
   [optional-native accelerator proposal](proposals/2026-09-02-optional-native-accelerator-proposal.md).
6. Complete the final public-API audit, stability commitment, comparison page,
   and package classifier; maintainers then decide whether to tag `1.0.0`.

## Evidence and operating references

- [Performance methodology](../docs/performance/methodology.md)
- [Reproducing performance results](../docs/performance/reproducing.md)
- [Competitive baseline](../docs/performance/comparison-baseline.md)
- [`benchmarks/results/`](../benchmarks/results/)

## Non-goals

- No aggregate winner claim across workloads.
- No runtime dependency in the core package.
- No lazy resolution, assisted injection, or implicit unbounded scanning.
- Declarative discovery stays inside an explicit application-selected boundary
  and completes before `freeze()`.
