# Competitive benchmark and leadership gate: design

Date: 2026-09-02

Status: approved, pending implementation plan

Scope: competitor adapters, equivalence records, paired comparative collection,
per-workload leadership verdicts, and the accepted baseline that governs the
remaining performance proposals.

Input:
`specs/proposals/2026-09-02-competitive-performance-leadership-proposal.md`.
The proposal's evidence-gated sequence was approved on 2026-09-02.

## Goal

Replace the exploratory competitor screening with an accepted, reproducible
dataset that can answer two independent questions for every required workload:

1. Is `depin` no slower than the fastest competitor that performs equivalent
   work with equivalent guarantees?
2. Is the measured increment over direct Python within the workload's absolute
   overhead target?

The result is an engineering gate, not a league table. It decides where the
compiled-runtime and FastAPI work must improve, and whether a native experiment
still has a justified target after the Python implementation is optimized.

## Governing decisions

- Comparisons are made per workload. There is no aggregate score, weighted mean,
  points table, or project-wide winner.
- Semantic classification is committed and reviewed before a measurement is
  accepted. A favorable timing cannot change an adapter from partial to
  equivalent.
- The existing base-versus-head regression gate remains the ordinary pull-request
  defense. Competitor collection is a separate locked workflow and is run before
  closing any of the three optimization proposals.
- Direct Python remains in every comparison for which a meaningful direct
  implementation exists. Relative leadership and absolute overhead receive
  separate verdicts.
- Dependency Injector, Dishka, Wireup, and svcs are pinned in the `bench`
  dependency group. They never become core or package runtime dependencies.
- An unavailable or inexpressible feature is recorded as incomparable; it is not
  emulated outside the competitor to manufacture a number.

## Architecture

The existing workload inventory remains the source of user questions, timed
regions, direct implementations, and observable behavior. Comparative code wraps
that inventory without adding competitor implementations to
`benchmarks.workloads.WORKLOADS`, so the normal benchmark gate does not begin
timing third-party libraries.

Three layers keep the concerns separate:

1. `benchmarks/comparison/` owns classification and typed competitor adapters.
2. `benchmarks/harness/comparison.py` collects counterbalanced paired samples and
   writes a self-describing dataset.
3. `benchmarks/harness/leadership.py` evaluates the dataset, while
   `benchmarks/harness/comparison_report.py` renders the same verdicts into
   documentation.

The evaluator reads data only. It does not import a competitor, construct a
container, or rerun a benchmark. A verdict is therefore reproducible from the
accepted dataset.

## Comparative data model

`benchmarks/comparison/contracts.py` defines immutable, slotted records.

`Equivalence` has exactly three values:

- `EQUIVALENT`: the candidate matches every relevant part of the workload claim;
- `PARTIAL`: the candidate performs useful related work but omits a named
  guarantee or operation; and
- `INCOMPARABLE`: expressing the workload would require external emulation or
  materially different work.

`Competitor` records the normalized distribution name and installed version.
The version comes from `importlib.metadata`, is checked against the exact pin,
and is written into every dataset.

`Candidate` records a competitor, an equivalence class, a non-empty reason, and
an optional `Implementation`. Equivalent and partial candidates must carry an
implementation. Incomparable candidates must not carry one. These invariants are
validated while the inventory is built, before timing starts.

`ComparativeWorkload` records the existing `Workload`, exactly one candidate for
each maintained competitor, an `AbsoluteTarget`, and the names of any secondary
metrics that must remain within the ordinary regression budgets. Duplicate or
missing competitor records make the inventory invalid.

`AbsoluteTarget` is an additive seconds-per-operation ceiling over the paired
direct implementation. Additive overhead is used instead of a ratio because a
ratio becomes unstable when the direct operation approaches a field access.

Partial implementations are timed and published with their omitted guarantee,
but they do not participate in a leadership verdict. Incomparable candidates
are published without a duration or ratio.

## Adapter boundary

Each competitor has one module under `benchmarks/comparison/adapters/` and owns
the complete set of its records. The shared adapter protocol is:

```python
class Adapter(Protocol):
    @property
    def competitor(self) -> Competitor: ...

    def candidates(self, workloads: Sequence[Workload]) -> tuple[Candidate, ...]: ...
```

Adapters use public APIs of the pinned release. They may import benchmark-domain
services and sinks so the competitor constructs the same objects as `depin` and
direct Python. They may not import private competitor modules, patch the
competitor, preconstruct a transient value outside the timed region, or add a
cache that the library does not provide.

Every timed candidate has an ordinary observation test. Equivalent candidates
must produce the same `Observation` as the workload subject. Partial candidates
carry a focused assertion for the behavior they do implement and an exact reason
why the full observation is not equivalent.

