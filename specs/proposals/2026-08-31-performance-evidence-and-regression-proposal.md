# Proposal: trustworthy performance evidence and regression protection

Date: 2026-08-31
Status: queued proposal; requires a design specification and implementation plan
Scope: performance methodology, production relevance, regression control, optimization, and public evidence

## Nature of this document

This document proposes a future body of work. It is not a design specification
and not an implementation plan. The agent that accepts it from the queue must
first refresh the evidence, investigate suitable tooling and infrastructure,
resolve the open methodological choices, write a design specification, obtain
review, and only then write an implementation plan.

The proposal is intentionally detailed about outcomes, validity rules, evidence,
and acceptance criteria. It does not prescribe file-by-file changes, job ordering,
or a sequence of implementation tasks.

## Executive summary

`depin` should treat performance as part of its user-facing quality contract. The
library sits on application construction and resolution paths, and some of those
paths may execute once at startup while others may execute for every request. A
small per-call cost can be irrelevant in an I/O-bound application or material at
high throughput. Users currently have no public evidence with which to make that
judgment.

The repository has useful beginnings: a `pytest-benchmark` suite covers several
hot paths, and pull requests compare the base and head commits on the same runner.
However, the suite is primarily a relative regression alarm. The project does not
publish a reproducible baseline, an end-to-end application result, resource-use
measurements, a comparison with direct Python, or a carefully controlled
comparison with other dependency-injection libraries. The README and public
documentation make no meaningful performance statement.

The proposed work should establish a complete performance evidence chain:

- define production-relevant workloads before measuring them;
- prove semantic equivalence between each measured implementation;
- measure isolated operations, realistic dependency graphs, and end-to-end apps;
- record latency, throughput, startup, CPU, memory, allocations, and scaling where
  each metric is relevant;
- compare `depin` with direct Python as the mandatory overhead baseline;
- compare competitors only when the same observable semantics can be expressed
  fairly;
- protect established workloads with noise-aware regression budgets;
- profile regressions and bottlenecks before proposing optimizations;
- accept optimizations only when they preserve correctness, typing, concurrency,
  maintainability, and the zero-dependency core;
- publish the harness, raw data, environment, limitations, and interpretation;
- prevent documentation and marketing from claiming more than the measurements
  demonstrate.

The goal is not to manufacture a favorable leaderboard. The goal is to make the
cost of using `depin` knowable, reproducible, difficult to misrepresent, and
continuously protected.

## Current position

At the time this proposal was written:

- `benchmarks/` contains 23 `pytest-benchmark` cases covering graph freezing,
  cached and transient resolution, scope entry and teardown, injection, async
  resolution, collections, aliases, decoration, warmup, and diagnostic views.
- Pull-request CI measures the base and head commits on the same runner and fails
  when a benchmark common to both reports regresses by more than 25%.
- New benchmarks are reported but cannot be regression-gated until a later change
  has a base measurement with the same benchmark identity.
- No benchmark JSON baseline or historical series is committed or published.
- Contributor documentation explains how to run the suite, but the README and
  public documentation do not explain expected overhead or production impact.
- There is no direct-Python baseline, end-to-end FastAPI benchmark, competitor
  comparison, memory or allocation suite, tail-latency report, or concurrency
  scaling report.
- Internal evidence documents contain point-in-time results, but they are not a
  stable public performance product and are not discoverable by ordinary users.

A single local run on 2026-08-31 produced the following examples. They are context
for this proposal, not publishable claims: the host was not a controlled benchmark
machine, the run was not independently reproduced, and no uncertainty or direct
baseline was reported.

| Scenario | Observed mean |
| --- | ---: |
| Resolve a cached singleton from a 100-node graph | 2.6 microseconds |
| Resolve that singleton through an alias | 4.6 microseconds |
| Call an injected function with one cached dependency | 9.7 microseconds |
| Resolve a 20-node transient chain | 42.4 microseconds |
| Enter a scope, resolve a 20-node scoped chain, and tear it down | 236 microseconds |
| Freeze 100 ordinary bindings | 4.35 milliseconds |
| Freeze 1,000 ordinary bindings | 39.3 milliseconds |
| Freeze 1,000 generic-key bindings | 92.8 milliseconds |
| Freeze 1,000 fully decorated bindings | 107.6 milliseconds |

