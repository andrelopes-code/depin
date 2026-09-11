# Declarative provider discovery design investigation

Date: 2026-09-11
Status: investigation complete; mechanism retained; formal-design gate failed; public API unselected
Source proposal: [declarative provider discovery](proposals/2026-09-05-declarative-provider-discovery-proposal.md)

## Decision boundary

This investigation retains **module-owned local provider catalogues composed
through an explicitly imported manifest** as the recommended mechanism, but the
completed cost gate blocks it from advancing into a formal-design phase. This
document does not accept a decorator name, a binding-collector method, an
argument shape, or an implementation.

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
| Result | Do not select recursive package scanning as the default. Exact-module inspection is narrower but keeps reexport/reload/attribute-scan complexity without beating an explicit catalogue. | **Retain as the recommended mechanism; formal design remains blocked by the gate below.** It provides direct primaries, explicit bounds, ordinary import behavior, isolation, and the smallest new mechanism. | Reject as the primary mechanism because it fails the direct-primary and provider-parity contracts. Reconsider only as optional pruning after complete catalogue selection. |

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

This contract was committed as `4dea4b9`; the cost results first appear in the
later commit `8b1ce17`. It evaluates a name-neutral throwaway prototype, not a
proposed API. The generated workload sizes are 10, 100, and 1,000 providers,
split into modules of at most ten providers. Every variant defines and imports
the same provider sources and builds the same dependency graph.

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

## Disposable proof results — 2026-09-11

All names used by these probes were fixture-local placeholders. They accept no
public decorator, catalogue, manifest, method, exception, or signature. The
cost contract is retained in commit `4dea4b9`; the results were first retained
in commit `8b1ce17`. The checkout used CPython 3.12.13 and uv 0.11.13 unless a
row says otherwise.

The scripts, generated packages, wheels, environments, and raw outputs were
temporary by design. To make the recorded runs identifiable, their SHA-256
digests before disposal were:

| Evidence | SHA-256 |
| --- | --- |
| Import-contract script / output | `a07a2e27ae57096923e03665e0a633cf350527be349954fcb8b879da6d75ac9b` / `15b1b53f63de9e698e135556f8dda5128773278934e8b845747c807810e76d69` |
| Typing positive / negative fixtures | `f7a4b8602de8d02d183e76f27cf43d3fde6386a9254e7cb2ec35fe843885b22b` / `d364522305f95a5dec193edf2d06d20578f1e4b2829c17a60c19a16597ea6080` |
| Cost script / JSON result | `f501f7f14861dcdd7f0287044cb5896e02546f87ec2a114c3dc95ad8d64c561d` / `1d2f7e7b62ffbbda237656f6c89ef5f08ce9fec7390be6cb0d34ad2657c3409f` |

The digests identify the retained runs; they are not substitutes for source.
The fixture construction, commands, assertions, configurations, and transcripts
needed to reconstruct the discarded probes are recorded below. Run them from
synchronized `a618c7a` after `uv sync --all-groups --all-extras`. Nothing
depends on an unpublished depin implementation.

### Consumer comparison

One representative nine-provider graph was built three ways. It contained a
`DirectPrimary` resolved only by primary lookup, `SqlStore` under the abstract
`Store` protocol and tag `primary`, a dependent sync `make_client` factory, a
coroutine factory, generator and async-generator lifecycle factories,
`contextmanager` and `asynccontextmanager` factories, `when=True`, a `healthy`
check, and a class carrying current `provides()` metadata.

| Form | Composition-root entries | Result |
| --- | ---: | --- |
| Current manual binding | 9 provider-level `bind()` calls | 9 records |
| Module-owned immutable catalogues | 2 local catalogues containing the same 9 records | no shared mutable catalogue |
| Explicit manifest | 2 explicit catalogue imports | ordered 9-record snapshot |

Moving from nine individual root bindings to two module imports removes seven
provider-level entries, a 77.8% reduction, while leaving both imports visible.
The manifest imported `CORE_CATALOGUE` and `LIFECYCLE_CATALOGUE` explicitly; it
did not enumerate a package, filesystem, or `sys.modules`.

Manual and catalogue tuples compared equal over every `BindRecord` field. Their
plans compared equal both as `ResolutionPlan` dataclasses and as explicit
signatures over `order`, `by_key`, `inactive`, and every ordered
`ProviderSpec` field. The disposable program exited zero with 20 top-level
assertions, and the current provider, lifecycle, health, and graph-validation
tests passed with 146 tests. A root set containing only `make_client` could
neither find direct-only `DirectPrimary` nor infer that `SqlStore` implements
its tagged `Store` parameter. Root reachability therefore still needs a reverse
provider index for the abstract-key case and explicit enumeration for the
direct-only case; it remains rejected as the primary mechanism.

### Atomic receiver mutation

The prototype imported and concatenated complete catalogue snapshots, checked
that every element was an immutable `BindRecord`, and called current
`build_plan(staged)` before one `include()` on a real receiver. A seeded
`Container` and `Registry` changed from exactly `before` to `before + staged`
only on successful commit. For every failure below, a commit-call counter stayed
at zero and `tuple(receiver.records()) == before` remained true:

| Failure before commit | Observed staging result |
| --- | --- |
| Manifest import | original `ImportError` from the deliberately failing module |
| Invalid declaration | current `InvalidProviderError` for source `42` |
| Manifest composition | fixture-local rejection of a non-immutable/non-record tuple |
| Duplicate binding | current `DuplicateProviderError` for `Store`, tag `primary` |
| Repeated catalogue | the same current duplicate error; no identity de-duplication |
| Overlapping catalogues/domains | the same current duplicate error; no implicit winner |

This is staging plus one depin-owned mutation, not transactional Python import.
Successfully imported dependencies, `sys.modules`, logging, I/O, or any other
application import effect are outside the atomicity claim and are not rolled
back.

### Provider parity

Every automatically converted declaration must populate the existing frozen
`BindRecord(source, scope, provides, tag, condition, check)` and then use
`build_specs()` and `build_plan()` unchanged.

