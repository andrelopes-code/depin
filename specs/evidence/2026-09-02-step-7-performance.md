# Step 7 evidence — performance evidence and regression protection

Date: 2026-09-02

Status: delivered

Design: `specs/2026-09-02-step-7-performance-design.md`
Plan: `specs/plans/2026-09-02-step-7-performance.md`
Baseline: `specs/evidence/2026-09-02-step-7-performance-baseline.md`

Nothing measured in the baseline is repeated here. This document records what was
built, what it measured, what failed, and what was deliberately not done.

## The two repairs

Both costs the roadmap carried into this step are closed by one change:
`depin/_core/longest_chain.py`, which computes the longest chain reaching every
unsatisfied parameter once, in O(V+E), for the walk `Container.freeze()` runs and
the walk `FrozenContainer.explain()` runs alike. `graph._collect_missing` is
deleted; `render._deepest_requirement` is a four-line adapter.

Failing `freeze()` over a linear chain whose deepest node requires an unbound
key:

| nodes | before | after |
| ---: | ---: | ---: |
| 50 | 0.0100 s | 0.0064 s |
| 100 | 0.0330 s | 0.0076 s |
| 200 | 0.1976 s | 0.0115 s |
| 400 | 1.3687 s | 0.0198 s |

`explain()` of an unbound key over a fan-in-2 layered DAG, where the count of
simple paths is Fibonacci in the node count:

| nodes | before | after |
| ---: | ---: | ---: |
| 14 | 0.0055 s | 0.0036 s |
| 16 | 0.0094 s | 0.0038 s |
| 18 | 0.0208 s | 0.0036 s |
| 20 | 0.0520 s | 0.0046 s |
| 22 | 0.1337 s | 0.0039 s |
| 24 | 0.3591 s | 0.0037 s |

69x and 97x at the largest size measured, and — the part that matters more — both
curves are flat rather than merely lower.

### What made the repair safe

The chain these walks produce is user-visible error text. A longest-path dynamic
program is exact on a directed acyclic graph, where every path is simple, and
wrong on a cyclic one, where longest simple path is NP-hard. `_check_missing`
runs before `_toposort` deliberately, so a graph carrying both a missing provider
and a cycle reports the missing provider: the cyclic case is reachable and its
output had to survive unchanged.

So the dynamic program runs when the graph is acyclic — Kahn's algorithm decides,
in O(V+E) — and the enumerating walk remains as the fallback when it is not.

Three properties had to be reproduced exactly, not merely approximately:

1. **The chain contents.** On a DAG every deepest path to a node of depth *d*
   passes a node of depth *i* at each position, so paths of one depth are
   extensions of paths of the depth below.
2. **The tie-break.** Children are taken in reverse parameter order, which is
   what the old LIFO stack did, and each depth is ranked by traversal order.
3. **The insertion order.** `_check_missing` sorts stably by chain length, so
   dictionary insertion order decides the line order among equally long chains.
   A separate O(V+E) pre-order pass reproduces it.

The evidence is a Hypothesis differential test holding the two replaced walks
verbatim as reference implementations and comparing **lists** of
`(ident, chain, owner, parameter)` — so contents, tie-break and insertion order
are all pinned — over random graphs with defaulted, optional and unsatisfied
parameters, on both the acyclic and the cyclic branch. A separate test pins the
exact message text a cycle beside a missing provider produces.

Two complexity tests guard the classes. Both were shown to fail against the code
they replace: timing the verbatim reference walks at the same sizes gives 1.3678 s
against a 0.5 s budget, and 0.3620 s against a 0.2 s budget. The new
implementation sits 25x and 54x under.

### The third routed finding

The elision benchmark needed no repair to `depin`, only a shape that exercises
what it claimed to guard. Confirmed first: rendering a 1000-node linear chain
produces zero `(shown above)` markers, so removing the guard could not change it.
`graphs.build_layered_dag` now builds a fan-in-2 DAG, and `explain_a_layered_dag`
over 500 nodes observes 998 lines with 498 elided against the linear chain's 1000
lines with 0. Deleting the guard is now detectable.

## What the suite became

| Tier | Workloads |
| --- | ---: |
| Isolated | 9 |
| Component | 20 |
| Application | 6 |
| Scaling | 21 |
| Allocations and retained memory | 9 |
| **Total** | **65** |

35 declare latency and are driven by the timing shell as 52 cases — one per
implementation, so a `depin` subject and its direct baseline land in the same
report and a published ratio comes from one run rather than two.

Two properties are enforced by ordinary tests rather than by review:

- **Every workload carries a complete claim** — the user question, the useful
  work, what the timed region includes and excludes, the semantics, the shape,
  the concurrency model, the metric and unit, the noise class, and both the valid
  and the invalid readings. A workload with no direct baseline must name the
  reason in the claim, in wording the test greps for.
- **Every subject and baseline are observably equivalent** — same result, same
  types constructed in construction order, same resources closed in teardown
  order, same error. 623 assertions, with no timing in any of them.

## Corrections the baseline required

Three, each carrying the measurement that motivated it into the code.

**The decoration workload was re-based** onto the 100-node graph the cached
lookup uses, rather than the 1-node graph it used while claiming the comparison.
The baseline had already shown the comparison was sound in substance — a cached
lookup costs 2021, 1970, 2033 and 1992 ns at sizes 1, 10, 100 and 300, flat
within 3% — so this controls a variable that does not move the number, which is
what stops the case depending on a fact stated nowhere. Measured after: 1.826 µs
against 1.802 µs for the plain lookup.

**The async workload gained its baseline.** 82% of its timed region was the event
loop. Its direct implementation now drives a bare coroutine through the same
`run_until_complete`, so the depin share is visible instead of buried: 17.06 µs
against 13.61 µs, or 3.4 µs attributable — reproducing the baseline's 3.5 µs.

**The error paths entered the suite.** Neither the failing-freeze path nor the
missing-key `explain()` path had any benchmark at all, which is why the two costs
this step repaired could regress unnoticed. Both are now workloads.

## A finding the new coverage produced immediately

With the walks repaired, most of what remains on both error paths is
`suggest_candidates`' scan over `sys.modules`: **2.97 ms of 3.41 ms** for the
unbound-key case. The claim states the attribution rather than presenting the
number as the cost of the walk.

This is not a defect. The scan runs only on a path that is already raising and
aborting a startup, and it exists because `gc.get_objects()` cannot be used on a
free-threaded build. It is recorded so that a later reading of these workloads is
not mistaken about what they measure.

## Competitor screen

Executed, and recorded rather than promised.

| Library | Latest | Released | requires_python | Declares 3.12 |
| --- | --- | --- | --- | --- |
| dishka | 1.10.1 | 2026-04-25 | >=3.10 | yes |
| wireup | 2.12.0 | 2026-07-09 | >=3.10 | yes |
| svcs | 26.2.0 | 2026-08-24 | >=3.10 | yes |
| dependency-injector | 4.49.1 | 2026-06-18 | >=3.8 | yes |

All four pass the mechanical eligibility criteria. Comparability does not follow
from eligibility and is not uniform across tiers: `svcs` is a service locator
rather than a constructor-injecting container, and no competitor validates a
whole graph at build time the way `freeze()` does, so the startup tier is largely
incomparable while cached and transient resolution is comparable.

**No competitor number is published in this release.** The protocol is in place — an
adapter is an `Implementation` like any other, held to the same `Observation`
equality by the same test — and Step 9 owns the comparison page. The deferral is
about validity, not effort: a comparison is only as fresh as its adapters, and a
competitor table is the part of this work most easily misread, so it belongs on a
methodology already exercised on `depin` alone.

## Findings routed to Step 8

Both are recorded in the roadmap under "Carried from Step 7".

**`freeze()` accepts graphs the runtime cannot resolve.** Cold resolution
recurses about three stack frames per dependency and dies at a chain of 332
providers from a bare interpreter, 331 under `pytest` — the number is a frame
budget divided by frames per provider, so the cliff is the property and the
integer is not. `freeze()` validates a 1000-provider chain and accepts it, and
`warmup()` succeeds on the same graph because it constructs in topological order.
A scaling workload pins it so it cannot move unnoticed. Repairing it means making
resolution iterative, which changes what the runtime is rather than how fast it
is.

**The evidence for compiling the plan into per-key closures.** Thirteen Python
calls per cached resolution, no function above 15% of profiled time, about 2 µs
against 0.06 µs for direct attribute access, and the same per-resolution cost
reappearing as the 8.2x ratio on a 20-deep transient chain. There is no hotspot
to remove; the cost is the depth of the call graph, plus one mutex acquisition
and one `ContextVar` read that both carry guarantees. Step 8 reserved the right
to compile the plan "only on evidence". This is the evidence, recorded and not
acted on, because restructuring the runtime is not measuring it.

## The budgets, and what replaced 25%

Budgets are derived from a paired null collection of the delivered suite: ten
runs of identical code, five per side, with the statistic evaluated over every
split of those runs into two halves — 1512 trials per workload.

The worst paired null p99 across the thirty-five latency workloads is **5.28%**
and the median is **2.36%**. Applying `max(class floor, 2 x p99)`:

| Budget | Workloads |
| ---: | ---: |
| 5% | 21 |
| 6% | 7 |
| 8% | 4 |
| 9% | 1 |
| 10% | 1 |
| 11% | 1 |

Every one is tighter than the uniform 25% it replaces — the quietest by a factor
of five — and each carries in `benchmarks/budgets.toml` the measurement that set
it. `benchmarks/harness/budgets.py` refuses a latency limit below its workload's
class floor, and refuses to loosen the deterministic budgets at all, so a failing
pull request cannot be made green by editing a number.

The deterministic budgets are exact: calls and allocations per operation may not
increase, retained memory may move 2% to absorb container resizing, and scaling
ratios carry 15% because they are a complexity-class test rather than a timing
one.

Gating the null collection — both sides the same code — returns **56 verdicts,
all pass, exit 0**, with every deterministic metric bit-identical at +0.00%.

## The published dataset

`benchmarks/results/2026-09-02/` is **92 KB**: environment metadata, five
per-repetition latency aggregates, the deterministic counts and the scaling
curves. One round-level `pytest-benchmark` report for the same suite is 21 MB, so
publishing the round arrays was never viable; what is published is the
observations every statistic here is computed from.

`docs/performance/results.md` is generated from that directory, and
`tests/integration/test_performance_docs.py` asserts the page equals the render
of the data and that every workload the inventory declares appears in it. A
number on the site cannot have been typed by hand, and a workload added or
renamed leaves the dataset incomplete until it is refreshed.

Two figures from it, both host-specific: a cached singleton resolution costs
**1.759 µs** against **92.6 ns** for attribute access on a held object, and a
20-deep transient chain costs **34.5 µs** against **2.18 µs** for constructing
the same twenty objects by hand.

## Proving the gates fail

Three seeded regressions, each committed as a patch under `benchmarks/seeds/`,
applied to a scratch copy of the tree, measured against the unmodified one, and
removed.

### Allocations

`allocation-per-resolution-dict.patch` builds one throwaway dictionary on every
cached resolution. Gate exit **1**, from a single repetition:

```
fail  allocations  allocations_of_a_cached_singleton_resolution: size 1168 -> 1352 (+15.75%) budget 0.0%
fail  allocations  allocations_of_a_request_shaped_scope:        blocks 27 -> 32 (+18.52%) budget 0.0%
fail  allocations  allocations_of_a_scope_cycle:                 size 6240 -> 9800 (+57.05%) budget 0.0%
```

Eighteen other verdicts passed in the same run. The point is not the size of the
numbers but that one repetition was enough: an allocation count carries no
dispersion, so there is nothing to average and no interval to clear.

### Scaling

`scaling-restore-enumerating-walk.patch` forces the pre-repair enumerating search
back on, which is cubic on the failing-freeze path and exponential on the
missing-key path. Gate exit **1**, again from a single repetition:

```
fail  scaling  scale_explain_missing_key: worst size-to-size growth +15.32% budget 15.0%
fail  scaling  scale_failing_freeze:      worst size-to-size growth +49.18% budget 15.0%
```

This is the seed that justifies the scaling gate existing at all. A complexity
change is invisible to a benchmark that only ever measures one size, and the
fixed-size latency workloads stayed green through it.

### Latency

`latency-eager-error-message.patch` formats the missing-provider message on every
lookup instead of only when the lookup fails — the shape a refactor produces when
a message is hoisted out of the branch that needed it. Gate exit **1**, over five
paired repetitions:

```
fail          latency  resolve_singleton_through_a_two_deep_decoration_chain: +17.14% [+15.22%, +20.03%] budget 8.0% n=5
inconclusive  latency  resolve_cached_singleton:                              +19.60% [ +7.51%, +23.29%] budget 8.0% n=5
inconclusive  latency  call_through_an_inject_wrapper:                         +9.61% [ -1.48%, +18.99%] budget 9.0% n=5
fail          work     allocations_of_a_cached_singleton_resolution:  9 -> 10  (+11.11%) budget 0.0%
fail          work     allocations_of_a_scope_cycle:               396 -> 397   (+0.25%) budget 0.0%
fail          work     allocations_of_a_transient_chain:           202 -> 203   (+0.50%) budget 0.0%
fail          work     allocations_of_an_inject_call:                29 -> 30   (+3.45%) budget 0.0%
fail          work     allocations_of_a_request_shaped_scope:      105 -> 106   (+0.95%) budget 0.0%
```

Three things in one run, and the second and third are worth more than the first.

**The latency gate failed**, on the workload where the interval cleared the
budget outright.

