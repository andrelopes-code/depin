# Declarative provider discovery design

Date: 2026-09-14
Status: formal mechanism and public API selected; implementation not authorized
Investigation: [declarative provider discovery design investigation](2026-09-11-declarative-provider-discovery-investigation.md)
Public API: [declarative provider discovery public API design](2026-09-14-declarative-provider-discovery-public-api-design.md)

## Decision

Declarative provider discovery uses immutable local catalogues owned by the
modules that declare providers. An explicitly imported manifest composes those
catalogues into an ordered snapshot. A private core staging boundary converts
that snapshot into the existing `BindRecord` representation, after which the
existing `build_specs()` and `build_plan()` pipeline is exclusively
authoritative.

This design selects the internal architecture only. It assigns no public name
to a declaration, catalogue, manifest, or ingestion operation, and selects no
decorator, public method, public class, signature, or argument spelling.

## Goals

- Move composition-root repetition from one entry per provider to one explicit
  import per provider module or explicitly composed domain manifest.
- Keep every provider declaration local to the module that owns its catalogue.
- Produce exactly the `BindRecord` sequence that equivalent manual bindings
  produce and reuse the complete existing validation and runtime pipeline.
- Make imports, catalogue membership, composition order, duplicate behavior,
  and failure boundaries deterministic and auditable from source.
- Preserve exact static types for every existing class and factory provider
  form across all five source type checkers used by the repository.
- Guarantee that discovery has zero role in resolution after `freeze()`.

## Non-goals

- Selecting or documenting public API, decorator syntax, method names, public
  types, signatures, or final terminology.
- Implementing the mechanism, prototyping it, or producing an implementation
  plan.
- Discovering providers by recursively scanning packages, enumerating the
  filesystem, inspecting `sys.modules`, walking module namespaces, using import
  hooks, or following dependency reachability from explicit roots.
- Automatically converting ready-made values, aliases, collections,
  scope-frame values, or provider decoration. Those binding forms remain
  explicit and continue through their current paths.
- Changing provider construction, graph validation, conditions, health checks,
  scopes, overrides, injection, caching, teardown, diagnostics, or rendering.
- Providing live update, hot reload, plugin entry-point discovery, or rollback
  of ordinary Python import side effects.
- Changing the benchmark harness, budgets, expected records, or recorded
  investigation results.

## Architectural invariants

1. A local catalogue has exactly one owning module: the module containing the
   declarations collected into that catalogue. Ownership is determined by the
   declaration site, never inferred from `__module__`, reexports, aliases, or a
   namespace scan.
2. Every catalogue and manifest exposed across a module boundary is an
   immutable, ordered snapshot. No consumer observes a construction buffer or
   a live view.
3. A manifest includes a catalogue or another manifest only through an
   ordinary, explicit Python import and an explicit entry in its ordered
   composition. Importing a package name never implies its descendants.
4. Discovery produces ordinary `BindRecord` values. It introduces no parallel
   provider representation into provider analysis or graph construction.
5. Discovery-specific work ends after an immutable `tuple[BindRecord, ...]`
   has been staged and committed as one contiguous segment of the mutable
   collector snapshot, immediately before the existing `build_specs()` stage.
6. `build_specs()` remains the only authority for conditions, annotation and
   key interpretation, provider shape, parameters, checks, and conversion to
   `ProviderSpec`.
7. `build_plan()` remains the only authority for duplicate keys, missing
   providers, cycles, captive lifetimes, decoration folding, topological order,
   and transitive async requirements.
8. A `FrozenContainer` is constructed only from the completed
   `ResolutionPlan`. No catalogue, manifest, declaration descriptor,
   provenance sidecar, discovery callback, or discovery state survives into
   the frozen runtime.
9. `resolve()`, `aresolve()`, synchronous and asynchronous scopes, overrides,
   injection, warmup, health, and teardown use only the plan and runtime state
   already derived from it. None may contain a discovery hook, branch, lookup,
   registry consultation, import, reflection step, or mutation path.