The existing cases are useful for self-comparison, but not all pairs are suitable
for cross-scenario conclusions. For example, a decorated-resolution benchmark
uses a much smaller graph than the cached-singleton benchmark that its docstring
references. The async benchmark avoids creating a new event loop per sample, but
still includes `run_until_complete` in every measured call. Those choices may be
correct for regression detection while being unsuitable for an absolute overhead
claim. The future design must audit every benchmark for the claim it is allowed to
support.

## Problem statement

The project cannot currently answer the performance questions a production user
would reasonably ask:

- How much latency does one cached resolution add?
- What is the incremental cost of injection, aliases, decoration, and overrides?
- What does a request-scoped dependency graph cost at 100, 1,000, or 10,000
  requests per second?
- How do cold startup and `freeze()` scale with graph size and generic keys?
- How much memory is retained by a frozen graph, singleton cache, or active scope?
- Does async resolution add meaningful overhead beyond normal event-loop costs?
- Are locks, context-local overrides, or teardown paths sensitive to contention?
- How does a realistic FastAPI application behave with and without `depin`?
- When does DI overhead become material relative to provider work?
- Is a reported regression measurement noise, a harness defect, or a real cost?
- Are comparisons with another library measuring the same behavior?

Without answers, the absence of reported problems is not evidence of acceptable
performance. Conversely, an isolated microbenchmark cannot prove that `depin`
will degrade a real application. Both optimistic and pessimistic claims would be
unsupported.

## Governing principles

### Honesty over favorable presentation

The benchmark program exists to discover the truth, including results that are
unfavorable to `depin`. Workloads, metrics, and interpretation rules must be
defined before results are inspected. Failed hypotheses and slower results must
not be silently removed.

### Compare behavior, not labels

Two operations are comparable only when they provide the same observable
semantics: lifetime, caching, graph shape, provider work, sync/async behavior,
resource cleanup, validation, and error behavior. Sharing a method name such as
`resolve` is not enough.

### Separate absolute cost from incremental overhead

Every user-facing workload needs an appropriate direct implementation that does
the same useful work without a DI container. `depin` overhead is the paired
difference or ratio, while total latency remains visible. Baseline subtraction
must not be used when measurement uncertainty makes the difference unreliable.

### Separate startup paths from request paths

`freeze()`, graph validation, warmup, and diagnostic rendering have different
production consequences from cached resolution, scoped construction, injection,
and teardown. Results must not combine one-time and recurring costs into a single
score.

### Optimize on profiles, not intuition

A benchmark regression or high absolute cost is a reason to investigate. It is
not permission to add caches, generated code, mutable global state, dependencies,
or type-system compromises without a profile and a verified bottleneck.

### Publish limitations with results

Every public result should state what it measures, what it excludes, how noisy it
is, which environment produced it, and which production conclusions it cannot
support.

### Reproducibility is part of the result

A number without source, configuration, versions, raw samples, and reproduction
instructions is not project evidence.

## Goals

- Give users evidence for estimating `depin` overhead in realistic applications.
- Protect startup and recurring hot paths against meaningful regressions.
- Measure both speed and resource cost where each can affect production.
- Create a workload taxonomy that separates micro, component, application, and
  scaling claims.
- Establish direct-Python baselines for every public comparison.
- Permit competitor comparisons only under an explicit fairness protocol.
- Make raw data, harness code, environments, and limitations public.
- Translate low-level results into bounded production examples without pretending
  to predict every application.
- Create a disciplined path from detected bottleneck to safe optimization.
- Ensure feature work adds or updates performance coverage when it changes a hot
  path or introduces a new scaling dimension.
- Keep the core free of runtime dependencies and invisible telemetry.

## Non-goals

- Claiming that one benchmark predicts every production application.
- Publishing a single overall speed score or universal winner.
- Optimizing only to beat a selected competitor.
- Comparing features that do not provide equivalent semantics.
- Hiding unfavorable results, outliers, regressions, or unsupported cases.
- Collecting performance telemetry automatically from user applications.
- Guaranteeing identical performance across hardware, operating systems, Python
  builds, deployment models, or future releases.