| Hypothetical declaration input | Existing authoritative path | Valid scopes proved |
| --- | --- | --- |
| Class | `source` -> class shape -> `ProviderSpec` -> graph | singleton, scoped, transient |
| Sync factory | `source` -> function shape and typed parameters -> graph | singleton, scoped, transient |
| Coroutine factory | `source` -> async-function shape/flag -> graph | singleton, scoped, transient |
| Generator factory | `source` -> generator lifecycle shape -> graph/teardown | singleton, scoped; transient rejected |
| Async-generator factory | `source` -> async-generator lifecycle shape -> graph/teardown | singleton, scoped; transient rejected |
| `contextmanager` factory | `source` -> context-manager lifecycle shape -> graph/teardown | singleton, scoped; transient rejected |
| `asynccontextmanager` factory | `source` -> async-context-manager lifecycle shape -> graph/teardown | singleton, scoped; transient rejected |
| Explicit key | `provides` -> current key resolution -> `ProviderSpec.key` | same as its source form |
| Tag | `tag` -> provider identity and `by_key` | same as its source form |
| Activation | `condition` -> current active/inactive filtering | same as its source form |
| Health check | `check` -> current checked-provider/health path | same as its source form |
| Existing `provides()` | current target metadata lookup composed in both decorator orders | class case proved |

The parity loop executed nine valid non-lifecycle shape/lifetime combinations,
eight valid lifecycle combinations, and all four lifecycle/transient
rejections. Ready-made values, aliases, collections, scope-frame values, and
provider decoration remain explicit APIs and are not automatic declaration
conversions.

### Import and determinism contract

The combined import evidence produced 24 PASS and no unresolved case: 22 core
loader/import assertions under Python 3.12.3, plus two follow-up editable and
wheel install assertions in fresh uv-managed CPython 3.12.13 environments. The
packaging reproduction commands were `uv venv`, `uv pip install --python
<venv>/bin/python -e <fixture>`, `uv build --wheel`, and installation of that
exact wheel into a second fresh environment.

| Case | Deterministic supported outcome |
| --- | --- |
| Regular module/package | import the exact manifest name and read its explicit catalogue references |
| Namespace package | import an explicit manifest from one portion; do not enumerate or include another portion |
| Editable/wheel install | the exact installed manifest imports and exposes the same catalogue tuple |
| Zip import | the exact manifest imports through the standard zip loader |
| Python-supported cycle | a cycle that defers catalogue access until both modules initialize completes as `('A', 'B')` |
| Early cyclic/partial access | ordinary `ImportError`/initialization failure; no manifest is consumed and the receiver stays unchanged |
| Partial import failure | the failing module is not consumable; successfully imported dependencies can remain cached |
| Reexport/alias | explicit references preserve object identity; no ownership or alias scan |
| Manifest/catalogue order | preserve manifest source order and each local declaration order; graph topological order remains authoritative afterward |
| Repeated/overlapping catalogue | preserve literal composition, then reject duplicate key/tag through current validation; never silently de-duplicate or select a winner |
| Module `__getattr__` | exact known imports/access avoid it; arbitrary namespace probing invokes it and is forbidden |
| Custom loader without enumeration | exact-name import succeeds; no `iter_modules` or equivalent is required |
| Reload | outside live-update support: reload creates new catalogue/provider identities; old references and snapshots remain old |

The reload probe froze a real container from the old catalogue, rewrote and
reloaded the provider module, and observed version `1` both before and after
reload. The old record tuple stayed equal, the reloaded class/catalogue had new
identities, and the frozen container rejected the new class key. A newly built
container may see only the new catalogue object explicitly supplied to it.

There is deliberately no fallback based on the filesystem, `sys.modules`,
implicit or recursive package scanning, module attribute enumeration, or
loader-specific enumeration. Python import caching and application side effects
remain ordinary Python behavior, not depin-owned state.

### Five-checker typing proof

A name-neutral identity declaration used overloads for bare and configured
forms. Seventeen typed identity assignments covered a class plus paired bare and
configured sync, coroutine, generator, async-generator, context-manager, and
async-context-manager factories. Configured cases supplied scope, key, tag,
condition, and health-check metadata. Both orders with current `provides()` were
typed. Factory parameter and return/yield/context-manager wrapper types stayed
exact.

| Checker pinned by the repository on this date | Positive fixture | Negative fixture |
| --- | --- | --- |
| mypy 2.3.1 | `mypy --strict`: zero diagnostics | five intended errors |
| Basedpyright 1.39.10 / Pyright 1.1.412 | repository-strict disposable config: zero errors, warnings, or notes | five `reportArgumentType` errors |
| stock Pyright 1.1.411 | source-gate-equivalent config: zero diagnostics | five `reportArgumentType` errors |
| ty 0.0.79 | repository-equivalent config: all checks passed | five `invalid-argument-type` diagnostics |
| Pyrefly 1.2.0 | `--preset strict` plus repository-equivalent config: zero errors | five `bad-argument-type` diagnostics |

The five negative cases supplied an invalid scope, key, tag, one-argument
condition, and non-callable health check. Every checker located each error at
the configuration call. A source scan found no `Any`, `cast`, suppression,
baseline, or expected-register reference; no register changed.

One signature limit belongs to future design: a conventional configured
decorator receives its health check before it receives the provider, so this
prototype could prove that metadata preserves the provider type but could not
relate the check parameter to that later return/yield type. The fixture used a
contravariant `Callable[[Never], object]` boundary. A formal API would need a
different type shape if it promises the same check-argument precision as
`bind(check=...)`. This does not select that shape or weaken provider identity.

### Cost results against the pre-registration

The cost harness ran 20 measured paired timings after three discarded warm-up
pairs, 15 paired retained-memory processes, and the fixed 10,000-resample
bootstrap. Manual/catalogue record tuples and plans were equal at every size.
The `depin/**/*.py` source hash was identical on main and the branch:
`d3b7ea2ab73f013e7627e74b037cabfa0f28dc59afbfd474a8f145dfb544d7af`.

