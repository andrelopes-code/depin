# Methodology

How the numbers on these pages are produced, and what would make them wrong.

## A result is not a measurement

A benchmark that runs is not yet evidence. Every published result on this site
has passed through the same chain, and a number that has not is not published.

1. **A claim contract**, written before the workload is measured. It states the
   user question, the useful work performed, what the timed region includes and
   excludes, the lifetime and caching semantics, the graph shape, the concurrency
   model, the metric and its unit, and — the part that matters most — the
   readings the result does **not** support.
2. **Semantic validation**, by an ordinary test with no timing in it. Two
   implementations of a workload are comparable only when they observably do the
   same thing: same result, same objects constructed in the same order, same
   resources closed in the same order, same failure behaviour. The test compares
   those observations directly.
3. **Measurement**, collecting raw samples with environment metadata.
4. **Statistical validation**, over independent repetitions rather than over
   samples inside one process.
5. **Regression evaluation**, against a per-workload budget derived from that
   workload's measured noise.
6. **Diagnosis** before remedy: a profile identifies the responsible call paths
   before anything is changed.
7. **Optimisation validation** across the whole suite, both type checkers, the
   concurrency tests and the teardown tests — not only the workload that
   motivated the change.
8. **Publication** with raw artifacts, environment, methodology and limitations.

## Direct Python is the mandatory baseline

Every workload is paired with the simplest honest Python that does the same
useful work without a container: direct attribute access for a cached singleton,
explicit construction for a dependency chain, a handwritten context manager for
a resource with teardown, the same framework application wired by hand for an
endpoint.

The baseline must perform the work. An empty function is not a baseline for a
provider that constructs objects.

Results show both the total cost and the difference from the baseline. Where the
difference sits inside the measurement noise, the conclusion recorded is that the
overhead was not resolved reliably — never that it was zero.

One workload class has no baseline: validating a dependency graph at build time
has no hand-wired counterpart, because hand-wiring has no validation step. Those
results are absolute costs and are labelled as such.

## Startup and recurring costs are never combined

`freeze()`, graph validation, warmup and diagnostic rendering happen once.
Cached resolution, scoped construction, injection and teardown happen per
request. They have different production consequences, so they are reported
separately and never summed into one score.

## Five metrics, because latency alone hides things

| Metric | What it answers |
| --- | --- |
| Latency | what one operation costs |
| Work — Python calls per operation | whether the code path grew, with no timing noise at all |
| Allocations per operation | whether the path started allocating more |
| Retained memory | what a frozen graph, a singleton cache or an open scope holds |
| Scaling | whether cost grows with graph size, depth or fan-out, and where it cliffs |

The last four matter because latency measurement has a noise floor, and the floor
differs by workload — measurably, by several times over. `benchmarks/budgets.toml`
records each workload's measured floor beside the budget derived from it. A change
that adds one dictionary copy to the resolution path can sit under that floor and
be invisible to a timing gate. Calls per operation and allocations per operation are
deterministic: they carry no noise, so the same change is caught exactly, on one
run, by a check that cannot produce a false alarm. They are proxies for cost
rather than cost itself, which is why they supplement latency instead of
replacing it.

## Tail quantiles and CPU, where they mean something

End-to-end results carry p50, p95 and p99, and the process CPU one request spent.
Microbenchmark results carry none of the four. A microbenchmark round is a
calibrated loop, so its p99 describes the calibration rather than the operation,
and process CPU has a clock resolution that a microsecond-scale operation sits
under.

CPU is reported and never gated. Process CPU on a shared runner carries the
runner's scheduling, and the deterministic metrics already carry what can be
gated exactly. It is published so a higher request rate bought with more CPU is
visible as what it is rather than read as an improvement.

## Two environments, doing different jobs

**The pull-request environment** measures the base commit and the proposed commit
on the same machine, in the same job. It exists to detect regressions. It never
produces a published absolute number, because a shared runner is not a benchmark
machine.

**The reference environment** produces the absolute numbers on these pages. It is
a documented developer workstation, not a dedicated benchmark machine — the
project does not own one, and says so rather than implying a controlled lab. Its
CPU, kernel, interpreter and load average at measurement time are recorded with
every dataset.