- Treating noisy shared CI runners as authoritative absolute benchmark machines.
- Replacing profiling with benchmark rankings.
- Trading away public type precision, thread safety, teardown guarantees, error
  quality, or maintainability for a microbenchmark improvement.
- Adding native extensions or core runtime dependencies without a separate,
  explicit product decision.

## Proposed performance evidence chain

The recommended program has eight connected stages. A result is user-facing only
when it has passed through the relevant stages.

### 1. Workload and claim definition

Each benchmark should begin with a short claim contract:

- the user question it answers;
- the useful work performed;
- setup excluded from the timed region;
- setup included because a user necessarily pays for it;
- lifetime and caching semantics;
- graph size, depth, breadth, and provider shape;
- concurrency model;
- metric and unit;
- expected noise class;
- valid and invalid interpretations.

The workload contract should exist before the first accepted result. Changing a
contract creates a new result series rather than silently rewriting history.

### 2. Semantic validation

Before timing, ordinary tests should prove that all implementations of a workload
return equivalent values, create the same number of objects, cache at the same
boundaries, close the same resources, and expose equivalent failure behavior.

For a competitor adapter, this validation is mandatory. A timing result must not
be accepted merely because the benchmark function completed.

### 3. Measurement

The harness should collect raw samples and environment metadata. It should
distinguish wall-clock latency, CPU time, throughput, allocations, retained
memory, peak memory, and scaling. Not every workload needs every metric, but the
metric choice must follow the production question.

### 4. Statistical validation

The result should include sample count, central tendency, dispersion, and a
confidence or stability measure appropriate to the harness. Warmup behavior,
garbage collection, order effects, outliers, background load, and timer
resolution must be controlled or reported.

Relative base/head results must use independent process-level repetitions as
paired observations. The harness should randomize, interleave, or otherwise
counterbalance which revision runs first, then calculate uncertainty from the
paired differences. One complete base run followed by one complete head run is
not sufficient for a blocking conclusion because thermal behavior, frequency
scaling, and background load can create systematic order bias that ordinary
within-run sample counts do not reveal.

### 5. Regression evaluation

Stable workloads should have per-benchmark budgets derived from observed noise
and production significance. A single global 25% threshold is too coarse as a
long-term contract: it can ignore a costly regression in a frequent hot path and
overreact to a noisy, infrequent operation.

### 6. Diagnosis

When a budget fails or an absolute cost looks material, the result should be
reproduced on a controlled environment and profiled. The investigation should
identify the responsible call paths, allocations, lock contention, or scaling
behavior before suggesting a remedy.

### 7. Optimization validation

An optimization should be tested against the targeted workload, the complete
performance suite, runtime correctness, both static checkers, concurrency
invariants, memory use, and maintainability constraints. A local speedup that
shifts cost into startup, memory, teardown, another lifetime, or another Python
version must be reported rather than described as an unqualified improvement.

### 8. Publication and maintenance

Accepted results should be published with raw artifacts, environment metadata,
the exact commit and dependency versions, methodology, interpretation, and known
limitations. A release or scheduled process should refresh results and detect
stale claims.

## Workload taxonomy

The future design should cover four tiers. The tiers answer different questions
and must not be merged into one leaderboard.

### Tier 1: isolated operations

These microbenchmarks protect specific hot paths and help attribute regressions:

- cached singleton lookup;
- first singleton construction;
- transient construction by chain depth;
- scoped construction, cache hit, scope entry, and teardown;
- sync and async resource teardown;
- alias and decoration hops;
- collection resolution by member count;
- generic-key lookup;
- injected wrapper dispatch with explicit and injected arguments;
- override lookup with and without an active override;
- lock and context-local state paths under no contention;
- graph lookup and diagnostic rendering where those operations are user-visible.

Every case should use the smallest graph that isolates the intended cost and an
explicit direct baseline where meaningful.

### Tier 2: representative dependency graphs

Component benchmarks should exercise complete patterns found in applications:

