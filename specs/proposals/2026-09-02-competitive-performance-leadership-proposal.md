# Proposal: competitive performance leadership

Date: 2026-09-02
Status: accepted, active
Scope: comparative evidence, performance targets, ergonomics guardrails, and sequencing of optimization work

## Nature of this document

This document proposes a program of future work. It is not an implementation
design or plan. Each optimization it admits still requires refreshed evidence, a
reviewed design, a written implementation plan, and the normal repository gates.

The proposal changes the project's performance objective. Regression protection
and a comparison page are not enough: `depin` should pursue the lowest measured
dependency-injection overhead in the Python ecosystem while retaining its
type-first API and its stronger correctness guarantees.

## Executive summary

The Step 7 evidence system established honest direct baselines and exposed a real
runtime gap. A preliminary same-host screening against Dependency Injector
4.49.1, Dishka 1.10.1, and Wireup 2.12.0 found `depin` behind modern competitors
on warm singleton lookup, a 20-provider transient chain, and a 20-provider scoped
cycle. The screening is not publication-grade and cannot support a ranking, but
the margins are too large to dismiss as noise.

Competitive measurements should therefore move ahead of the Step 9 comparison
page and become engineering input before the Step 8 surface freeze. The public
page may remain a 1.0 commitment; the measurements that make optimization
possible may not.

The target is leadership per semantically equivalent workload, not an aggregate
score. `depin` must be no slower than the fastest eligible implementation within
a calibrated statistical margin, must retain absolute overhead budgets against
direct Python, and must not obtain a favorable number by omitting lifecycle,
teardown, override, validation, typing, or concurrency semantics.

## Current evidence

The accepted Step 7 dataset records these recurring costs on the reference host:

- a warm singleton resolution costs 1.759 microseconds against 92.580 nanoseconds
  for direct access;
- a 20-provider transient chain costs 34.548 microseconds against 2.179
  microseconds for direct construction;
- a scoped cycle that constructs 20 values costs 325.633 microseconds against
  2.948 microseconds for the direct lifecycle;
- the CPU-light FastAPI endpoint adds 81.785 microseconds over its direct route.

A separate exploratory run, deliberately excluded from the accepted dataset,
used current releases and equivalent empty provider graphs. Its directional
medians were:

| Workload | depin | Dependency Injector | Dishka | Wireup |
| --- | ---: | ---: | ---: | ---: |
| Warm singleton, 100-provider frozen graph | 2.76 us | 0.22 us, thread-safe | 1.43 us | 0.41 us |
| Transient chain, 20 providers | 48.15 us | 21.31 us | 6.27 us | 6.21 us |
| Enter scope, construct 20 scoped values, exit | 135.75 us | incomparable | 9.67 us | 13.95 us |

These values are motivation, not publishable results. They were collected in one
interleaved diagnostic process, do not yet have committed competitor adapters,
and do not establish feature equivalence beyond the stated workload. The first
deliverable of this proposal is to replace them with accepted evidence.

The architecture behind the result matters. Dependency Injector implements its
providers as Cython extension types. Dishka and Wireup are pure Python in the
tested distributions but compile provider-specific execution paths instead of
interpreting the dependency graph on every node. That makes runtime structure,
not merely implementation language, the first optimization target.

## Objective

Make `depin` the lowest-overhead Python dependency-injection library for every
required workload that can be compared under equivalent semantics, while making
the ordinary call site at least as ergonomic as it is today.

Leadership has three simultaneous meanings:

1. **Competitive:** the paired median is no slower than the fastest equivalent
   eligible competitor and the uncertainty remains inside the calibrated noise
   allowance.
2. **Absolute:** the increment over direct Python remains inside an explicit
   workload budget. A slow field does not become acceptable because every
   competitor is also slow.
3. **Operational:** improvements reduce CPU or latency in representative
   applications, not only in isolated microbenchmarks.

## Non-negotiable quality constraints

An optimization is rejected if it requires any of the following:

- weaker graph validation or later discovery of a configuration error;
- weaker singleton single-flight, scope isolation, teardown ordering, or
  exception aggregation;
- a global container or implicit process-wide mutable state;
- manual resolution or manual scope plumbing at an ordinary consumer call site;
- additional markers, decorators, or annotations for an already-supported use;
- weaker inferred return types or a new suppression in library or conformance
  code;
- a runtime dependency in the pure-Python core;
- installation failure on a supported platform when an optional accelerator is
  unavailable.

The existing `Container` to `freeze()` to `FrozenContainer` mental model remains
the ergonomic baseline. Existing valid consumer code must continue to type-check
without changes unless a separately accepted Step 8 surface decision says
otherwise.

## Comparative evidence system

### Required competitor set

The initial maintained set is Dependency Injector, Dishka, Wireup, and svcs. A
candidate remains eligible only while it is maintained, installable on a
supported CPython, and able to express at least one required workload without a
private fork.

Versions are pinned in the benchmark dependency group and recorded in every
dataset. Updating a competitor is an explicit calibration change, not an
unreviewed lock-file side effect.

### Equivalence classes

Every adapter records one of three classifications before it is timed:

- **Equivalent:** lifetime, construction count, cache visibility, scope entry and
  exit, resource finalization, async behavior, override visibility, and relevant
  concurrency guarantees match the workload contract.
- **Partial:** the competitor omits a relevant guarantee or operation. The number
  may explain a trade-off but cannot establish leadership.