The timing cells show control/candidate medians:

| Providers | Cold import I0/C | Declaration M/C | Freeze M/C | Verdicts |
| ---: | ---: | ---: | ---: | --- |
| 10 | 197.863/196.623 ms | 17.278/18.077 µs | 1.651/1.691 ms | PASS / PASS / PASS |
| 100 | 200.322/200.958 ms | 163.405/159.054 µs | 14.954/13.970 ms | PASS / PASS / **INCONCLUSIVE** |
| 1,000 | 245.320/258.232 ms | 1.660/1.595 ms | 138.744/138.395 ms | PASS / PASS / **INCONCLUSIVE** |

| Providers | Retained before freeze M/C | Retained after freeze M/C | Contract result |
| ---: | ---: | ---: | --- |
| 10 | 1,056/1,352 B | 4,036/4,107 B | PASS / PASS |
| 100 | 8,992/11,144 B | 30,573/32,653 B | PASS / PASS |
| 1,000 | 88,928/109,064 B | 284,608/305,244 B | PASS / PASS |

For auditability, the next table exposes the paired point estimate, one-sided
95% upper bound (`U95`), and pre-registered cap used for every timing verdict.
Absolute values are candidate minus control. Negative values favor the
catalogue fixture.

| Providers | Metric | Absolute point / U95 / cap | Relative point / U95 / cap | Result |
| ---: | --- | ---: | ---: | --- |
| 10 | cold import | +0.066 / +1.069 / +2.300 ms | 1.0004 / 1.0055 / 3.0000 | PASS |
| 10 | declaration/composition | +0.890 / +1.021 / +1,150.000 µs | 1.0522 / 1.0579 / 2.5000 | PASS |
| 10 | freeze | +0.099 / +0.128 / +0.510 ms | 1.0618 / 1.0815 / 1.1000 | PASS |
| 100 | cold import | −0.181 / +2.920 / +5.000 ms | 0.9991 / 1.0149 / 1.7500 | PASS |
| 100 | declaration/composition | −4.008 / −3.229 / +2,500.000 µs | 0.9749 / 0.9803 / 2.0000 | PASS |
| 100 | freeze | −0.469 / +2.000 / +0.600 ms | 0.9674 / 1.1358 / 1.1000 | **INCONCLUSIVE** |
| 1,000 | cold import | +12.476 / +19.445 / +32.000 ms | 1.0522 / 1.0761 / 1.5000 | PASS |
| 1,000 | declaration/composition | −70.688 / −49.104 / +16,000.000 µs | 0.9565 / 0.9697 / 2.0000 | PASS |
| 1,000 | freeze | +0.525 / +10.204 / +1.500 ms | 1.0008 / 1.0778 / 1.1000 | **INCONCLUSIVE** |

Memory was judged as a margin, `observed − cap`, rather than by hiding the
controls inside a verdict. A row passes only when both its paired point and U95
are at most zero. The first two post-freeze margins are bytes; the last is the
dimensionless `C/M − 1.10` margin.

| Providers | Phase | Absolute point / U95 | Relative-to-I0 point / U95 | Post-freeze ratio point / U95 | Result |
| ---: | --- | ---: | ---: | ---: | --- |
| 10 | before freeze | −69,304 / −69,304 B | −65,504 / −65,504 B | n/a | PASS |
| 100 | before freeze | −105,592 / −105,592 B | −65,632 / −65,632 B | n/a | PASS |
| 1,000 | before freeze | −468,472 / −468,472 B | −67,632 / −67,632 B | n/a | PASS |
| 10 | after freeze | −66,889 / −66,323 B | −66,348.50 / −66,269.25 B | −0.100089 / −0.100018 | PASS |
| 100 | after freeze | −70,504 / −70,262 B | −71,074.25 / −70,994.00 B | −0.099826 / −0.099797 | PASS |
| 1,000 | after freeze | −109,517 / −109,512 B | −116,244.75 / −116,049.00 B | −0.098118 / −0.098117 | PASS |

No point estimate failed. Freeze at 100 providers had paired median difference
−0.469 ms but U95 +2.000 ms over the +0.600 ms absolute cap, and ratio U95
1.1358 over 1.10. Freeze at 1,000 had paired median +0.525 ms and ratio U95
1.0778, but absolute U95 +10.204 ms exceeded +1.500 ms. Both are therefore
INCONCLUSIVE under the rule fixed before measurement.

The unchanged-resolution control measured main/branch medians of
5,895.53/5,924.73 ns per transient-chain resolution. Its paired ratio was
0.9887 with U95 1.0433, within 1.05, but the paired absolute difference U95 was
+251.42 ns, above +50 ns. Its absolute point/U95/cap was
−67.47/+251.42/+50.00 ns, and its relative point/U95/cap was
0.9887/1.0433/1.0500. It too is INCONCLUSIVE. Overall cost evidence is 13 PASS,
zero FAIL, and three INCONCLUSIVE. The required next evidence is a fresh,
separately pre-registered higher-power paired experiment that reduces the
freeze and absolute-resolution confidence intervals below the existing bounds;
this run cannot be repeated selectively or used to loosen them.

### Pre-registered higher-power paired cost contract — 2026-09-11

This second contract decides only the three inconclusive rows above. It does
not reinterpret or replace any earlier result, measure import, declaration,
composition, memory, startup, or tails, and does not evaluate an API or a
runtime implementation. The only candidate remains the name-neutral disposable
prototype: immutable catalogues owned by their modules and concatenated by an
ordinary explicitly imported manifest. Recursive package discovery,
explicit-root reachability, filesystem or `sys.modules` scanning, global state,
and mutation after `freeze()` remain excluded.

