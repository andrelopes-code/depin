# Declarative provider discovery public API design

Date: 2026-09-14
Status: public API and naming selected; implementation not authorized
Investigation: [declarative provider discovery design investigation](2026-09-11-declarative-provider-discovery-investigation.md)
Internal design: [declarative provider discovery design](2026-09-14-declarative-provider-discovery-design.md)

## Decision

The public API consists of four new exports: `provider`, `Provider`, `Catalog`,
and `Manifest`. A provider declaration is an ordinary expression, not a
decorator. `provider(target)` binds the target's produced type first;
`Provider.configure()` optionally returns a new immutable declaration carrying
the same `scope`, `provides`, `tag`, `when`, and `check` concepts already used
by `BindingCollector.bind()`.

Each provider module completes an immutable `Catalog` with an explicit owner
and ordered declarations. A composition module imports those values normally
and completes an immutable `Manifest` from catalogues and nested manifests.
`Manifest` satisfies the existing `Bindings` protocol, so the existing
`include()` verb is the only ingestion verb on both `Container` and `Registry`.
`Container(manifest)` remains the constructor shorthand for the same concept.

The selected surface is:

```python
from depin import Catalog, Manifest, Provider, provider
```

No public discovery function, package argument, implicit current catalogue,
registration decorator, or frozen-runtime surface is introduced.

## Goals

- Preserve the original class or factory object, including identity and its
  exact static type.
- Express every provider form currently accepted by `bind()` with one typed
  declaration shape.
- Relate a health check to the value produced, awaited, yielded, or entered by
  its provider without type erasure.
- Make module ownership, catalogue membership, manifest imports, and
  composition order visible in source.
- Reuse the existing registration vocabulary and the same `BindRecord` to
  `ProviderSpec` to `ResolutionPlan` pipeline as manual bindings.
- Keep local and composed values immutable and keep collector mutation atomic
  for each manifest ingestion.
- Keep the core free of runtime dependencies and preserve the existing frozen
  runtime without discovery state or work.

## Non-goals

- Implementing this API, its runtime support, its tests, or its documentation.
- Producing an implementation sequence or assigning implementation work.
- Discovering packages, files, loaded modules, namespace attributes, entry
  points, import hooks, or providers reachable from explicit roots.
- Adding ready-made values, aliases, collections, scope-frame values, or
  decoration layers to declarative catalogues.
- Replacing `Registry`, manual binding, or `provides()`.
- Changing resolution, scope, override, injection, teardown, health, graph, or
  diagnostic semantics after a `ResolutionPlan` exists.
- Reopening the internal mechanism or collecting more performance evidence in
  this phase.

## Architectural invariants carried into the API

The public surface is constrained by the closed internal design:

1. A catalogue is local, explicitly owned, ordered, and immutable.
2. A manifest has only explicitly imported `Catalog` and `Manifest` inputs.
3. No import enumerates a package, filesystem, `sys.modules`, module namespace,
   or dependency graph.
4. No module-level mutable collector, global catalogue, ambient current
   catalogue, or registration side channel exists.
5. Manifest ingestion materializes a complete `BindRecord` tuple before one
   collector mutation.
6. Discovery ends when that tuple is committed. `build_specs()` receives only
   ordinary records, and `build_plan()` remains authoritative for the graph.
7. `FrozenContainer`, `resolve()`, `aresolve()`, scopes, overrides, injection,
   and integrations use only the completed `ResolutionPlan` and structures
   already derived from it.
8. A declarative provider produces the same record, spec, plan, behavior, and
   error as the equivalent manual `bind()` call.

## Public names and roles

| Name | Role |
| --- | --- |
| `provider` | Overloaded function that captures one class or factory as a typed immutable declaration. |
| `Provider[T]` | Immutable declaration whose type parameter is the value delivered by the provider. |
| `Catalog` | Immutable ordered set of provider declarations owned by one module. |
| `Manifest` | Immutable ordered composition of catalogues and nested manifests; a `Bindings` source. |
| `include` | Existing shared ingestion verb; no discovery-specific synonym is added. |