10. Manual and declarative bindings may coexist, but declarative input receives
    no precedence. The explicit order in which their record segments enter the
    collector is preserved until the current graph algorithm establishes its
    dependency order.
11. Core discovery code uses only the Python standard library and existing
    depin core types. Optional integrations cannot add framework imports or
    framework-specific discovery behavior to the core.

## Internal representations and ownership

### Local declaration descriptor

A local declaration first produces a private immutable descriptor. It carries
the six inputs needed by `BindRecord`—source, lifetime, explicit key, tag,
condition, and health check—plus immutable diagnostic provenance identifying
the declaring module and declaration position. Catalogue identity and manifest
path are added as immutable staging provenance at each composition occurrence.
Provenance is discovery-only data; it is not added to `BindRecord`,
`ProviderSpec`, or `ResolutionPlan`.

The descriptor never replaces or wraps the provider target visible to user
code. Any future declaration syntax must leave the class or callable identity
and exact static type unchanged. How source code creates the descriptor is a
public-API decision outside this design.

### Module-owned catalogue

A catalogue is an immutable ordered tuple of local declaration descriptors.
The declaring module constructs and exports the completed value. Another
module may import the catalogue but cannot append to it, seal it, or register
through it. There is no shared cross-module sink and no process-global index.

A module may own more than one catalogue when it intentionally exposes
different explicit subsets. A catalogue contains each local declaration at an
explicit position. The same immutable descriptor may appear in several
catalogues, but literal composition preserves every occurrence and can
therefore produce a duplicate-provider error.

Catalogue ownership describes who declares the binding, not who originally
defined the target object. An explicitly imported class or callable can be
declared locally without an ownership scan. Reexports and aliases therefore
retain normal Python object identity.

### Explicit manifest

A manifest is an immutable ordered composition of completed catalogue
snapshots and completed nested manifest snapshots. Its module explicitly
imports every input it names. A higher-level manifest may compose domain
manifests, but it gains no implicit transitive search: every edge in the
composition graph is an import and an entry visible in source.

Manifest construction eagerly flattens nested inputs left to right. Catalogue
records remain in local declaration order; a nested manifest contributes its
already flattened order at its declared position. The resulting snapshot is
independent of later imports, reloads, or references to its inputs.

Only a successfully initialized manifest module is consumable. Catalogues are
not fetched from a package, module namespace, loader, registry, entry point, or
filesystem by convention or fallback.

### Private staging boundary

The private staging boundary accepts one completed manifest snapshot. It first
materializes and validates the entire flattened descriptor sequence in local
temporary state. It then maps every descriptor field-for-field to an immutable
`BindRecord(source, scope, provides, tag, condition, check)` and prepares one
tuple. Structural or conversion failure aborts before collector mutation.

Once the tuple is complete, the receiver appends it in one internal mutation.
The manifest therefore occupies one contiguous position relative to manual
bindings and other explicitly composed sources. The collector retains only
the resulting records, not the manifest or its provenance.

This staging operation is the final discovery operation. From its return
onward, the records are indistinguishable from manual records.

## Complete data flow

1. Provider modules are imported only because an explicit manifest imports
   them through ordinary Python statements.
2. Each provider module exposes completed immutable local catalogue snapshots
   containing its ordered private declaration descriptors.
3. The manifest explicitly combines those catalogues, and any explicitly
   imported nested manifests, into one immutable left-to-right snapshot.
4. The private staging boundary eagerly flattens the snapshot, validates its
   structure, constructs every `BindRecord`, and commits the complete tuple to
   the collector once.
5. At this boundary discovery ends. No discovery representation or operation
   crosses into provider analysis.
6. `Container.freeze()` reads the collector's `BindRecord` snapshot and invokes
   the current `build_specs()` path. Active records become `ProviderSpec`
   values; inactive identities remain governed by current condition semantics.
7. The current `build_plan()` path validates and orders the specs and produces
   the immutable `ResolutionPlan`.
