# Step 4, cycle 2 — eager warmup, health checks, and the named-scopes decision: design

Date: 2026-08-31
Baseline: 0.11.0 at `d2b8ceb`
Target: 0.12.0
Status: approved, pending implementation plan

## Goal

Close the three Step 4 deliverables that read a validated plan without changing
it.

**Eager warmup** constructs every singleton at boot. `di.warmup()` and `await
di.awarmup()` walk the plan in resolution order, build what is not built
already, and return a report over the nodes they touched. A provider that
fails to construct fails at startup, where a deployment can roll back, instead
of on the first request.

**Health checks** let a binding declare how to verify the value it produced.
`bind(Database, check=ping)` records the callable; `di.checks()` exposes what is
declared, and `di.health()` / `await di.ahealth()` run them and return a report
a readiness endpoint can serialise.

**Custom named scopes** are decided here, against the criterion the roadmap set:
they ship only if Steps 3 and 4 surface a concrete use case the three fixed
scopes cannot express. The decision and its reasoning are recorded below.

Neither warmup nor health checks alter the `ResolutionPlan`. That is why they
ship together and after the cycle that does alter it: everything here is a read
over a graph `freeze()` has already validated.

## What changes for an existing graph

| Before | After |
| --- | --- |
| A singleton is constructed on first resolution. | Unchanged. `warmup()` is opt-in and constructs nothing that resolution would not. |
| A binding declares no way to verify its value. | It may declare `check=`. |

Both are additions. A graph that froze at 0.11.0 freezes unchanged, and a
container that never calls `warmup()` or `health()` behaves exactly as it did.

## Measurements

Four questions were measured against the tree at `d2b8ceb` rather than assumed.

**A singleton's cache entry is observable without new machinery.**
`FrozenContainer._resolve_cached_sync` caches under `(spec.key, spec.tag)` on
the root frame, and `ScopeFrame.lookup` reports absence as `MISSING` without
raising. Reading `self._root.lookup((spec.key, spec.tag))` therefore
distinguishes a singleton already built from one this call must build, using
the frame API that already exists.

**`needs_async` is already per-spec, and that is the rule to match.**
`resolve` raises `AsyncInSyncContextError` when *the spec it was asked for* has
`needs_async`, not when the graph contains an async provider anywhere. A graph
with an async singleton reports `needs_async` on that singleton and on every
singleton depending on it, measured directly off the plan. `warmup()` therefore
gates on the singletons it would construct, which is the existing rule applied
to a set of keys rather than to one.

**`check: Callable[[T], object]` infers `T` from the binding.**
`bind(Database, check=ping)` with `def ping(db: Database) -> None`,
`def is_open(db: Database) -> bool`, and `async def aping(db: Database) -> None`
are all clean under `mypy --strict` and `basedpyright --strict`, as is
`bind(make_database, check=ping)` where the key comes from a factory's return
annotation, and `value(port, 8080, check=lambda value: value > 0)`. An `async
def` check type-checks because a coroutine is an `object`; whether a check can
run without an event loop is therefore a runtime question, answered by
`inspect.iscoroutinefunction`.

**A decorated singleton is two singleton nodes.** After
`bind(Config).decorate(Config, Loud)`, the plan holds `Config (undecorated)` and
`Config`, both singletons. Warming both is idempotent — building the public node
builds the inner one as its parameter — and a generator singleton warmed twice
opens once and closes once, measured through `close()`.

## Public surface

Five methods, five types, one keyword argument.

| Symbol | Role |
| --- | --- |
| `FrozenContainer.warmup` / `awarmup` | Construct every singleton; return a `WarmupReport`. |
| `WarmupReport` | Which singletons this call built, and which were already built. |
| `BindingCollector.bind` / `value` gain `check=` | Declares how to verify the produced value. |
| `FrozenContainer.checks` | The declared checks, as data. |
| `FrozenContainer.health` / `ahealth` | Run them; return a `HealthReport`. |
| `HealthCheck`, `HealthResult`, `HealthReport` | The check as declared, one outcome, and the set of outcomes. |

```python
def warmup(self) -> WarmupReport: ...
async def awarmup(self) -> WarmupReport: ...


def checks(self) -> tuple[HealthCheck, ...]: ...
def health(self) -> HealthReport: ...
async def ahealth(self) -> HealthReport: ...
```