- small graph: approximately 10 bindings and shallow depth;
- medium graph: approximately 100 bindings with mixed lifetimes;
- large graph: approximately 1,000 bindings for startup and tooling scale;
- deep transient and scoped paths;
- wide fan-out and collections;
- protocol, token, alias, generic, decorated, and conditional bindings;
- sync and async resources with deterministic teardown;
- successful resolution and selected actionable error paths;
- warmup of cold singleton graphs;
- graph validation and freeze scaling by nodes and edges.

The later design should derive actual shapes from representative application
architectures rather than treating these approximate sizes as final fixtures.

### Tier 3: end-to-end applications

At least one sync-oriented and one async-oriented application should measure the
cost users experience through a framework boundary. FastAPI is the first required
integration because `depin.ext.fastapi` is public and already tested with real
HTTP clients.

Candidate application workloads include:

- a CPU-light endpoint where DI overhead is visible;
- an endpoint with a request-scoped service graph;
- an endpoint with cached singletons and transient request services;
- an async endpoint with a resource provider and teardown;
- a realistic endpoint with simulated provider work, showing when DI overhead
  becomes negligible relative to application work;
- startup with freeze and optional warmup;
- sustained and burst concurrency.

Results should report total app latency and the paired direct-app baseline. A
framework benchmark without the same framework and equivalent endpoint in the
baseline cannot isolate DI overhead.

### Tier 4: scaling and stress

Scaling cases should identify cliffs rather than produce marketing numbers:

- graph size and edge count;
- dependency depth and fan-out;
- collection size;
- concurrent requests and active scopes;
- singleton first-use contention;
- override nesting;
- sync and async teardown count;
- long-running allocation and retention behavior;
- supported Python language versions and free-threaded builds where meaningful.

Stress tests should use explicit synchronization and controlled workloads, not
sleeps or uncontrolled network services.

## Metrics and production interpretation

### Latency

Microbenchmarks should report an appropriate distribution, not only the fastest
sample. End-to-end workloads should include p50, p95, and p99 when sample count
and methodology make those quantiles meaningful.

### Throughput and CPU

Throughput should be paired with CPU consumption. A higher request rate obtained
by consuming more cores is not an unqualified improvement. Public interpretation
may translate per-operation CPU time into bounded examples such as 100, 1,000,
and 10,000 operations per second, with assumptions shown explicitly.

### Startup

Measure package import separately from container declaration, freeze, validation,
warmup, and framework startup. Users can then distinguish cold-start cost from
request cost.

### Memory and allocations

Measure retained graph memory, singleton-cache growth, active-scope memory,
temporary allocations per resolution, peak warmup memory, and cleanup after
scopes close. The harness must distinguish Python allocator behavior from objects
that remain reachable because of `depin`.

### Scaling

Report curves or tables, not a single large input. Complexity changes and cliffs
are more important than one absolute result.

### Errors and diagnostics

Error and rendering paths are not normally request hot paths, but large graph
operations can affect startup, health tooling, and incident response. Publish
them separately from resolution performance.

## Mandatory direct baselines

Every public workload should include the simplest honest Python implementation
that provides the same behavior without a DI framework. Depending on the case,
that may be:

- direct object access for a cached singleton;
- a direct function or constructor call for a transient;
- explicit construction of the same dependency chain;
- a handwritten context manager with equivalent teardown;
- a normal decorated or wrapper call with the same argument behavior;
- a FastAPI endpoint with the same service work wired explicitly;
- an asyncio implementation using the same event-loop boundary.

The baseline must perform the useful work. An empty function is not a valid
baseline for a provider that constructs objects or manages resources.

Results should show both total cost and the difference from the baseline. When
the difference is near measurement noise, the correct conclusion is that the
overhead was not resolved reliably, not that it was zero.

## Competitor comparison protocol

Competitor results are optional and conditional. They should be included only
when they improve a user's decision and pass the fairness protocol below.

### Eligibility

A competitor should be relevant to the same Python audience, actively maintained
or still materially used, installable on the tested Python version, and capable
of expressing the workload's required semantics. Selection criteria must be
published before results are collected.

The project must not choose only slow competitors, exclude a strong result, or
keep an obsolete version merely because it favors `depin`.

### Semantic equivalence sheet

Each competitor workload should record:

- lifetime and cache behavior;
- validation timing;
- sync or async provider behavior;
- scope creation and disposal;
- resource teardown guarantees;
- graph shape and number of constructed objects;
- decorator, alias, collection, or override semantics where relevant;
- error handling included in the timed path;
- framework integration behavior;
- configuration and optimization switches.

An ordinary correctness test should prove the equivalence sheet before the
adapter is benchmarked.

### Configuration fairness

The primary comparison should use documented, production-appropriate
configuration for every library. If a library has an optional compiled, generated,
or explicitly optimized mode, report it as a separately labeled variant rather
than comparing it silently with another library's default.

Setup outside the timed region must be equivalent. Precompiling one container
while timing another container's validation would be invalid unless the result is
explicitly a startup comparison that includes both setup costs.

### Refusal to compare

If equivalent semantics cannot be represented, label the workload incomparable
and explain why. Do not approximate the missing semantics, weaken correctness, or
convert the absence into a win for `depin`.

### Presentation

Competitor results should be workload-specific. There should be no aggregate
winner, geometric-mean league table, or badge claiming the fastest DI library.
Each table must retain the direct-Python baseline, versions, uncertainty, and a
link to the adapter and raw data.

Unfavorable `depin` results must be published under the same rules. Conclusions
should distinguish a real library cost from differences caused by architecture,
feature guarantees, or implementation language.

### Maintenance

Competitor versions and adapters should be reviewed when the public report is
refreshed. A stale adapter must not be presented as representative of a current
library.

## Measurement environment and reproducibility

The future design must separate two environments:

- **relative PR environment:** base and head run close together on the same
  machine to detect regressions;
- **public absolute environment:** a stable, documented runner suitable for
  longitudinal results and release comparisons.

The design should evaluate tooling that can control or report:

- CPU model, core allocation, frequency behavior, and power mode;
- operating system and kernel;
- Python implementation, version, build flags, allocator, and free-threading;
- dependency and competitor versions;
- process isolation and background load;
- paired independent processes with randomized, interleaved, or counterbalanced
  base/head order;
- warmup and garbage-collection policy;
- timer resolution and sample calibration;
- environment variables and optional accelerators.

Every published result should identify the source commit and carry machine-readable
raw data. A reader should be able to reproduce the harness even if their absolute
numbers differ.

The later design should decide whether the existing tool remains sufficient or a
more controlled benchmark runner and history system is justified. Tool choice
must follow the validity requirements rather than precede them.

## Regression budgets and CI policy

The current same-runner base/head comparison is a sound foundation and should be
preserved. The future system should strengthen it with the following properties:

- per-workload thresholds based on measured noise and impact;
- independent process-level base/head pairs whose execution order is randomized,
  interleaved, or counterbalanced;
- uncertainty calculated over paired base/head differences rather than inferred
  only from samples inside one process;
- both relative and absolute checks where an absolute budget is meaningful;
- minimum sample quality before a result can gate;
- explicit handling of missing, renamed, and new benchmarks;
- failure on malformed or empty reports;
- a visible result for every expected workload;
- repeat or escalation rules for a near-threshold failure;
- separate budgets for latency, memory, and scaling regressions;
- protection against improving one metric by silently degrading another;
- a documented process for intentional performance trade-offs.

The gate must be proven sensitive. A future evidence report should introduce
representative seeded regressions, show the expected jobs fail, then remove the
regressions and show the jobs pass. At least one seeded case should affect a
frequent resolution path, one should affect scaling, and one should affect memory
or allocation behavior when those gates exist.

A new benchmark should not be advertised as regression-protected until the system
has an accepted baseline and a sensitivity demonstration for the relevant class
of failure.

## From finding to optimization

The performance program should define a disciplined optimization decision:

1. The cost is reproduced in a relevant workload.
2. Its production significance is estimated with explicit assumptions.
3. A profile identifies a concrete bottleneck.
4. A hypothesis predicts which metric should improve and which may regress.
5. The proposed change preserves public behavior and type precision.
6. Runtime tests, static checks, concurrency tests, and teardown tests remain
   green.
7. The targeted workload improves beyond noise on repeated runs.
8. The full suite shows no unacceptable displacement into startup, memory, other
   lifetimes, platforms, or Python versions.
9. The result and trade-offs are documented.

