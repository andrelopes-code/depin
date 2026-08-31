# Step 5, cycle 1 — the integration contract: design

Date: 2026-08-31
Baseline: 0.12.0 at `76dfd33`
Target: 0.13.0
Status: approved, pending implementation plan

## Goal

Give integration authors a public, versioned surface to write against, and
prove it is sufficient by rewriting the one integration that exists on top of
it.

**The contract** is the seam `depin.ext.fastapi.RequestScope` already uses,
extracted into `depin` proper: publish a container into the ambient context,
open a scope around one unit of work, seed the framework's own object into that
scope, and read the container back where only an annotation is in scope. Four
operations, named `Host`, `hosted_container`, and `optional_hosted_container`,
versioned by `CONTRACT_VERSION`.

**The proof** is `depin.ext.fastapi` rewritten to import nothing from
`depin._core`, plus contract tests that fail when any module under `depin/ext/`
reaches into it.

**The guide** is `docs/guide/integrations.md`, the normative prose for a third
party writing an integration depin does not ship.

**The matrix** is how every integration — this one and the six that follow —
gets tested against both its declared minimum and the current release of its
framework, for the cost of one additional CI job in total rather than two per
integration.

One resolution rule changes with them, because the contract makes seeding a
documented operation and the current rule makes a seeded value silently outrank
a registered binding.

## What changes for an existing graph

| Before | After |
| --- | --- |
| A parameter whose key was seeded with `frame.provide()` received the seeded value, even when a provider was registered under that key. | The registered provider wins, and `resolve(key)` and the parameter agree. |
| A parameter carrying a tag received a frame value seeded under the bare key. | The tag is honoured; a frame value seeded under the bare key satisfies only an untagged parameter. |
| A `scope_value` parameter read the frame directly on every resolution. | It resolves through its plan node, which reads the frame once and caches the result for the scope. |
| An active `override()` did not reach a parameter whose key was seeded: the short-circuit ran ahead of `_lookup_optional`, which is where overrides are honoured. | The override reaches the parameter, because the parameter now goes through `_lookup_optional` like every other. |
| A parameter in a nested scope that re-seeded a key already resolved in the enclosing scope received the re-seeded value. | It receives the enclosing scope's value, which is what `resolve(key)` already returned there. |
| Nothing in `depin` names the integration seam. | `Host`, `hosted_container`, `optional_hosted_container`, `ContractVersion`, and `CONTRACT_VERSION` are public. |

The first five rows are one change: `FrozenContainer._resolve_params_sync`
and `_resolve_params_async` consult the plan before the frame, rather than
short-circuiting to the frame ahead of it. The first three are the rule
itself; the fourth and fifth follow from routing the parameter through
`_lookup_optional` first, which is where an override is consulted and where
the frame cache is read under `(key, tag)`. Both are improvements in the same
direction as the first three: a parameter and `resolve(key)` agree under an
override, and under a re-seed in a nested scope, where they previously
disagreed. A graph that seeds only keys declared with `scope_value`,
overrides no seeded key, and re-seeds no key across nested scopes resolves to
exactly the values it did at 0.12.0. A parameter carrying a default, or
admitting `None`, whose key has no binding but was seeded into the frame,
still receives the seeded value — exactly as at 0.12.0 — because the guard
falls back to the frame only once the plan and any active override have both
said no.

## Measurements

Six questions were measured against the tree at `76dfd33` rather than assumed.

**The four operations suffice for WSGI, CLI, and worker hosts.** The candidate
`Host` was prototyped and driven from three hosts outside ASGI. A Flask app
wrapped at `app.wsgi_app` with `host.scope()`, seeding
`starlette`-free `flask.Request`, resolved a scoped session per request and
ran its teardown. A `click` group callback registered the scope on Click's own
`ExitStack` with `ctx.with_resource(host.scope())`, seeded a `Token[bool]`, and
the subcommand resolved both through `hosted_container()`. A worker whose
lifecycle is a pair of hooks rather than a block entered and exited
`host.ascope()` by hand with `__aenter__` / `__aexit__`; two concurrent
messages each got their own scope, their own seeded value, and their own
teardown. No operation beyond the four was needed, and no host needed to reach
past `Host` into `depin._core`.

