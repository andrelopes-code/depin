# Step 7 — performance evidence and regression protection: design

Date: 2026-09-02

Status: approved, pending implementation plan

Scope: measurement methodology, workload contracts, regression gating, the two
algorithmic repairs Step 7 owns, and the public performance report.

Input: `specs/evidence/2026-09-02-step-7-performance-baseline.md`, measured
against `3c2ed50` on 2026-09-02. Nothing measured there is re-derived here.

Normative source:
`specs/proposals/2026-08-31-performance-evidence-and-regression-proposal.md`.

## Goal

Make the cost of using `depin` knowable, reproducible, and protected, without
publishing a claim the measurements do not support.

The baseline found the project at a specific starting point: a 24-case suite that
is a competent relative alarm, no public performance statement of any kind, and
no direct-Python baseline anywhere. Nothing published has to be corrected. The
design therefore builds the evidence chain forward rather than repairing a claim.

## What the baseline settled, and what follows from it

Five measurements decide most of this design.

**A uniform threshold cannot be right.** Per-benchmark run-to-run dispersion
spans 0.9% to 7.0%. A single 25% tolerance sits just above the noisiest case and
twenty times above the quietest, so it is simultaneously too loose to protect the
quiet workloads and too tight to be a long-term contract for the noisy one. Per
workload budgets are not a refinement; they are the only defensible form.

**Pairing works, but not everywhere.** Five paired process-level repetitions cut
the worst null excursion from 18.6% to 14.4% and the false-alarm rate at a 5%
budget from 7.45% to 1.10%. For 23 of 24 cases the null band roughly halves. One
case does not improve, and two mitigations for it were tried and rejected on
their own data. The design keeps pairing and gives that workload a budget from
its measured band.

**A round-level artifact is 21 MB.** The published raw data has to be the
per-repetition aggregates the statistics are computed from, not the round arrays.

**The hot path has no hotspot.** Thirteen Python calls per cached resolution, no
function above 15% of profiled time, one mutex and one `ContextVar` read that
both carry guarantees. There is nothing here to micro-optimise, and the
structural remedy is the plan compilation Step 8 already reserved "only on
evidence".

**`freeze()` accepts graphs the runtime cannot resolve.** Cold resolution dies at
332 providers of depth. That is a public-surface question, not a performance one.

## Non-goals for this step

- No aggregate ranking, league table, or "fastest DI library" claim, in any form.
- No competitor numbers published in 0.18.0. The reason is in "Competitors" below.
- No optimisation of the cached resolution path. The evidence for restructuring it
  is recorded and handed to Step 8.
- No repair of the depth cliff. Recorded and handed to Step 8.
- No hosted dashboard.

## The claim contract

`benchmarks/contracts.py` carries the shapes. A workload is not measurable until
it states, in data rather than prose, the eleven things the proposal requires: the
user question, the useful work, what the timed region includes and excludes, the
lifetime and caching semantics, the graph shape, the concurrency model, the metric
and unit, the expected noise class, and both the valid and the invalid readings.

Two consequences are mechanical rather than editorial.

**`Implementation` separates the timed callable from what it observably does.**
An implementation carries `prepare`, which returns the callable a harness times,
and `observe`, which returns an `Observation`: the result, the types constructed
in construction order, the resources closed in teardown order, and any error.
Equivalence between two implementations is then equality of two dataclasses,
proved by an ordinary test with no timing in it.

**`Workload` holds the `depin` subject, the direct baseline, and any
alternatives.** A competitor adapter is an `Implementation` like any other and is
held to the same `Observation` equality. There is no path by which an adapter is
timed without having been proved equivalent first, because the contract test
covers every implementation a workload carries.

The direct baseline is optional in the type for one case only: a startup workload
such as `freeze()` has no direct counterpart, because hand-wiring has no
validation step to compare against. The contract test requires a baseline
everywhere else and requires the claim to name the reason where it is absent.

## Workload taxonomy

Four tiers, never merged into one score.

**Tier 1, isolated.** Cached singleton lookup; first construction; transient
construction by depth; scope entry, cache hit and teardown; alias and decoration
hops; collection resolution by member count; generic-key lookup; injected wrapper
dispatch; override lookup with and without an active override; async resolution
against the bare event-loop boundary. Each uses the smallest graph that isolates
the cost, and each carries a direct baseline.

**Tier 2, component.** Small, medium and large graphs; deep transient and scoped
paths; wide fan-out; mixed lifetimes; sync and async resources with deterministic
teardown; warmup of a cold singleton graph; freeze and validation scaling; and —
absent from the suite today — the actionable error paths, which the baseline
showed are exactly where the two unrepaired algorithmic costs live.