The documented conventional export name is `providers` for a module's primary
`Catalog` and `manifest` for a composition module's `Manifest`. These are
ordinary Python bindings, not names that depin searches for. A module that
intentionally owns multiple catalogues uses descriptive exports such as
`production_providers` and `testing_providers`; a manifest imports the exact
one it needs.

`Catalog` is deliberately distinct from `Registry`. A catalogue is an
immutable declaration snapshot limited to class and factory providers. A
registry remains the mutable builder for every explicit binding form.

## Declaration syntax

The declaration is written immediately after its class or factory and assigned
to an ordinary module name:

```python
from collections.abc import AsyncGenerator

from depin import Catalog, Scope, provider


class Database:
    pass


database_provider = provider(Database)


async def open_session(database: Database) -> AsyncGenerator[Session, None]:
    session = Session(database)
    try:
        yield session
    finally:
        await session.close()


session_provider = provider(open_session).configure(
    scope=Scope.SCOPED,
    provides=Session,
    tag='primary',
    when=lambda: settings.database_enabled,
    check=session_is_healthy,
)

providers = Catalog(__name__, database_provider, session_provider)
```

`provider` is not a decorator. It neither calls, wraps, replaces, annotates,
nor mutates its target. `Database is database_provider` is not claimed; the
class remains bound to `Database`, while `database_provider` is a separate
immutable descriptor. Likewise, `open_session` retains its original callable
identity and complete parameter and return annotation.

At the call, `provider()` records the declaring module from that execution
frame's exact `__name__` and its source location as immutable provenance. It
does not enumerate the frame's globals or inspect any module attribute. Calling
the function through an alias records the module where the call executes, not
the module that originally exported the function or target.

`provider(target)` is the bare form and carries the same defaults as
`bind(target)`: singleton scope, inferred key, no tag, no condition, and no
health check. `configure()` creates a new descriptor for the same target. It
does not mutate either the bare descriptor or the target. It preserves the
input descriptor's exact declaration-site module and source location,
regardless of the module from which `configure()` is called. Configuration is
not a declaration-site transfer.

A second `configure()` call is legal and is a complete reconfiguration: the
latest call uses the same target, the arguments supplied to that call, and the
documented defaults for omitted arguments. It does not merge metadata from an
earlier configured descriptor. Normal declarations call `configure()` at most
once, directly after `provider(target)`.

## Complete public signatures

The signatures below are normative. Overloads appear from the most specific
factory forms to the general synchronous factory so coroutine, generator, and
context-manager results are unwrapped before the fallback is considered.

```python
from __future__ import annotations

from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Generator,
    Iterable,
)
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Self, overload


class _ProviderToken: ...


class Provider[T]:
    def __new__(cls, _token: _ProviderToken, /) -> Self: ...

    def configure[U](
        self: Provider[U],
        *,
        scope: Scope = Scope.SINGLETON,
        provides: ProviderKey | None = None,
        tag: str | None = None,
        when: Condition | None = None,
        check: Callable[[U], object] | None = None,
    ) -> Provider[U]: ...


@overload
def provider[T](target: type[T], /) -> Provider[T]: ...


@overload
def provider[**P, T](
    target: Callable[P, Generator[T, None, None]],
    /,
) -> Provider[T]: ...


@overload
def provider[**P, T](
    target: Callable[P, AsyncGenerator[T, None]],
    /,
) -> Provider[T]: ...


@overload
def provider[**P, T](
    target: Callable[P, AbstractContextManager[T]],
    /,
) -> Provider[T]: ...


@overload
def provider[**P, T](
    target: Callable[P, AbstractAsyncContextManager[T]],
    /,
) -> Provider[T]: ...


@overload
def provider[**P, T](
    target: Callable[P, Awaitable[T]],
    /,
) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, T], /) -> Provider[T]: ...


class Catalog:
    def __init__(
        self,
        module: str,
        /,
        *providers: Provider[object],
    ) -> None: ...

    @property
    def module(self) -> str: ...

    @property
    def providers(self) -> tuple[Provider[object], ...]: ...


class Manifest:
    def __init__(
        self,
        module: str,
        /,
        *sources: Catalog | Manifest,
    ) -> None: ...

    @property
    def module(self) -> str: ...

    @property
    def sources(self) -> tuple[Catalog | Manifest, ...]: ...

    def records(self) -> Iterable[BindRecord]: ...
```

