# Proposal: compile resolution instead of interpreting it

Date: 2026-09-02
Status: deep sync transient instructions accepted; complete sync calls selected next
Scope: synchronous and asynchronous core resolution, caching, overrides, depth, and teardown registration

## Nature of this document

This proposal defines the outcome and proof required from the remaining runtime
experiments and any resulting redesign. It does not select source generation,
closure composition, or an instruction engine without measuring prototypes.
That choice belongs to a future design phase and must be supported by accepted
evidence.

## Executive summary

`FrozenContainer.resolve()` still interprets recurring decisions from the
validated plan. A warm cache hit crosses multiple Python helpers. A transient
provider repeats key lookup, override lookup, lifetime branching, parameter
traversal, and construction dispatch at every graph node.

The runtime now uses explicit-stack sync and async executors for deep graphs, so
the original cold-resolution failure near 332 providers is closed. Remaining
experiments must preserve that support instead of treating depth as unfinished
work.

There is no dominant function to micro-optimize. The call graph is the cost.

`freeze()` should compile the validated `ResolutionPlan` into provider-specific
sync and async execution programs. The recurring path should execute already-made
decisions, while diagnostics continue to read the declarative resolution plan.
The redesign must reduce recurring dispatch while preserving deep-graph support
and every lifecycle, override, concurrency, error, and teardown guarantee.

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

## Experiment decision: 2026-09-04

The bounded runtime experiment added an empty override-stack snapshot and a
protected read for a hot synchronous cached-singleton value. The cached
singleton improved from 4.910 to 4.665 microseconds (-5.0%), and the no-active-
override path improved from 4.799 to 4.589 microseconds (-4.4%). Guard
workloads changed by +3.3% for active overrides, +4.2% for aliases, -2.5% for
decorators, and +1.0% for transients. Ninety focused tests and the ruff,
basedpyright, and mypy gates were green.

This is a NO-GO: neither required path reached the >=10% improvement gate. No
budget or code from this experiment is accepted. The next selected bounded
experiment is freeze-time composition of closures for synchronous transient
chains, subject to measurement. FastAPI remains subsequent to the core work,
and the native path remains NO-GO.

## Experiment decision: 2026-09-08 closure composition

The bounded closure-composition experiment compiled shallow synchronous
transient function-provider chains during `freeze()`. A five-repetition paired
comparison against `a4a7513` reduced the 20-provider transient-chain median from
34.125 to 10.558 microseconds, a decisive -69.13% interval of [-69.77%,
-68.65%]. Python calls fell from 181 to 47 per resolution. The profile retained
one root lookup per resolution while removing per-node resolution, parameter,
and construction dispatch; the 20-provider plan retained 20 closure objects
with a shallow size of 3,200 bytes.

The gain did not satisfy the experiment's system-wide acceptance rule.
Transient-chain allocations increased from 52 to 72 blocks (+38.46%), from
4,904 to 6,184 allocated bytes, and from 5,688 to 6,968 peak bytes. Warm cached
singleton resolution regressed from 1.849 to 2.090 microseconds (+13.44%,
[+9.54%, +15.61%]); a two-decorator singleton regressed from 1.864 to 2.101
microseconds (+13.45%, [+9.57%, +16.27%]); and the no-active-override path
regressed from 1.828 to 2.102 microseconds (+14.77%, [+11.58%, +19.02%]). The
active-override path remained within budget at +2.61% [-0.64%, +3.38%]. Strict
work budgets also failed when cached resolution rose from eight to nine calls,
request-shaped scope work from 88 to 89, and scope-cycle work from 358 to 359.
Transient-depth scaling exceeded its budget with a +104.76% change in the
worst size-to-size growth ratio.

Retained memory stayed bounded: containers of 100 and 1,000 providers each
retained 112 additional bytes (+0.32% and +0.03%). The correctness suite,
including 1,000-provider sync and async depth coverage, was green before the
measurement. These passing guards do not offset the allocation and unrelated
hot-path regressions.

This is a NO-GO. No closure compiler, routing change, prototype-only test, or
new budget is retained. The next bounded experiment is one generated Python
function per eligible shallow synchronous transient resolution. It must avoid
adding work to ineligible cached and override paths and must measure whether a
single generated call graph removes the closure-chain allocation cost. The
denser typed instruction program remains the subsequent private strategy; the
native path remains NO-GO.

## Experiment decision: 2026-09-08 generated functions

The next bounded prototype generated one Python function per eligible shallow
synchronous transient resolution. Generated source contained only fixed
project-owned syntax and integer indexes into a namespace tuple; no provider
name, key, tag, annotation, or representation was interpolated. Eligibility was
limited to function providers whose complete dependency subgraph was transient,
synchronous, positional-or-keyword, and no deeper than 200 providers. Plans at
the runtime's 256-provider recursive threshold retained the iterative executor,
as did defaults, optional or keyword-only parameters, cached dependencies,
classes, resources, aliases, collections, async providers, and any active
override.

