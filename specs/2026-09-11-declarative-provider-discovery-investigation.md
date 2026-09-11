# Declarative provider discovery design investigation

Date: 2026-09-11
Status: investigation complete; mechanism recommended for formal design; public API unselected
Source proposal: [declarative provider discovery](proposals/2026-09-05-declarative-provider-discovery-proposal.md)

## Decision boundary

This investigation recommends **module-owned local provider catalogues composed
through an explicitly imported manifest** as the mechanism to take into a future
design phase. It does not accept a decorator name, a binding-collector method,
an argument shape, or an implementation.

Recursive package scanning is not selected as the definitive mechanism.
Reachability from explicit roots is not sufficient as the primary mechanism,
although a later design could evaluate it as an opt-in pruning rule after a
complete explicit catalogue exists.

The recommendation is conditional. The formal-design gate at the end of this
document must be satisfied before a public contract is written.

## Evidence examined

### Repository behavior

- [`BindingCollector`](../depin/_core/bindings.py) stores immutable
  `BindRecord` values, returns a tuple snapshot from `records()`, and copies
  records from a `Registry` into a `Container`.
- [`build_specs()`](../depin/_core/providers.py) evaluates conditions, resolves
  annotations and `provides()` metadata, detects provider shape, and converts
  active records into immutable `ProviderSpec` values.
- [`build_plan()`](../depin/_core/graph.py) rejects duplicate and missing
  providers, cycles, and captive lifetimes before returning an immutable
  `ResolutionPlan`.
- [`FrozenContainer`](../depin/_core/frozen.py) receives only that plan and
  derives its generated or instruction-based resolution paths from it. There is
  no registration lookup in the resolution path.
- [`ScopeDecorator`](../depin/_core/bindings.py) already returns a decorated
  class or callable unchanged. The five-checker registration corpus in
  [`c07_registration.py`](../conformance/corpus/core/c07_registration.py)
  verifies assignability for classes and callable parameters, while the
  `provides()` marker preserves a concrete class type.
- Existing provider tests cover classes, synchronous and asynchronous
  factories, generators, async generators, context managers, all three
  lifetimes, conditions, tags, checks, decoration, aliases, collections, scope
  values, graph errors, resolution, overrides, caching, and teardown.
- The [source conformance harness](../conformance/README.md) explains how mypy,
  Basedpyright, stock Pyright, ty, and Pyrefly check the same source and consumer
  contracts without treating `Any` as successful evidence.
- The accepted [discovery proposal](proposals/2026-09-05-declarative-provider-discovery-proposal.md)
  supplies the consumer outcome, provider-parity boundary, rejected global and
  lazy mechanisms, and performance evidence requirements.

### Python import and loader behavior

The following Python 3.12 contracts constrain any discovery mechanism:

- The [import system](https://docs.python.org/3.12/reference/import.html#loading)
  checks `sys.modules` first and inserts a module before its loader executes it.
  This makes circular imports possible but also makes a partially initialized
  module observable during its import.
- When execution fails, Python removes the failing module from `sys.modules`.
  Successfully imported side-effect modules remain cached. Depin can therefore
  make its own collector mutation atomic, but it cannot truthfully promise to
  roll back Python import effects.
- [Namespace packages](https://docs.python.org/3.12/reference/import.html#namespace-packages)
  can have portions in multiple filesystem, zip, network, or virtual locations.
  Their paths are dynamic rather than a fixed directory list.
- [`pkgutil.walk_packages()`](https://docs.python.org/3.12/library/pkgutil.html#pkgutil.walk_packages)
  imports packages to read their `__path__`. Enumeration requires a non-standard
  finder `iter_modules()` method; the standard library supplies adapters for
  `FileFinder` and `zipimporter`, not a universal loader contract.
- [`importlib.import_module()`](https://docs.python.org/3.12/library/importlib.html#importlib.import_module)
  follows ordinary import semantics. Exact explicit imports therefore have a
  wider loader contract than recursive enumeration.
- [`importlib.reload()`](https://docs.python.org/3.12/library/importlib.html#importlib.reload)
  retains the module dictionary, redefines objects with new identities, and does
  not rebind references imported elsewhere with `from ... import ...`.

A disposable Python 3.12 probe, retained only as these results, confirmed that:

- sorted `walk_packages()` enumeration found regular, two-portion namespace,
  and zip-package modules in the standard finders tested;
- filtering by `target.__module__ == module.__name__` excluded a package
  reexport, and identity deduplication collapsed an alias in its defining
  module;
- reload created a new class identity, left a `from`-import reference on the old
  class, and retained a module name not recreated by the second execution; and
- a failed module disappeared from `sys.modules`, while a dependency it imported
  successfully remained cached.

The probe shows useful behavior for common loaders. It cannot turn the
non-standard enumeration hook into a general Python loader guarantee.

## Existing pipeline and required insertion boundary

The only acceptable data flow is:

```text
explicit declaration source
  -> stage complete tuple[BindRecord, ...]
  -> append once to a mutable BindingCollector
  -> build_specs()
  -> build_plan()
  -> FrozenContainer(ResolutionPlan)
```

Discovery-specific work ends before `build_specs()`. The current pipeline then
remains authoritative for provider shape, annotations, conditions, explicit
keys, tags, checks, lifetime validity, graph validation, async propagation,
construction, caching, overrides, health, teardown, and diagnostics.

The atomicity boundary is the receiving `Container` or `Registry`: imports,
manifest loading, declaration extraction, and record construction must all
succeed before its record list changes. Python's module cache and arbitrary
application import side effects are outside that transaction and must be
documented as such.

## Alternatives compared

The terms below describe mechanisms only. None implies a public name.

- **Explicit package/module discovery:** import named modules and inspect their
  namespaces for marked targets; package recursion also enumerates descendants.
- **Local provider catalogue:** each provider module owns an explicit catalogue;
  an explicitly imported manifest combines selected catalogues and hands a
  snapshot to a collector.
- **Explicit-root reachability:** start from named roots and materialize marked
  concrete dependencies reached through their annotations.

| Criterion | Explicit package/module discovery | Local provider catalogue | Explicit-root reachability |
| --- | --- | --- | --- |
| Imports and loaders | Exact module imports use the normal loader contract, but recursive package enumeration depends on non-standard finder support and imports the entire selected tree. | Uses only ordinary, explicit imports. A namespace package needs an explicit importable manifest module; it is not recursively enumerated. | Imports only explicitly referenced roots and whatever normal imports their modules perform. It cannot infer which module implements an abstract key. |
| Determinism | Sorting fully qualified module names and inspecting `vars(module)` can stabilize common cases. Reexports need ownership filtering; aliases need deduplication; reload changes identities and retains names. | Manifest membership and composition order are source-controlled. Reexports are ordinary catalogue aliases, not namespace scan results. Reload produces a new catalogue; existing collector snapshots remain unchanged. | Traversal order can be stable, but forward references, unions, abstract keys, tags, and multiple implementations do not define a unique next provider. |
| Partial imports | A caller can pass or observe a partially initialized module. Recursive import failure may leave successfully imported siblings or dependencies cached. | A manifest is consumed only after its import completes. A failed import never reaches the receiver, though successful dependency imports remain cached under normal Python rules. | A root object already obtained from a partial module can expose an incomplete annotation graph; there is no public initialized-module predicate to make this generally safe. |
| Container isolation | Markers on targets avoid a global registry, but imported modules and their side effects still share the process cache. Domains can be bounded per collector. | Each module owns its catalogue; each container copies the selected manifest snapshot. A cross-module shared mutable catalogue is explicitly rejected. | The root set and staged closure can be local to one collector, so no global provider state is required. |
| Atomic failure | Records can be staged before one append, but imports themselves cannot be rolled back. Namespace inspection must finish without invoking module `__getattr__`. | Import the manifest, obtain all record snapshots, then append once. Module-owned catalogues prevent a failed sibling import from partially mutating a shared catalogue or receiver. | The entire closure can be staged before append, but annotation or metadata errors may appear only after a deep traversal. |
| Provider forms and lifetimes | Marked classes and every factory shape can become ordinary records. Decorator order and ownership of wrapped functions need a precise rule. | A typed identity declaration can record every class/factory shape and all `BindRecord` options. Existing value, alias, collection, scope-value, and decoration APIs remain explicit as the proposal requires. | Concrete class construction is natural. Factories, abstract-to-concrete mappings, tokens, tags, multiple implementations, direct-only providers, and conditional choices require an external index, defeating pure reachability. |
| Five-checker typing | Feasible only if declaration metadata returns the exact target type. The scanner itself adds no typing value and cannot repair an erasing decorator. | Strongest existing evidence: collector-bound scope decorators already preserve class and callable types across the corpus. A future form still has to prove health-check and all metadata configurations in all five checkers. | Root arguments can be typed, but discovered registration is not represented statically. Any declaration metadata still needs the same five-checker proof as the other mechanisms. |
| Explicit discovery limit | Exact modules are clear. Recursive package boundaries are syntactic but not uniformly enumerable across loaders, and importing every descendant is broader than provider membership. | The manifest lists exactly the catalogues in the domain. Nothing outside those imports can appear, and a catalogue cannot be found merely because its module is in `sys.modules`. | The explicit roots and their transitive, resolvable annotation edges are the boundary. A primary provider absent from that closure is invisible. |
| Expected import/discovery/freeze cost | Cold cost is all selected module imports plus enumeration, namespace inspection, ownership checks, deduplication, and sorting. Warm discovery still scans attributes. Freeze remains the existing cost for the resulting graph. | Cold cost is explicit manifest imports. Registration and composition are linear in declared providers/catalogues, with no attribute scan. Freeze is unchanged for an equivalent record set. | Lowest cost for a small reachable subset, but adds a pre-freeze graph traversal and repeated annotation/metadata work before the normal graph is built. |
| Expected retained memory | Python retains every imported descendant; declarations add metadata and staged records. The frozen plan is unchanged after staging is released. | Retains explicitly selected modules, their catalogues, their normal transitive imports, and the same frozen plan, while avoiding descendants imported only by recursive scanning. Collector snapshots are linear in declared providers. | Retains roots and the reachable records, but any reverse implementation index needed for parity becomes a catalogue under another name. |
| Resolution when unused | Can be zero only if no scan hook, global index, or resolution fallback is installed and `FrozenContainer` remains plan-only. | Naturally zero: consumers that do not import or include a catalogue keep the current registration and frozen runtime paths. | Can be zero if traversal ends before plan creation; any lazy expansion from `resolve()` is rejected. |
| Result | Do not select recursive package scanning as the default. Exact-module inspection is narrower but keeps reexport/reload/attribute-scan complexity without beating an explicit catalogue. | **Recommended for formal design**, subject to the gate below. It provides direct primaries, explicit bounds, ordinary import behavior, isolation, and the smallest new mechanism. | Reject as the primary mechanism because it fails the direct-primary and provider-parity contracts. Reconsider only as optional pruning after complete catalogue selection. |

## Cost model and evidence boundary

Let `M` be imported modules, `A` inspected module attributes, `C` composed local
catalogues, `P` providers, and `E` dependency edges.

- Recursive scanning adds roughly `O(M + A)` discovery work, plus sorting, on
  top of Python import execution. It retains all imported modules whether or not
  they contain providers.
- Local catalogues add `O(P)` declaration recording and `O(C + P)` manifest
  composition. They inspect no unrelated module attributes.
- Root reachability adds `O(P_reachable + E_reachable)` traversal before the
  existing plan builder, but cannot achieve parity without another provider
  index.
- For equal `BindRecord` sets, every alternative should have the same
  `build_specs()`/`build_plan()` complexity and the same frozen-plan memory.
- No benchmark, budget, or published evidence is changed by this investigation.

Zero unused-resolution impact is structural, not aspirational: discovery must
not add a branch, lookup, registry consultation, reflection step, or mutation
hook to `FrozenContainer`. Equivalent manual and catalogue-derived records must
produce equivalent plans, and existing no-discovery resolution workloads must
remain the control.

### Pre-registered disposable cost contract — 2026-09-11

This contract was written before running or inspecting any discovery cost
measurement. It evaluates a name-neutral throwaway prototype, not a proposed
API. The generated workload sizes are 10, 100, and 1,000 providers, split into
modules of at most ten providers. Every variant defines and imports the same
provider sources and builds the same dependency graph.

The controls are:

- **I0, import-only:** explicit imports of the generated modules, with the same
  provider definitions but no declaration metadata or catalogue construction;
- **M, manual:** I0 followed by the current public binding calls, one call per
  provider, and the current `freeze()` pipeline;
- **C, catalogue:** ordinary explicit imports of modules that own immutable
  local record tuples, followed by an explicitly imported manifest that stages
  those tuples before one receiver mutation; and
- **R0, no-discovery resolution:** the unchanged transient-resolution workload
  run from synchronized `main` at
  `a618c7aaea0d92dbad6d758f8873242f0c32c760`; **R1** is the same workload and
  source run from the investigation branch. Documentation is excluded from the
  import path for both.

Cold import is measured in fresh interpreters and includes Python loading plus
module-local declaration work; I0 isolates the cost of loading the same source
modules. Hot declaration/composition is measured separately after importing the
targets: M times the equivalent binding calls, while C times local immutable
record construction, ordered manifest staging, validation, and its single
receiver commit. Freeze timing begins only after equal `BindRecord` tuples have
been demonstrated and ends when the current `ResolutionPlan` is built. Retained
memory is the live `tracemalloc` delta after `gc.collect()`, never peak memory,
recorded before and after freeze against both I0 and M.

Each timing result uses 20 independent paired samples after three discarded
warm-up pairs. Pair order alternates AB/BA, `PYTHONHASHSEED=0`, the same
interpreter and environment, and garbage collection disabled only inside the
timed interval. Inner loops are calibrated without inspecting comparative
results to last at least 50 ms; cold import remains one fresh import per
interpreter. Memory uses 15 fresh paired interpreters. Paired ratios and paired
differences are summarized by the median. A deterministic bootstrap with seed
`20260911` and 10,000 resamples supplies one-sided 95% lower and upper
confidence bounds.

| Metric, for each provider count | Absolute upper bound | Upper bound relative to baseline |
| --- | --- | --- |
| C cold import versus I0 | incremental time at most `2 ms + 30 µs × P` | C/I0 at most 3.00 for P=10, 1.75 for P=100, and 1.50 for P=1,000 |
| C declaration plus manifest composition versus M binding | incremental time at most `1 ms + 15 µs × P` | C/M at most 2.50 for P=10 and 2.00 for P=100 or 1,000 |
| C freeze versus M freeze after record equality | incremental time at most `0.5 ms + 1 µs × P` | C/M at most 1.10 |
| C retained memory before freeze versus I0 and M | C−I0 at most `64 KiB + 512 B × P` | C−I0 at most `1.25 × (M−I0) + 64 KiB` |
| C retained memory after freeze versus I0 and M | C−M at most `64 KiB + 64 B × P` | C−I0 at most `1.25 × (M−I0) + 64 KiB`, and C/M at most 1.10 after subtracting interpreter startup |
| R1 warm resolution versus R0 | incremental time at most 50 ns per resolution | R1/R0 at most 1.05 |

A metric is **PASS** only when its point estimate and one-sided 95% upper
confidence bound meet every applicable absolute and relative bound. It is
**FAIL** when the point estimate and one-sided 95% lower confidence bound exceed
any applicable bound. It is **INCONCLUSIVE** otherwise, including unavailable
controls, fewer samples, non-positive adjusted memory denominators, or a plan
inequivalence. Every provider count must pass independently; no averaging across
sizes or compensating one regression with another is allowed. A complete cost
gate passes only if all timing and memory rows pass at all sizes, every M/C
record tuple and `ResolutionPlan` is equal, R0/R1 source hashes match, and the
resolution control passes. A noisy or inconclusive result is not permission to
loosen this contract; it requires a fresh pre-registered experiment in a later
investigation.

## Recommended mechanism for a future design

The design candidate should have these properties:

1. A provider module owns its catalogue. Declaration beside a class or factory
   records ordinary `BindRecord` data in that catalogue and returns the target
   unchanged.
2. A manifest explicitly imports and combines the catalogues that form one
   application domain. It does not enumerate a package, inspect `sys.modules`,
   or discover descendants from the filesystem.
3. A container or registry consumes a complete manifest snapshot before
   `freeze()`. Import, manifest, or declaration failure leaves that receiving
   collector unchanged.
4. Two containers can consume disjoint or shared snapshots without later
   catalogue mutation changing either container.
5. Reload is not a live-update facility. A frozen container never changes; a
   newly built container sees only the catalogue object explicitly supplied to
   it after any controlled reload.
6. The resulting records enter the existing provider and graph pipeline without
   a second validation, construction, caching, scope, override, or teardown
   path.

This mechanism shifts the explicit list from every provider at the composition
root to one import per provider module in a domain manifest. The future design
must verify that this is a meaningful ergonomic improvement rather than merely
moving the same repetition.

## Risks and rejection conditions

Reject the recommended mechanism if any of the following is required:

- provider modules mutate one shared cross-module catalogue during import;
- a process-global catalogue, ambient `sys.modules` scan, implicit package
  recursion, or post-`freeze()` registration is needed for correctness;
- importing a manifest can partially mutate the receiving collector;
- the manifest must repeat one entry per provider rather than one explicit
  module/catalogue boundary;
- any supported class/factory shape, lifetime, key, tag, condition, check,
  `provides()` composition, override, health, or teardown behavior bypasses the
  current `BindRecord` pipeline;
- declaration order around generator/context-manager or ordinary decorators
  cannot be specified without surprising shape changes;
- any of the five checkers loses the exact decorated target type, reports new
  source diagnostics, or requires a suppression/baseline increase;
- a custom error fails to inherit `DepinError`, hides the original import cause,
  or promises rollback of Python import side effects;
- unused applications pay resolution overhead, or equal record sets produce
  observably different frozen plans; or
- measured import, declaration, freeze, or retained-memory cost is worse than
  explicit module inspection while satisfying no stronger consumer outcome.

Recursive package scanning stays rejected as the definitive mechanism unless a
later investigation supplies a bounded loader contract, deterministic reload
and reexport rules, and measured value that the explicit-manifest approach
cannot provide. Pure root reachability stays rejected unless it can represent
direct-only providers and all factory/key/tag cases without introducing a hidden
global reverse index.

## Open questions

- What declaration metadata shape covers `scope`, explicit key, tag, condition,
  and health check for every class/factory form while preserving exact types?
- What is the smallest manifest contract that composes module-owned catalogues
  without accepting a new public naming scheme prematurely?
- Is repeated inclusion of the same catalogue an existing duplicate-provider
  error, or should manifest composition remove exact repeated record identities?
- Which decorator orders with `provides()`, generator/context-manager wrappers,
  and ordinary wrappers are supported, rejected, or normalized?
- Is reload explicitly outside the supported contract, or must a new-container
  workflow after controlled reload receive deterministic tests?
- Which import failures need a discovery-specific `DepinError` subtype, and
  which existing provider/graph errors remain authoritative?
- Which numerical, baseline-relative import, declaration, freeze,
  retained-memory, and no-discovery resolution bounds will be recorded before
  measuring 10, 100, and 1,000 providers?
- Does a manifest with one entry per provider module remove enough
  composition-root repetition in representative applications to justify a new
  public surface instead of documenting the existing `Registry` pattern?

## Objective gate for writing a formal design

A formal design may be written only when all of these checks are green:

1. **Consumer proof:** the same representative application is expressed with
   manual binding, module-owned catalogues, and explicit roots; the catalogue
   form includes a direct-only primary provider and reduces composition-root
   entries from providers to modules without hiding imports.
2. **Atomicity proof:** a disposable prototype shows that an import failure,
   invalid declaration, and manifest-composition failure each leave the
   receiving collector's `records()` tuple equal to its pre-operation snapshot.
   The write is one commit after complete staging.
3. **Provider-parity map:** every source and option in the proposal maps to a
   `BindRecord` field and an existing `ProviderSpec`/`ResolutionPlan` path;
   excluded value/alias/collection/scope-value/decoration forms remain explicit.
4. **Import contract:** regular modules/packages, an explicit manifest under a
   namespace package, editable and wheel installs, and zip imports use only
   ordinary import semantics. Unsupported custom-loader or reload behavior is
   stated as a boundary, not silently skipped.
5. **Determinism contract:** manifest order, reexports, repeated and overlapping
   catalogues, duplicates, aliases, import cycles, partially initialized
   modules, and reload each have one testable outcome.
6. **Typing proof:** a throwaway signature prototype covers configured and
   unconfigured declaration of every provider shape in the five-checker corpus,
   with no `Any`, suppression, new diagnostic, or expected-register increase.
7. **Cost acceptance contract:** before measurement, a dated probe contract
   records numerical baseline-relative upper bounds and a statistical decision
   rule for import overhead against importing the same application modules,
   declaration and freeze overhead against manual binding of the same graph,
   retained memory against both controls, and no-discovery resolution against
   current `main`. No result is seen before those pass/fail bounds are fixed.
8. **Cost proof:** disposable 10, 100, and 1,000-provider measurements separate
   imports from catalogue work and freeze, record retained memory, demonstrate
   plan equivalence, and meet every predeclared bound, including the
   no-discovery resolution control. They do not edit `budgets.toml` or published
   evidence.
9. **Error contract:** proposed failure classes all inherit `DepinError`, retain
   import exception chaining, name the requested manifest and failing module or
   declaration, and limit atomicity claims to depin-owned state.

The mechanism comparison and import-system analysis are complete. The consumer,
atomicity, five-checker signature, and bounded cost proofs remain prerequisites,
not implementation work authorized by this investigation.