`Provider[T]` is covariant in the produced type so heterogeneous declarations
can enter `Catalog(*providers: Provider[object])`. Its generic-self
`configure()` signature fixes `U` from the already-created provider before
checking metadata. This layout is deliberate: `check` cannot influence or
widen the type inferred from the target. The callable overloads use `ParamSpec`
so the target is accepted with its complete parameter list even though the
descriptor needs only its produced value type.

`Provider` is opaque and cannot be constructed directly. `Provider(...)` is
both outside the static contract and rejected with `InvalidProviderError` at an
untyped runtime boundary; `provider(target)` is its only constructor. This
prevents malformed descriptors from bypassing target-first type inference and
provenance capture. The private, unexported `_ProviderToken` makes construction
statically unavailable; `provider()` alone owns a valid token. The runtime
constructor converts a missing or foreign token into the stated depin error
rather than leaking a standard exception.

`Catalog.module` and `Manifest.module` are required positional owner labels.
Provider and composition modules pass `__name__`. Each constructor reads only
the current execution frame's exact `__name__` and requires the supplied
non-empty string to equal it. `Catalog` also requires every `Provider` to carry
that same declaration-site owner. An imported declaration must therefore be
consumed through its owning module's `Catalog`, not inserted into a new local
catalogue. A mismatch raises `InvalidProviderError` before a value is returned.
This exact comparison is provenance validation, not module namespace
inspection or discovery. The tuple properties expose read-only snapshots.
None of these classes offers append, extend, register, seal, or mutation
methods.

`Manifest.records()` exists because `Manifest` structurally satisfies the
already-public `Bindings` protocol. `BindRecord` remains an internal
representation exposed through that existing protocol annotation; it is not a
new root export. `Catalog` deliberately does not satisfy `Bindings`, so a
catalogue cannot bypass explicit manifest composition.

The existing ingestion signatures do not gain a synonym or special overload:

```python
class BindingCollector:
    def include(self, *sources: Bindings) -> Self: ...


class Container(BindingCollector):
    def __init__(self, *sources: Bindings) -> None: ...
```

Because `Manifest` is a `Bindings`, all of these are type-correct:

```python
container = Container(manifest)
container = Container().include(manifest)
registry = Registry('application').include(manifest)
```

`Container(catalog)` and `Registry().include(catalog)` are type errors and
raise `InvalidProviderError` at the untyped runtime boundary. Composition must
cross a `Manifest`.

## Configuration vocabulary and semantics

`Provider.configure()` repeats the exact public concepts and spellings already
used by `bind()`:

| Argument | Meaning |
| --- | --- |
| `scope` | Existing `Scope`; defaults to `Scope.SINGLETON`. |
| `provides` | Explicit `ProviderKey`; `None` preserves existing key inference. |
| `tag` | Existing optional string qualifier. |
| `when` | Existing `Condition`: a bool or zero-argument callable evaluated by `freeze()`. |
| `check` | Callable evaluated by the existing health path against the produced value. |

There is no `key`, `condition`, `health_check`, `lifetime`, or other alias on
this surface. The descriptor maps field-for-field to
`BindRecord(source, scope, provides, tag, condition, check)`; only the existing
internal record field name `condition` differs from the already-public keyword
`when`.

The explicit `provides=` argument has the same precedence as manual binding.
When it is not `None`, it wins over a class's `provides()` marker. When it is
`None`, `build_specs()` reads the existing marker and otherwise infers the key
from the class or factory annotation.

Because `provider()` stores the original target and `provides()` returns that
class unchanged, both source orders are valid before `freeze()`:

```python
@provides(Service)
class DatabaseService:
    pass


database_service_provider = provider(DatabaseService)
```

```python
class MemoryService:
    pass


memory_service_provider = provider(MemoryService)
MemoryService = provides(Service)(MemoryService)
```

The second form is useful primarily as a conformance witness. In both cases
the class has the same identity and exact type. Applying `provides()` after a
plan has been built cannot change that plan, just as it cannot change a plan
already built from a manual record.

## Exact health-check typing

The target is supplied to `provider()` before `configure()` is type-checked.
Consequently `Provider[T].configure(check=...)` requires
`Callable[[T], object]`, where `T` is the value depin actually delivers:

| Provider form | Accepted target | `T` received by `check` |
| --- | --- | --- |
| Class | `type[T]` | Constructed instance. |
| Synchronous factory | `Callable[P, T]` | Returned value. |
| Coroutine factory | `Callable[P, Awaitable[T]]` | Awaited value. |
| Generator factory | `Callable[P, Generator[T, None, None]]` | Yielded resource. |
| Async-generator factory | `Callable[P, AsyncGenerator[T, None]]` | Async-yielded resource. |
| Context-manager factory | `Callable[P, AbstractContextManager[T]]` | Entered resource. |
| Async-context-manager factory | `Callable[P, AbstractAsyncContextManager[T]]` | Async-entered resource. |

A check accepting a supertype such as `object` is valid by callable
contravariance. A check accepting only an unrelated type or a narrower subtype
is rejected. The signature uses neither an erasing top type nor an uninhabited
placeholder. Runtime timing, truth interpretation, error handling, and health
aggregation remain exactly those of an equivalent manual `bind(check=...)`.

## Immutable catalogues and manifests

A provider module constructs its complete catalogue in one expression from
local immutable declarations:

```python
# billing/providers.py
invoice_service_provider = provider(InvoiceService)
payment_gateway_provider = provider(create_gateway).configure(
    scope=Scope.SCOPED,
    provides=PaymentGateway,
)

providers = Catalog(
    __name__,
    invoice_service_provider,
    payment_gateway_provider,
)
```

There is no module-level collector to mutate and no decorator that registers
by import side effect. `provider`, `configure`, and `Catalog` each allocate a
completed value. A module may own multiple catalogues by constructing multiple
values; no catalogue is a view over another. A declaration imported from a
different module is rejected as a direct member because its captured owner
does not match `Catalog(__name__, ...)`; importing the completed owning
catalogue is the supported composition boundary.

A manifest uses ordinary exact imports and composes only completed catalogues
or manifests:

```python
# application/manifest.py
from application.accounts.manifest import manifest as accounts_manifest
from application.billing.providers import providers as billing_providers
from application.infrastructure.providers import providers as infrastructure_providers

manifest = Manifest(
    __name__,
    infrastructure_providers,
    billing_providers,
    accounts_manifest,
)
```

`Manifest` snapshots the ordered source references passed to it. Nested
composition is recursive and left-to-right. It never imports a string, package,
or module on the caller's behalf. Adding a provider requires editing a local
`Catalog`; adding a module requires an explicit Python import and a `Manifest`
entry.

## Complete data flow and termination point

The selected API realizes the internal flow as follows:

1. `provider(target)` creates a typed immutable public `Provider[T]` for the
   unchanged target.
2. Optional `configure()` creates a replacement descriptor carrying the five
   existing binding options.
3. `Catalog(__name__, ...)` snapshots local declarations and adds immutable
   owner and declaration-position provenance.
4. `Manifest(__name__, ...)` snapshots explicitly imported catalogues and
   nested manifests in source order.
5. `include(manifest)` invokes the private staging boundary. It fully flattens
   that one manifest in temporary state, validates its structure, converts
   every occurrence to `BindRecord`, and prepares a tuple.
6. The collector appends the entire tuple once. This successful commit is the
   exact end of discovery. The collector retains records, not `Provider`,
   `Catalog`, `Manifest`, or provenance objects.