Graph shapes are derived from the repository's own `examples/` tree and the
FastAPI integration tests rather than invented, so "small", "medium" and "large"
mean something a reader can check.

**Tier 3, application.** One sync-oriented and one async-oriented FastAPI
application, driven in-process through `httpx.ASGITransport` so no socket, DNS or
network stack enters the timed region. Each has a paired baseline that is the same
FastAPI application with the same service work wired explicitly. Startup — import,
declaration, freeze, warmup — is measured separately from per-request cost.

**Tier 4, scaling and stress.** Curves rather than single points: graph size and
edge count, dependency depth, fan-out, collection size, teardown count, and the
error paths by size. The depth cliff at 332 is pinned here so it cannot move
unnoticed.

## Metrics

Five, each chosen because a production question needs it, and each gated
differently because they differ in how noisy they are.

| Metric | How | Noise |
| --- | --- | --- |
| Latency | `pytest-benchmark`, reduced to one aggregate per repetition | High; needs the paired protocol |
| Work | Python-level calls per operation, counted with `sys.setprofile` | **Deterministic** |
| Allocations | `tracemalloc` block count and bytes per operation | Deterministic under a fixed hash seed |
| Retained memory | `tracemalloc` snapshot difference while the object is held | Deterministic under a fixed hash seed |
| Scaling | the same operation at sizes S and 2S, gated on the ratio | Ratios cancel most host noise |

The deterministic metrics are the important addition. A latency gate cannot see a
regression smaller than its workload's noise band, and on the delivered suite
those bands put the budgets between 5% and 11%. Calls per operation and
allocations per operation carry no noise at all, so a change that adds one
dictionary to the resolution path is caught exactly, on the first run, by a check
that cannot produce a false alarm. They are a proxy for cost rather than cost
itself, which is why they supplement the latency gate rather than replacing it.

Throughput and CPU time are recorded for tier 3 only, paired, because a higher
request rate bought with more CPU is not an improvement.

## Measurement protocol

### Two environments, stated as different things

**The relative environment** is the pull-request runner. Base and head are
measured on the same machine within the same job. It gates; it never produces a
published absolute number.

**The public absolute environment** is a documented reference host. The project
does not own a quiet benchmark machine, and the design does not pretend
otherwise: the reference host is recorded in the dataset with its CPU, kernel,
interpreter, and the load average at measurement time, and every published
absolute figure is labelled as host-specific. What transfers is the ratio to the
direct baseline, the complexity class, and the deterministic counts.

Refusing to publish absolute numbers at all would be the other defensible
choice. It is rejected because a user asking "what does a resolution cost" is
better served by "about 2 µs on a 2.1 GHz Xeon, and here is the host" than by
silence.

### The paired protocol

For a relative comparison the harness performs R repetitions. Each repetition
measures both revisions in independent processes, and the order within a
repetition alternates, so a systematic drift over the job — thermal behaviour,
frequency scaling, a noisy neighbour — falls on both sides equally instead of on
whichever ran second.

The statistic is the median of the paired log ratios. Its uncertainty is a 95%
percentile bootstrap interval over those paired differences, 2000 resamples, from
a fixed seed so a verdict is reproducible from the same data.

R is 5 by default. Below R = 5 the gate refuses to conclude rather than
concluding weakly.

### Minimum sample quality

A repetition contributes to a verdict only when its workload accumulated at least
1000 rounds or 0.5 s of measured time. A repetition below that is recorded and
excluded, and a workload whose valid repetitions fall under R is reported as
having no verdict rather than passing.

### The decision rule

Let `b` be the workload's budget and `[lo, hi]` the interval on the ratio.

- **fail** when `lo > b`: the regression is larger than the budget with
  confidence.
- **inconclusive** when the point estimate exceeds `b` but `lo` does not.
- **pass** otherwise.

Failing only when the *lower* bound clears the budget is deliberately
conservative: on a shared runner a blocking gate that cries wolf is turned off
within a month, and the deterministic gates carry the sensitivity that this rule
gives up.

An inconclusive verdict triggers exactly one escalation, at double R. The second
verdict is final, and a second inconclusive is a failure. There is no unlimited
retry, because unlimited retries are how a real regression is eventually rolled
into a green run.

### Budgets

For latency, per workload:

```
budget = max(class_floor, 2 x measured_paired_null_p99)
```

rounded up to the whole percent, with class floors of 5% for `LOW`, 8% for
`MEDIUM` and 15% for `HIGH`. The class is the band the workload's paired null
p99 falls in — at or below 3%, at or below 6%, above 6%.

The factor of two is the margin between "noise this workload produced under the
null" and "a difference this gate is willing to call real". `budgets.toml`
carries every budget with the measurement that justifies it, and
`benchmarks.harness.budgets` refuses a budget below its workload's class floor,
so a failing pull request cannot be made green by editing a number.

