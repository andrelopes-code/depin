# Proposal: declarative provider discovery

Date: 2026-09-05
Status: accepted for investigation; public API and mechanism unselected
Scope: provider declaration, explicit package discovery, freeze-time registration,
consumer typing, startup cost, and import behavior

## Nature of this document

This proposal defines a consumer outcome, not a final API or implementation
plan. The candidate spelling uses `@provide` and `Container.discover(...)` to
make the discussion concrete, but neither name nor the package-scanning
mechanism is accepted by this document.

The design phase may replace that mechanism when investigation finds a more
robust Python-native approach. A replacement must preserve the ergonomics,
isolation, freeze boundary, typing, lifecycle behavior, and performance
requirements below, and the design must record the evidence and trade-off that
caused the change.

Implementation still requires a reviewed design, a written test-first plan,
and the normal repository gates.

## Executive summary

Today, every provider must be mentioned by a `Container` or `Registry` binding
even when the provider already carries everything needed to describe itself.
This creates a distant composition-root edit for each new class or factory and
makes consumer applications repeat information already present in type hints.

`depin` should investigate declarative provider metadata paired with an
explicit discovery boundary. A consumer should be able to mark a module-level
class or factory once, ask a builder to discover a selected application package
before `freeze()`, and resolve both primary and transitive providers without
individual `bind()` calls.

Discovery must feed the existing `BindRecord` to `ProviderSpec` to
`ResolutionPlan` pipeline. It must not create a second construction engine,
weaken validation, introduce process-global registration, or add reflection to
resolution. Classes, sync and async factories, generators, async generators,
context managers, scopes, conditions, checks, tags, teardown, and errors retain
their existing semantics.

## Problem

The current explicit surface is predictable:

```python
di = (
    Container()
    .bind(Settings)
    .bind(Session, scope=Scope.SCOPED)
    .bind(UserRepository, scope=Scope.SCOPED)
    .bind(UserService)
    .freeze()
)
```

It also forces the composition root to import and repeat every provider. That
cost grows with the application rather than with the number of genuine wiring
decisions. Moving the declarations to a `Registry` improves composition but
still requires each provider module to share and mutate an explicit registry.

The desired experience is closer to this candidate:

```python
from depin import Scope, provide


@provide(scope=Scope.SCOPED)
class UserRepository: ...
```

```python
di = Container().discover('app.services').freeze()
```

The final spelling may differ. The important outcome is that the provider is
declared beside its implementation, the application chooses a bounded discovery
domain, and no file repeats one binding per provider.

## Python import boundary

Python cannot decorate a class or function in a module that has never been
imported. This proposal does not claim otherwise.

All discovered providers must be known before `freeze()`. The candidate
`discover()` operation owns any required imports inside the explicitly selected
domain. A module imported only after `freeze()` does not mutate an existing
`FrozenContainer`, and a lookup for its provider does not compile a new graph on
first use.

This preserves the meaning of `freeze()`: the complete resolvable graph is
validated and converted into an immutable runtime plan before construction.
Missing dependencies, cycles, captive dependencies, invalid lifetimes, and
duplicates remain startup failures rather than traffic-dependent failures.

## Ergonomics contract

The accepted design must provide all of the following:

- one declaration beside a class or factory, with no individual composition-root
  binding for an ordinarily self-described provider;
- direct resolution of a discovered primary provider, not only discovery through
  another provider's constructor;
- one explicit, bounded application-level discovery decision rather than an
  import for every provider at the composition root;
- unchanged manual `bind()` and `Registry` workflows for consumers that prefer
  them or need explicit wiring;
- no service-locator calls or manual scope plumbing in ordinary consumer code;
- errors that name the requested discovery domain, the module or provider that
  failed, and a concrete corrective action; and
- documentation that states import execution and the `freeze()` boundary without
  presenting Python runtime discovery as compiler magic.

The feature is additive. Existing applications must not adopt decorators or
discovery to keep working.

## Non-negotiable invariants

An approach is rejected if it requires any of the following:

- an implicit process-wide provider catalogue or global container;
- scanning every object in `sys.modules` without an application-selected
  boundary;