Potential investigation areas include plan representation, provider dispatch,
signature introspection, cache lookup, alias and decoration indirection, scope and
teardown bookkeeping, context-local overrides, lock selection, async boundaries,
graph traversal, and allocation churn. This list is not a pre-approved refactor
list. Profiling must establish whether any item matters.

Optimizations that introduce generated code, caching, specialized fast paths, or
more mutable state should receive additional scrutiny for code size, invalidation,
thread safety, free-threading, debugging, and error quality.

## Public performance documentation

The public site should eventually expose a performance section with at least:

- a concise statement of what the project measures and why;
- production-oriented results separated into startup and recurring costs;
- direct-Python overhead baselines;
- end-to-end application results;
- scaling and memory results;
- competitor comparisons that passed the fairness protocol;
- methodology and environment;
- raw-data and harness links;
- reproduction instructions;
- release and result dates;
- limitations and invalid interpretations;
- a history or changelog for material performance changes.

The README should link to the performance section and avoid embedding many numbers
that become stale. Any concise claim in the README must be generated from or
traceable to a current public report.

The project should not publish a number until its workload contract, semantic
validation, raw data, and reproduction instructions are available. Removing or
correcting a misleading result is preferable to preserving a favorable claim.

Documentation should help users estimate their own case. Examples may show how a
per-request overhead translates into CPU at a stated request rate, but must state
that provider work, graph shape, contention, hardware, and framework behavior can
change the result.

## Data lifecycle and freshness

Performance data should be versioned by source commit, library release, Python
version, environment, workload schema, and competitor versions. Changing workload
semantics should start a new series.

The future design should define:

- how raw artifacts are stored and retained;
- which results are release artifacts versus scheduled observations;
- how public pages discover the current accepted dataset;
- how stale results are detected;
- when a competitor adapter is retired;
- how a benchmark correction is disclosed;
- how historical data remains interpretable after renames or methodology changes.

Results should never update silently. A public data refresh should be reviewable
and should explain material movements.

## Failure classification

When a performance check or publication run fails, classify it before changing a
budget:

1. **Real regression:** reproduce, profile, fix, or document an intentional
   trade-off before merging.
2. **Harness defect:** correct setup, timing boundaries, semantic validation, or
   result parsing; invalidate affected published results if necessary.
3. **Environmental noise:** rerun under the documented policy and improve
   isolation if the noise is recurring.
4. **Workload drift:** create a new result series and explain the semantic change.
5. **Dependency or interpreter change:** isolate the external movement and report
   both the environment change and its user impact.
6. **Competitor adapter defect:** withdraw the comparison until equivalence is
   restored.
7. **Budget defect:** revise a threshold only with accumulated noise data and an
   impact argument, never solely to make a failing PR green.

## Acceptance criteria for the future implementation

The future design may refine mechanics, but the completed work should not claim
success until all of the following are demonstrated:

- Every public benchmark has a workload and claim contract.
- Ordinary correctness tests prove semantic behavior independently of timing.
- Direct-Python baselines exist for every published workload.
- The suite separates isolated, component, end-to-end, and scaling evidence.
- Startup, recurring resolution, scoped teardown, injection, async behavior, and
  FastAPI integration have production-relevant coverage.
- Latency, CPU/throughput, memory/allocations, and scaling are measured where each
  can materially affect users.
- Base/head regression gates use per-workload budgets justified by observed noise
  and impact rather than a single unexplained tolerance.
- Blocking relative gates use independent process-level pairs, control base/head
  order bias, and evaluate uncertainty over the paired differences.
- Missing, malformed, empty, renamed, and new benchmark reports are handled
  explicitly.
- Seeded regression evidence proves that speed, scaling, and memory protections
  fail when their guarded behavior regresses.
- A controlled, documented environment produces reproducible public results.
- Raw samples, metadata, harness source, dependency versions, and reproduction
  instructions are public.
- Public documentation explains limitations and does not extrapolate beyond the
  workloads.
- The README links to current evidence without embedding stale marketing numbers.
- Competitors appear only after passing the eligibility, semantic-equivalence,
  configuration, and freshness rules.
- Incomparable competitors or workloads are labeled as such and cannot count as
  wins.