Applied to the delivered suite the formula yields 5% for twenty-one of the
thirty-five latency workloads, 6% for seven more, and 8% to 11% for the remaining
seven. Every one of them is tighter than the uniform 25% it replaces, and each
carries in the file the measurement that set it.

For the deterministic metrics the budget is exact: work and allocation counts may
not increase at all, and retained memory may move by 2% to absorb container
resizing. Scaling ratios carry 15%, which is a complexity-class test rather than
a timing one.

### Malformed, missing, renamed, new

The gate fails on a report that is not an object, carries no `benchmarks` array,
carries an empty one, or is unreadable. A workload in the inventory with no result
in either report fails the gate — "a visible result for every expected workload"
is a property of the run, not of the report. A workload present only on the base
side is reported as removed; present only on the head side, reported as new and
not gated, because it has no base measurement to compare against. Renames are
removals plus additions and are reported as both.

## Proving the gate works

A gate that has never failed is not known to work. Three seeded regressions,
committed as patches under `benchmarks/seeds/` with the command that applies them
to a scratch worktree, so the demonstration is reproducible rather than reported:

1. **A frequent resolution path.** The missing-provider message formatted on
   every lookup instead of only when the lookup fails. Expected to fail the
   latency gate on the resolution workloads, most clearly on the ones that
   resolve repeatedly per operation.
2. **Scaling.** The failing-freeze walk restored to its pre-repair shape.
   Expected to fail the scaling gate and leave the fixed-size latency gates
   green — which is the point: the scaling gate exists because the others cannot
   see a complexity change.
3. **Allocation.** A throwaway dictionary built per cached resolution. Expected
   to fail the allocation gate exactly, from a single repetition — an allocation
   count carries no dispersion, so there is nothing to average and no interval to
   clear.

Each is applied, shown to fail the gate it targets, removed, and shown to pass.
A workload is not described as regression-protected until its class of failure
has been demonstrated.

## The two repairs Step 7 owns

Both were confirmed in the baseline and neither is re-derived.

**The failing freeze is cubic** because `_check_missing` walks from every root and
`_collect_missing` rebuilds its chain-identity set on every stack pop.

**The missing-key walk is exponential** because `_deepest_requirement` enumerates
every simple path from every node without memoisation.

Both compute the same thing: the longest chain reaching the provider that
declares an unsatisfied parameter. That is a longest-path dynamic program over a
DAG in O(V+E), written once and called from both sites.

The constraint that governs the repair is that **the reported chain is
user-visible error text and must not change.** Both walks keep the longest chain
and break ties by traversal order — children pushed in forward order onto a LIFO
stack, compared with a strict `>`, so the first chain of a given length stands —
and `render._deepest_requirement`'s docstring states that the two agree on that
tie-break.

A longest-path dynamic program is exact on an acyclic graph, where every path is
simple. It is not exact on a cyclic one: longest simple path is NP-hard, so no
polynomial algorithm reproduces the current output there. `_check_missing` runs
before `_toposort` deliberately, so a graph carrying both a missing provider and
a cycle reports the missing provider, and the cyclic case is reachable.

The dynamic program therefore runs when the reachable graph is acyclic — cycle
detection is itself O(V+E) — and the existing walk remains as the fallback when it
is not. Reordering `_check_missing` and `_toposort` to avoid the fallback is
rejected: it would change which error a graph with both faults raises.

The evidence that the repair is safe is a differential test over random graphs,
generated with Hypothesis, asserting that the new implementation returns exactly
what the current one returns, chain contents and tie-break included.

The third routed finding needs no repair to `depin`, only to the benchmark: a
layered-DAG generator and an `explain()` case over it, so the subtree-elision
guard is exercised at all.

## Competitors

The protocol is implemented; no competitor number is published in 0.18.0.

The eligibility screen is applied to dishka, wireup, svcs and
dependency-injector, and its outcome recorded. The `Workload.alternatives` slot
and the `Observation` equality rule are in place, so an adapter added later is
held to semantic equivalence by a test rather than by a reviewer's attention.

Publication is deferred to Step 9, which owns the comparison page, for two
reasons that are about validity rather than effort. A comparison is only as fresh
as its adapters, and the freshness process — reviewing adapter configuration
against each library's own documentation whenever the report is refreshed — needs
a cadence that Step 7 does not own. And a competitor table is the part of this
work most easily misread, so it should be published onto a methodology that has
already been exercised on `depin` alone.

Configuration fairness is reviewed by the pull request that adds an adapter,
against a written equivalence sheet held in the repository, with the competitor
version pinned in a dependency group of its own so a silent upgrade is visible in
the diff.

## Publication

### Where the numbers live