The first maintained core adapters cover, where the public library supports the
contract:

- warm singleton and scoped cache hits;
- transient chains at depths 1, 5, and 20;
- scoped construction at depths 1, 5, and 20;
- one shared DAG;
- synchronous resource construction and reverse teardown; and
- container construction or validation as a separate cold workload.

Every other required workload receives an explicit partial or incomparable
record in the first dataset. Later adapter additions change classification and
code together in one reviewed commit.

## Required inventory

The comparative inventory includes every workload named by the governing
proposal. Existing Step 7 workloads are reused when their timed region and
semantics already match. Missing shapes are added to a comparison-only workload
module so they do not silently expand the ordinary regression gate:

- scoped cache hits and empty scope entry/exit;
- aliases, decorators, conditions, collections, and overrides;
- synchronous and asynchronous providers and resources;
- light and resource-owning scope lifecycles;
- singleton-only, request-scoped, async-resource, and representative FastAPI
  endpoints;
- synchronized first use, scope contention, and supported free-threaded cases;
- allocations, retained memory, scaling curves, and maximum cold depth.

The inventory contract test requires a direct implementation or a claim that
explains why direct Python has no corresponding operation, exactly one
classification per competitor, and a target for every latency workload with a
direct implementation.

## Absolute targets

`benchmarks/leadership-targets.toml` is an authored engineering contract, not a
noise calibration artifact. It is reviewed separately from
`benchmarks/budgets.toml`, which remains generated and continues to govern only
base-versus-head regressions.

Targets use the preliminary same-host evidence to set ceilings before accepted
competitor collection:

- warm cache lookup: at most 0.5 microseconds over direct access;
- provider construction: at most 0.5 microseconds per constructed provider over
  the matching direct graph;
- scope entry and exit: at most 2 microseconds plus 0.5 microseconds per value
  constructed or finalized;
- alias, decoration, condition, collection, and override dispatch: at most
  0.5 microseconds per container-owned dispatch step;
- FastAPI injection: at most 10 microseconds plus 2 microseconds per injected
  parameter, and no more than 10% of the matching direct endpoint duration;
- cold validation and construction: at most 1 microsecond per provider and edge,
  subject to the existing linear-scaling gate.

When both a fixed and proportional FastAPI ceiling apply, the lower ceiling is
the target. Resource finalizers' own useful work is present on both sides and is
excluded from the additive container budget.

Changing a target requires a design change with user-impact evidence. A target
is never recalibrated from the current `depin` result or widened to pass a loss.

## Collection protocol

`python -m benchmarks.harness.comparison` runs the locked comparison inventory.
Each repetition measures all implementations on one host, interpreter, CPU
affinity, source revision, and harness revision. Candidate order alternates by
repetition. Each implementation is prepared outside its timed region and runs in
an independent child process with a fixed hash seed.

Five paired repetitions are the minimum. Every latency case must accumulate the
existing Step 7 sample-quality floor. A comparison with fewer than five qualified
pairs receives no verdict.

Round arrays remain transient. The committed dataset contains the per-repetition
median, round count, duration, order, and CPU cost where applicable. Those are
the raw paired samples from which every published statistic is recomputed.

The dataset schema records:

- schema version, UTC collection time, source revision, dirty-tree flag, and
  harness revision;
- interpreter, platform, CPU, affinity, load, hash seed, and installed
  distribution versions;
- the committed equivalence records and absolute targets;
- the calibration p99 and non-inferiority allowance for each workload;
- one reduced sample per implementation and repetition; and
- deterministic work, allocation, retained-memory, and scaling readings.

A dirty tree, a version that differs from the pin, an incomplete inventory, or a
failed observation check prevents an accepted collection.

## Noise calibration and leadership verdict

The calibration workflow measures identical code on both sides using the same
counterbalanced protocol. For each workload it records the 99th percentile of
the paired null statistic. The non-inferiority allowance is that p99 rounded up
to one tenth of a percentage point, with a hard maximum of 5%.

A workload whose measured null p99 exceeds 5% is ineligible for a leadership
claim until its measurement is stabilized. The evaluator does not truncate a
larger noise band to manufacture a verdict.

For every equivalent competitor, the evaluator computes the existing median
paired log-ratio and 95% bootstrap interval with `depin` as the numerator. The
fastest equivalent competitor is the one with the lowest median within that
workload. `depin` reaches competitive leadership only when its median is no
greater and the interval's upper bound is within the calibrated allowance.

The direct-Python verdict uses the paired median of `depin - direct`, expressed
in seconds per operation, against the authored absolute target. Secondary
deterministic metrics are evaluated through their existing budgets. All three
verdicts are retained separately.

The final workload status is one of:

- `leader`: competitive, absolute, and secondary verdicts pass, and the interval
  excludes a slower result;