A five-repetition paired comparison of `c196d7c` against the prototype-free
`d5d8d03`, with seed 20260902, reduced the isolated 20-provider transient-chain
median from 34.405 to 4.687 microseconds. The paired change was -86.39% with a
decisive [-86.60%, -85.79%] interval. In the competitive workload the generated
path measured 4.618 microseconds, versus 2.267 for direct Python, 7.167 for
Dishka, 7.465 for Wireup, and 17.009 for Dependency Injector. Python calls fell
from 181 to 28 per resolution. Allocation size fell from 4,904 to 1,224 bytes
(-75.04%); blocks fell from 52 to 12 and peak bytes from 5,688 to 2,008.

The earlier 34.125-microsecond baseline was a single-run diagnostic used to
decide whether to pay for the paired collection; 34.405 microseconds is the
independently recalibrated median of the five accepted baseline repetitions.
The raw repetitions, environment, generated report, gate output, revision
identities, and verification commands are retained together under
`benchmarks/results/2026-09-08-generated-sync-functions/`.

The routing avoided the closure prototype's unrelated regressions. Cached
singleton resolution changed from 1.876 to 1.837 microseconds (-2.23%), the
no-active-override path from 1.832 to 1.839 microseconds (+0.43%), and the active
override path from 3.868 to 4.022 microseconds (+3.98%); all remained within
their existing budgets. Cached, request-scope, and scope-cycle work stayed
exactly at 8, 88, and 358 calls, and their allocation counts did not change.
Every latency, allocation, work, retained-memory, and scaling gate passed.

Freeze workloads remained within budget: the paired changes were +1.71% at 10
providers, +2.30% at 100, and +4.45% at 1,000. The generic retained-container
measurements added 112 bytes at 100 and 1,000 providers (+0.32% and +0.03%). The
generated executable itself retained 18,400 shallow bytes for a 20-provider
chain and, because each root currently owns its namespace tuple and nested code,
505,600 shallow bytes for 160 providers. Generation is therefore accepted only
inside the existing shallow-plan and 200-expression limits. Sharing or otherwise
deduplicating executable storage is a prerequisite for expanding the strategy,
not a reason to broaden those limits now.

Security review then found that synthetic signatures could disagree with the
real function argument order and that a small shared DAG could expand into an
exponential source expression. Revision `2ea58f5` made exact real parameter
name/order/quantity matching an eligibility condition, rejected synthetic
varargs and positional/keyword-only mismatches, and added per-program plus
cumulative source-generation budgets before concatenation. The original
16-provider reproducer fell from a 170.6 MB peak to 1.36 MB and stopped
generation after provider 9. A focused five-pair rerun against `d5d8d03`
covered every performance path changed by the hardening: transient latency was
-86.47% [-87.24%, -85.93%], freeze changed +1.94% at 10 providers, +0.22% at
100, and -0.57% at 1,000, while retained and deterministic results preserved
the full-matrix result. Every applicable gate passed. The complete `c196d7c`
matrix and the focused `2ea58f5` hardening dataset are retained separately so
the evidence never presents the earlier revision as the final one.

This bounded experiment is a GO. Its implementation, differential tests, and
complete paired evidence are retained.

The first expansion prerequisite then shared one immutable provider namespace
across every generated program. That removed the quadratic tuple snapshots, but
not the duplicated nested bytecode: unique executable storage measured 12,120,
132,440, and 298,280 bytes at 20, 100, and 160 providers. The corresponding
growth exponent was 1.54 from 20 to 160 rather than linear. A one-run diagnostic
kept the target path at 4.589 microseconds and the 10/100/1,000-provider freeze
medians at 384.496 microseconds, 3.538 milliseconds, and 36.842 milliseconds,
all consistent with the accepted intervals.

Expanding generated functions across the full runtime matrix is therefore a
NO-GO. The measured shallow transient path remains as a strictly bounded leaf
fast path, with its compiler budgets unchanged. A linear dense instruction
program is selected as the complement for deep graphs and for the cached,
scoped, resource-owning, asynchronous, alias, collection, decorator, default,
and active-override paths. Generated functions do not become the general
runtime representation unless a later design removes their duplicated code
without giving back the accepted latency and allocation result.

## Experiment decision: 2026-09-08 dense sync transient instructions

The first dense prototype compiles one immutable `Operation` tuple in plan
order, one integer dependency tuple per provider, and one key-to-index map. Its
executor walks those indexes with local explicit stacks. It stores no transitive
schedule per key and does not memoize repeated transient dependencies. Exact
parameter callability is captured by `ParamSpec` while the provider signature
is already inspected, so executable compilation does not repeat
`inspect.signature`.

Stored operations and edges were exactly 20/19, 100/99, 160/159, and 1,000/999.
Measured representation bytes were 2,832, 15,208, 21,448, and 141,072 at those
sizes; the 20-to-160 exponent was 0.974. On a 20-provider chain, the isolated
instruction executor measured 14.052 microseconds versus 33.465 for the public
interpreter, 4.161 for the generated public path, and 2.040 for direct Python.
It used 22 Python calls and retained 12 blocks / 1,248 bytes for one operation,
versus 181 calls and 54 blocks / 4,824 bytes for the interpreter. The generated
fast path remains superior for this bounded shape.