- No aggregate fastest-library claim or misleading overall ranking is published.
- Unfavorable `depin` results remain visible under the same methodology.
- At least one real bottleneck investigation demonstrates the path from benchmark
  to profile, decision, validation, and public interpretation; if no material
  bottleneck is found, that outcome is recorded rather than forcing an
  optimization.
- Any accepted optimization preserves runtime behavior, type precision,
  concurrency guarantees, teardown semantics, error quality, and the core's zero
  runtime dependencies.
- The ordinary formatting, linting, type checking, testing, coverage,
  documentation, packaging, and mutation gates remain green.

## Alternatives considered

### Publish the existing microbenchmark table

This would be fast but misleading. The current numbers come from an uncontrolled
host, lack direct baselines and uncertainty, and include cases designed for
self-regression rather than cross-scenario interpretation. Publishing them would
create confidence without evidence.

### Strengthen only the current regression gate

This would protect development better but still would not tell users what the
cost means in production. Relative CI and public evidence solve different
problems; the project needs both.

### Build a competitor leaderboard first

This optimizes for visibility rather than truth. Without direct baselines,
semantic contracts, realistic apps, and controlled environments, a leaderboard is
easy to manipulate accidentally. Competitor comparisons should be a conditional
output of the evidence system, not its foundation.

### Launch a hosted performance dashboard immediately

A dashboard can make history accessible, but it cannot repair invalid workloads
or misleading metrics. The methodology and initial validated dataset should
precede a permanent observatory. A hosted history system remains a reasonable
later evolution.

## Questions the future design specification must resolve

The proposal fixes the desired evidence standard but leaves these implementation
choices to the design phase:

- Which benchmark runner, statistical model, and history system satisfy the
  validity requirements?
- What stable environment should produce public absolute results?
- Which Python versions and platforms belong in required, scheduled, and public
  matrices?
- Which graph shapes best represent small, medium, and large real applications?
- What direct implementation is valid for each workload?
- Which current benchmarks can support public claims, which require correction,
  and which should remain regression-only?
- How should CPU, allocations, retained memory, and peak memory be measured
  without confusing allocator behavior with retained objects?
- How should sync and async FastAPI applications be driven without measuring an
  unrelated network stack or event-loop setup accidentally?
- What per-workload noise and impact data justify the initial regression budgets?
- How should the system rerun near-threshold results without allowing unlimited
  retries to hide a regression?
- Which competitor libraries are sufficiently relevant and semantically
  comparable for the initial public report?
- Who or what reviews competitor adapters for configuration fairness?
- How should raw artifacts and historical data be stored without bloating the
  source repository?
- What release or scheduled cadence keeps public claims fresh?
- How should an upstream Python, framework, or competitor regression be displayed?
- What evidence would justify a future hosted dashboard?

The design specification should answer these with fresh experiments and primary
tool documentation. It should not assume that the point-in-time numbers in this
proposal remain valid.

## Expected handoff artifacts

Before implementation is authorized, the future work should have these reviewed
inputs:

- a fresh audit of the current benchmark suite, timing boundaries, CI behavior,
  noise, and public documentation;
- a workload inventory and claim classification;
- a design specification resolving the questions above;
- an implementation plan derived from the approved design.

Completion of the future work should provide these outcomes:

- the benchmark, regression, profiling, and documentation implementation;
- an evidence report including normal results, seeded-regression results,
  reproducibility checks, and competitor-equivalence reviews;
- the first public performance report, but only after the evidence standard is
  met.

These are governance prerequisites and deliverables, not a prescribed ordering of
implementation tasks.

The proposal must not be treated as permission to skip design review, select tools
before methodology, optimize without profiling, or publish preliminary numbers as
production claims.

## Decision recorded by this proposal

The project intends to make performance a measured and public part of `depin`'s
quality contract. It will protect applications from meaningful regressions,
investigate material costs through profiling, and pursue optimizations when
evidence justifies them. Public data will include enough methodology and raw
evidence to be audited. Direct Python is the mandatory comparison baseline.
Competitors may be included only when a fair, semantically equivalent comparison
is possible; otherwise the project will refuse to rank them rather than publish a
misleading result.