7. `freeze()` passes the record snapshot to the existing `build_specs()`;
   active records become `ProviderSpec` values with manual-binding semantics.
8. The existing graph builder validates and orders those specs into a
   `ResolutionPlan`.
9. The frozen runtime receives only that plan. No declaration, catalogue,
   manifest, discovery state, branch, hook, or lookup survives into resolution.

In compact form:

```text
provider declarations -> Catalog -> Manifest -> BindRecord
    -> ProviderSpec -> ResolutionPlan -> frozen runtime
```

The staging boundary is the only bridge from the new API to the existing
pipeline. It cannot bypass `build_specs()`, construct `ProviderSpec` directly,
or influence graph ordering after records are committed.

## Equivalence with manual binding

For each declaration:

```python
service_provider = provider(create_service).configure(
    scope=Scope.SCOPED,
    provides=Service,
    tag='primary',
    when=is_enabled,
    check=service_is_healthy,
)
```

staging must create exactly the record produced by:

```python
registry.bind(
    create_service,
    scope=Scope.SCOPED,
    provides=Service,
    tag='primary',
    when=is_enabled,
    check=service_is_healthy,
)
```

Equality is required for all six `BindRecord` fields and, given an equivalent
ordered graph, for every `ProviderSpec` and `ResolutionPlan` field. Resolution,
scope caching, teardown, checks, diagnostics, rendering, override, injection,
and integration behavior must then be observationally identical.

## Forms that remain explicit

`Catalog` accepts only `Provider` declarations for the seven class and factory
forms. The following remain exclusively on `Container` and `Registry` through
their current APIs:

- ready-made values through `value()`;
- aliases through `alias()`;
- collections through `collect()`;
- scope-frame values through `scope_value()`; and
- provider decoration through `decorate()`.

Those operations can appear before or after one manifest segment:

```python
registry = (
    Registry('application')
    .value(Settings, settings)
    .include(manifest)
    .alias(ServicePort, Service)
    .decorate(Service, instrument_service)
)
```

The resulting record order is the call order: the value, the complete manifest
segment, the alias, then the decoration. A manifest does not absorb, reorder,
or copy adjacent manual bindings.

## Ordering, repetition, and conflicts

Ordering is fully lexical and stable:

1. declarations keep their argument order inside a `Catalog`;
2. manifest sources keep their argument order;
3. nested manifests flatten left-to-right at their occurrence;
4. a repeated source contributes its complete contents again; and
5. the staged tuple occupies one contiguous collector segment at the position
   of `include(manifest)`.

No path, provider name, key, tag, dependency, import time, or object identity
causes sorting or de-duplication.

A catalogue or manifest repeated directly, reached through two nested
manifests, reexported under two names, or overlapped with a manual binding is a
literal repeated declaration. Active declarations for the same key and tag
reach the existing `DuplicateProviderError` at `freeze()`. The API defines no
first-wins, last-wins, shadowing, or merge rule.

Tags remain part of identity. Equal keys with distinct tags are distinct;
equal key/tag pairs conflict. `when` retains current behavior: a false bool or
false zero-argument callable excludes that record before graph construction,
so an inactive occurrence does not collide with an active one. Its declared
identity remains available to the current inactive-provider diagnostic path.
Conditions are evaluated only by `freeze()`, not during declaration, catalogue
construction, manifest construction, or import.

## Observable atomicity

`include(manifest)` is atomic for the whole manifest occurrence. The private
boundary completes recursive flattening, member validation, provenance,
conversion, and tuple materialization before the receiver changes. A failure
leaves the receiving `Container` or `Registry` record snapshot exactly as it
was. Success performs one append and cannot expose a prefix.

The guarantee applies equally when the manifest was supplied through
`Container(manifest)`. When callers need multiple manifests to be one atomic
declarative unit, they first compose them into one outer `Manifest`; the
existing general `include(*sources)` contract for multiple independent
`Bindings` arguments is not broadened.

Graph validation retains its separate existing boundary. Duplicate, missing,
cycle, captive-dependency, invalid-scope, and other graph failures occur at
`freeze()` after records have been successfully ingested. They return no
partial `FrozenContainer` and do not roll the mutable builder back, exactly as
with manual bindings.