**Two workloads came back inconclusive rather than failing**, and both are
correct. `resolve_cached_singleton` measured +19.60% against an 8% budget — a
regression by any reading — but its interval reached down to +7.51%, which does
not clear 8%. The rule fails only on the interval, so the verdict is
inconclusive and CI re-measures once at double the repetitions. This is the
conservative rule costing something real, visibly, rather than in the abstract:
a gate that failed on the point estimate would be quicker here and would cry wolf
elsewhere.

**The work gate failed deterministically on all five**, including
`allocations_of_a_scope_cycle` at **396 -> 397 calls, +0.25%**. A quarter of one
percent is an order of magnitude below the noise floor of every latency workload
in the suite; no timing gate at any budget could see it. It is caught exactly,
from one repetition, because a call count has no dispersion. That is the entire
argument for the deterministic metrics, measured rather than asserted.

### One seed that did not fire, and was replaced

The first latency seed duplicated the `overrides.active` lookup in
`_lookup_optional`. It measured **-0.64%** on `resolve_cached_singleton` — no
effect at all — and the reason was in the patch: the duplicate call sat behind
`if ... is not None`, so it only ran when an override was active, which no
measured workload has. The seed added work exclusively to a path nothing
exercises.

It was replaced rather than reported, and the replacement was sized before it was
committed: measured in process at +11.5% on a cached resolution, against budgets
of 5% to 11%. A second candidate — claiming the scope cache twice — was measured
first and discarded, because it deadlocks: the second claim waits on the flight
the first one opened.

The general point is that a seeded regression has to be verified to regress.
A patch that looks like a slowdown and measures as nothing would have certified
the gate on evidence it never produced.

## Method notes

### An environmental-noise event, classified rather than absorbed

The first attempt to derive budgets from the delivered suite was taken while
several agents were running type checkers and test suites on the same four-core
host. The result was discarded:

| Workload | quiet window | contaminated window |
| --- | ---: | ---: |
| `export_a_large_graph_as_dot` | 0.9% | 14.2% |
| `build_the_graph_view` | 2.6% | 11.2% |
| `explain_a_deep_chain` | 1.7% | 10.7% |

Identical code, identical workloads. The paired null p99 for
`build_the_graph_view` reached 20.94%, which by the design's own formula would
have produced a 42% budget — looser than the uniform 25% this whole step exists
to replace.

This is the third row of the proposal's failure classification: environmental
noise, whose correct response is to re-measure under the documented policy and
improve isolation, never to adopt the numbers. Budgets are derived only from a
run taken with nothing else executing on the host, and the dataset records the
load average so a reader can see the condition rather than trust it.

### A harness defect the first gated run exposed

Running the gate over a collection where both sides are the same code should
produce nothing but passes. It produced 55 passes and one `no-verdict`, and the
cause was worth more than a clean run would have been.

`pytest-benchmark` decides how many rounds to run by calibrating against its
time budget, and that calibration is not reliable. In one repetition of
`build_the_graph_view` it chose **16 rounds** where the other four repetitions of
the same workload, in the same collection, ran 183, 232, 225 and 216:

| repetition | rounds | measured |
| --- | ---: | ---: |
| base 0 | 183 | 1.098 s |
| base 1 | 232 | 1.363 s |
| base 2 | 225 | 1.318 s |
| **base 3** | **16** | **0.069 s** |
| base 4 | 216 | 1.218 s |

`reduce.qualifies` excluded that repetition — a sample of 16 has no business
setting a median that a release gate reads — which left four valid pairs where
five are required, so the gate refused a verdict rather than computing one. Both
rules behaved exactly as designed, on a real anomaly rather than a constructed
one.

An earlier complete collection showed the same shape on two other workloads, so
this is systematic rather than a single unlucky process. Left alone it would
send most pull requests down the escalation path and double the benchmark job.

Classified as a harness defect, the second row of the proposal's failure table,
and fixed at the collection step: the latency command now carries a rounds floor,
so a repetition cannot be admitted having sampled a hundredth of what its
siblings did. The floor is documented in `pairs.py` against the measurement above.

### A mitigation tried and rejected

The baseline's two attempts to stabilise the noisiest workload — disabling
garbage collection during measurement, and collecting around every benchmark —
both made it worse or did nothing, and neither was adopted. The dispersion is
treated as a property of the workload and given a budget from its measured band.

## Checker coverage for `benchmarks/`

`benchmarks/` was outside every checker's file list. The plan carried adding it
as an attempt with an explicit fallback, because `AGENTS.md` requires the five
lists to mirror one another, so partial adoption was not available: it had to
pass Basedpyright strict, mypy strict, stock Pyright at zero, and the ty and
Pyrefly registers, or be reverted.

