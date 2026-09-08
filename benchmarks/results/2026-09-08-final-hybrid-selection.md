# Final compiled-runtime hybrid selection

The final selection tested whether the dense instruction representation could
replace the remaining shallow production interpreter while retaining generated
functions for their accepted synchronous transient slice. The candidate
compiled sync and async instruction tables for every plan, routed every cold
non-generated root through them, and left only active overrides and live-scope
supplied-value precedence on the explicit-stack fallback.

The implementation was test-first and passed 1,303 unit tests with six expected
free-threaded skips. A literal specification review approved its routing and
fallback boundary. A separate quality review found one stale benchmark seed;
after the seed was rebased, its published integration guard passed and the
review approved the candidate.

## Deterministic gate

The official deterministic harness compared the accepted async-instruction
runtime at `72db10e` with the universal shallow candidate at `61e5d1c`. Three
published gates failed:

| Gate | `72db10e` | Candidate | Change | Budget |
| --- | ---: | ---: | ---: | ---: |
| Request-shaped scope Python calls | 88 | 97 | +10.23% | 0% |
| Request-shaped scope allocation blocks | 27 | 29 | +7.41% | 0% |
| Retained bytes, frozen 100-provider container | 36,144 | 64,392 | +78.15% | 2% |

The retained-memory failure is the cost of storing a second executable form for
a shallow plan that previously needed none. The request-shaped scope is frame-
sensitive, so it cannot use fixed default/optional slots while a live frame may
supply a value; it pays the extra selection work and still correctly enters the
dynamic fallback.

These metrics are exact under `PYTHONHASHSEED=0`, carry no confidence interval,
and cannot be rescued by a latency result. The full timed comparison was
therefore stopped at the deterministic gate, as required by the proposal's
no-wider-budget rule. No budget was changed.

After the candidate was removed, the selected hybrid completed one full
`--benchmark-only` pass over the published inventory: 120 measured workloads
passed and 35 non-benchmark harness/comparison tests were skipped by that mode.
This verifies that every published workload remains executable; the accepted
per-slice paired and deterministic results remain the comparative evidence.

## Decision

Universal shallow instruction compilation is a NO-GO and its implementation
and tests were removed. The final accepted hybrid is:

- generated Python functions for eligible shallow synchronous transient roots;
- the dense typed sync executor for deep synchronous graphs;
- the separately typed dense async executor for deep asynchronous graphs; and
- the existing shallow runtime plus explicit-stack dynamic fallback for shapes
  whose second executable representation or context-sensitive behavior failed
  the final gate.

Deep active-override graphs retain the dynamic fallback so nested and repeated
substitutions observe the current context. Frame-sensitive roots retain it so a
value supplied by an active scope continues to beat a compiled default or
`None`. Warm cached roots continue to use the direct cache path.

The result does not meet the proposal's aspiration to remove the interpreter
from production entirely. It is retained as a concrete residual because the
only measured replacement violated three existing gates. This closes the
proposal's bounded experiments without weakening semantics, hiding memory, or
widening budgets; a future design must eliminate that residual with a more
compact representation or a context-sensitive overlay.