## Imports and Python module behavior

The API performs no import. Application manifest modules use ordinary Python
statements whose exact targets are visible in source. Therefore:

- a regular package contributes only explicitly imported values;
- a namespace package contributes only explicitly imported portions;
- editable installs, wheels, zip imports, custom loaders, and reexports need no
  enumeration support;
- an alias refers to the same immutable object and does not acquire new
  ownership or membership;
- module `__getattr__` is never probed as a discovery mechanism;
- reload creates new class, declaration, catalogue, and manifest identities;
  existing manifests, collectors, plans, and frozen containers remain fixed;
  and
- a new builder observes reloaded declarations only through a newly obtained
  manifest reference.

Cycles obey Python initialization rules. A manifest can participate only when
the values it names have completed initialization before access. Early access
to a partially initialized module fails through the ordinary import rather
than exposing a partial catalogue or manifest. Depin provides no lazy string
reference or fallback to make the cycle appear successful.

An import failure occurs before depin receives a manifest, so the original
Python exception propagates unchanged. This API deliberately has no
depin-owned import-by-name boundary and therefore never wraps import errors.
The original exception and any existing `__cause__` are preserved verbatim.

## Error taxonomy

No new public exception is introduced. The existing taxonomy completely
represents the selected surface:

- `InvalidProviderError` covers a non-class/non-callable target at an untyped
  boundary, direct `Provider` construction, invalid declaration metadata, an
  invalid or mismatched declaration/catalogue/manifest owner, a malformed
  catalogue member, a non-`Catalog`/non-`Manifest` manifest member, staging
  structure failures, and existing source-shape or annotation failures;
- `InvalidScopeError` retains existing invalid lifetime semantics;
- `DuplicateProviderError`, `MissingProviderError`,
  `CircularDependencyError`, and `CaptiveDependencyError` remain authoritative
  at graph construction; and
- existing health, resolution, scope, override, injection, and teardown errors
  are unchanged after the plan boundary.

Every error raised by `provider`, `Provider`, `Catalog`, `Manifest`, or private
staging is one of these `DepinError` subclasses. Structural messages identify
the manifest owner and path, catalogue owner and occurrence, declaration
position, offending value, and a concrete correction such as replacing a raw
declaration with a `Catalog` or composing a catalogue through `Manifest`.

Errors from `build_specs()` and `build_plan()` are not translated merely to add
discovery provenance; doing so would make declarative and manual records
observably different. Ordinary import exceptions are not raised by depin and
are not converted to `DepinError`.

## Immutability and state lifetime

`Provider`, `Catalog`, and `Manifest` are frozen, slotted value objects. Their
ordered collections are tuples. Configuration and composition allocate new
values and never mutate their inputs. There is no live view of a module,
collector, registry, or container.

Before `freeze()`, the existing `Container` and `Registry` builders remain
mutable through their documented methods. After manifest staging, those
builders retain only `BindRecord` values. After `freeze()`, the plan and all
plan-derived runtime structures are independent snapshots. Rebinding module
variables, reconstructing catalogues, composing new manifests, or reloading
modules cannot affect an existing builder segment or frozen runtime.

No declaration, catalogue, or manifest has a back-reference to a collector or
`FrozenContainer`. No mutable state is kept at module or process scope by the
new API.

## Core and optional integrations

The four new names belong to depin core and use only the standard library.
Their definitions and staging logic cannot import an optional framework.
Framework integrations continue to receive explicit containers, hosts, or
injection targets through their existing contracts.

An integration may document a framework-specific provider module whose
catalogue an application explicitly imports into its manifest. It may not
inspect routes, tasks, commands, plugin registries, loaded modules, or
framework state to discover providers, and importing the integration may not
import an application manifest. Applications that never import an optional
catalogue incur no import, staging, freeze, retained-state, or resolution cost
for it.

## Public exports and documentation ownership