It was cheap. `basedpyright` and `mypy` were already clean over the new tree.
Stock Pyright stays at **zero over 182 files**. Pyrefly reported two new
`implicit-any-lambda` diagnostics in `gate.py`, both **fixed in code rather than
registered** — one lambda replaced by `dict.__getitem__`, one by a named ordering
function — so the extension added no waiver of its own.

One register entry was added, and it was required regardless: ty reports
`unsound-assignment` on `longest_chain._chain`, which reassigns its `position`
parameter from `parents[position]` while the loop condition also reads it. ty
breaks that cycle with `Unknown` in the element type — the same shape as the
`graph.py` entry already in the register, and the same classification.

The net is that the harness which gates a release is now checked by the same five
checkers as the library it gates.

## Gates

Measured on the delivered tree, at the reference host recorded in the dataset.

| Gate | Result |
| --- | --- |
| `ruff format` | 296 files unchanged |
| `ruff check` | clean |
| `basedpyright` strict | 0 errors over 182 files, `benchmarks/` included |
| `mypy` strict | clean over 182 files, `benchmarks/` included |
| `pytest` | 2142 passed, 6 skipped |
| coverage over `depin/` | 99% against a 95% floor |
| stock Pyright, source | zero over 182 files |
| ty, source | 45 diagnostics, 31 registered |
| Pyrefly, source | 2 diagnostics, 2 registered |
| `mkdocs build --strict` | built |
| mutation, `depin/_core/` | 97.6% (2530 killed, 62 survived) against a 95% floor |

Every one of the 26 pull-request checks passed. The mutation score moved from
97.7% to 97.6%: `longest_chain` contributed 10 of the 62 surviving mutants, which
is within the floor and is left as available follow-up rather than presented as
complete. The `benchmarks` job skipped its gate, correctly — the base branch
predates the harness, so there was nothing to compare against, and the gate
engages from the next pull request onward.

## Correction, after the first live gate run

The `benchmarks` job could not gate anything on the pull request that introduced
it, because the base branch carried no harness. The first run against a real base
was the documentation-only pull request that followed, and it failed. Two claims
in this report need qualifying.

**`scale_failing_freeze` does not detect what its claim says.** Measured on the
runner with both sides identical, its cost is 7.095, 7.021 and 7.026 ms at sizes
25, 50 and 100 — flat across a fourfold range, because the path is dominated by
the `sys.modules` scan this report already attributes at 2.97 ms of 3.41 ms. The
growth ratios are all ≈1.0 and their difference between two identical revisions
reached +23.61% against a 15% budget.

The seeded scaling demonstration above stands: restoring the cubic walk makes the
walk dominate the constant again, which is why the seed fired. But the curve
detects only a regression large enough to overtake the constant, and is noise
below that — so "the scaling gate is protected" is true for the seeded class and
overstated in general. The repair is what invalidated the workload, by removing
the cost the curve was built to watch.

**The sample-quality floor does not transfer between hosts.**
`MINIMUM_LATENCY_ROUNDS = 120` was derived from one measurement on the reference
host. On the runner it bound `build_the_graph_view` to 120 rounds and 0.408 s,
under the half-second the rule requires, and it does not bind a fast workload at
all: `resolve_a_collection_of_10` ran 485 rounds for 0.007 s where the reference
host gives 20,174. A round count cannot satisfy a rule stated in seconds.

Both come from the same mistake: budgets and floors measured on a quiet
workstation and applied to a shared runner. This report's gate table describes
the reference host, and the blocking gate runs somewhere else.

The repairs, and a calibration collection on CI rather than only on the reference
host, are specified in
`specs/2026-09-02-step-7-coverage-completion-design.md`.

## What this step did not do

Recorded so that a later reader does not mistake absence for oversight.

- **No competitor number is published.** The screen ran; the protocol is in
  place; Step 9 owns the page.
- **The cached resolution path was not optimised.** The profile says the cost is
  the depth of the call graph, not a hotspot, and the structural remedy belongs
  to Step 8.
- **The depth cliff was not repaired.** Pinned, routed, and left to the step that
  owns what the public surface commits to.
- **No absolute latency budget is gated.** Absolute figures are host-specific, so
  gating them on a shared runner would gate the runner. The deterministic metrics
  carry the absolute checks instead, because a count does not depend on the host.
- **Cross-version performance is not measured.** The deterministic metrics differ
  by interpreter version, so a cross-version gate would compare unlike things,
  and cross-version absolute results would need a controlled host the project
  does not have.