What transfers from one host to another is the ratio to the direct baseline, the
complexity class, and the deterministic counts. The absolute microsecond figures
do not, and are labelled host-specific wherever they appear.

## Repetitions are paired, and their order is alternated

A relative comparison uses several independent repetitions. Each repetition
measures both revisions in separate processes, and the order within a repetition
alternates between repetitions.

This matters more than the sample count inside any one process. Thermal
behaviour, frequency scaling and background load drift over the minutes a job
takes, and one complete run of the base followed by one complete run of the head
turns that drift into a systematic bias favouring whichever ran first.
Alternating the order spreads it across both sides.

The statistic is the median of the paired log ratios; its uncertainty is a
percentile bootstrap over the paired differences, from a fixed seed, so a verdict
can be recomputed from the same data.

## When a verdict is refused

A repetition counts only if it accumulated enough rounds or enough measured time.
Below five valid repetitions the check reports no verdict rather than a pass.

The rounds a repetition needs are derived per workload, from the cost the
published dataset already records for it, and widened for a host faster than the
one that dataset was measured on. A single round count cannot serve: 120 rounds
is half a second of a 4 ms operation, six seconds of a 50 ms one, and a
thousandth of a second of a microsecond one. The first version of this gate used
one count for every workload, and it neither bound the fast workloads nor carried
the rule for the slow ones on the runner it ran on.

A workload fails only when the *lower* bound of its interval exceeds its budget —
that is, when the regression is larger than the budget with confidence. A point
estimate over budget whose interval still spans it is inconclusive, and triggers
exactly one re-measurement at double the repetitions. The second verdict is final.
There is no unlimited retry, because unlimited retries are how a real regression
eventually lands in a green run.

## Budgets come from measured noise

Each workload's budget is twice its measured noise under the null hypothesis —
repeated runs of identical code — with a floor set by the band its noise falls
in. Every budget is stored beside the measurement that justifies it, and a budget
below its workload's floor is rejected, so a failing change cannot be made green
by editing a number.

For the deterministic metrics the budget is exact: calls and allocations per
operation may not increase at all.

The budget file is generated, never typed. `benchmarks.harness.calibrate` reads a
null collection — both sides the same revision — and writes the file, so every
number in it is the output of a measurement rather than a decision about one. The
runs in such a collection are exchangeable, which is what lets ten of them carry
1512 trials of the same statistic: every way of splitting them into two halves is
another trial.

It is calibrated on the environment the gate runs in — the pull-request runner —
because that is where its false alarms are paid for. A budget derived on a
developer workstation and applied to a shared runner is not a relative gate, and
the first version of this one was exactly that: it failed a documentation-only
pull request on its first live run. The reference host is calibrated too, and the
two are published together, because the distance between them is what the rule
above is protecting against.

## A workload that stops measuring what it claims

A measurement can be invalidated by the repair it motivated. Both error-path
scaling curves were: they watched a walk that dominated their cost, the walk was
made cheap, and what remained was a constant that does not depend on graph size —
so the curves went flat and reported the constant's dispersion as growth.

The response is to withdraw the workload rather than widen its budget. A budget
retuned to accommodate a number that means nothing publishes the same number with
a wider band. Every withdrawal is recorded on the [results](results.md) page with
what it claimed, what invalidated it, and what covers the path instead — because
a workload that is quietly deleted is indistinguishable from one that was never
written.

## The checks are proven to fail

A gate that has never failed is not known to work. Three seeded regressions are
kept in the repository as patches — one on a frequent resolution path, one on
scaling behaviour, one on allocation behaviour — each applied to a scratch
worktree, shown to fail the check it targets, removed, and shown to pass. A
workload is not described as regression-protected until its class of failure has
been demonstrated.

## What these pages will not do

- No aggregate score, league table, or claim to be the fastest library.
- No comparison between operations whose observable semantics differ.
- No competitor result that has not passed eligibility, semantic equivalence,
  configuration fairness and freshness. Where equivalent semantics cannot be
  expressed, the workload is labelled incomparable — it is never converted into a
  win.
- No prediction that a benchmark result determines what any particular
  application will do.

Unfavourable results are published under exactly these rules. Removing or
correcting a misleading result is preferred to keeping a favourable one.