8. `FrozenContainer` receives only that plan and derives its current generated
   and instruction-based runtime structures from it.
9. Every resolution operation consults only the plan-derived structures,
   scope frames, caches, context-local overrides, and lifecycle state already
   present in the current runtime.

In compact form:

```text
local declarations
  -> immutable module-owned catalogues
  -> explicitly imported immutable manifest
  -> staged tuple[BindRecord, ...]          discovery ends
  -> build_specs() -> tuple[ProviderSpec, ...]
  -> build_plan() -> ResolutionPlan
  -> FrozenContainer -> resolution
```

## Equivalence with manual bindings

For the same providers and explicit composition position, the declarative path
must produce a `BindRecord` tuple equal field-for-field and in the same order as
the manual path. Equality covers source identity, scope, `provides`, tag,
condition, and check.

Given equal complete record sequences, both paths must produce equal
`ProviderSpec` sequences and equal `ResolutionPlan.order`,
`ResolutionPlan.by_key`, and `ResolutionPlan.inactive` values. They must expose
the same graph diagnostics, async requirements, construction, cache, scope,
override, health, teardown, and error behavior.

There is no declarative fast path, secondary validator, alternate graph, or
alternate runtime. A mismatch is an implementation defect, not an allowed
semantic difference.

## Ordering, duplicates, and conflicts

Ordering is source-controlled and contains no discovery-time sort:

1. each catalogue preserves its local declaration order;
2. each manifest preserves its explicit input order;
3. nested manifests flatten left to right at their declared position;
4. collector composition preserves the position of each complete manifest
   segment relative to manual and other explicit binding sources; and
5. the existing stable graph construction determines dependency order after
   the record sequence enters `build_plan()`.

Repeated catalogues, repeated manifests, overlapping domain manifests, aliases,
reexports, and overlaps with manual bindings are never deduplicated by object
identity or name. Their records remain literal inputs. If two active records
resolve to the same key and tag, the existing `DuplicateProviderError` from
`build_plan()` is authoritative. The same source repeated twice is still a
duplicate. Distinct tags and inactive conditions retain their current
semantics; discovery adds no winner, precedence, or merge rule.

The timing of graph errors also matches manual binding: discovery staging
validates the manifest structure and record conversion, while duplicate,
missing, cycle, lifetime, and other graph validation occurs during
`freeze()` through the existing pipeline.

## Failure atomicity

Atomicity has two explicit boundaries.

At manifest ingestion, imports, manifest construction, flattening, descriptor
validation, and construction of the complete record tuple all finish before
the receiving collector changes. Any failure in those steps leaves its prior
`records()` snapshot unchanged. Successful ingestion performs one depin-owned
append of the already materialized tuple; it cannot expose a prefix.

At freeze, `build_specs()`, `build_plan()`, and frozen-runtime construction
complete from local immutable values before a `FrozenContainer` is returned.
Any existing provider or graph error returns no partial frozen runtime and
does not mutate the collector. Records successfully ingested before that call
remain in the mutable builder exactly as manually registered records do; the
design does not invent rollback semantics for graph errors.

These guarantees assume the existing single-writer collector contract. They do
not make mutable builders safe for concurrent registration.

Python import state is outside both transactions. Successfully imported
dependencies, entries in `sys.modules`, logging, I/O, and arbitrary application
side effects are not rolled back.

## Import behavior

- The application imports the exact manifest module through the ordinary
  Python loader contract. There is no package enumeration or fallback path.
- Regular packages, namespace packages, editable installs, wheels, and zip
  imports behave according to their standard exact-name import semantics. A
  namespace package contributes only the explicitly imported manifest portion.
- A Python-supported import cycle is supported only when catalogue access is
  deferred until the participating modules have completed their required
  initialization. Early cyclic access and partial initialization fail instead
  of publishing or consuming a partial manifest.
- A failed manifest import never reaches the depin staging boundary. Python may
  retain successfully imported dependencies, as it normally does.
