# Proposal: compile resolution instead of interpreting it

Date: 2026-09-02
Status: proposed; depends on the competitive performance leadership baseline
Scope: synchronous and asynchronous core resolution, caching, overrides, depth, and teardown registration

## Nature of this document

This proposal defines the outcome and proof required from a future runtime
redesign. It does not select source generation, closure composition, or an
instruction engine without measuring prototypes. That choice belongs to the
design phase and must be supported by accepted evidence.

## Executive summary

`FrozenContainer.resolve()` currently interprets the validated plan for every
node of every resolution. A warm cache hit crosses roughly thirteen Python calls.
A transient provider repeats key lookup, override lookup, lifetime branching,
parameter traversal, construction dispatch, and recursion at every graph node.
The same recursion causes cold resolution to fail near 332 providers even though
`freeze()` accepts and validates much deeper graphs.

There is no dominant function to micro-optimize. The call graph is the cost.

`freeze()` should compile the validated `ResolutionPlan` into provider-specific
sync and async execution programs. The recurring path should execute already-made
decisions, while diagnostics continue to read the declarative resolution plan.
The redesign must remove the cold-depth cliff and preserve every lifecycle,
override, concurrency, error, and teardown guarantee.

## Evidence

The Step 7 profile over 200,000 warm resolutions recorded 2.6 million calls,
distributed across public resolution, lookup, key validation, override lookup,
lifetime dispatch, cache claiming, and construction. No function accounted for
more than fifteen percent of profiled time.

The accepted baseline measured a 20-provider transient chain at 34.548
microseconds, 8.2 times its direct construction. The preliminary competitor
screening placed pure-Python Dishka and Wireup around 6.2 microseconds for an
equivalent empty chain. Both packages precompute provider-specific work. This is
evidence that most of the current dispatch overhead is avoidable without first
introducing native code.

## Goals

- Make the common no-override path execute a specialized program per requested
  key.
- Remove repeated key normalization, plan lookup, parameter discovery, and
  lifetime branching from each node.
- Read context-local override state once per top-level resolution where possible.
- Make cold resolution depth limited by available memory and an explicit project
  budget, not Python recursion depth.
- Preserve exact sync and async construction semantics and teardown order.
- Preserve atomic claim-or-join behavior for cached values under supported
  threaded and free-threaded interpreters.
- Meet the leadership and absolute-overhead gates defined by the competitive
  performance proposal.
- Make no public API change solely for performance.

## Non-goals

- Revalidating the graph during resolution.
- Weakening errors or removing diagnostics to shorten the hot path.
- Making active test overrides as fast as the ordinary production path at the
  expense of ordinary resolution.
- Keeping two production runtimes indefinitely.
- Introducing Rust, Cython, or another core runtime dependency in this body of
  work.

## Proposed architecture

### Declarative plan and executable plan

`ResolutionPlan` remains the immutable, inspectable result of validation. A new
private executable representation is derived from it during `freeze()` and owns
only recurring runtime decisions.

For every resolvable key, the executable representation fixes:

- the provider callable and construction shape;
- dependency slots and argument order;
- lifetime and cache location;
- sync, coroutine, generator, or async-generator behavior;
- decorator, alias, collection, and conditional edges;
- teardown registration behavior; and
- the stable dependency-chain metadata required for errors.

Public diagnostics never reverse-engineer generated code. They continue to read
the validated declarative plan.

### Selection experiment

The design phase implements bounded prototypes of three private strategies over
the same immutable execution model:

1. generated Python functions compiled at freeze time;
2. provider-specific closure composition; and
3. an iterative typed instruction program.

The experiment measures warm hits, transient chains, scoped DAGs, async
providers, active overrides, startup cost, memory, traceback quality, and cold
depth. Generated source is acceptable only when it contains fixed project-owned
templates and refers to user objects through a namespace; user names and reprs
must never be interpolated as executable text.

The fastest strategy that passes all correctness and maintainability gates wins.
A hybrid is allowed when, for example, a compact iterative program solves deep
graphs while a generated leaf resolver produces a materially faster cache hit.

### Fast path and override path

Top-level resolution snapshots the current override stack once. An empty stack
selects the immutable fast executor directly. An active stack selects an
override-aware executor or overlay compiled from the same execution model.

Override correctness is never optional: aliases, decorators, collections, and
every repeated occurrence of an overridden key must observe the same context-
local replacement. The design may accept a slower active-override path because
it is explicitly selected and measured, but it may not fall back to different
semantics.