- mutation of a `FrozenContainer` after a later import;
- deferred graph validation or provider-shape detection on first resolution;
- partial mutation of a `Container` or `Registry` when discovery fails;
- a second construction, caching, scope, override, or teardown path for
  discovered providers;
- weaker singleton single-flight, cancellation, teardown ordering, or grouped
  failure behavior;
- a runtime dependency in the core;
- weaker inferred decorator return types or a suppression in library or
  conformance code; or
- a measurable resolution regression merely because discovery exists but is not
  used.

Provider metadata may live on the decorated target. Decorating a target must
return that target unchanged and must not add it to shared mutable state.

## Provider parity

Declarative discovery covers the sources and options accepted by `bind()`:

- classes;
- synchronous factories;
- coroutine factories;
- generators;
- async generators;
- `contextmanager` factories;
- `asynccontextmanager` factories;
- singleton, scoped, and transient lifetimes where already valid;
- an explicit provided key, tag, activation condition, and health check; and
- existing `provides()` metadata where the two decorators can compose without
  ambiguity.

Each discovered declaration must become an ordinary `BindRecord` before graph
construction. From that point forward the existing provider inference,
validation, ordering, diagnostics, warmup, health, sync and async resolution,
override, cache, eviction, and teardown code is authoritative.

Ready-made values, aliases, collections, scope-frame values, and provider
decoration are not automatically converted into target decorators by this
proposal. Their present explicit APIs remain available unless later evidence
identifies an equally clear declarative contract.

## Candidate direction: explicit package discovery

The leading hypothesis is a method on the binding collector, represented here
as `discover()` so that `Container` and `Registry` share one verb and one
implementation:

```python
app = Registry('app').discover('app.providers')
di = Container(app).freeze()
```

or:

```python
di = Container().discover('app.providers').freeze()
```

The candidate operation imports or receives one named module or package,
enumerates its selected submodules deterministically, finds declarations owned
by those modules, and appends normal binding records. It does not search unrelated
loaded modules.

The design must decide, rather than assume:

- whether the argument is an import string, a module object, or both;
- whether recursion is the only mode or an explicit choice;
- support expectations for regular packages, namespace packages, zip imports,
  editable installs, and installed wheels;
- how module ownership is established so reexports do not duplicate providers;
- whether an overlapping or repeated discovery is idempotent or becomes the
  existing duplicate-provider error;
- whether only module-level targets are eligible and how an ineligible local
  target is diagnosed;
- how decorator ordering composes with `provides()`, `contextmanager`,
  `asynccontextmanager`, and ordinary wrappers; and
- whether import failures need a new public `DepinError` subtype or an existing
  error can report them without losing the original cause.

These are design questions. The proposal does not accept `pkgutil`, filesystem
walking, or any other traversal implementation in advance.

## Alternatives the design must compare

### Explicit package or module discovery

This is the leading candidate. It supports providers resolved directly, avoids
per-class composition-root imports, isolates different applications and tests,
and performs work before `freeze()`. Its costs are importing the selected module
tree and defining precise behavior across Python loaders and reexports.

### Explicit local catalogue

A decorator bound to a `Registry` is maximally deterministic and already close
to the current `singleton()`, `scoped()`, and `transient()` surface. It avoids
module scanning but requires provider modules to import or receive a shared
registry. The design must determine whether a small ergonomic refinement here
solves the real consumer problem more reliably than discovery.

### Reachability from explicit roots

`freeze()` could materialize marked concrete dependencies reached from a small
set of roots. This minimizes imports and unused bindings, but a provider used
only as `di[UserRepository]` is invisible unless separately declared as a root.
The design must measure whether a concise root declaration plus transitive
expansion is a better Python contract than package discovery.

### Process-global decorator registration

Rejected as a baseline. It couples containers and tests through import order,
makes reload behavior surprising, and violates the project's shared-mutable-state
rule. It also does not solve modules imported after `freeze()` without weakening
the frozen graph.

### Lazy registration from `FrozenContainer.resolve()`