`depin/__init__.py` will reexport `provider`, `Provider`, `Catalog`, and
`Manifest` and list them in `__all__`. Their Google-style public docstrings
will live with their definitions in `depin/_core/discovery.py`; the root module
only reexports them. `Bindings`, `Condition`, `ProviderKey`, `Scope`, and
`provides` remain their existing single definitions; the new API uses them
rather than introducing aliases.

`Provider.configure()`, `Catalog.__init__`, `Manifest.__init__`, and
`Manifest.records()` document semantics, ordering, immutability, ownership,
errors, and short executable examples without restating annotations. The
`Provider` class docstring states that direct construction is invalid and names
`provider()` as the sole constructor. The shared `include()` docstring will add
`Manifest` as a normal `Bindings` example. Reference pages remain generated
from those docstrings.

Future narrative documentation will explain the progression from local
declaration to catalogue to explicit manifest to `freeze()`, show composition
with manual bindings, and state the absence of scanning. Runnable examples
will keep container construction inside their entry point and will be executed
by the existing example integration test.

## Typing evidence used for selection

A disposable proof under `/tmp/depin-discovery-public-api-typing` modeled the
normative overloads. It covered a class plus synchronous, coroutine, generator,
async-generator, context-manager, and async-context-manager factories in bare
and configured forms. It preserved the six callable identities with exact
`ParamSpec` parameter and wrapper types, checked both orders between
`provider()` and existing `provides()`, and placed heterogeneous declarations
in one catalogue.

The positive fixture configured all metadata and related each `check` to the
produced `T`. The negative fixture contained exactly five misuse sites: invalid
`scope`, `provides`, `tag`, `when`, and an unrelated health-check argument.
One separate negative fixture called `Provider[Service]()` without the private
token. The final matrix was:

| Checker | Positive | Invalid metadata | Direct construction |
| --- | --- | --- | --- |
| mypy 2.3.1 | zero diagnostics | five `arg-type` diagnostics | one `call-arg` diagnostic |
| Basedpyright 1.39.10 | zero errors, warnings, or notes | five `reportArgumentType` errors | one `reportCallIssue` error |
| stock Pyright 1.1.411 | zero errors, warnings, or information diagnostics | five `reportArgumentType` errors | one `reportCallIssue` error |
| ty 0.0.79 | all checks passed | five `invalid-argument-type` diagnostics | one `missing-argument` diagnostic |
| Pyrefly 1.2.0 | zero diagnostics under the strict preset | five `bad-argument-type` diagnostics | one `bad-argument-count` diagnostic |

The commands used the repository interpreter and pinned checker versions:

```console
uv run mypy --strict --warn-unreachable --no-incremental <fixture.py>
uv run basedpyright --project <disposable-pyrightconfig.json> <fixture.py>
uvx pyright@1.1.411 --project <disposable-pyrightconfig.json> <fixture.py>
uvx ty@0.0.79 check --config-file <disposable-ty.toml> --python .venv --error all --output-format concise <fixture.py>
uvx pyrefly@1.2.0 check --config <disposable-pyrefly.toml> --preset strict <fixture.py>
```

A source scan found no erasing top type, cast, suppression, baseline, or
expected-register reference. No repository checker configuration or expected
register changed. The proof also compared a single overloaded configured call
with the selected two-step form: binding `T` in `provider(target)` and checking
metadata in the non-overloaded `configure()` call produced one precise
diagnostic per misuse in all five checkers and removed the decorator prototype's
uninhabited health-check workaround. All disposable files are excluded from
the delivered diff and must be removed before delivery.

## Future validation strategy

The implementation must later add evidence at four levels:

1. unit coverage for immutable declaration values, rejected direct
   `Provider` construction, complete reconfiguration, declaration-site and
   constructor-site owner matching, cross-module declaration rejection,
   declaration owner retention under cross-module `configure()`, catalogue
   construction, manifest nesting, flattening, provenance, malformed members,
   and one-shot staging;
2. parity coverage over the seven provider forms, every supported scope,
   explicit and inferred keys, tags, active and inactive conditions, checks,
   both `provides()` orders, manual interleaving, and equality of records,
   specs, and plans;
