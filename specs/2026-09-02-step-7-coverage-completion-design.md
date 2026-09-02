# Step 7 coverage completion: design

Date: 2026-09-02

Status: implemented; measured in `specs/evidence/2026-09-02-step-7-gate-repair.md`

Scope: the coverage the Step 7 design specification promised and the
implementation did not deliver, plus the tier 4 items its own narrowing dropped
without recording a reason.

Inputs: `specs/2026-09-02-step-7-performance-design.md`,
`specs/evidence/2026-09-02-step-7-performance.md`, and the proposal
`specs/proposals/2026-08-31-performance-evidence-and-regression-proposal.md`,
whose acceptance criteria are already met and are not reopened here.

Released state: 0.17.1. The performance evidence system exists, is gated, and is
published. This document closes the distance between what the design said it
would cover and what the inventory actually covers.

## Two defects the first live gate run exposed, which come first

The `benchmarks` job could not gate anything until `main` carried the harness.
The first pull request where it ran for real was documentation-only — no change
under `depin/` or `benchmarks/` — and it failed. Both causes are defects in what
Step 7 shipped, and both outrank the coverage work below.

### `scale_failing_freeze` does not measure scaling

Measured on the runner, base and head being identical code:

| | size 25 | size 50 | size 100 |
| --- | ---: | ---: | ---: |
| base | 7.095 ms | 7.021 ms | 7.026 ms |
| head | 4.413 ms | 5.028 ms | 6.219 ms |

The base curve is **flat across a fourfold size range**. The cost is dominated by
a constant that has nothing to do with graph size: `suggest_candidates` scanning
`sys.modules`, which the Step 7 evidence already recorded as 2.97 ms of 3.41 ms
on this path. The gate compares growth ratios, those ratios are all ≈1.0, and
their difference between two identical revisions came out at +23.61% against a
15% budget.

Worse, the two sides differ systematically on identical code — 7.0 ms against
4.4–6.2 ms — because the module scan depends on how many modules each process has
loaded, which is not a property of the revision under test.

The workload was valid before the repair, when the walk dominated the constant,
and the repair is what invalidated it. That is why the seeded scaling regression
still fires: restoring the cubic walk makes it dominate again. So the curve
detects a large complexity regression and is noise for everything else, which is
not what its claim says.

**Fix:** retire the curve rather than retune its budget, and state the reason on
the results page. The failing-freeze path keeps its deterministic work-count
check, which is sensitive to the walk and immune to the constant. The same audit
applies to `scale_explain_missing_key`, which shares the constant.

### The sample-quality floor is tuned to the wrong host

Three workloads returned `no-verdict` because a repetition fell under the
quality rule. `MINIMUM_LATENCY_ROUNDS = 120` was chosen against a measurement on
the reference host and does not transfer:

- `build_the_graph_view` ran exactly 120 rounds for 0.408 s. The floor bound it,
  and 120 rounds only reaches half a second for an operation slower than about
  4.2 ms. It is 5.9 ms on the reference host and 3.4 ms on the runner.
- `resolve_a_collection_of_10` ran 485 rounds for 0.007 s, where the same
  workload takes 20,174 rounds locally. The floor does not bind a fast operation
  at all, so it inherits the calibration unreliability it was added to remove.

A fixed round count cannot satisfy a rule stated in seconds, because the rounds
needed depend on the operation's cost. The floor must be derived per workload
from that cost, which the published dataset already records as each workload's
median. `pytest.mark.benchmark(min_rounds=...)` applied per workload by the
timing shell expresses it directly.

Note this was checked and is **not** an `iterations` accounting error:
`pytest-benchmark` reports `iterations = 1` for every workload here, so
`rounds x mean` is the measured time.

### What both have in common

Budgets and floors were derived on a quiet workstation and applied to a shared
runner. The Step 7 design separates the two environments and then calibrated the
blocking gate against the wrong one. A relative gate has to take its noise from
the environment it runs in, so the re-measurement below must include a
calibration collection **on CI**, not only on the reference host.

## What this is repairing

An audit of the delivered tree against the Step 7 design found three
discrepancies where the design asserts coverage that does not exist, and one
place where the design silently narrowed the proposal.

**The design's tier 1 lists ten operations; the inventory has nine workloads,
and they are not the same nine.** Missing outright: override lookup with and
without an active override, generic-key lookup at resolution time, first
singleton construction, sync resource teardown, and injected-wrapper dispatch
with explicit arguments beside injected ones. The word "override" appears in the
suite only inside claim prose, never as a measured path.

**CPU time is measured and thrown away.** The tier 3 workloads return
`Cost(cpu_nanoseconds=...)` from their timed callable, and nothing reads it. The
dataset contains no CPU field. The design states that "Throughput and CPU time
are recorded for tier 3 only, paired, because a higher request rate bought with
more CPU is not an improvement" — the reason is right and the recording never
happened.

**End-to-end results carry no quantiles.** The proposal asks for p50, p95 and
p99 "when sample count and methodology make those quantiles meaningful". The
published report gives a median and a spread across repetitions.

**Tier 4 dropped five of the proposal's scaling cases without a recorded
reason.** Concurrent requests and active scopes, singleton first-use contention,
override nesting, async teardown count, and long-running retention. Narrowing is
legitimate; narrowing silently is not, because a later reader cannot tell a
decision from an oversight.

## Principles carried forward

Unchanged from the Step 7 design, and binding here:

- A workload is not measurable until it carries a complete claim, including the
  readings it does not support.
- Every workload carries a direct-Python baseline unless there is genuinely no
  hand-written counterpart, and then the claim names the reason.