The first experiment used 20 measured pairs and 50 ms calibrated intervals.
For a conservative power calculation, assume that longer intervals provide no
precision benefit and that a one-sided interval's distance from its point
estimate contracts only as `1 / sqrt(n)`. If `w = U95 − point` and `b` is the
unchanged limit, the pair count needed to place the projected upper endpoint at
the limit is `ceil(20 × (w / (b − point))²)`. Published values therefore require
107 pairs for the 100-provider absolute freeze result
(`w = 2.469 ms`, `b − point = 1.069 ms`), 1,972 for the 1,000-provider result
(`w = 9.679 ms`, `b − point = 0.975 ms`), and 148 for absolute resolution
(`w = 318.89 ns`, `b − point = 117.47 ns`). This run fixes 160, 2,304, and 192
measured pairs respectively. The corresponding conservative projected absolute
upper endpoints are approximately +0.507 ms, +1.427 ms, and +45.27 ns. The
250 ms minimum interval is a separate fivefold reduction of within-process
sampling noise and is not credited in those projections.

Each metric discards exactly 10 warm-up pairs. Each side of every warm-up,
calibration, and measured pair runs in a fresh interpreter process; a process
measures only one side. A non-comparative calibration phase chooses a common
loop count for both sides that made each side run for at least 250 ms. That
count is then fixed for every warm-up and measured pair of the metric. The
orchestrator sets `PYTHONHASHSEED=0`, uses the same interpreter and environment
for both sides, disables garbage collection only inside the timed interval, and
pins itself and descendants to the lowest CPU in `os.sched_getaffinity(0)` when
that API and permission are available. Failure to pin is recorded and does not
change the protocol. Even-numbered pairs run baseline then candidate; odd-numbered
pairs run candidate then baseline, giving exact AB/BA balance because every
fixed pair count is even.

For freeze, **M** is a `Container` populated by one current manual `bind()` call
per source. **C** uses the same source objects grouped ten per module into
immutable local `BindRecord` tuples; an explicitly imported manifest
concatenates them in source order, validates the staged count and callable
sources, and exposes one immutable `Bindings.records()` snapshot to a fresh
`Container`. Before any calibration or timing, a semantic worker must prove
`tuple(M.records()) == tuple(C.records())` and
`build_plan(M.records()) == build_plan(C.records())` at both 100 and 1,000
providers. The proof and the timings use the same generated application,
sources, scopes, order, and dependency-free graph. A failed equality aborts
before measurement and yields no cost verdict. The timed operation is the
current `Container.freeze()` call on a fresh, already-populated builder; local
catalogue construction, manifest staging, validation, and binding calls remain
outside it.

For resolution, **R0** is synchronized `main` and **R1** is this documentation
worktree. Before calibration or timing, the harness computes SHA-256 for every
sorted relative `depin/**/*.py` path and hashes the sequence
`path + NUL + file_digest + LF`; the aggregate hashes and every per-file digest
must be identical. Both sides use the same fresh interpreter to import from the
selected checkout, build the same transient three-class chain, and time only
the existing `resolve(Root)` path. No discovery hook, lookup, branch, or state
may be added to either checkout. Hash inequality aborts before measurement and
yields no resolution verdict.

For pair `i`, freeze uses `d_i = C_i − M_i` and `r_i = C_i / M_i`; resolution
uses `d_i = R1_i − R0_i` and `r_i = R1_i / R0_i`. Each point estimate is the
median of its paired values. A deterministic paired percentile bootstrap draws
the pair indices with replacement, preserving each difference/ratio pair, and
computes 50,000 resampled medians with `random.Random(2026091102)`. After sorting
the bootstrap values, quantile `q` uses linear interpolation at
`h = (B − 1)q`; L95 is `q = 0.05` and U95 is `q = 0.95`, the existing one-sided
95% rule. All durations must be finite and positive and every fixed sample must
be present.

The limits remain exactly:

| Metric | Absolute limit | Relative limit |
| --- | ---: | ---: |
| C−M `freeze()`, 100 providers | ≤ +0.600 ms | C/M ≤ 1.10 |
| C−M `freeze()`, 1,000 providers | ≤ +1.500 ms | C/M ≤ 1.10 |
| R1−R0 resolution | ≤ +50 ns per resolution | R1/R0 ≤ 1.05 |

A row is **PASS** only when the point estimate and U95 meet both its absolute
and relative limits. It is **FAIL** when the point estimate and L95 exceed
either limit. It is **INCONCLUSIVE** in every other case. Rows cannot be
averaged or compensate for one another.

Smoke runs may validate generation, equivalence, CLI behavior, configured
sample counts, and output shape, but may neither emit nor retain comparative
timings. The dedicated run writes no intermediate comparison to stdout and
publishes its raw JSON atomically only after every fixed pair is complete. A
mechanical failure before the first measured pair permits a harness correction
and a complete restart, with the correction and new hash recorded. After the
first measured pair, methodology, limits, sampling, fixtures, and harness bytes
are frozen: an interrupted run may be restarted once only in full with identical
bytes and a documented external cause, without inspecting partial timings; a
second interruption makes the experiment mechanically INCONCLUSIVE. There is
no optional stopping, retuning, selective repetition, or new measurement after
observing the completed comparison in this session, regardless of its verdict.

The harness, generated package, environment-specific files, and raw JSON are
temporary. Only their sufficient construction rule, exact commands, versions,
content hashes, scalar estimates and bounds, limits, and verdicts may survive in
this Markdown document. The formal-design gate remains unchanged until this
contract has one completed result.

### Higher-power paired cost results — 2026-09-11

The contract above was committed separately as `95e4a11` before the harness or
fixtures existed and before any new comparison. The smoke run emitted
`comparative_timings: false`, proved both source-tree hashes equal, and proved
record and plan equality at both sizes. The dedicated run then completed all
fixed pairs without interruption or correction. No partial timing was inspected
and no metric was repeated.