The first production routing is deliberately narrower than compiler
eligibility: only synchronous transient roots in plans of at least 256 providers
use dense instructions, and only when no override is active. Shallow plans keep
the generated fast path; unsupported deep shapes and active overrides keep the
iterative interpreter. At depth 1,000 the public instruction route measured
724.930 microseconds against 2,617.506 for the interpreter (-72.3%). Compiling
the deep executable changed `freeze()` from 34.051 to 36.166 milliseconds
(+6.21%). Both `resolve()` and synchronous `inject()` select the instruction
route; the async executor remains unchanged.

This slice is a GO. The operation model is linear, immutable, faster than the
deep interpreter, and preserves the bounded generated leader. The next slice
encodes the complete synchronous call contract and override-aware execution;
cached/scoped claims and resource lifecycles remain outside the instruction
program until their dedicated correctness phases.

## Goals

- Make the common no-override path execute a specialized program per requested
  key.
- Remove repeated key normalization, plan lookup, parameter discovery, and
  lifetime branching from each node.
- Read context-local override state once per top-level resolution where possible.
- Preserve the existing explicit-stack support for graphs beyond Python's
  recursion limit.
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

The selection experiment includes a dense private provider-ID representation as
either a shared representation or a controlled sub-variant. `freeze()` assigns
integer IDs and cache slots, and the recurring path reads immutable tuple- or
array-backed tables instead of resolving `(key, tag)` pairs again. The IDs remain
private: diagnostics, errors, and the public API continue to use the original
typed keys. The experiment must measure this layout against a keyed control
rather than assuming integer indexing is faster.

Public diagnostics never reverse-engineer generated code. They continue to read
the validated declarative plan.

### Selection experiment

The design phase implements bounded prototypes of three private strategies over
the same immutable execution model:

1. generated Python functions compiled at freeze time;
2. provider-specific closure composition; and
3. a denser typed instruction program that refines or replaces the current
   explicit-stack executor.

Every prototype is compared with the current interpreter, direct Python, and the
eligible competitors under the accepted equivalence contracts. The experiment
matrix includes:

- warm and cold singleton resolution;
- transient chains at multiple depths and fan-out/shared DAGs;
- collections of 10 and 100 providers;
- empty, light, and resource-owning scope entry and exit;
- inactive and active overrides;
- positional and keyword parameter resolution;
- synchronous and asynchronous providers; and
- startup cost, traceback quality, and cold depth.

Each row records latency, Python-call count and call-graph attribution,
allocations per resolution, peak and retained memory, freeze-time cost, and the
size of the executable representation per provider. Allocation evidence must
identify temporary argument dictionaries and other per-node objects; a prototype
may retain them only where Python call semantics require them and the measured
trade-off is accepted. Diagnostic call or allocation reductions do not substitute
for latency, absolute-overhead, or application evidence.

Generated source is acceptable only when it contains fixed project-owned
templates and refers to user objects through a namespace; user names and reprs
must never be interpolated as executable text.

The fastest strategy that passes all correctness and maintainability gates wins.
A hybrid is allowed when, for example, a compact iterative program solves deep
graphs while a generated leaf resolver produces a materially faster cache hit.
Before selection, the representative FastAPI application workloads must also
remain within their existing regression budgets. A core strategy is not accepted
solely because it wins isolated microbenchmarks.

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

The current runtime already uses explicit stacks when graph depth requires them.
A selected strategy retains that behavior or replaces it with a compiled
straight-line program, never one Python recursion layer per provider. Sync and
async executors share an immutable operation model but have separate typed
execution paths; the sync path must not pay an event-loop or awaitability branch
at each node.

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

- Existing sync and async resolution of the repository's 1,000-provider
  supported graph remains successful without changing the recursion limit.
- Warm singleton, transient-chain, scoped-cycle, and representative DAG workloads
  reach the competitive leadership target or record a concrete residual owned by
  another accepted proposal.
- No required core workload regresses beyond its existing budget.
- Startup and memory costs remain within newly declared budgets justified by the
  selected compiler strategy.
- The selected strategy publishes a current-interpreter versus optimized-Python
  table covering latency, Python calls, allocations, retained memory, freeze cost,
  and executable size for the required experiment matrix.
- Representative FastAPI application workloads do not regress beyond their
  calibrated budgets.
- All current observable construction, override, concurrency, cancellation,
  teardown, and error contracts pass differential tests.
- Core still has zero runtime dependencies and all supported installations have a
  complete pure-Python implementation.
- Public call sites and inferred types do not change.

## Stop conditions

The redesign is rejected or returned to design if:

- its gain comes primarily from skipping a current guarantee;
- it cannot explain generated failures using stable dependency metadata;
- it regresses existing deep-graph support or introduces a new depth cliff;
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

## Active decision

Retain the bounded generated synchronous transient path. The 2026-09-04
cached-runtime experiment and the 2026-09-08 closure-composition experiment are
NO-GO; the generated-function experiment is a GO. Expand the winning generated
representation across the required matrix while deduplicating its executable
storage and preserving the iterative deep-graph path. Final runtime selection
remains pending that expansion; the denser typed instruction strategy remains
the planned complement or fallback.