3. import and atomicity coverage for regular and namespace packages, aliases,
   reexports, wheel and editable installs, reload, supported and failing
   cycles, partial initialization, repeated and overlapping manifests, and
   unchanged receiver snapshots on staging failure; and
4. positive and negative conformance entries for all five source checkers,
   including exact target identity, every provider form, metadata errors,
   heterogeneous catalogues, and rejection of passing a `Catalog` directly to
   `Container` or `Registry`.

Behavioral tests use real `Container`, `Registry`, and `FrozenContainer`
instances. Documentation examples remain doctests. Coverage includes the
public error paths and preserves the package target of at least 95 percent.
This strategy specifies acceptance evidence, not an implementation sequence.

## Performance acceptance inherited from the mechanism design

This API phase performs no performance investigation or collection. The
completed `freeze()` experiments with 100 and 1,000 providers remain PASS
evidence for the chosen manifest architecture.

The future real implementation must compare synchronized `main` with the
actual implementation using equivalent graphs and workloads. Resolution must
satisfy both preserved limits: an absolute delta no greater than `+50 ns` and
a ratio no greater than `1.05`. The earlier null control remains an honest
statistical FAIL but is not repeated; identical runtime source cannot establish
discovery-caused overhead. No benchmark, `budgets.toml`, expected record, or
historical result changes in this API phase.

## Rejected public surfaces

### Mutable module-bound decorator

A catalogue object offering a decorator that appends into itself is rejected.
It makes import order mutate module state, turns the exported value into a live
collector, couples declarations to a shared sink, and makes reload and partial
imports harder to reason about. Freezing that collector later does not remove
the forbidden module-level mutation that already occurred.

### Identity decorator plus immutable catalogue

An identity-preserving declaration decorator followed by an explicit immutable
catalogue is rejected. Bare decorators can preserve the target's type, but a
configured decorator receives `check` before it receives the target from which
the produced type must be inferred. The investigation's disposable proof had
to substitute an uninhabited callable argument and therefore could not promise
the same precision as `bind(check=...)`. Decorator stacking with `provides()`
also adds an order-sensitive surface that the separate descriptor does not
need.

### Single configured declaration call

Putting the target and every option in one overloaded call is rejected even
though it is shorter. Each factory wrapper competes with the general callable
fallback while metadata participates in overload selection. The comparative
strict-checker probe produced cascading overload diagnostics at invalid
metadata sites. The selected two-step form first fixes `Provider[T]` from the
target, then validates all metadata through one non-overloaded method, giving
the health check one stable produced type and one actionable diagnostic.

### New ingestion verb

A discovery-specific method on `Container` and `Registry` is rejected because
ingesting a manifest is still inclusion of ordered bindings. A second verb
would be a synonym for existing `include()`, split the shared collector
surface, and make manual and declarative composition appear semantically
different.

### Direct catalogue ingestion

Making `Catalog` a `Bindings` is rejected. It would let a composition root skip
the explicit manifest boundary, weaken the audit trail, and make later nested
composition inconsistent with the closed architecture. Only `Manifest`
satisfies `Bindings`.

### String imports and package roots

Manifest constructors accepting module strings, package roots, globs, entry
points, or reachability roots are rejected. They reintroduce depin-owned import
behavior or implicit enumeration and require an import-error surface that an
ordinary explicit Python import does not need.

## Decisions intentionally left for a later implementation phase

This design completes public API shape and naming. A later authorized phase may
choose private module decomposition, private helper names, storage layout,
provenance encoding, and the mechanics used to stage the immutable record
tuple. Those choices may not alter the public names, signatures, ordering,
atomicity, errors, typing guarantees, manifest-only ingestion, or runtime
boundary selected here.

Documentation prose, example domain names, and internal file placement can be
refined during implementation without adding aliases or new public behavior.
The implementation phase must not add package scanning, global state, target
decoration, direct catalogue ingestion, or discovery work after the record
commit.