The disposable generator again wrote ten empty provider classes per module.
Each module owned a tuple of those classes and an immutable tuple of transient
`BindRecord` values; `manifest.py` explicitly imported every module and
concatenated both tuples in source order. M called current `Container.bind()`
once per manifest source. C validated the manifest count, callability, and
source identity, then supplied its immutable snapshot through current
`Container(*sources)`. A semantic worker called current `build_plan()` on both
record tuples before the timing workers were allowed to start. Freeze workers
created already-populated builders outside the timed region and timed only
`freeze()`; resolution workers built and froze the three-transient-class chain
outside the timed region and timed only `resolve(Root)`. Every side of every
pair was a new subprocess.

The original commands were:

```console
$ uv run python /tmp/depin-discovery-cost-20260911.1UnHtN/paired_cost_probe.py --smoke --root /tmp/depin-discovery-cost-20260911.1UnHtN --main /home/dreco/dev/depin --candidate /home/dreco/dev/depin/.worktrees/declarative-discovery-cost-gate
$ uv pip install numpy
$ PYTHONHASHSEED=0 uv run --no-sync python /tmp/depin-discovery-cost-20260911.1UnHtN/paired_cost_probe.py --run --root /tmp/depin-discovery-cost-20260911.1UnHtN --main /home/dreco/dev/depin --candidate /home/dreco/dev/depin/.worktrees/declarative-discovery-cost-gate --output /tmp/depin-discovery-cost-20260911.1UnHtN/paired-cost-results.json
```

The environment was CPython 3.12.13 built with Clang 22.1.3, uv 0.11.13,
NumPy 2.5.3, and Linux 6.8.0-138-generic x86_64 with glibc 2.39 on a four-CPU
Intel Xeon E5-2683 v4. Affinity was available and both orchestrator and workers
were pinned to CPU 0. Main was
`531d6e335312a6a028a9007306458f70838db450`; the pre-registered documentation
worktree was `95e4a11ec126f7faa10fd565d6d1d7a601790a1e`.

| Temporary artifact | SHA-256 |
| --- | --- |
| Harness | `f7198085926efd7c9c16c6bd14409d6146ae956997243104bcbeb673ad741201` |
| Generated fixture tree, 114 files | `248061fdc40a1f13f13b162d6ce44add03309fa01f6398e3ccdd6a621e7fda37` |
| Raw result JSON | `ea740cfb0d53af6960374a92a020556293afd2f71b151163b9a943156b0a0239` |

The sorted 48-file `depin/**/*.py` hash was identical on both worktrees:
`dcdba3cc85275f9a58dc54abdd7dac9669b90efe466beedc47a267c932390173`.
The semantic controls were exact:

| Providers | M/C records | Records equal | M/C plan order | Plans equal |
| ---: | ---: | --- | ---: | --- |
| 100 | 100/100 | yes | 100/100 | yes |
| 1,000 | 1,000/1,000 | yes | 1,000/1,000 | yes |

The non-comparative calibration fixed 32 loops for freeze/100, two for
freeze/1,000, and 65,536 for resolution. Verification intervals were
531.050/488.476 ms for M/C at 100, 296.016/298.417 ms for M/C at 1,000, and
368.679/386.781 ms for R0/R1, so every side exceeded 250 ms before the loop
counts were frozen.

The table reports the paired point estimate, L95, U95, unchanged limit, and
per-metric verdict. Absolute freeze values are milliseconds; resolution values
are nanoseconds per resolution.

| Metric | M or R0 median | C or R1 median | Absolute point / L95 / U95 / limit | Relative point / L95 / U95 / limit | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `freeze()`, 100 providers | 14.991952 ms | 14.961293 ms | +0.022135 / −0.007376 / +0.051490 / +0.600000 ms | 1.001480 / 0.999503 / 1.003443 / 1.100000 | **PASS** |
| `freeze()`, 1,000 providers | 149.977675 ms | 150.943945 ms | +1.119652 / +1.027894 / +1.211556 / +1.500000 ms | 1.007468 / 1.006857 / 1.008081 / 1.100000 | **PASS** |
| resolution without discovery | 5,742.411 ns | 5,851.304 ns | +134.879 / +101.553 / +161.847 / +50.000 ns | 1.023390 / 1.017728 / 1.028706 / 1.050000 | **FAIL** |

The difference of the two displayed side medians need not equal the paired
median difference; the decision statistic is the pre-registered median of
within-pair differences. Both freeze rows are now decisive PASS results. The
resolution ratio also passes, but its absolute point and L95 both exceed +50 ns,
which makes the row FAIL under the rule fixed before measurement. Identical
source hashes exclude discovery runtime code as the cause but do not cancel or
reinterpret the measured null-control failure.

Overall, the focused experiment produced two PASS and one FAIL. It was not
repeated. The cost proof is therefore FAIL, and declarative provider discovery
is not ready for formal design. The redirect is a separate investigation of the
identical-source resolution-control bias before any further cost claim. The
gate may be reconsidered only after that investigation supplies a falsifiable
cause and a new independently pre-registered control that meets the same
+50 ns and 1.05 limits; more samples, selective repetition, or relaxed limits
alone are not a remedy. This conclusion retains the catalogue-plus-explicit-
manifest mechanism only as the preferred mechanism among those investigated;
it accepts no public API, signature, decorator, method, class, or name.

### Reconstructing the discarded probes

This section retains enough source shape and command detail to reconstruct the
temporary evidence without retaining an executable probe. Identifiers such as
`CATALOGUE`, `MANIFEST`, and `Declaration` are fixture placeholders only. They
are neither proposed nor accepted public names.

Start from the authority commit and create a disposable directory outside the
repository:

```console
$ git worktree add /tmp/depin-discovery-reproduction a618c7aaea0d92dbad6d758f8873242f0c32c760
$ cd /tmp/depin-discovery-reproduction
$ uv sync --all-groups --all-extras
$ uv run python --version
Python 3.12.13
$ uv --version
uv 0.11.13
```

#### Consumer, parity, and atomicity fixture