- `shared-leader`: all verdicts pass and parity remains inside the interval;
- `loss`: at least one eligible equivalent competitor is faster outside the
  allowance;
- `absolute-failure`: the direct-Python target fails independently of the field;
- `regression`: a secondary metric exceeds its existing budget;
- `unstable`: calibration or sample quality cannot support a verdict; or
- `no-equivalent-competitor`: every attempted competitor is partial or
  incomparable.

No status is aggregated across workloads.

## Report and evidence

`benchmarks.harness.comparison_report` generates the public and evidence tables
from the accepted dataset. Each workload row shows the timed-region summary,
classification, medians, interval, noise allowance, direct overhead, absolute
target, secondary verdicts, and conclusion. Partial and incomparable rows show
their reasons in the same table rather than disappearing from it.

The first accepted dataset and report live under a date-and-commit directory in
`benchmarks/results/`. The evidence report under `specs/evidence/` records the
command, environment, profiles, unfavorable findings, and which later proposal
owns each residual. The generated public page is not promoted as the Step 9
comparison page until the three optimization proposals have closed.

## CI and dependency isolation

The pinned competitor distributions live only in the `bench` dependency group.
The comparison modules are type-checked with the rest of `benchmarks/`; the
ordinary library wheel and the `threads` group remain free of them.

The source-checking CI job syncs the locked `bench` group in addition to its
normal development environment before running the five checkers. Adapter
observation tests live under `benchmarks/`, outside the default `pytest`
`testpaths`, and the dedicated comparison workflow runs them with the same
locked group. Contract and evaluator tests that do not import a competitor stay
under `tests/integration/` and remain part of the ordinary gate.

A dedicated `competitive-benchmarks.yml` workflow runs on manual dispatch or an
explicit calibration label. It installs the locked `bench` group, verifies
adapter observations, collects or evaluates the dataset, and uploads raw
artifacts. It is not an unpinned network-facing PR gate.

The normal CI benchmark job continues to call `benchmarks.harness.pairs` and
never imports `benchmarks.comparison`.

## Error behavior

Harness and adapter-contract failures raise `HarnessError` with the workload,
competitor, failed invariant, and corrective action. A provider exception remains
the provider exception inside an `Observation`; the adapter does not swallow or
translate it merely to keep a run alive.

One failed candidate invalidates that candidate's repetition and the workload's
verdict, but collection continues far enough to write diagnostic output for the
other candidates. No failure is silently converted to incomparable.

## Verification

Development is test-first. The verification layers are:

1. data-model invariant tests for all three equivalence classes;
2. inventory tests for complete competitor coverage, exact pins, direct
   baselines, targets, and unique labels;
3. observation tests over every equivalent adapter;
4. synthetic collector tests that prove counterbalancing, process isolation,
   malformed-result handling, and dataset reproducibility;
5. synthetic evaluator tests for leader, shared leader, loss, absolute failure,
   regression, instability, and no-equivalent cases;
6. a seeded comparison regression shown to change a passing workload into a
   loss;
7. the repository's formatting, linting, five source type checkers, test,
   coverage, and strict documentation gates; and
8. a clean-host collection from the locked `bench` group.

## Delivery sequence

1. Land the typed model, authored targets, and complete classification inventory.
2. Land Dependency Injector, Dishka, Wireup, and svcs adapters with observation
   evidence.
3. Land the collector, calibration, evaluator, report generator, and dedicated
   workflow.
4. Prove the gate with synthetic cases and a seeded regression.
5. Collect the accepted baseline, publish its evidence, and change the governing
   proposal status from proposed to accepted and active.
6. Use the recorded core losses as the input to the compiled-runtime design.

## Acceptance criteria

- Every required workload has a direct record and exactly one reviewed
  classification for every maintained competitor.
- Dependency Injector, Dishka, and Wireup have executable adapters for every
  equivalent core workload their public APIs express; svcs has executable or
  explicit partial records for its service-locator model.
- The locked workflow reproduces raw paired samples with dependency versions,
  source and harness revisions, and complete environment metadata.
- Equivalent, partial, and incomparable results remain distinct in data,
  evaluation, and generated documentation.
- Competitive, absolute, and secondary verdicts are computed and rendered
  independently.
- The accepted baseline names every loss and routes it to the compiled-runtime,
  FastAPI, or native decision without making an aggregate claim.
- The normal regression gate, public API, inferred types, and core dependency
  boundary do not change.

## Non-goals

- Optimizing `depin` in this delivery.
- Treating a partial result as evidence of leadership.
- Reproducing a competitor's own published benchmark instead of this
  repository's workload contract.
- Running competitor comparisons on every pull request.
- Publishing the final Step 9 comparison page before the optimization sequence
  closes.