```python
def bind[T](
    self,
    source: type[T] | Callable[..., T],
    *,
    scope: Scope = Scope.SINGLETON,
    provides: type[object] | None = None,
    tag: str | None = None,
    when: Condition | None = None,
    check: Callable[[T], object] | None = None,
) -> Self: ...


def value[T](
    self,
    token: Token[T],
    value: T,
    *,
    when: Condition | None = None,
    check: Callable[[T], object] | None = None,
) -> Self: ...
```

The runner methods are named `health` / `ahealth` rather than `check` /
`acheck`, because `check()` and `checks()` differ by one character and name
different things — one runs, the other describes.

## Data model

### Warmup

No new field anywhere. `warmup` reads `ResolutionPlan.order`, filters to
`Scope.SINGLETON`, and reports over the same `GraphNode` the graph view already
exposes:

```python
@final
@dataclass(frozen=True, slots=True)
class WarmupReport:
    constructed: tuple[GraphNode, ...]
    cached: tuple[GraphNode, ...]
```

Both tuples are in resolution order. Reusing `GraphNode` is what the roadmap
means by "a report built on the Step 2 graph structure": a caller that wants the
key, the scope, the shape, or the dependencies of a warmed node reads them off
the node it already knows.

### Health checks

`BindRecord` and `ProviderSpec` each gain one field:

```python
@dataclass(frozen=True, slots=True)
class BindRecord:
    ...
    check: object | None = None


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    ...
    check: object | None = None
```

The field is `object` for the reason `source` is: the plan is built from
heterogeneous records and the callable's parameter type is erased by the time it
reaches the plan. `depin._core.typeguards` narrows it at the one boundary that
calls it.

The three public records:

```python
@final
@dataclass(frozen=True, slots=True)
class HealthCheck:
    key: ProviderKey
    tag: str | None
    needs_async: bool


@final
@dataclass(frozen=True, slots=True)
class HealthResult:
    key: ProviderKey
    tag: str | None
    healthy: bool
    error: Exception | None


@final
@dataclass(frozen=True, slots=True)
class HealthReport:
    results: tuple[HealthResult, ...]

    @property
    def healthy(self) -> bool: ...
```

`HealthCheck.needs_async` is true when the checked provider needs async
resolution or the check itself is a coroutine function — the two reasons
`health()` cannot run it.

## Semantics

### Warmup

| Situation | Behaviour |
| --- | --- |
| `warmup()` on a graph of sync singletons | Constructs each in resolution order; reports them under `constructed`. |
| A singleton already resolved | Reported under `cached`; not rebuilt. |
| `warmup()` called twice | The second call reports everything under `cached`. |
| A scoped or transient provider | Not touched. A scoped value belongs to a scope, and a transient one is never cached, so neither has a boot-time instance to build. |
| A singleton whose construction raises | The exception propagates unchanged. A partially warm container is a startup to abort, not a state to report. |
| A singleton that needs async | `warmup()` raises `AsyncInSyncContextError` **before constructing anything**, naming the keys. `awarmup()` builds it. |
| A decorated singleton | Both the wrapper node and `Underlying(key, 0)` are singletons, and both are reported. Building the public node builds the inner one as its parameter, so nothing is constructed twice. |
| A generator or context-manager singleton | Entered once; its teardown runs at `close()` / `aclose()` as it always did. |
| An active `override()` | Honoured: warmup resolves through the same lookup every other resolution uses. An overridden provider is transient, so nothing is cached and the node is still reported under `constructed` — the call did construct it. |
| Concurrency | The `constructed` / `cached` split is read before each construction, so two threads warming at once may classify a node differently. Construction itself stays single-flighted; only the report's labelling is best-effort. `warmup()` is a boot operation. |

### Health checks