- Subject and baseline are proved observably equivalent by an ordinary test with
  no timing in it, before either is measured.
- Budgets come from measured noise, never from what makes a run green.
- A gate is not described as protecting anything until it has been shown to fail.

## The five tier 1 workloads

Each carries a direct baseline, because each has an obvious hand-written
counterpart.

| Workload | What it isolates | Direct baseline |
| --- | --- | --- |
| `resolve_with_no_active_override` | The `ContextVar` read on the resolution path when nothing has been overridden — the production case | Attribute read on a held object |
| `resolve_through_an_active_override` | The same path with one override installed, so the cost of the branch that fires is visible against the branch that does not | A held object reached through one level of indirection |
| `resolve_a_generic_key` | `as_provider_key`'s `get_origin` branch at resolution time, not at freeze time, which is the only place it is currently measured | Attribute read on a held object |
| `construct_a_singleton_for_the_first_time` | Cold construction, against the cached lookup that every other workload measures | Calling the constructor once |
| `resolve_a_sync_resource_with_teardown` | A `yield`-style provider entered and drained, which tier 1 does not cover at all today | A handwritten context manager doing the same work |

`call_through_an_inject_wrapper` gains a sibling,
`call_through_an_inject_wrapper_with_explicit_arguments`, so the dispatch cost of
an argument the caller supplies is separable from one the container resolves.

The override pair is the important one. `overrides.active` is called on every
resolution — it is in the profile that Step 7 published — and no workload has
ever exercised it with an override present. The pair also makes the cost of the
feature legible: a reader can see what an override costs when it is used, rather
than only what it costs when it is not.

## CPU time, collected

`Prepared.call` may return a `Cost`. The harness must read it.

- `benchmarks/harness/reduce.py` gains an optional CPU aggregate per workload,
  populated when the workload's callable returns one and absent otherwise.
- `benchmarks/harness/pairs.py` collects it beside the latency aggregate.
- `benchmarks/harness/report.py` renders a CPU column for the workloads that
  carry one, so a wall-clock figure is never published alone for tier 3.
- The gate does **not** budget CPU. It is reported, not enforced: process CPU on
  a shared runner carries the runner's noise, and the deterministic metrics
  already cover what can be gated exactly. The design records this rather than
  leaving a metric that looks gated and is not.

## Quantiles

`pytest-benchmark` already reports per-round percentiles. `reduce.Aggregate`
keeps only the median and the interquartile range, which is what discards them.

- `Aggregate` gains `p95` and `p99`, read from the report where present.
- The published report carries them **for the application tier only**. For a
  microbenchmark whose rounds are calibrated loops, a p99 describes the
  calibration more than the operation; for an end-to-end request it describes the
  tail a user actually meets.
- Budgets continue to be set on the median. A tail statistic over five
  repetitions is not stable enough to gate, and saying so is better than gating
  it badly.

## Tier 4: what is added, and what is refused

**Added:**

- `scale_async_teardown` — teardown count for async resources, the counterpart of
  the sync curve that already exists.
- `scale_override_nesting` — resolution cost by depth of nested overrides, which
  is a real scaling dimension of a public feature and is currently unmeasured.

**Refused, with the reason recorded rather than left blank:**

- **Concurrent requests, active scopes, and singleton first-use contention.**
  These are the proposal's most valuable scaling cases and the hardest to make
  honest. `AGENTS.md` forbids timed sleeps, so contention has to be created with
  explicit synchronisation — `threading.Barrier`, a reduced switch interval — and
  a benchmark built that way measures the synchronisation as much as the lock.
  The repository already tests these invariants for correctness under
  free-threading in `tests/unit/test_free_threading.py`, where the guarantee is
  what matters. A performance number for them needs its own design, and belongs
  with the free-threading work rather than bolted onto this suite. **Routed to
  Step 8**, which owns what the public surface commits to under concurrency.
- **Long-running allocation and retention behaviour.** Retention is currently a
  point-in-time reading. A drift measurement needs a soak, and a soak in a
  pull-request gate is a runner-time decision, not a methodology one. Recorded as
  a candidate for a scheduled job, not a blocking gate.

## Re-measurement

Adding workloads changes the inventory, which invalidates the committed dataset
and the budgets derived from it. Both are regenerated:

1. A paired null collection on a quiet host — nothing else executing, because
   Step 7 already measured what contamination does to this exact procedure.
2. Budgets re-derived by the unchanged formula, with the new workloads' bands
   measured rather than assumed.
3. The dataset republished and `docs/performance/results.md` regenerated from it.
4. The gate re-run over the null collection, which must return all-pass.

The three seeded regressions are re-run against the new budgets. A seed that
stops firing is a finding, not a nuisance: it would mean the budget it used to
clear has moved.

## Acceptance

- The design's tier 1 list and the inventory name the same operations.
- No metric is measured and discarded: CPU time appears in the dataset and the
  report, or the workload stops computing it.
- Application-tier results carry p95 and p99; microbenchmarks do not, and the
  page says why.
- Every proposal scaling case is either measured or refused in writing, with the
  refusal naming what would be needed instead.
- Budgets and dataset regenerated from a quiet host; the gate returns all-pass on
  a null collection.
- The three seeds still fail the checks they target.
- The ordinary gates stay green, `benchmarks/` included in all five checkers.

## What this does not do

It does not reopen the proposal's acceptance criteria, which the Step 7 evidence
report already demonstrates. It adds no competitor comparison, does not repair
the resolution depth cliff, and does not compile the plan into per-key closures —
all three remain Step 8's, for the reasons recorded there.