`benchmarks/results/<date>/` holds one accepted dataset: environment metadata,
per-repetition latency aggregates, deterministic counts, and scaling curves. The
directory name carries no commit, because it has to be chosen before the commit
that adds it exists; the dataset is published by that commit, so
`git log -- benchmarks/results/<date>` identifies the source exactly and the
environment file records the interpreter, host and distribution versions beside
it. History is git history, not an accumulating directory.

Round-level samples are reduced as they are collected and never written out. The
alternative — keeping them as a CI artifact — was rejected once the baseline
measured one report at 21 MB: the aggregates are what every statistic here is
computed from, and the round arrays are regenerable from the harness by anyone
who wants them.

### The public pages

`docs/performance/` carries what the project measures and why, results separated
into startup and recurring cost, the direct-Python baselines, end-to-end results,
scaling and memory, methodology and environment, reproduction instructions,
limitations, and the readings each result cannot support.

The results page is **generated** from the committed dataset, and a test asserts
the committed page equals the render of the committed data. A number cannot drift
from its evidence, because the page is not written by hand.

The README links to the performance section and embeds no number.

Contract and equivalence tests live under `tests/integration/`, not
`tests/unit/`. `tests/unit` is kept framework-free for the free-threaded job, and
anything the unit suite reads from the working tree has to be added to
`[tool.mutmut] also_copy`; routing these tests to the integration suite avoids
both couplings.

### Freshness

The dataset records the commit and version it was measured at. The generated page
carries both. A workload added, renamed or removed makes the committed dataset
incomplete, and the coherence test fails until the dataset is refreshed — so the
inventory and its evidence cannot diverge silently.

A refresh is a reviewable change that explains material movements. Results never
update silently.

## Questions the proposal left to this design

| Question | Resolution |
| --- | --- |
| Runner, statistical model, history system | `pytest-benchmark` as the timing engine; a project-owned, stdlib-only harness for pairing, statistics and gating; git as the history |
| Stable environment for public absolute results | A documented reference host, recorded per dataset, with every absolute figure labelled host-specific. The project has no quiet machine and says so |
| Python versions and platforms | All gates on 3.12, the version the existing job uses. Cross-version performance is not measured: the deterministic metrics differ by interpreter, so a cross-version gate would compare unlike things |
| Graph shapes for small, medium, large | Derived from `examples/` and the FastAPI integration tests |
| Valid direct implementation per workload | Declared per workload and proved by `Observation` equality |
| Which current benchmarks can support public claims | The baseline's inventory table: two corrections, one coverage gap, one regression-only case, the rest publishable once they carry a contract and a baseline |
| CPU, allocations, retained and peak memory without confusing allocator behaviour | `tracemalloc`, which counts Python-level blocks, under a fixed hash seed; retained measured while the object is held, peak from the traced maximum |
| Driving FastAPI without measuring a network stack | In-process `httpx.ASGITransport`, one event loop for the measurement, startup measured separately |
| Noise and impact data justifying budgets | The null experiment, re-run against the delivered suite; the formula above |
| Rerunning near-threshold results without hiding a regression | One escalation at double R; the second verdict is final |
| Which competitors | Screened; none published in 0.18.0; the reason is recorded |
| Who reviews adapters for fairness | The pull request that adds one, against a written equivalence sheet, with the version pinned in its own dependency group |
| Storing raw artifacts without bloating the repository | Per-repetition aggregates, not round arrays: 21 MB becomes kilobytes |
| Cadence keeping claims fresh | Refresh on any release that changes `depin/_core/` or the harness; the coherence test forces it when the inventory moves |
| Displaying an upstream regression | The failure classification in the proposal, implemented as a triage section in `CONTRIBUTING.md` |
| Evidence justifying a hosted dashboard | Recorded as not yet justified: the methodology and one validated dataset come first |

## Verification

The delivered work is verified by, and not before:

- every workload carrying a complete claim contract, enforced by a test;
- every workload with a baseline proving `Observation` equality, enforced by a
  test;
- the differential test over random graphs for the two repairs;
- complexity tests that fail against the pre-repair implementations;
- three seeded regressions, each shown to fail its gate and pass once removed;
- the generated results page matching the committed dataset;
- `ruff format`, `ruff check`, `basedpyright`, `mypy`, `pytest`, coverage at or
  above 95%, the mutation threshold, and `mkdocs build --strict`, all green.

## Acceptance

The step is complete when the proposal's acceptance criteria hold and the two
findings this design routes to Step 8 — the depth cliff and the evidence for plan
compilation — are recorded in the roadmap under "Carried from Step 7".

The proposal's `Status:` field is closed in the same change as the evidence
report. Step 6 left its predecessor reading `queued proposal` through an entire
release cycle; this design treats closing it as part of the deliverable rather
than as follow-up.