The representative sources are fully specified by this table. Every factory
has the named return or yield annotation; only `make_client` has a parameter,
`store: Annotated[Store, Tag('primary')]`. `Store` is a `Protocol`, `SqlStore`
implements it structurally, `ProvidedImplementation` carries the current
`@provides(ProvidedKey)` marker, and `healthy(store: Store) -> bool` returns
`True`.

| Fixture source | Python form | Produced key | Scope in representative graph |
| --- | --- | --- | --- |
| `DirectPrimary` | class | itself | singleton |
| `SqlStore` | class | `Store`, tag `primary` | singleton |
| `make_client` | sync factory | `Client` | transient |
| `make_async_value` | coroutine factory | `AsyncValue` | transient |
| `ProvidedImplementation` | class with `provides()` | `ProvidedKey` | singleton |
| `make_generator_value` | generator factory | `GeneratorValue` | scoped |
| `make_async_generator_value` | async-generator factory | `AsyncGeneratorValue` | scoped |
| `make_context_value` | `@contextmanager` factory | `ContextValue` | scoped |
| `make_async_context_value` | `@asynccontextmanager` factory | `AsyncContextValue` | scoped |

The manual control is a real `Container` with those nine `.bind()` calls in
table order. The `SqlStore` call supplies `provides=Store`, `tag='primary'`,
`when=True`, and `check=healthy`; every other call supplies only the listed
scope. The catalogue variant constructs the following current internal records
in the same order, split after the fifth record into two module-local tuples:

```python
BindRecord(
    source=source,
    scope=scope,
    provides=provided_key,
    tag=tag,
    condition=condition,
    check=check,
)
```

The explicit manifest is exactly `(CORE_CATALOGUE, LIFECYCLE_CATALOGUE)`.
Staging and the one receiver mutation use this fixture-local `Bindings`
implementation and ordering:

```python
@dataclass(frozen=True, slots=True)
class SnapshotBindings:
    snapshot: tuple[BindRecord, ...]

    def records(self) -> tuple[BindRecord, ...]:
        return self.snapshot


def stage(manifest: tuple[tuple[BindRecord, ...], ...]) -> tuple[BindRecord, ...]:
    if any(type(catalogue) is not tuple for catalogue in manifest):
        raise TypeError('manifest catalogue is not an immutable BindRecord tuple')
    staged = tuple(record for catalogue in manifest for record in catalogue)
    if any(not isinstance(record, BindRecord) for record in staged):
        raise TypeError('manifest catalogue is not an immutable BindRecord tuple')
    build_plan(staged)
    return staged


staged = stage(MANIFEST)
receiver.include(SnapshotBindings(staged))
```

For both `Container().bind(str)` and `Registry().bind(str)`, snapshot
`before = tuple(receiver.records())` before calling a manifest loader. Instrument
the final `include()` call with a list-backed counter. The six failing inputs
are: a loader that raises `ImportError('deliberate manifest import failure')`;
a record whose `source` is `42`; a manifest containing a list instead of a
tuple; the `SqlStore` record twice in one catalogue; the same catalogue twice;
and the two-catalogue manifest twice. For each, catch the exception shown in the
atomicity table, then assert both `tuple(receiver.records()) == before` and an
empty commit counter. On the success path, assert one commit and
`tuple(receiver.records()) == before + staged`.

Compare the two nine-record tuples directly, then compare both
`build_plan(records)` values directly and by the tuple
`(order, tuple(by_key.items()), inactive)`. For the parity loop, substitute each
source form above into a single `BindRecord`; run singleton, scoped, and
transient for the first three shapes, singleton and scoped for all four
lifecycle shapes, and assert `InvalidScopeError` for lifecycle/transient. Repeat
with each of `provides`, `tag`, `condition`, and `check` populated and with
`provides()` inside and outside the fixture identity declaration. The exact
commands and retained transcript were:

```console
$ PYTHONPATH=$PWD uv run python /tmp/depin-discovery-consumer/run_probe.py
PASS assertions=20
$ uv run pytest tests/unit/test_providers.py tests/unit/test_context_managers.py \
    tests/unit/test_health_declaration.py tests/unit/test_graph_validation.py -q
146 passed in 1.97s
```

#### Import fixture

The import driver creates all files under one temporary directory, prepends
only that directory to `sys.path`, calls `importlib.invalidate_caches()`, and
imports exact manifest names with `importlib.import_module()`. These are the
minimal generated file bodies for the cases whose behavior is not evident from
an ordinary one-file module:

```text
regular/manifest.py:       from .provider import CATALOGUE
regular/provider.py:       CATALOGUE = ('regular',)
namespace-root-1/nspkg/manifest.py: from .provider import CATALOGUE
namespace-root-1/nspkg/provider.py: CATALOGUE = ('namespace-one',)
namespace-root-2/nspkg/other.py:    CATALOGUE = ('namespace-two',)
partial_dep.py:             SIDE_EFFECT = True
partial_fail.py:            from . import partial_dep; raise RuntimeError('intentional partial import failure')
reexport.py:                from .provider import PROVIDER
getattr_module.py:          def __getattr__(name): raise RuntimeError('attribute scan invoked')
```

Neither namespace root contains `nspkg/__init__.py`. The driver asserts that
the explicit namespace manifest contains only `namespace-one`, a failing module
is absent from `sys.modules`, its successfully imported dependency may remain,
and the receiver snapshot is unchanged. Reexport and alias checks use `is` on
the explicitly imported object. Repeat and overlap concatenate tuples literally
and leave duplicate rejection to `build_plan()`.

A supported cycle defers access until ordinary import has completed:

```python
# cycle_a.py
from . import cycle_b

CATALOGUE = ('A',)


def combined() -> tuple[str, ...]:
    return CATALOGUE + cycle_b.CATALOGUE


# cycle_b.py
from . import cycle_a

CATALOGUE = ('B',)
```

Importing `cycle_a` and then calling `combined()` must return `('A', 'B')`.
The rejected early-access control instead has each module import the other's
`CATALOGUE` before defining its own, and must raise `ImportError` or
`AttributeError` before receiver mutation.