Rejected as a baseline. It delays graph failures, adds synchronization and work
to runtime resolution, and changes `FrozenContainer` from a closed validated
plan into a mutable compiler cache.

### Implicit whole-process or whole-environment scanning

Rejected as a baseline. It makes unrelated imports affect application wiring,
has an unbounded startup domain, and produces behavior that is difficult to
reproduce in tests and embedding applications.

## Error behavior

Discovery must fail loudly and deterministically. It must never skip a module,
provider, or metadata error to make startup continue.

Candidate imports and declarations must be collected before binding records are
appended. If discovery fails, the receiving `Container` or `Registry` remains
unchanged so a caller never observes a partially discovered domain.

The design must preserve exception chaining for failures raised while importing
a selected module. A depin-owned discovery error must include the requested
domain and failing module. Provider declaration errors that the existing graph
pipeline already understands should continue to use the established
`InvalidProviderError`, `InvalidScopeError`, `DuplicateProviderError`, and graph
errors at `freeze()`.

Reexports, repeated aliases to the same object, and overlapping discovery domains
must have one documented rule. Nothing may silently choose a winner for two
distinct bindings of the same key and tag.

## Typing contract

The provider decorator must preserve the exact class or callable type it
receives. The source checker matrix must demonstrate this for every supported
provider shape and configured decorator form under Basedpyright, mypy, stock
Pyright, ty, and Pyrefly.

The design must prove that:

- decorating a class still leaves it usable as that class at construction and
  annotation sites;
- factory parameters and return types retain their callable signatures;
- overloads distinguish supported provider shapes without exposing `Any`;
- configured and unconfigured decorator forms infer the original target type;
- `provides()` composition retains its existing consumer types; and
- incorrect decorator arguments fail at the expected checker boundary and with
  a `DepinError` for untyped runtime callers.

## Verification strategy

New core behavior is test-first. Tests use real `Container`, `Registry`, and
`FrozenContainer` objects and cover at least the following matrix.

### Provider behavior

- class, sync function, coroutine, generator, async generator,
  `contextmanager`, and `asynccontextmanager` sources;
- singleton, scoped, and transient identity rules;
- direct primary lookup and transitive constructor or factory injection;
- explicit keys, `provides()`, tags, conditions, checks, and postponed
  annotations across modules;
- synchronous rejection of async dependency chains;
- override and eviction behavior; and
- sync and async teardown success, failure aggregation, cancellation, and
  reverse ordering.

### Import and discovery behavior

- a regular module, regular package, nested subpackage, namespace package,
  editable source tree, and installed wheel fixture where supported by the
  selected mechanism;
- deterministic discovery independent of filesystem enumeration order;
- reexports, aliases, two modules with the same short class name, repeated
  discovery, and overlapping domains;
- import cycles that Python itself supports and a selected module whose import
  fails;
- targets imported before discovery, imported by discovery, and imported only
  after `freeze()`;
- two independent containers discovering disjoint domains in one process;
- test isolation across module caching and explicit reload scenarios; and
- modules with `__getattr__` or unrelated non-provider objects, without invoking
  surprising attribute behavior during inspection.

### Consumer evidence

- a runnable example with no module-level container construction;
- doctested guide and public docstrings;
- source conformance for all five checkers;
- an integration test that imports an application package and resolves both a
  primary provider and an async resource dependency; and
- a comparison showing the before and after composition root for a representative
  application.

Tests must use temporary packages and deterministic synchronization where
needed. They must not rely on network access, wall-clock sleeps, or the ambient
contents of the test runner's `sys.modules`.

## Performance evidence

Discovery is startup work. The design must measure it separately from module
import time so the project can distinguish Python application loading from depin
metadata collection and `freeze()` work.

Required evidence includes:

- decorator declaration cost at import for classes and each factory shape;
- cold and already-imported discovery for representative 10, 100, and 1,000
  provider package trees;
- manual binding versus discovered binding record creation and `freeze()`;
- retained memory for discovery metadata and the frozen plan;
- warm singleton, transient chain, scoped, sync, and async resolution proving
  that discovered and manually bound plans have equivalent runtime cost; and