- Reexports and aliases preserve explicit object identity; no ownership or
  alias scan runs.
- Known attribute access only is permitted. Discovery never probes arbitrary
  module attributes and therefore never invokes module `__getattr__` as a
  search mechanism.
- Reload is not live update. A reload creates new provider, catalogue, and
  manifest identities. Existing snapshots, collectors, plans, and frozen
  containers remain unchanged. A new builder sees reloaded values only when
  they are explicitly supplied through a newly imported manifest reference.

When application code performs the import, its original import exception
propagates unchanged. If the future public surface introduces a depin-owned
exact-name import boundary, any wrapper it raises must inherit `DepinError`,
must use explicit exception chaining, and must preserve the original exception
in `__cause__`. This requirement does not authorize import-by-search behavior.

## Error integration

Every exception raised by depin-specific declaration, catalogue, manifest, or
staging logic inherits `DepinError`. Invalid declaration metadata, malformed
catalogue entries, invalid manifest members, and failed descriptor conversion
use the existing `InvalidProviderError` boundary with an actionable message
that identifies the manifest, owning module, catalogue, and declaration
position available in provenance.

Once `BindRecord` staging succeeds, existing errors remain authoritative and
are neither translated nor duplicated merely to add a discovery category:

- `InvalidProviderError` for invalid provider shapes, annotations, keys,
  conditions, or checks;
- `InvalidScopeError` for invalid lifetime combinations;
- `DuplicateProviderError` for an active key/tag collision;
- `MissingProviderError` for unsatisfied dependencies;
- `CircularDependencyError` for cycles; and
- `CaptiveDependencyError` for invalid singleton-to-scoped dependencies.

Errors raised while discovery still has provenance name the relevant manifest
and declaration. Errors from the existing provider and graph pipeline keep
their current messages and causal behavior so manual and declarative records
remain equivalent. No error promises rollback beyond depin-owned staging and
freeze state.

## Immutability and state lifetime

Declaration descriptors, exported catalogues, manifests, staged record tuples,
`BindRecord`, `ProviderSpec`, and `ResolutionPlan` are immutable snapshots.
Composition allocates a new snapshot and never mutates an input. A collector's
existing mutability ends at the same point it does today: `freeze()` copies its
records into a plan and creates an independent frozen runtime.

After `freeze()`, mutation of a builder, rebinding a module name, or reloading a
module cannot change the plan or runtime derived from it. No catalogue or
manifest has a back-reference to a collector or frozen container. No global
mutable catalogue, reverse provider index, ambient current catalogue, import
hook, or module registry exists.

Discovery is always opt-in through an explicitly imported manifest. Importing
depin, importing a provider module without its manifest, or resolving from an
unrelated container performs no discovery and changes no discovery state.

## Provider-shape and typing requirements

The declarative frontend must preserve the exact target type for every
currently supported provider source:

| Source form | Required preserved type behavior | Existing lifetime rules |
| --- | --- | --- |
| Class | the same concrete `type[T]` | singleton, scoped, transient |
| Synchronous factory | the same `Callable[P, R]` | singleton, scoped, transient |
| Coroutine factory | the same `Callable[P, Awaitable[R]]` | singleton, scoped, transient |
| Generator factory | the same `Callable[P, Generator[R, None, None]]` | singleton or scoped; transient rejected |
| Async-generator factory | the same `Callable[P, AsyncGenerator[R, None]]` | singleton or scoped; transient rejected |
| Context-manager factory | the same `Callable[P, AbstractContextManager[R]]` | singleton or scoped; transient rejected |
| Async-context-manager factory | the same `Callable[P, AbstractAsyncContextManager[R]]` | singleton or scoped; transient rejected |

Parameter specifications, return or yield types, context-manager wrapper types,
and class identities remain exact. Configuration metadata must statically
accept only current key, scope, tag, condition, and health-check contracts.
Existing `provides()` metadata must compose in either source-order arrangement
without changing the target type or context-manager shape detection.