| Situation | Behaviour |
| --- | --- |
| `checks()` | The declared checks, in resolution order. It resolves nothing and runs nothing. |
| `health()` | Resolves each checked provider and calls its check. A check that returns anything but `False`, and does not raise, is healthy. |
| A check that raises | `healthy=False`, with the exception on `HealthResult.error`. Every check runs; one failure never hides another. |
| A check that returns `False` | `healthy=False`, `error=None`. Exactly `False` — a `0` or an empty string is a value, not a verdict. |
| A check whose provider fails to resolve | The resolution error propagates. A container that cannot build its provider is misused, not unhealthy. |
| An async provider or an `async def` check | `HealthCheck.needs_async` is true; `health()` raises `AsyncInSyncContextError` naming the keys, before running anything. `ahealth()` awaits them. |
| A sync check that returns an awaitable anyway | `InvalidProviderError`. `health()` has no loop to await it in, and silently discarding a coroutine is how a check passes without running. |
| A check on a scoped binding | Runs inside an active scope like any scoped resolution; outside one it raises `OutsideScopeError`. |
| A check on an inactive conditional binding | Absent. An inactive binding is in no plan, so it declares nothing. |
| A check on a decorated binding | Rides with the binding it was declared on, so it verifies the undecorated value and `HealthCheck.key` is `Underlying(key, 0)`. A decorator that wants its own check declares one on itself. |
| `HealthReport.healthy` | True when every result is healthy. An empty report is healthy: nothing declared a check, so nothing failed. |

## Errors

| Trigger | Error | Message names |
| --- | --- | --- |
| `warmup()` where a singleton needs async | `AsyncInSyncContextError` | the keys, and that `awarmup()` drives them |
| `health()` where a check needs async | `AsyncInSyncContextError` | the keys, and that `ahealth()` drives them |
| `check=` is not callable | `InvalidProviderError` | the value, and that a check is called with the produced value |
| A sync check returns an awaitable | `InvalidProviderError` | the key, and that an async check requires `ahealth()` |

No new exception type. Every trigger is an existing one raised for its existing
reason, which is what keeps a single `except DepinError` sufficient.

## Custom named scopes — rejected

The roadmap admits named scopes only if Steps 3 and 4 surface a concrete use
case the three fixed scopes cannot express. None appeared.

**Step 3** shipped aliasing, optional dependencies, collection injection,
generic keys, and the `provides` signature repair. Every one is a statement
about *what a key resolves to*, and each landed as an ordinary node under one of
the three existing lifetimes. An alias and a collection cache nothing and are
transient; their members keep whatever lifetime they were bound with. No
deliverable asked for a lifetime that outlives a scope but not the container, or
that nests below a scope.

**Step 4, cycle 1** shipped decoration and conditional activation. Decoration
was the one place a fourth lifetime could plausibly have been needed — a wrapper
could in principle live longer or shorter than what it wraps — and the design
measured that it must not: a wrapper occupying the public key with a different
lifetime from the binding it wraps would need its own captivity rule, and every
use identified wants the wrapper to live exactly as long as the value it
decorates. Conditional activation has no lifetime at all; it decides membership
of the plan at `freeze()`.

**Step 4, cycle 2** — this one — confirms it. Warmup partitions the plan by
`Scope.SINGLETON` and needs no other distinction: a lifetime bounded by boot is
the singleton, and a lifetime bounded by a request is the scope. Health checks
run against whatever lifetime their binding already has.

The cases named for custom scopes in other containers — a session scope, a job
scope, a tenant scope — are all "a scope that some code opens and closes", which
`FrozenContainer.scope()` / `ascope()` already are. What a named scope adds is
the ability to have *two of them open at once and pick between them by name*.
Nothing in Steps 3 or 4 needed that, and nothing in `depin.ext.fastapi` needed
it: a request scope is the only scope an ASGI application opens.

**Decision: rejected, and not revisited before 1.0.** The cost of shipping it
would be a fourth entry in `Scope`, a name on every registration and every
resolution, a scope-resolution order to specify, and a captivity rule between
named scopes — permanent surface, for a case no deliverable produced. The cost
of not shipping it is that a consumer needing two concurrent named lifetimes
must open nested scopes and key by value instead. Adding named scopes after 1.0
is a compatible addition; removing them would not be, which is the asymmetry
that settles it.

## Module layout

Two new modules. Both operate over a validated plan and neither can alter one.

| Module | Change |
| --- | --- |
| `_core/warmup.py` | **New.** `WarmupReport`, and the walk that builds every singleton. |
| `_core/health.py` | **New.** `HealthCheck`, `HealthResult`, `HealthReport`, and the runners. |
| `_core/spec.py` | `BindRecord.check`; `ProviderSpec.check`. |
| `_core/bindings.py` | `check=` on `bind` and `value`. |
| `_core/providers.py` | Carry `check` from record to spec; reject a non-callable one. |
| `_core/decoration.py` | The fold carries `check` onto the `Underlying` node and gives wrappers none of their own. |
| `_core/typeguards.py` | `as_check`, narrowing the plan's `object` to a callable at the one place that calls it. |
| `_core/frozen.py` | `warmup`, `awarmup`, `checks`, `health`, `ahealth`, each delegating. |
| `depin/__init__.py` | Exports the five new types. |

