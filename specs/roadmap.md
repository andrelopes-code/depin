# Roadmap to 1.0

`depin` released v0.18.0 and has an accepted competitive performance baseline.
The package remains pre-1.0: its public API may change in any pre-1.0 release.
The exact commit tagged `1.0.0` becomes the API-freeze baseline. Milestones do
not reserve intermediate version numbers.

## Active sequence

1. Close lifecycle and type-correctness findings that affect the public
   contract.
2. Maintain comparative evidence under the accepted
   [competitive-performance leadership proposal](proposals/2026-09-02-competitive-performance-leadership-proposal.md).
3. Run bounded compiled-Python experiments under the
   [compiled-resolution runtime proposal](proposals/2026-09-02-compiled-resolution-runtime-proposal.md).
4. Recalibrate FastAPI application performance under the
   [FastAPI minimum-overhead proposal](proposals/2026-09-02-fastapi-minimum-overhead-proposal.md).
5. Consider an optional native accelerator only if optimized Python still loses
   materially, under the
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
- No lazy resolution, assisted injection, or scanning feature without a new
  accepted proposal.