**Deleting the frame check outright, rather than reordering it behind the plan
and an active override, breaks a route the test suite pins.** Deleting the
`if frame is not None and param.key in frame` branch from both
`_resolve_params_sync` and `_resolve_params_async` — with nothing put in its
place — removes the only route by which a parameter carrying a default, or
admitting `None`, whose key has no binding ever received a value seeded into
the frame; the four tests that pinned that route had to be rewritten rather
than left passing. Reordering the check instead, so the frame is consulted
only when `self._lookup_optional(param.key, param.tag)` has already said
`None`, keeps that route open while still letting the plan and an active
override win whenever either claims the key — which is the guard actually
shipped.

**The plan-first guard is kept on a cost a direct timer does not see.**
`pytest-benchmark`, the harness the CI regression gate runs, measured
`test_open_and_close_a_scope` with GC on and off, three order-alternated runs:
without the guard the min lands around 300 µs; with it, 185-205 µs, matching
the 184.9 µs of 0.12.0 (`76dfd33`). A direct `time.perf_counter` loop over the
identical graph disagrees in direction — without the guard, 104-107 µs/cycle;
with it, 121 µs/cycle — because it is not the harness the gate runs. `cProfile`
over the direct-timer loop explains the disagreement without excusing it:
removing the guard executes 38 000 fewer `ScopeFrame.lookup` calls and 38 000
fewer `ScopeFrame.__contains__` calls per 2 000 cycles, and a lower cumulative
time — strictly less work. An instrumented run of the guarded code counts 0
firings of the frame fallback out of 950 parameter resolutions in that graph.
The guard is kept anyway: it does strictly less work and is still
approximately 55% slower on `test_open_and_close_a_scope` under the harness
the project gates on, which makes the code shape — not the work done — the
thing CPython's specializing interpreter rewards on this hot path.

**A generic `Seed[T]` dataclass buys no type safety, so seeding stays
`frame.provide`.** `@dataclass(frozen=True, slots=True) class Seed[T]: key:
type[T] | Token[T]; value: T` was probed under both checkers. PEP 695 variance
inference does make `T` covariant, so `Seed[Request]` is assignable to
`Seed[object]` and a heterogeneous `*seeds: Seed[object]` parameter type-checks
— but `Seed(Request, 'oops')` also type-checks under `basedpyright --strict`
and `mypy --strict`, because `T` solves to `object` and satisfies both fields.
Narrowing `key` to `type[T]` alone does not change it. The pairing a `Seed`
type exists to enforce is therefore not enforceable in one call, and the
contract keeps the `ScopeFrame.provide` that is already public.

**`fastapi.Request` is `starlette.requests.Request`.** `fastapi` re-exports the
Starlette class rather than subclassing it, so the object an ASGI middleware
seeds is the same key for a FastAPI provider and a Starlette provider. Cycle 3
can share one middleware across both without a second key.

**`ContainerNotBoundError` must stay actionable per integration.** The message
`Inject[...]` raises today names the middleware to install. A
`hosted_container()` that raises a contract-level message would replace that
advice with a generic one. The contract therefore exposes both the raising and
the non-raising read, and each integration raises its own message — which is
also why the pair mirrors `depin._core.scope`'s existing
`active_frame` / `optional_frame`.

## Public surface

Five symbols, in one new module, re-exported from `depin`.

| Symbol | Role |
| --- | --- |
| `Host` | Holds a `FrozenContainer` and hosts it: ambient publication, and a scope per unit of work. |
| `hosted_container` | The container hosted in this context; raises when there is none. |
| `optional_hosted_container` | The same read, reporting absence as `None`. |
| `ContractVersion` | A `(major, minor)` pair with the compatibility rule attached. |
| `CONTRACT_VERSION` | The version this release of depin implements. |

```python
@final
@dataclass(frozen=True, slots=True, order=True)
class ContractVersion:
    major: int
    minor: int

    def __str__(self) -> str: ...


CONTRACT_VERSION: Final = ContractVersion(1, 0)


@final
class Host:
    def __init__(self, container: FrozenContainer) -> None: ...
    @property
    def container(self) -> FrozenContainer: ...
    def activated(self) -> AbstractContextManager[None]: ...
    def scope(self) -> AbstractContextManager[ScopeFrame]: ...
    def ascope(self) -> AbstractAsyncContextManager[ScopeFrame]: ...


def hosted_container() -> FrozenContainer: ...
def optional_hosted_container() -> FrozenContainer | None: ...
```

Nothing else is added. Seeding is `ScopeFrame.provide`, resolution is
`FrozenContainer.resolve` / `aresolve`, startup is `warmup` / `awarmup`, and
shutdown is `close` / `aclose` — all public since earlier steps, all reached
through `Host.container`.