The eventual public typing surface must use PEP 695 generics, `ParamSpec`, and
overloads where the return type depends on the input. It may not introduce
`Any`, `typing.cast`, checker suppressions, or expected-diagnostic baseline
changes. Positive and negative conformance cases must pass Basedpyright, mypy,
stock Pyright, ty, and Pyrefly under the repository's checked configurations.

The exact relationship between a configured health check's parameter and a
provider target supplied later belongs to the public-API phase. That phase must
either preserve the same check-argument precision as manual `bind(check=...)`
or explicitly omit that configuration shape; it may not use an imprecise type
escape to simulate support. This decision does not affect the internal record
pipeline selected here.

Ready-made values, aliases, collections, scope-frame values, and provider
decoration keep their current typed APIs and are not synthesized from provider
declarations.

## Core and optional integration boundary

The catalogue, manifest, staging, record conversion, and plan boundary belong
to depin core and use no third-party runtime dependency. Core modules never
import FastAPI, Starlette, Flask, Litestar, Taskiq, Typer, Pydantic, or another
optional framework.

An integration under `depin/ext/` may explicitly consume a frozen container or
an application manifest through the same core contract. It may not scan the
framework application, routes, tasks, commands, plugin registries, or loaded
modules for providers. Importing an integration does not import application
provider manifests. Framework-specific injection still resolves through the
same `FrozenContainer` and completed `ResolutionPlan`.

Optional provider modules enter a graph only when an explicitly imported
manifest names their catalogue. Applications that do not import that manifest
pay no import, declaration, freeze, retained-state, or resolution cost for it.

## Test strategy

The implementation phase must establish the following evidence without mocks
of the DI machinery:

1. Unit tests for immutable descriptor conversion, catalogue ownership,
   manifest flattening, nested composition, source order, provenance, malformed
   members, and one-shot collector mutation.
2. Atomicity tests that seed real `Container` and `Registry` instances and
   prove their record snapshots remain byte-for-byte equal after import,
   manifest, descriptor, or conversion failures. A successful staging operation
   appends the whole expected tuple once.
3. Parity tests comparing real manual and declarative containers across class,
   sync, coroutine, generator, async-generator, context-manager, and
   async-context-manager providers; every valid lifetime; lifecycle/transient
   rejection; explicit keys; tags; conditions; checks; and both orders with
   current `provides()` metadata.
4. Exact equality tests for `BindRecord`, `ProviderSpec`, and every
   `ResolutionPlan` field, followed by behavioral checks for resolution,
   scopes, overrides, injection, health, teardown, diagnostics, and errors.
5. Duplicate and conflict tests covering repeated catalogues, repeated and
   nested manifests, overlapping domains, reexports, aliases, manual overlap,
   tags, and inactive conditions. They assert current `build_plan()` outcomes
   and no discovery-specific winner.
6. Import integration tests for regular and namespace packages, editable and
   wheel installs, zip imports, supported and early-failing cycles, partial
   failures, aliases, reexports, module `__getattr__`, loaders without
   enumeration, and reload snapshots. Original causes and depin-owned state
   boundaries are asserted.
7. A five-checker conformance corpus with exact positive assignments and
   negative metadata cases for every provider form. No checker configuration,
   suppression, or expected register changes to accommodate the feature.
8. Runtime guard tests that make any catalogue, manifest, import, or discovery
   operation fail if touched after plan construction, then exercise
   `resolve()`, `aresolve()`, scopes, overrides, and injection through real
   containers. The test must fail when the guard separating discovery from
   runtime is removed.
9. Whole-package coverage of at least 95%, with every public error and edge
   branch introduced by the eventual API exercised.

All tests are deterministic. Import and concurrency cases synchronize through
explicit state or events, never sleeps, network access, or clock timing.

## Performance acceptance

The higher-power investigation already established decisive `freeze()` PASS
results for both retained scales:

| Workload | Absolute point / U95 / limit | Relative point / U95 / limit | Result |
| --- | ---: | ---: | --- |
| 100 providers | +0.022135 / +0.051490 / +0.600000 ms | 1.001480 / 1.003443 / 1.100000 | **PASS** |
| 1,000 providers | +1.119652 / +1.211556 / +1.500000 ms | 1.007468 / 1.008081 / 1.100000 | **PASS** |

Those results remain completed evidence and are not rerun by this design.

The implementation acceptance gate retains the resolution limits of at most
+50 ns per resolution and a ratio of at most 1.05. It compares synchronized
`main` with the real implementation, not two identical-source checkouts. Before
timing, the candidate and control must construct equivalent provider graphs,
exercise identical resolution workloads, and demonstrate equal plan-relevant
inputs. The implementation passes only when the existing paired decision rule
meets both the absolute and relative limits; one limit cannot compensate for
the other.

The earlier identical-source control is not repeated. Its +134.879 ns point,
+101.553 ns L95, and +161.847 ns U95 remain an honest FAIL under the original
+50 ns contract, while its passing ratio remains recorded. Because R0 and R1
had identical `depin/**/*.py` hashes and no discovery runtime code, that result
is evidence about the measurement system rather than causal evidence of
discovery overhead.

The implementation must satisfy the structural zero-overhead invariant before
measurement: no discovery hook, branch, lookup, state, or retained object may
exist in resolution. This design session changes nothing under `benchmarks/`,
does not edit `budgets.toml`, and does not update any expected performance
record.

## Rejected alternatives

- **Recursive package scanning:** rejected because it imports and enumerates an
  implicit tree, depends on loader enumeration, complicates namespace packages,
  cycles, aliases, reload, and partial failure, and hides the composition root.
- **Filesystem fallback:** rejected because an installed package need not map
  to an enumerable filesystem and because it creates loader-dependent behavior
  outside ordinary Python imports.
- **`sys.modules` scanning:** rejected because the loaded-module set is ambient,
  order-sensitive process state with no application ownership boundary.
- **Module namespace inspection:** rejected because it mistakes aliases and
  reexports for ownership, can invoke `__getattr__`, and makes unrelated
  attributes part of discovery cost and semantics.
- **Explicit-root reachability as the primary mechanism:** rejected because it
  cannot find direct-only providers, abstract-key implementations, or all
  key/tag/factory cases without a hidden reverse index.
- **A shared mutable or process-global catalogue:** rejected because imports
  would mutate ambient state, applications would interfere, reload would be
  live mutation, and collector snapshots would lose isolation.
- **Entry points, plugin registries, and import hooks:** rejected because they
  make discovery installation- or process-global and introduce implicit import
  and ordering behavior.
- **Deduplication or precedence during manifest composition:** rejected because
  it hides configuration conflicts and diverges from manual binding semantics.
- **A discovery-aware frozen runtime:** rejected because it adds unused-path
  overhead and creates a second source of provider truth after graph validation.
- **A separate declarative validation or construction pipeline:** rejected
  because it would drift from existing provider shapes, lifetimes, errors,
  overrides, health, and teardown behavior.

Manual binding remains supported as the explicit baseline and interoperability
path. It is not rejected; declarative manifests must remain exactly equivalent
to it after record staging.

## Decisions deferred to the public API and naming phase

The following decisions are intentionally outside this internal mechanism and
do not block it:

- public names for declarations, catalogues, manifests, and ingestion;
- whether the declaration spelling is a decorator or another identity-
  preserving source form;
- public methods, classes, constructors, parameters, overload layout, and
  argument ordering;
- the public spelling for selecting or composing multiple catalogues owned by
  one module;
- the precise typed surface that relates a configured health check to a
  provider supplied later;
- whether discovery-specific context requires a new public `DepinError`
  subclass or is fully represented by existing public errors; and
- documentation, migration guidance, and release positioning for the eventual
  public surface.

The later API phase must obey every invariant in this document. It cannot
reopen recursive scanning, ambient discovery, runtime discovery, implicit
conflict resolution, or an alternate provider pipeline as a naming choice.