- **Incomparable:** expressing the workload would require emulation outside the
  library or would measure materially different work. No ratio is calculated.

Feature names are not evidence of equivalence. For example, a non-thread-safe
singleton is not compared with a single-flight singleton as though they offered
the same contract.

### Required workloads

The leadership suite covers:

- warm singleton and scoped cache hits;
- transient and scoped linear chains at multiple depths;
- shared DAGs, aliases, decorators, conditions, collections, and overrides;
- synchronous and asynchronous providers and teardown;
- scope entry and exit with empty, light, and resource-owning graphs;
- cold construction and startup validation;
- FastAPI endpoints with singleton-only, request-scoped, async-resource, and
  representative application work;
- concurrent first use, concurrent scope use, and free-threaded execution where
  the interpreter supports it;
- memory, allocations, scaling, and the maximum supported cold depth.
- Python-call count and call-graph attribution for runtime-strategy diagnosis.

Direct Python remains mandatory beside every accepted comparison.
Python-call counts are diagnostic evidence, not a leadership metric. Reducing
calls cannot replace competitive latency, absolute overhead, secondary budgets,
or representative application results.

### Statistical decision

Competitors and `depin` run as paired samples on the same host, interpreter, CPU
affinity, and harness revision. The harness derives a non-inferiority allowance
from repeated noise calibration for that workload, capped at five percent.

A workload reaches the leadership target only when:

- the `depin` median is no greater than the fastest equivalent competitor's
  median;
- the upper confidence bound of the paired ratio is within the calibrated
  allowance;
- the absolute direct-Python overhead budget passes; and
- no secondary metric named by the workload regresses beyond its budget.

Statistical ties for the lowest median count as shared leadership. A clear win is
reported only when its confidence interval excludes parity. No geometric mean,
points table, or selected subset may be used to claim the fastest library.

## Ergonomics contract

Performance work must preserve or improve these observable properties:

- provider registration remains type-driven;
- resolved and injected values retain their precise static types;
- common FastAPI handlers retain a single parameter annotation per dependency;
- scopes and resource teardown remain automatic in supported integrations;
- errors continue to identify the failing key and dependency chain;
- installation of the pure-Python implementation remains a normal wheel install.

The consumer conformance corpus is the regression gate for type ergonomics.
Example diff size, required setup calls, public symbols, and application wiring
steps are reviewed in every optimization design so a speedup cannot quietly move
work onto the user.

## Program sequence

1. Land competitor adapters and accepted baseline evidence.
2. Execute the compiled-runtime proposal against the core gaps.
3. Recalibrate and execute the FastAPI proposal against the remaining
   application overhead.
4. Evaluate the native-accelerator proposal only against the optimized Python
   implementation.
5. Publish the Step 9 comparison page from fresh accepted data.

The sequence prevents Rust from receiving credit for algorithmic work Python can
do, and prevents framework overhead from hiding a successful core optimization.

## CI and release policy

The existing base-versus-head regression gate remains the per-commit defense.
Pinned competitor comparisons run in a dedicated calibration workflow and before
closing any performance proposal. They do not run as an unpinned network-facing
PR gate.

A release that claims a performance improvement includes:

- accepted before-and-after raw samples;
- the current competitor dataset for affected workloads;
- profiles explaining the change;
- correctness, typing, concurrency, and free-threading results; and
- a generated public interpretation that includes unfavorable results.

Budgets may be tightened after an accepted improvement. They may not be widened
merely to make a regression or competitor loss pass.

## Acceptance criteria

- Every required workload has a direct implementation and an equivalence record
  for each attempted competitor.
- At least Dependency Injector, Dishka, and Wireup have maintained adapters for
  the core workloads they can express.
- Comparative runs are reproducible from the repository and record dependency
  versions, source revisions, environment, and raw paired samples.
- The harness distinguishes equivalent, partial, and incomparable results in its
  data model and generated documentation.
- Relative leadership and absolute overhead are evaluated independently.
- The public documentation never claims an aggregate winner.
- The three optimization proposals use these results as their entry and exit
  evidence.

## Alternatives considered

### Keep comparisons for Step 9

Rejected. A comparison page after the surface freeze can describe the gap but
cannot guide the architectural work needed to close it.

### Optimize only against direct Python

Rejected. Direct Python is the correct theoretical baseline but does not reveal
which costs peer libraries have already demonstrated are avoidable.

### Optimize to a single aggregate score

Rejected. Weighting workloads hides losses, rewards benchmark selection, and
cannot describe whether a particular application shape is safe to adopt.

### Relax semantics until depin wins

Rejected. That would replace the product rather than improve it.

## Expected handoff artifacts

- a design for competitor adapters and the paired statistical gate;
- accepted baseline evidence and an updated generated performance report;
- separate reviewed designs and plans for the runtime, FastAPI, and optional
  native work;
- evidence reports that close or reject each optimization proposal; and
- a fresh Step 9 comparison page generated from accepted data.

## Primary references

- [Dependency Injector providers](https://python-dependency-injector.ets-labs.org/providers/)
- [Dependency Injector changelog](https://python-dependency-injector.ets-labs.org/main/changelog.html)
- [Dishka technical requirements](https://dishka.readthedocs.io/en/latest/requirements/technical.html)
- [Wireup benchmark methodology and results](https://maldoinc.github.io/wireup/latest/benchmarks/)

## Decision requested

Accept performance leadership, semantic equivalence, and unchanged ergonomics as
the governing quality contract for the remaining pre-1.0 performance work.