### Cache and concurrency

Each cached provider receives a stable private cache slot. Cache-hit work should
not repeat plan lookup or lifetime dispatch. Lock elision on an apparent hit is
permitted only if tests and an explicit concurrency argument prove visibility,
single-flight, and failure recovery on the normal and free-threaded interpreters.

If that proof is unavailable, the lock remains. The proposal values a slower
correct cache over a fast data race, but requires the surrounding dispatch to be
removed so the lock's real cost is visible.

Concurrent construction retains the current guarantees:

- one owner constructs a cached value;
- joiners receive the same value or the same construction failure;
- circular wait detection remains actionable;
- a failed construction does not poison later valid attempts; and
- teardown is registered once, by the owner that published the value.

### Iterative construction and teardown

Cold graph traversal uses an explicit stack or a compiled straight-line program,
not one Python recursion layer per provider. Sync and async executors share an
immutable operation model but have separate typed execution paths; the sync path
must not pay an event-loop or awaitability branch at each node.

Teardown records are appended in construction order and drained in the current
reverse order. Generator advancement, async-generator advancement, partial
construction, cancellation, and grouped teardown failures must remain
observationally identical.

## Error behavior

Every failure raised by the compiled runtime remains a `DepinError` or the
documented `ExceptionGroup` for multiple teardown failures. Messages retain the
requested key, dependency chain, active tag, and actionable remedy.

Generated implementation frames must not replace the dependency chain with an
opaque generated-function name. The executable model carries stable provider
metadata so errors do not depend on parsing tracebacks.

Internal compiler failures are freeze-time validation failures, never silently
handled runtime fallbacks. A failure must identify the key whose executable form
could not be produced.

## Verification strategy

The old interpreter is retained as a test oracle during development. Differential
tests generate valid and invalid graphs containing all provider shapes,
lifetimes, aliases, decorators, conditions, collections, scopes, overrides, and
teardowns, then compare values, construction logs, closure logs, and exceptions.

The verification set includes:

- deterministic deep graphs beyond 1,000 providers;
- cancellation and failure at every construction and teardown position;
- synchronized first-use contention with the guard shown to fail when removed;
- normal and free-threaded interpreter jobs;
- sync/async parity without sharing unsafe implementation shortcuts;
- the five-checker consumer corpus and public doctests; and
- complete before-and-after benchmark evidence.

The reference interpreter is removed from production packaging after equivalence
is proved. It may remain in test support when that does not create a second public
behavioral implementation.

## Acceptance criteria

- Cold resolution of the repository's 1,000-provider supported graph succeeds in
  sync and async forms without changing the recursion limit.
- Warm singleton, transient-chain, scoped-cycle, and representative DAG workloads
  reach the competitive leadership target or record a concrete residual owned by
  another accepted proposal.
- No required core workload regresses beyond its existing budget.
- Startup and memory costs remain within newly declared budgets justified by the
  selected compiler strategy.
- All current observable construction, override, concurrency, cancellation,
  teardown, and error contracts pass differential tests.
- Core still has zero runtime dependencies and all supported installations have a
  complete pure-Python implementation.
- Public call sites and inferred types do not change.

## Stop conditions

The redesign is rejected or returned to design if:

- its gain comes primarily from skipping a current guarantee;
- it cannot explain generated failures using stable dependency metadata;
- it solves cache hits while retaining the cold-depth failure;
- it creates unbounded code or memory growth per key;
- it requires a public escape hatch to select the correct engine; or
- it makes the pure-Python package depend on a compiler at installation time.

## Alternatives considered

### Micro-optimize individual helpers

Rejected as the primary approach. The profile has no dominant helper; eliminating
a few calls cannot close a roughly eightfold transient-chain gap.

### Make every cache read lock-free

Rejected without a free-threading proof. It addresses only one portion of a warm
hit and risks the guarantee the current mutex exists to provide.

### Move the current interpreter to Rust unchanged

Rejected at this stage. It would preserve repeated decisions, obscure which
architecture change produced the gain, and add distribution cost before Python
has reached its demonstrated potential.

## Expected handoff artifacts

- profile and prototype evidence for all three execution strategies;
- a reviewed runtime design with the selected executable representation;
- a test-first implementation plan;
- differential, concurrency, depth, memory, and performance evidence; and
- tightened regression budgets after the accepted improvement.

## Decision requested

Accept freeze-time compilation and iterative cold construction as the primary
core performance direction, with the final execution strategy selected by a
measured prototype rather than preference.