The custom-loader control installs a temporary `MetaPathFinder`/`Loader` whose
`find_spec()` recognizes one exact name and whose `exec_module()` assigns only
`CATALOGUE = ('exact',)`. It deliberately has no `iter_modules`; exact import
must succeed. The zip control writes `zipcatalog/__init__.py` and
`zipcatalog/manifest.py` with `CATALOGUE = ('zip',)` to one zip and imports that
exact name in a subprocess.

The scripted core transcript contained 22 `PASS` lines and exited zero. Its
last relevant assertions were:

```text
PASS partial import leaves receiver unchanged
PASS failed module absent and successful dependency retained
PASS exact manifest avoids module __getattr__
PASS early cyclic catalogue rejected before consumption
PASS custom exact-name loader; iter_modules=False
PASS zip import exact manifest ('zip',)
SUMMARY PASS
```

The host lacked `ensurepip`, so editable and wheel packaging were repeated in
fresh uv-managed environments rather than counted in that 22-assertion output:

```console
$ uv venv --python 3.12 /tmp/import-probe/editable-env
$ uv pip install --python /tmp/import-probe/editable-env/bin/python -e /tmp/import-probe/package
$ /tmp/import-probe/editable-env/bin/python -c \
    "import contract_probe; assert contract_probe.CATALOGUE == ('installed',)"
$ uv build --wheel --out-dir /tmp/import-probe/dist /tmp/import-probe/package
$ uv venv --python 3.12 /tmp/import-probe/wheel-env
$ uv pip install --python /tmp/import-probe/wheel-env/bin/python /tmp/import-probe/dist/contract_probe-0.0.1-py3-none-any.whl
$ /tmp/import-probe/wheel-env/bin/python -c \
    "import contract_probe; assert contract_probe.CATALOGUE == ('installed',)"
```

All six commands exited zero, giving the other two PASS results. The package
contains only `contract_probe.py` with `CATALOGUE = ('installed',)` and ordinary
PEP 517 project metadata.

For reload, retain `old_catalogue` and `old_provider`, freeze a real container
built from that record, rewrite the module so the provider returns version 2,
invalidate caches, and call `importlib.reload()`. Assert new catalogue/provider
identity, unchanged old tuple identity, and version 1 from the old frozen
container both before and after reload. Resolving with the newly created class
key from that frozen container must raise the current missing-key error. This
is the executable basis for excluding live reload while guaranteeing frozen
snapshot stability.

#### Typing fixture and commands

The complete type-preserving boundary used by both fixtures was:

```python
type Condition = bool | Callable[[], bool]
type HealthCheck = Callable[[Never], object]
type ProviderKey = type[object] | Key | str


class ConfiguredDeclaration:
    @overload
    def __call__[T](self, target: type[T], /) -> type[T]: ...

    @overload
    def __call__[**P, R](self, target: Callable[P, R], /) -> Callable[P, R]: ...


class Declaration:
    @overload
    def __call__[T](self, target: type[T], /) -> type[T]: ...

    @overload
    def __call__[**P, R](self, target: Callable[P, R], /) -> Callable[P, R]: ...

    @overload
    def __call__(
        self,
        target: None = None,
        /,
        *,
        scope: Scope = Scope.SINGLETON,
        key: ProviderKey | None = None,
        tag: str | None = None,
        condition: Condition | None = None,
        health_check: HealthCheck | None = None,
    ) -> ConfiguredDeclaration: ...
```

Both implementations return the received target unchanged; the configured
call returns a `ConfiguredDeclaration`. Define bare and fully configured forms
for a class and for each factory row in the parity table. Preserve exactness
with assignments to `type[Concrete]`, `Callable[[Config], Product]`,
`Callable[[Config], Awaitable[Product]]`, `Callable[[Config],
Generator[Product]]`, `Callable[[Config], AsyncGenerator[Product]]`,
`Callable[[Config], AbstractContextManager[Product]]`, and
`Callable[[Config], AbstractAsyncContextManager[Product]]`, plus the configured
two-parameter equivalents. Add both decorator orders with current
`provides(Service)`. This produces the 17 positive witnesses.

The negative fixture repeats the boundary and decorates five distinct classes
with `scope='wrong'`, `key=42`, `tag=42`, a one-argument `condition`, and
`health_check=42`. These are the only intended diagnostics. The disposable
configurations were exactly the following, with the checkout path replaced when
reconstructing elsewhere:

```json
{
  "typeCheckingMode": "strict",
  "pythonVersion": "3.12",
  "extraPaths": ["/home/dreco/dev/depin/.worktrees/declarative-discovery-gate"]
}
```

```toml
# ty.toml
[environment]
python-version = "3.12"
python-platform = "linux"
extra-paths = ["/home/dreco/dev/depin/.worktrees/declarative-discovery-gate"]
```

```toml
# pyrefly.toml
project-includes = ["positive.py", "negative.py"]
python-version = "3.12"
python-platform = "linux"
search-path = ["/home/dreco/dev/depin/.worktrees/declarative-discovery-gate"]
```

`--preset strict` remains on the Pyrefly command line. The exact command matrix
is the five-checker results table above, replacing its old
`/tmp/depin-discovery-typing-20260911` with the new probe directory.

Run the positive and negative command for each checker, require respectively
zero and exactly five diagnostics, then run:

```console
$ rg -n "\\bAny\\b|\\bcast\\b|type: ignore|pyright: ignore|noqa|baseline|expected" /tmp/typing-probe
```

The retained transcript was `0/5`, `0/5`, `0/5`, `0/5`, and `0/5` diagnostics
for mypy, Basedpyright, stock Pyright, ty, and Pyrefly respectively; the scan
printed nothing.

#### Cost-fixture generation and command

The cost script creates ten-provider modules. For every provider count and
module index, both I0 and C define the same empty classes and `SOURCES` tuple;
only C adds this expression:

```python
CATALOGUE = tuple(BindRecord(source=source, scope=Scope.TRANSIENT, provides=None, tag=None) for source in SOURCES)
```