- a no-discovery control proving that adding the feature does not regress current
  workloads.

Any new benchmark claim receives a workload contract and calibrated budget
through the existing performance evidence system. `budgets.toml` remains
generated from identical-code calibration and is never edited by hand.

The investigation may reject recursive package discovery if its bounded startup
cost or loader compatibility is not competitive with a better approach. It may
not hide that cost inside a broad end-to-end number.

## Compatibility and migration

Manual registration remains the reference behavior. Discovery and explicit
bindings may coexist in one builder, with ordinary duplicate validation when
they declare conflicting keys.

The design must state how project-owned provider metadata coexists with the
current `provides()` marker and whether discovery metadata becomes part of the
documented public stability surface. No current method changes meaning, and no
existing valid application requires a migration.

The feature adds no runtime dependency and imports no framework from the core.

## Non-goals

- Discover providers from modules outside a consumer-selected boundary.
- Make a never-imported Python object exist without importing its module.
- Modify an existing frozen plan when a module is imported later.
- Replace explicit aliases, collections, ready-made values, scope values, or
  provider decoration without a separate accepted design.
- Infer application package boundaries from the current working directory.
- Introduce a build-time compiler, import hook, packaging plugin, or entry-point
  protocol in the initial implementation.
- Promise that importing arbitrary consumer modules is free of their own import
  side effects.
- Copy Angular terminology or semantics where they conflict with Python's import
  model and depin's validated freeze boundary.

## Acceptance criteria

- A consumer can declare each supported class or factory beside its
  implementation and resolve it without an individual `bind()` call.
- A discovered provider used only as a primary `di[key]` lookup is present in the
  plan before `freeze()` returns.
- Every currently supported provider shape, lifetime, check, condition, tag,
  teardown, override, and sync/async rule has parity tests through discovery.
- Discovery is bounded by an explicit application choice and does not use shared
  mutable registration state.
- A failed discovery leaves the receiving binding collector unchanged.
- Late imports do not mutate or extend a `FrozenContainer`.
- Import, ownership, reexport, duplicate, reload, and multi-container behavior is
  deterministic and documented for the selected mechanism.
- The complete checker matrix preserves exact decorated target types without new
  suppressions.
- Existing manual-registration tests and consumer call sites pass unchanged.
- Core retains zero runtime dependencies.
- Measured discovery and freeze costs receive justified budgets, and current
  resolution workloads show no regression attributable to the feature.
- Public docs include a short runnable example and state the import and freeze
  boundaries plainly.

## Stop and redirect conditions

The candidate package-discovery direction is replaced or the proposal is
rejected if investigation shows that it:

- cannot support the required Python package and loader forms deterministically;
- requires global registration or ambient `sys.modules` state for correctness;
- needs runtime mutation after `freeze()` to support primary providers;
- cannot preserve all provider shapes and lifecycle semantics through the
  existing binding pipeline;
- weakens consumer typing on any blocking checker;
- adds resolution overhead instead of containing work to declaration, discovery,
  and freeze; or
- costs more startup time or retained memory than an alternative that satisfies
  the same ergonomics contract.

A redirect is a successful outcome of the proposal when it is evidence-backed.
The subsequent design must update the candidate surface, comparison, and
acceptance mapping rather than preserving `discover()` for consistency with an
early sketch.

## Expected handoff artifacts

- a focused Python import-system and package-loader compatibility experiment;
- a comparison of explicit discovery, local catalogue, and explicit-root
  reachability against the same consumer examples;
- startup, freeze, memory, and resolution baseline evidence;
- a reviewed design selecting the public spelling and discovery mechanism;
- a test-first implementation plan covering runtime, typing, documentation,
  examples, and performance evidence; and
- an evidence report mapping every acceptance criterion to tests or measurements.

## Active decision

Investigate declarative provider discovery. Treat explicit package discovery as
the leading hypothesis, not as an accepted API. A future design may select a
better mechanism when it satisfies the same consumer outcome and invariants with
stronger Python compatibility, isolation, typing, or measured performance.