## Data model

`Host` holds one reference and no state of its own. The ambient publication is
a module-level `ContextVar[FrozenContainer | None]`, one per process, set and
reset around each unit of work.

A module-level variable is right rather than per-`Host` state because
`hosted_container()` is read from a place that has no reference to the host —
a route annotation, a Click command, a task body. Two `Host` objects in one
process do not collide: the variable holds whichever container the innermost
enclosing `activated()` published, and resets to the enclosing one on exit.

`ContractVersion` is ordered so a third party can write
`if depin.CONTRACT_VERSION < ContractVersion(1, 2): ...` without unpacking it.

## Semantics

| Operation | Guarantee |
| --- | --- |
| `Host(container)` | Stores the container. Publishes nothing, opens nothing. |
| `Host.container` | The same object that was passed in. |
| `Host.activated()` | Publishes the container for the duration of the block, in the current `contextvars.Context` only. Nested blocks stack; the innermost wins; exit restores the enclosing one. No scope is opened. |
| `Host.scope()` | `activated()` plus `FrozenContainer.scope()`. Yields the frame, so the caller can seed it before anything resolves. Teardowns run on exit, then the publication is undone. |
| `Host.ascope()` | The same, over `FrozenContainer.ascope()`. Required when any provider in the scope is async. |
| `hosted_container()` | The published container, or `ContainerNotBoundError`. |
| `optional_hosted_container()` | The published container, or `None`. |
| `CONTRACT_VERSION` | Bumps its minor when an operation is added, its major when one changes meaning or is removed. |

Both scope context managers are ordinary context-manager objects, so a host
whose lifecycle is a pair of hooks rather than a block stores the object and
calls `__enter__` / `__exit__` (or `__aenter__` / `__aexit__`) itself. This is
measured, not incidental: it is how the worker probe ran.

`Host.scope()` publishes before it opens the scope and unpublishes after the
scope drains, so a teardown can still resolve through `hosted_container()`.

### The resolution rule that changes

`_resolve_params_sync` and `_resolve_params_async` guard the frame behind the
plan and an active override, rather than reading it ahead of them: a parameter
takes a value from the active frame only when `self._lookup_optional(param.key,
param.tag)` — the same call that resolves the parameter otherwise, and the one
that honours `override()` — has already returned `None` for that key and tag.
A key declared with `Container.scope_value` has a plan node of shape
`ProviderShape.FRAME` and scope `Scope.SCOPED`, which reads the active frame,
so seeding reaches such a parameter by the route the plan describes; the guard
is what a parameter falls back to when no route through the plan exists at all.

Four consequences follow, all intended:

- A value seeded under a key that also has a registered binding no longer
  shadows that binding. `resolve(key)` never honoured the seed; now the
  parameter does not either, because `_lookup_optional` finds the binding
  before the guard is reached.
- An active `override()` reaches a parameter whose key was only seeded, for
  the same reason: `_lookup_optional` reports the override, not `None`, so the
  guard never takes the frame value over it.
- A `scope_value` key's value is cached in the frame under `(key, tag)` on
  first use, so re-seeding the same key after something has already resolved
  it does not change what a later parameter receives within that scope. Seed
  before resolving, which is what every integration does anyway.
- A parameter carrying a default, or admitting `None`, whose key has no
  binding but was seeded into the frame, still receives the seeded value —
  the route `depin/_core/graph.py` excuses such a parameter for not having.
  The guard is checked first in the source only because that code shape is
  what the gated benchmark rewards; the plan and any override still decide
  whenever either has an answer.

## Errors

| Trigger | Exception | Message |
| --- | --- | --- |
| `hosted_container()` with nothing published | `ContainerNotBoundError` | `no container is hosted in this context; open a scope with Host.scope() / Host.ascope(), or publish one with Host.activated()` |
| `Inject[T]` outside a `RequestScope` | `ContainerNotBoundError` | unchanged, and still names the middleware to install |

No new exception type. `ContainerNotBoundError` already exists; its docstring
stops describing itself as FastAPI's and describes the contract instead, with
the FastAPI case as an example.

## Module layout