Each generated manifest uses one explicit `from . import mNNNN as mNNNN` per
module and concatenates `SOURCES` in source order; C also concatenates those
module-local `CATALOGUE` tuples in the same order. The cold worker starts
`perf_counter_ns()` immediately before `importlib.import_module(exact_name)` in
a fresh interpreter and stops immediately afterward.

The hot M worker constructs fresh dynamic classes and calls
`Container.bind(source, scope=Scope.TRANSIENT)` for each. The hot C worker
groups the same class objects by ten, constructs the same `BindRecord` values,
validates their count and callable sources, flattens them in manifest order,
and supplies one immutable `Bindings.records()` snapshot to a fresh
`Container`. Before timing freeze, it asserts direct record equality and direct
`ResolutionPlan` equality. Each operation is calibrated independently until
at least 50 ms, then divided by its loop count with collection disabled only
inside that interval.

The memory worker starts `tracemalloc`, collects, records interpreter origin,
creates the same dynamic sources, collects again for I0, constructs M or C,
collects for the pre-freeze reading, freezes, and collects for the post-freeze
reading. It retains C's local and staged tuples through the last reading. The
resolution worker imports depin from the checkout path, builds a transient
three-class chain with current declarations, freezes it, calibrates to 50 ms,
and times `resolve(Root)` only. The orchestrator fixes
`PYTHONHASHSEED=0`, pins the lowest permitted CPU when available, alternates
AB/BA order, and applies the constants and formulas in the pre-registration.

Run the no-argument orchestrator once:

```console
$ uv run python /tmp/depin-discovery-cost/cost_probe.py
{"output":"/tmp/depin-discovery-cost/cost-results.json","summary":{"PASS":13,"FAIL":0,"INCONCLUSIVE":3},"source_hashes_equal":true}
```

The exact scalar results needed to audit that JSON are retained in the timing,
memory-margin, and resolution tables above. The script and JSON digests identify
the original run; a reconstruction is a new experiment and cannot turn these
three inconclusive results into PASS without a separately pre-registered
contract.

### Error boundary for a future design

- Every discovery-specific exception must inherit `DepinError`.
- A wrapper around an import failure must use explicit exception chaining so
  the original import exception remains in `__cause__`.
- The message must name the requested manifest or domain and the failing module;
  declaration and composition errors must also name the offending declaration
  or catalogue.
- Current pipeline errors such as `InvalidProviderError`,
  `InvalidScopeError`, `DuplicateProviderError`, `MissingProviderError`,
  `CircularDependencyError`, and `CaptiveDependencyError` remain authoritative
  once staged records enter the existing pipeline. Discovery must not translate
  or duplicate them merely to change their category.
- Atomicity covers only depin-owned collector records and the one staged commit.
  It never promises rollback of `sys.modules` or application import side
  effects.

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

## Questions intentionally left to design

No public name, decorator shape, manifest type, method, signature, or exception
taxonomy was accepted. A future design, once authorized, would still need to
choose the smallest public surface, decide how a configured declaration relates
a health-check parameter to the later provider type, and specify decorator
ordering without changing context-manager shape detection. The mechanism proof
does not answer those API questions.

## Objective gate for writing a formal design

| Gate | Result | Reproducible evidence or exact missing evidence |
| --- | --- | --- |
| 1. Consumer proof | **PASS** | Nine manual provider entries became two explicit module-catalogue imports (77.8% fewer); the graph includes direct-only, abstract-key, dependent factory, async/lifecycle, tag, condition, and check cases. Root reachability missed the direct-only and abstract implementation cases. |
| 2. Atomicity proof | **PASS** | Six pre-commit failures left real receiver `records()` equal to the seeded snapshot and made zero commit calls; successful staging made one `include()`. |
| 3. Provider-parity map | **PASS** | All seven source shapes, all valid lifetimes, six record fields, current `provides()` composition, and four lifecycle/transient rejections use the existing provider/graph pipeline. The five excluded binding forms remain explicit. |
| 4. Import contract | **PASS** | Exact ordinary imports passed for module/package, namespace manifest, editable, wheel, zip, supported cycle, partial failure, reexports/aliases, reload, `__getattr__`, and a loader with no enumeration API. No fallback was used. |
| 5. Determinism contract | **PASS** | Source/declaration order is preserved; explicit object identity governs aliases/reexports; repeats/overlaps preserve literal input then use current duplicate validation; incomplete imports are not consumed; reload is not live update and frozen containers remain unchanged. |
| 6. Typing proof | **PASS** | All five pinned checkers accepted 17 exact-type positive assignments for every provider form and both `provides()` orders, and rejected all five invalid metadata categories at configuration. No forbidden type escape or register change occurred. |
| 7. Cost acceptance contract | **PASS** | The dated absolute/relative bounds, controls, bootstrap decision rule, and inconclusive rule are retained in `4dea4b9`; cost results first appear in the later commit `8b1ce17`. |
| 8. Cost proof | **FAIL** | The separately pre-registered higher-power run proved exact record/plan and source-hash equality and moved both pending freeze rows to PASS. Resolution without discovery failed its unchanged absolute limit: point +134.879 ns, L95 +101.553 ns, and U95 +161.847 ns against +50 ns, although its ratio passed. |
| 9. Error contract | **PASS** | The documented boundary requires `DepinError`, preserved import `__cause__`, manifest/domain plus module/declaration context, current pipeline errors unchanged, and atomicity only for depin-owned state. |

The formal-design gate is **FAIL** and declarative provider discovery is **not
ready for formal design**. The cost proof now contains an observed limit
violation in the identical-source resolution control, not an interval that
merely needs more precision. The recommended redirect is the independent
control-bias investigation recorded with the higher-power results; consumer,
atomicity, parity, import, determinism, typing, and error evidence need not
expand into runtime or public-API work while that failure remains. Mechanism
evidence, public API, and naming stay separate, and no formal design or
implementation plan is authorized by this document.