`graph.py`, `construct.py`, `diagnostics.py`, `render.py`, `scope.py`,
`teardown.py`, `injection.py`, `overrides.py`, `introspect.py`, and `markers.py`
are unchanged. Nothing here adds a `ProviderShape`, a validation rule, or a plan
node.

## Verification

- `tests/unit/test_warmup.py`: an empty container; a graph of sync singletons;
  the report's two tuples and their order; idempotence across two calls; a
  scoped and a transient provider left untouched; a construction failure
  propagating unchanged and leaving earlier singletons built; a generator
  singleton entered once and drained once; a decorated singleton reported as
  both nodes; `warmup()` refusing an async singleton before constructing
  anything, proved by asserting that no side effect of an earlier singleton ran;
  `awarmup()` driving the same graph.
- `tests/unit/test_health.py`: a check that passes, one that raises, one that
  returns `False`, one that returns `None`; every check running despite an
  earlier failure; `checks()` resolving and running nothing, asserted through a
  provider with a side effect; `HealthReport.healthy` over mixed results and
  over an empty report; an async check and an async provider under `ahealth()`;
  `health()` refusing both, naming the keys; a sync check returning an awaitable;
  a non-callable `check=`; a check on a scoped binding inside and outside a
  scope; a check on a decorated binding keyed by `Underlying`; no check for an
  inactive conditional binding.
- `tests/unit/test_graph_properties.py`: the generative model gains a `checks`
  field, drawn last with a default, so `checks()` and `health()` are exercised
  over arbitrary validated graphs — including the invariant that `warmup()`
  followed by `health()` leaves the plan and the graph view unchanged.
- `tests/typing/test_conformance.py`: `assert_type` over `warmup()`,
  `checks()`, `health()`, and `bind(..., check=...)` inferring the bound type.
- `tests/unit/test_public_api.py`: the five new exports.
- `benchmarks/`: `warmup()` over a chain of 1000 singletons.
- `examples/warmup/main.py` and `examples/health/main.py`, listed in
  `examples/README.md` and executed by `tests/integration/test_examples.py`.
- `tests/integration/test_fastapi_ext.py`: `awarmup()` in a lifespan, and a
  readiness route returning `ahealth()`'s report.
- `docs/guide/operations.md`, a new page covering both, in the `mkdocs.yml` nav,
  with `pycon` doctests.
- `docs/reference/` gains the five types.
- The mutation gate in CI covers both new modules.

## Acceptance criteria

- `warmup()` on a graph whose singletons include an async provider raises rather
  than blocking an event loop, matching the `resolve` / `aresolve` rule, and
  constructs nothing before it raises.
- A provider may declare a verification callable, and `checks()` exposes them.
- The named-scopes decision is recorded with the criterion that produced it,
  before the freeze.
- `depin/` carries exactly the three suppressions it carries at `d2b8ceb`.
- The five gates and `mkdocs build --strict` pass with no warnings or waivers.
- Coverage over `depin/` stays at or above 95%.
- No regression against the benchmark baseline.

## Out of scope

| Item | Reason |
| --- | --- |
| Warming scoped providers inside an active scope | A scope is opened per request; warming it is what resolving it does. A boot-time operation that needs a scope is a scope the caller already controls. |
| A warmup that collects failures instead of raising | A container with some singletons built and some failed is not a state to hand a caller. Failing at the first error is what makes the failure a startup abort. |
| Timing in the warmup report | A duration is nondeterministic and would make the report untestable without a fake clock, for a number `benchmarks/` already measures properly. |
| `check=` on `alias`, `collect`, `scope_value`, or `decorate` | An alias and a collection produce no value of their own; a `scope_value` receives one from outside the container; a decorator is verified through the key it occupies. Each would need its own rule for no identified consumer. |
| Several checks on one binding | One callable can call several. A list would need an aggregation rule and a per-check identity in the report. |
| A check receiving anything besides the produced value | A check that needs a second dependency is a function of two arguments, which is a provider, not a check. |
| Retries, timeouts, or caching in `health()` | Policy belongs to the readiness endpoint that calls it. `health()` reports what the checks said, once. |
| Custom named scopes | Rejected above, against the roadmap's stated criterion. |