| Module | Change |
| --- | --- |
| `depin/_core/hosting.py` | **New.** `ContractVersion`, `CONTRACT_VERSION`, `Host`, the ambient variable and its two readers. |
| `depin/_core/frozen.py` | `_resolve_params_sync` / `_resolve_params_async` guard the frame short-circuit behind the plan and an active override. |
| `depin/__init__.py` | Re-exports the five symbols. |
| `depin/errors.py` | `ContainerNotBoundError` is documented against the contract. |
| `depin/ext/fastapi.py` | Rewritten on `Host` / `optional_hosted_container`; imports nothing from `depin._core`. |
| `AGENTS.md` | `hosting.py` enters the `_core` module map. |

The contract lives in `_core` and is re-exported, like every other public
symbol in this package. That placement is deliberate and has a consequence
worth naming: `[tool.mutmut] only_mutate` is `depin/_core/*.py` and the
`mutation` workflow triggers on `depin/_core/**`, so the contract is mutated
and gated from the day it lands. A module at `depin/contract.py` or
`depin/ext/contract.py` would be neither without editing both, and a public
seam that six integrations depend on is the last place to accept a weaker gate.

`depin/ext/` gains nothing this cycle. The middleware stays in
`depin/ext/fastapi.py` rather than moving to a shared `depin/ext/asgi.py`,
because cycle 3 is what gives that module its second and third consumer; an
abstraction extracted for one user is a guess.

## Verification

- **Unit.** `tests/unit/test_hosting.py`: `Host` publishes and unpublishes,
  nests, restores the enclosing container, and unpublishes on an exception;
  `scope` and `ascope` seed, resolve, and drain; a teardown can still read
  `hosted_container()`; the two readers agree; `ContractVersion` orders and
  renders; `CONTRACT_VERSION` is the declared value.
- **Contract.** `tests/unit/test_integration_contract.py`: every module under
  `depin/ext/` is parsed with `ast` and asserted to import nothing under
  `depin._core`, and every name it imports from `depin` is asserted to be in
  `depin.__all__`. The scanner is a pure function over source text, so the same
  test proves it fails: a source string that imports `depin._core.frozen` is
  asserted to be reported.
- **Resolution.** `tests/unit/test_resolution.py` and
  `tests/unit/test_frozen_async.py` gain the case the short-circuit used to get
  wrong: a key that is both seeded and bound resolves to its binding, in a
  parameter and at the top level alike.
- **Typing.** `tests/typing/test_conformance.py` gains `assert_type` over
  `Host.container`, both readers, and the two scope managers.
- **Integration.** `tests/integration/test_fastapi_ext.py` and
  `test_fastapi_robustness.py` pass unchanged — the rewrite is behaviour
  preserving, and an unchanged suite is the evidence.
- **Example.** `examples/integration/` hosts a container in a framework depin
  does not ship: a small job runner that opens one scope per job and seeds the
  job into it.
- **Benchmarks.** `benchmarks/test_resolution.py` gains a request-shaped
  graph with a seeded frame value, alongside the existing scope open/close, so
  both sides of the short-circuit trade are guarded.
- **Docs.** `docs/guide/integrations.md` and `docs/reference/hosting.md`, both
  in the nav, with executable `pycon` blocks.

## Acceptance criteria

- `depin.ext.fastapi` imports nothing from `depin._core`, and the FastAPI
  integration suite passes unchanged.
- The contract test reports a module that imports `depin._core`, proven by a
  positive control in the same test file.
- All 832 existing tests still pass, plus the new ones.
- Coverage over `depin/` stays at or above 95%.
- The mutation gate stays at or above 95% killed with `depin/_core/hosting.py`
  in scope.
- `CONTRACT_VERSION == ContractVersion(1, 0)`, pinned by a test.
- `depin/` still carries exactly three suppressions.
- Every integration extra is exercised at its declared floor by
  `minimum-versions` and at its current release by `latest-versions`.

## Out of scope

| Item | Reason |
| --- | --- |
| A shared `depin/ext/asgi.py` | It gets its second and third consumer in cycle 3. Extracting it here would be an abstraction with one user. |
| Singleton-cache eviction, and the `pytest` plugin | Cycle 2. Eviction changes teardown semantics and deserves the release that ships its only consumer. |
| A public `ProviderKey` renderer | Routed to Step 6 by cycle 2 of Step 4. No integration this cycle prints a key. |
| A `Seed` type for frame seeding | Measured to add no type safety over `ScopeFrame.provide`. |
| Making `Host` generic over a framework request type | Every host seeds a different number of values under different keys; a single type parameter would describe only the simplest of them. |
| A `Protocol` third parties implement | The contract is consumed, not implemented. What a third party needs is a stable surface and a version, both of which this cycle ships. |
