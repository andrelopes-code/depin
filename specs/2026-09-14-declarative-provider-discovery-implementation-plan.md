# Declarative Provider Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved `provider()` / `Provider[T]` / `Catalog` / `Manifest` declarative provider surface as a type-preserving, explicitly composed frontend that becomes ordinary `BindRecord` values before the existing provider-analysis and runtime pipelines begin.

**Architecture:** `depin/_core/discovery.py` owns immutable declaration values, caller provenance, owner validation, manifest flattening, and conversion to a complete tuple of existing `BindRecord` values. `BindingCollector.include()` materializes and validates one complete `Bindings` source before one receiver mutation, so a `Manifest` is ingestible and atomic while a `Catalog` is not. `build_specs()`, `build_plan()`, and every frozen-runtime module continue to consume only existing records, specs, and plans.

**Tech Stack:** Python 3.12 PEP 695 generics, `ParamSpec`, `Protocol`, frozen slotted dataclasses, `inspect`/ordinary import machinery from the standard library, pytest and pytest-asyncio, ruff, Basedpyright strict, mypy strict, stock Pyright, ty, Pyrefly, MkDocs, and the existing benchmark harness conventions. The core gains no runtime dependency.

**Specs:** [mechanism design](2026-09-14-declarative-provider-discovery-design.md), [public API design](2026-09-14-declarative-provider-discovery-public-api-design.md), and the closed [investigation](2026-09-11-declarative-provider-discovery-investigation.md).

## Global constraints

- The four public names and all public signatures are normative; no alias, decorator form, discovery verb, package root, string import, or direct catalogue ingestion is added.
- `Provider[T]`, `Catalog`, and `Manifest` are frozen, slotted values. Their collections are tuples, and every configuration or composition operation allocates a completed replacement.
- `provider()` does not decorate, wrap, call, annotate, or mutate its target. The original class or callable object is the eventual `BindRecord.source`.
- The provider source forms are exactly class, synchronous factory, coroutine factory, generator factory, async-generator factory, context-manager factory, and async-context-manager factory.
- No source scan, module namespace walk, `sys.modules` scan, filesystem enumeration, entry point, import hook, global collector, or module-level mutable state participates.
- Conditions are evaluated only by the existing `build_specs()` path during `freeze()`. Declaration and staging may validate that a condition is a bool or callable but never invoke it.
- Discovery finishes at the single append of a fully materialized `tuple[BindRecord, ...]`. No discovery value, provenance, hook, lookup, state, or branch crosses into `build_specs()`, `ResolutionPlan`, or resolution.
- Existing manual binding remains the semantic oracle. Declarative and manual paths must produce equal records, `ProviderSpec` values, and `ResolutionPlan` values for equal inputs.
- No `Any`, `typing.cast`, checker suppression, checker configuration relaxation, or source expected-register change is permitted.
- `depin/_core/providers.py`, `depin/_core/graph.py`, `depin/_core/frozen.py`, generated/instruction runtime modules, scopes, overrides, injection, construction, and teardown remain behaviorally unchanged.
- `benchmarks/budgets.toml` remains generated and untouched. The final focused acceptance comparison is against synchronized `main`, uses the real implementation, and must meet both `+50 ns` and `1.05`.
- Each execution slice contains no more than three tasks, ends by overwriting `.codex/progress/current.md`, and the next slice starts from that checkpoint in a fresh context.

## File map and locked responsibilities

### Production surface

| Path | Change | Exact responsibility |
| --- | --- | --- |
| `depin/_core/discovery.py` | Create | Define the four public discovery objects/functions and all private provenance, ownership, validation, immutable storage, recursive flattening, and `BindRecord` conversion. It performs no import, collector mutation, provider-shape analysis, graph construction, or runtime work. |
| `depin/_core/bindings.py` | Modify | Materialize and validate each `Bindings.records()` result before one `list.extend`; reject `Catalog` with guidance to compose a `Manifest`; retain the current non-atomic-across-distinct-sources contract. |
| `depin/_core/container.py` | Modify documentation only | Name `Manifest` as a constructor binding source and state that it is converted before `freeze()`; leave `freeze()` executable code unchanged. |
| `depin/_core/registry.py` | Modify documentation only | Distinguish mutable manual `Registry` from immutable declarative `Catalog`; retain `Registry.__or__` unchanged. |
| `depin/_core/spec.py` | Modify documentation only | Add `Manifest` to the `Bindings` explanation; do not change `BindRecord`, `ProviderSpec`, `SpecSet`, `ResolutionPlan`, or the protocol signature. |
| `depin/errors.py` | Modify documentation only | Extend `InvalidProviderError` documentation with declaration, owner, member, staging, direct-construction, and direct-catalogue triggers; add no exception class. |
| `depin/__init__.py` | Modify | Reexport `provider`, `Provider`, `Catalog`, and `Manifest`, add them to `__all__`, and extend the package mental model without duplicating discovery docstrings. |

`depin/_core/providers.py` and `depin/_core/spec.py` data definitions are explicit no-change controls. A diff to provider conversion, provider shapes, graph planning, or frozen runtime is a failed scope gate unless it only corrects a proven blocking contradiction in the approved designs.

### Test, typing, documentation, and example surface

| Path | Change |
| --- | --- |
| `tests/unit/test_discovery.py` | Create for immutable values, construction, metadata, ownership, provenance, members, and staging. |
| `tests/unit/test_discovery_parity.py` | Create for the seven provider forms and record/spec/plan equivalence. |
| `tests/unit/test_discovery_composition.py` | Create for order, repetition, conditions, tags, checks, manual interleaving, duplicates, and the runtime boundary. |
| `tests/unit/test_container.py` | Extend for per-source materialization, atomic receiver mutation, direct `Catalog` rejection, and constructor ingestion. |
| `tests/unit/test_registry.py` | Extend for manifest ingestion and unchanged registry composition. |
| `tests/unit/test_errors.py` | Extend the existing exception-inheritance inventory only if the new public-path cases expose an untested branch; no new class is expected. |
| `tests/unit/test_public_api.py` | Extend exact `__all__`, importability, docstring, and zero-third-party-import assertions. |
| `tests/unit/test_discovery_acceptance.py` | Create non-timing tests for the focused performance command, seeded classifier, sample validation, confidence bounds, decision boundaries, and preflight failures. |
| `tests/integration/test_discovery_imports.py` | Create for regular/namespace packages, editable/wheel/zip paths, custom loaders, aliases, reexports, `__getattr__`, cycles, partial initialization, and reload. |
| `tests/fixtures/discovery_imports/regular/` | Create a small explicit-import application package reused as an editable tree and zipped wheel-shaped import artifact. |
| `tests/fixtures/discovery_imports/namespace/` | Create two namespace-package portions and one explicit composition module. |
| `tests/fixtures/discovery_imports/cycles/` | Create supported, early-failing, and partially initialized import packages. |
| `conformance/corpus/core/c10_discovery.py` | Create the positive consumer-typing corpus for all four public names and seven provider forms. |
| `conformance/negative/n08_discovery_scope.py` through `n15_catalog_ingestion.py` | Create one misuse per negative fixture: five metadata errors, direct construction, and direct catalogue ingestion through both consumers. |
| `conformance/expected/negative.toml` | Add exact checker rule/line expectations for `n08`–`n15`. |
| `conformance/coverage.toml` | Map all four new exports to `corpus/core/c10_discovery.py`. |
| `docs/guide/discovery.md` | Create the narrative declaration → catalogue → manifest → include/freeze guide. |
| `docs/guide/composition.md` | Link the declarative path and distinguish `Catalog` from `Registry`. |
| `docs/reference/discovery.md` | Create generated-reference directives for the four new exports. |
| `mkdocs.yml` | Add the guide and reference pages to navigation. |
| `examples/declarative_discovery/__init__.py` | Create the example package marker. |
| `examples/declarative_discovery/providers.py` | Declare local targets, immutable `Provider` values, and a module-owned `Catalog`. |
| `examples/declarative_discovery/manifest.py` | Compose the completed catalogue into an explicit module-owned `Manifest`. |
| `examples/declarative_discovery/main.py` | Build the `Container` inside `build()`, resolve a value, and expose an executable `main()`. |
| `examples/README.md` | List the executable example. |
| `tests/integration/test_examples.py` | Execute and assert the example through the same integration gate as every existing example. |
| `benchmarks/harness/discovery_acceptance.py` | Create the reproducible command that generates the fixed three-class fixture, runs the transferred paired protocol, proves structural equivalence, and applies the absolute and relative decision rule. |

No checker configuration, source expected register, lockfile, dependency declaration, benchmark budget, or benchmark result file changes. The focused acceptance command and its deterministic unit tests are the only new benchmark-related source files; measurements remain temporary evidence and `benchmarks/budgets.toml` remains generated and untouched.

The fixture directories above contain exactly these source-controlled files:

- regular/editable/archive fixture: `regular/discovery_fixture/__init__.py`, `targets.py`, `providers.py`, `reexports.py`, and `manifest.py`;
- namespace fixture: `namespace/portion_a/discovery_namespace/accounts/providers.py`, `namespace/portion_b/discovery_namespace/billing/providers.py`, `namespace/composition/discovery_application/__init__.py`, and `namespace/composition/discovery_application/manifest.py`; namespace directories intentionally omit `__init__.py` outside the composition application; and
- cycle fixtures: `cycles/supported/cycle_supported/__init__.py`, `a.py`, `b.py`, and `manifest.py`; `cycles/early/cycle_early/__init__.py`, `a.py`, and `b.py`; `cycles/partial/partial_discovery/__init__.py`, `providers.py`, and `manifest.py`.

## Concrete representation and invariants

### Private representation in `depin/_core/discovery.py`

| Private name | Frozen contents or contract |
| --- | --- |
| `_ProviderToken` | An unexported nominal type used only as the required positional annotation on `Provider.__new__`; callers cannot obtain a supported constructor argument. |
| `_ProviderMeta` | Intercepts every direct runtime call of `Provider(...)` and raises `InvalidProviderError`; it never allocates an instance. |
| `_SourceLocation` | Declaring module name, `frame.f_code.co_filename`, and `frame.f_lineno` captured at the `provider()` call. |
| `_ProviderData` | Original target object, `Scope`, explicit key or `None`, tag, condition, health check, owner module, and `_SourceLocation`. |
| `_StagingPath` | Ephemeral immutable manifest occurrence path, catalogue occurrence, and zero-based declaration position used only while formatting discovery-owned structural errors. |
| `_allocate_provider` | The sole private allocator. It bypasses `_ProviderMeta.__call__` with `object.__new__`, writes the frozen slot once, and returns a typed descriptor without a cast or erasing top type. |
| `_caller_location` | Reads only the direct caller frame's `__name__`, filename, and line; it releases frame references immediately and raises actionable `InvalidProviderError` if the execution frame does not expose a valid non-empty module name. |
| `_stage_manifest` | Recursively validates the immutable manifest snapshot, preserves every occurrence left-to-right, constructs all `BindRecord` values in temporary storage, and returns one tuple. |

Only immutable sentinel/type objects may exist at module scope. None carries declarations or application state.

### Public representation

- `Provider[T]` is a frozen, slotted public value wrapping one `_ProviderData`. It exposes `configure()` but no mutation method, registration method, collector back-reference, or public target/provenance escape hatch.
- `Catalog` is a frozen, slotted value containing a validated owner string and the exact ordered tuple of `Provider[object]` occurrences. Declaration position is the stable tuple index; no sort or identity-based collapse occurs.
- `Manifest` is a frozen, slotted value containing its validated owner string and the exact ordered tuple of `Catalog | Manifest` occurrences. Its `records()` method returns the tuple produced by `_stage_manifest`, so it structurally satisfies `Bindings` without inheriting it.
- `Catalog` has `module` and `providers` properties only. It deliberately has no `records()` method, so it does not satisfy `Bindings` statically or dynamically.
- `Manifest` has `module`, `sources`, and `records()`. `records()` is the only public bridge from discovery values to the existing binding protocol.

### Normative typing and construction

- `Provider.__new__` has the required positional `_ProviderToken` parameter from the public API design. `Provider[Service]()` therefore produces a missing-argument diagnostic in all five checkers.
- `_ProviderMeta.__call__` converts zero arguments, arbitrary arguments, and attempts using an imported private token into `InvalidProviderError`. Only `provider(target)` and `Provider.configure()` reach `_allocate_provider`.
- `Provider[T]` remains covariant in its produced type so heterogeneous descriptors are assignable to `Provider[object]` in `Catalog`.
- `provider()` declares overloads in this order: class; `Generator[T, None, None]`; `AsyncGenerator[T, None]`; `AbstractContextManager[T]`; `AbstractAsyncContextManager[T]`; `Awaitable[T]`; general synchronous `T`. Every callable overload binds the complete `ParamSpec` `P` and returns `Provider[T]` for the delivered value, not its wrapper.
- The implementation signature accepts only `type[object] | Callable[..., object]` and returns the covariant `Provider[object]`; overloads carry the exact consumer contract. A non-class/non-callable target is rejected at runtime with `InvalidProviderError`.
- Target identity is preserved by storing the exact object and later assigning it directly to `BindRecord.source`. `provider()` never returns the target and never replaces its module binding; the descriptor is a separate value.
- `configure()` uses generic self `self: Provider[U]` and returns `Provider[U]`. `check` is `Callable[[U], object] | None`, so metadata cannot infer or widen `U`.
- Each `configure()` call is a complete replacement: it preserves only the original target, owner, and source location; all five metadata fields come from that call and their declared defaults. A second call therefore resets omitted fields instead of merging with the first.

### Ownership and metadata validation

- `provider()` captures the module where the call executes, not `target.__module__`. An imported target may be declared locally; an imported descriptor retains its original owner.
- `configure()` never inspects its caller and retains the original declaration location even when called through an alias or from another module.
- `Catalog(module, *providers)` requires a non-empty `module` equal to the direct constructor caller's exact `__name__`, requires every member to be a `Provider`, and requires every member's captured owner to equal `module`.
- `Manifest(module, *sources)` requires a non-empty `module` equal to the direct constructor caller's exact `__name__` and requires every member to be a `Catalog` or `Manifest`. Source owners may differ from the manifest owner because explicit cross-module composition is the purpose of the boundary; each source retains its already-validated owner.
- Declaration configuration accepts only an actual `Scope`, a valid existing `ProviderKey` or `None`, `str | None` for `tag`, `Condition | None` for `when`, and a callable or `None` for `check`. Obvious untyped violations raise `InvalidProviderError` at declaration/configuration. A valid lifecycle provider configured as transient continues to raise the existing `InvalidScopeError` during `freeze()`.
- Validation never calls `when`, checks health, analyzes a provider shape, resolves annotations, infers a key, or builds a graph. Those remain in the existing pipeline.

### Staging and the pipeline boundary

For one `include(manifest)` occurrence, `_stage_manifest` walks nested manifests and catalogues left-to-right. It defensively revalidates every stored owner/member invariant, constructs `BindRecord(source, scope, provides, tag, condition, check)` for every occurrence, and completes a tuple before returning. Provenance is used only if that walk fails and never appears in the record.

`BindingCollector.include()` then performs these steps once per supplied source: reject `Catalog` with `InvalidProviderError`; require the runtime `Bindings` protocol; require its resolved `records` attribute to be callable; call it once; materialize the returned iterable as a tuple; validate that every element is a `BindRecord`; and call `_records.extend(staged)` exactly once. A missing/non-callable `records`, a non-iterable result, or a non-`BindRecord` member raises actionable `InvalidProviderError`. An exception raised inside a valid external `records()` implementation propagates unchanged, but still changes no receiver state because mutation has not begun. Earlier distinct sources in the same `include(a, b)` call remain committed, preserving the existing contract; callers compose one outer `Manifest` when they need a single atomic declarative unit.

After the extend, the receiver retains only records. `Container.freeze()` remains `FrozenContainer(build_plan(self.records()))`; the unchanged graph path calls existing `build_specs()` and then produces the existing `ResolutionPlan`. This is the exact end-to-end boundary:

`Provider` occurrences → `Catalog` → `Manifest` → staged tuple → one record append → existing `build_specs()` → existing plan builder → existing frozen runtime.

## Slice 1 — Immutable declarations and ownership

### Task 1: Create opaque typed provider declarations

**Observable result:** `provider(target)` returns an immutable `Provider[T]` carrying the exact target and declaration location; unsupported targets and every direct `Provider(...)` call fail with `InvalidProviderError`.

**Files under responsibility:** Create `depin/_core/discovery.py`; create `tests/unit/test_discovery.py`.

**Test that must fail first:** `test_provider_stores_the_exact_target_and_location`, `test_provider_is_frozen_and_slotted`, the parametrized unsupported-target case, and the parametrized direct-construction case fail because the discovery module and public value do not exist.

**Minimum expected change:** Add `_ProviderToken`, `_ProviderMeta`, `_SourceLocation`, `_ProviderData`, `_caller_location`, `_allocate_provider`, `Provider[T]`, the seven normative overloads, and `provider()`; no catalogue, manifest, or collector integration yet.

**Focused validation:**

```bash
uv run pytest tests/unit/test_discovery.py -k 'provider and not configure and not catalog and not manifest' -q
uv run basedpyright depin/_core/discovery.py tests/unit/test_discovery.py
uv run mypy depin/_core/discovery.py tests/unit/test_discovery.py
```

**Dependencies:** Synchronized `main`; no implementation task.

**Objective completion criterion:** Tests prove target `is` identity, captured module/file/line, frozen-slot rejection, non-class/non-callable rejection, and `InvalidProviderError` for `Provider()`, `Provider(object())`, and a private-token attempt; both local type checkers report zero diagnostics.

- [ ] Write the failing unit tests and run the focused pytest command.
- [ ] Implement only provider allocation, provenance capture, validation, and overloads.
- [ ] Run the focused pytest, Basedpyright, and mypy commands.
- [ ] Commit with `feat: add declarative provider values`.

### Task 2: Add complete immutable configuration

**Observable result:** `configure()` returns a new `Provider[U]` with exact metadata, preserves target/owner/location, validates untyped metadata, and resets omitted metadata on a later complete reconfiguration.

**Files under responsibility:** Modify `depin/_core/discovery.py`; extend `tests/unit/test_discovery.py`.

**Test that must fail first:** Tests for all five fields, unchanged bare descriptor, cross-module owner retention, second-call reset, `provides()` before/after declaration, and invalid runtime metadata fail because `configure()` is absent.

**Minimum expected change:** Add the normative generic-self `configure()` and one private metadata validator. Store `when` as `_ProviderData.condition`; do not evaluate it or inspect provider shape.

**Focused validation:**

```bash
uv run pytest tests/unit/test_discovery.py -k 'configure or metadata or provides' -q
uv run basedpyright depin/_core/discovery.py tests/unit/test_discovery.py
uv run mypy depin/_core/discovery.py tests/unit/test_discovery.py
```

**Dependencies:** Task 1.

**Objective completion criterion:** Every valid field is preserved by identity/value, the first descriptor remains unchanged, a second call resets omitted fields to singleton/`None`, cross-module configuration retains original provenance, invalid obvious values raise `InvalidProviderError`, and conditions/checks have not run.

- [ ] Write and run the failing configuration tests.
- [ ] Implement complete replacement and runtime metadata validation.
- [ ] Run the focused pytest and both source type checkers.
- [ ] Commit with `feat: configure declarative providers`.

### Task 3: Add module-owned catalogues and explicit manifests

**Observable result:** `Catalog(__name__, ...)` and `Manifest(__name__, ...)` create immutable ordered snapshots only from valid owned members; foreign descriptors, forged owner names, and malformed members fail with actionable `InvalidProviderError`.

**Files under responsibility:** Modify `depin/_core/discovery.py`; extend `tests/unit/test_discovery.py`.

**Test that must fail first:** Constructor/property/immutability tests, declaration-owner and constructor-owner mismatch tests, foreign configure retention, multiple-local-catalogue tests, and invalid member tests fail because both classes are absent.

**Minimum expected change:** Add frozen slotted `Catalog` and `Manifest`, exact constructor signatures and tuple properties, direct-caller owner validation, catalogue member ownership validation, and manifest member validation. `Manifest.records()` is introduced as a method that still fails the staging tests until Task 4.

**Focused validation:**

```bash
uv run pytest tests/unit/test_discovery.py -k 'catalog or manifest or owner or member' -q
uv run basedpyright depin/_core/discovery.py tests/unit/test_discovery.py
uv run mypy depin/_core/discovery.py tests/unit/test_discovery.py
```

**Dependencies:** Tasks 1–2.

**Objective completion criterion:** Properties expose exact tuples, mutation fails, imported targets declared locally succeed, imported descriptors fail local catalogue ownership, manifests accept foreign completed catalogues/nested manifests, and each structural error names owner, occurrence/member, offending value, and correction.

- [ ] Write and run the failing catalogue/manifest tests.
- [ ] Implement owner/member validation and immutable storage.
- [ ] Run focused tests and both local type checkers.
- [ ] Commit with `feat: add catalogues and manifests`.

**Slice 1 checkpoint:** Run `uv run pytest tests/unit/test_discovery.py -q`, overwrite `.codex/progress/current.md` with commits, test state, scope discoveries, and the exact Task 4 command, then end the slice.

## Slice 2 — Staging, collectors, and public integration

### Task 4: Stage complete manifests into ordinary records

**Observable result:** `Manifest.records()` recursively flattens all occurrences in lexical order and returns a fully materialized tuple of ordinary, provenance-free `BindRecord` values.

**Files under responsibility:** Modify `depin/_core/discovery.py`; extend `tests/unit/test_discovery.py`.

**Test that must fail first:** Flat/nested/repeated manifest record tests and a forged-snapshot staging-failure test fail because `Manifest.records()` does not yet stage.

**Minimum expected change:** Add `_StagingPath`, `_stage_manifest`, defensive invariant checks, left-to-right recursive flattening, and field-for-field `BindRecord` creation. Do not call `build_specs()` or `build_plan()`.

**Focused validation:**

```bash
uv run pytest tests/unit/test_discovery.py -k 'records or staging or flatten or repeated or provenance' -q
uv run basedpyright depin/_core/discovery.py tests/unit/test_discovery.py
uv run mypy depin/_core/discovery.py tests/unit/test_discovery.py
```

**Dependencies:** Task 3.

**Objective completion criterion:** The exact record tuple equals an explicitly constructed oracle; nested paths preserve every repeated occurrence; a structural failure produces no partial tuple and reports manifest path, catalogue owner/occurrence, declaration index/location, offending value, and correction.

- [ ] Write and run the failing staging tests.
- [ ] Implement recursive one-shot tuple staging.
- [ ] Run focused tests and both local type checkers.
- [ ] Commit with `feat: stage declarative manifests`.

### Task 5: Make binding-source ingestion atomic per source

**Observable result:** `Container(manifest)`, `Container().include(manifest)`, and `Registry().include(manifest)` append one complete contiguous segment; a staging/iterator/member failure leaves that receiver snapshot unchanged, and direct `Catalog` ingestion raises `InvalidProviderError`.

**Files under responsibility:** Modify `depin/_core/bindings.py`; extend `tests/unit/test_container.py` and `tests/unit/test_registry.py`; create `tests/unit/test_discovery_composition.py` for the post-commit runtime guard.

**Test that must fail first:** A `Bindings.records()` generator that yields one valid record and then raises currently leaves a prefix in `_records`; objects with a non-callable `records`, a non-iterable `records()` result, or an invalid yielded member currently leak protocol/iteration errors or invalid state; `Container(Catalog(...))` currently raises the wrong exception; manifest ingestion is unsupported.

**Minimum expected change:** Add per-source runtime protocol checking, callable-member validation, one call to `records()`, tuple materialization, `BindRecord` member validation, actionable `InvalidProviderError` wrapping for malformed structural sources, direct `Catalog` guidance, and one `extend(staged)` after success. Preserve an exception raised by a valid external `records()` implementation as the original cause and do not make `include(a, b)` jointly atomic.

**Focused validation:**

```bash
uv run pytest tests/unit/test_container.py tests/unit/test_registry.py tests/unit/test_discovery_composition.py -k 'include or manifest or catalog or atomic or malformed or runtime_boundary' -q
uv run basedpyright depin/_core/bindings.py tests/unit/test_container.py tests/unit/test_registry.py tests/unit/test_discovery_composition.py
uv run mypy depin/_core/bindings.py tests/unit/test_container.py tests/unit/test_registry.py tests/unit/test_discovery_composition.py
```

**Dependencies:** Task 4.

**Objective completion criterion:** A tracking list observes exactly one `extend` for a successful manifest and none for a failed one; receiver snapshots are equal after a generator raises following a valid yield and after every malformed structural-source case; missing/non-callable `records`, non-iterable results, and invalid members raise `InvalidProviderError` with the source and a corrective action; exceptions originating inside valid external sources retain their identity; multiple independent sources retain earlier successful segments; a `Catalog` is neither a static nor runtime `Bindings`; and monkeypatching `_stage_manifest` to raise after inclusion cannot affect `freeze()`, `resolve()`, `aresolve()`, scopes, overrides, or injection.

- [ ] Add the red atomicity, ingestion, and runtime-boundary tests.
- [ ] Implement per-source materialization and one mutation.
- [ ] Run focused tests and both local type checkers.
- [ ] Commit with `fix: make binding source ingestion atomic`.

### Task 6: Publish the selected API and integrate existing documentation contracts

**Observable result:** All four names import from `depin`, exact `__all__` and zero-dependency import gates pass, and existing public docstrings accurately name manifest ingestion and discovery failures without adding error types.

**Files under responsibility:** Modify `depin/__init__.py`, `depin/_core/container.py`, `depin/_core/registry.py`, `depin/_core/spec.py`, `depin/_core/bindings.py`, and `depin/errors.py`; extend `tests/unit/test_public_api.py` and, only for exercised existing-class branches, `tests/unit/test_errors.py`.

**Test that must fail first:** Add `Catalog`, `Manifest`, `Provider`, and `provider` to `EXPECTED_EXPORTS` and add import/docstring assertions before editing production exports; the exact-surface and documentation tests fail.

**Minimum expected change:** Add root reexports/`__all__`; update the root mental model, `Container` source description, `Registry` distinction, `Bindings`/`include()` examples, and `InvalidProviderError` documentation. Add no new executable path outside imports.

**Focused validation:**

```bash
uv run pytest tests/unit/test_public_api.py tests/unit/test_errors.py depin/__init__.py depin/_core/discovery.py depin/_core/bindings.py depin/_core/container.py depin/_core/registry.py depin/_core/spec.py depin/errors.py -q
uv run basedpyright depin tests/unit/test_public_api.py tests/unit/test_errors.py
uv run mypy depin tests/unit/test_public_api.py tests/unit/test_errors.py
```

**Dependencies:** Tasks 1–5.

**Objective completion criterion:** Exact export order is updated, every name is importable, reloading `depin` imports no third party, every public discovery callable/class has Google-style semantics/errors/examples, `Manifest` is documented as `Bindings`, and `InvalidProviderError` remains the only discovery structural exception.

- [ ] Make the public-surface/docstring tests fail.
- [ ] Add exports and update only the listed public documentation contracts.
- [ ] Run focused pytest and both local type checkers.
- [ ] Commit with `feat: export declarative discovery`.

**Slice 2 checkpoint:** Run the focused commands from Tasks 4–6 plus `git diff --check`, verify no graph/runtime file changed, overwrite `.codex/progress/current.md`, and end the slice.

## Slice 3 — Semantic parity and composition behavior

### Task 7: Prove all seven provider forms are identical to manual binding

**Observable result:** Each approved provider form produces the same `BindRecord`, `ProviderSpec`, `SpecSet`, `ResolutionPlan`, resolution value, async requirement, and teardown behavior as manual `bind()`.

**Files under responsibility:** Create `tests/unit/test_discovery_parity.py`; modify `depin/_core/discovery.py` only if a field mapping defect is exposed.

**Test that must fail first:** A parametrized seven-row parity matrix fails on the first missing or incorrectly mapped declaration form before any corrective production edit.

**Minimum expected change:** Add tests first; any implementation correction is limited to overload ordering, produced-type unwrapping at the static boundary, or direct `_ProviderData` → `BindRecord` mapping. `build_specs()` and runtime modules stay unchanged.

**Focused validation:**

```bash
uv run pytest tests/unit/test_discovery_parity.py -q
uv run basedpyright depin/_core/discovery.py tests/unit/test_discovery_parity.py
uv run mypy depin/_core/discovery.py tests/unit/test_discovery_parity.py
```

**Dependencies:** Tasks 4–6.

**Objective completion criterion:** Class/sync/coroutine rows pass singleton, scoped, and transient; generator/async-generator/context-manager/async-context-manager rows pass singleton and scoped and match the existing transient `InvalidScopeError`; all equality assertions and sync/async teardown observations pass.

- [ ] Add and run the seven-row failing matrix.
- [ ] Correct only discovery mapping defects exposed by the matrix.
- [ ] Run focused pytest and both local type checkers.
- [ ] Commit with `test: prove declarative provider parity`.

### Task 8: Prove ordering, repetition, conditions, tags, checks, and manual composition

**Observable result:** Declarative segments preserve literal order and existing conflict rules across nested/repeated manifests and adjacent manual bindings; no discovery precedence or deduplication appears.

**Files under responsibility:** Create `tests/unit/test_discovery_composition.py` or extend the file created by Task 5; modify only `depin/_core/discovery.py` or `depin/_core/bindings.py` if a test exposes a defect.

**Test that must fail first:** The matrix for nested order, same catalogue twice, same manifest twice, overlap through two manifests, overlap with manual binding, distinct tags, inactive collision, checks, and both `provides()` orders fails before any focal correction.

**Minimum expected change:** Add behavior tests against real `Container`, `Registry`, and `FrozenContainer`; retain every occurrence and rely on existing `DuplicateProviderError` at `freeze()`.

**Focused validation:**

```bash
uv run pytest tests/unit/test_discovery_composition.py tests/unit/test_discovery_parity.py -q
uv run basedpyright tests/unit/test_discovery_composition.py tests/unit/test_discovery_parity.py
uv run mypy tests/unit/test_discovery_composition.py tests/unit/test_discovery_parity.py
```

**Dependencies:** Task 7.

**Objective completion criterion:** Records show manual-before/manifest/manual-after contiguity; nested flattening is left-to-right; repeated active key/tag occurrences raise the existing graph error; distinct tags coexist; false conditions do not collide and are called only at freeze; check identity/health behavior matches manual binding; already-built plans ignore later marker/reload changes.

- [ ] Add and run the failing composition matrix.
- [ ] Apply only corrections required to restore literal/manual semantics.
- [ ] Run focused pytest and both local type checkers.
- [ ] Commit with `test: cover declarative composition semantics`.

**Slice 3 checkpoint:** Run `uv run pytest tests/unit/test_discovery*.py tests/unit/test_container.py tests/unit/test_registry.py -q`, inspect the exclusive diff for changes outside the locked file map, overwrite `.codex/progress/current.md`, and end the slice.

## Slice 4 — Ordinary Python import behavior

### Task 9: Cover explicit imports across loader and installation layouts

**Observable result:** Exact imports work for regular packages, namespace portions, editable trees, wheel-shaped zip imports, plain zip imports, and a custom exact-name loader without enumeration; aliases and reexports preserve identity and module `__getattr__` is not probed.

**Files under responsibility:** Create `tests/integration/test_discovery_imports.py`; create `tests/fixtures/discovery_imports/regular/` and `tests/fixtures/discovery_imports/namespace/` package trees; modify `depin/_core/discovery.py` only for a proven caller/ownership defect.

**Test that must fail first:** Add imports of the not-yet-created regular and namespace fixtures and run the targeted module; collection fails with missing fixture modules before the package fixtures are created.

**Minimum expected change:** Add explicit-import fixture modules and tests. Build wheel/zip artifacts under `tmp_path` from the same fixture bytes; install nothing from the network and perform no filesystem enumeration in production.

**Focused validation:**

```bash
uv run pytest tests/integration/test_discovery_imports.py -k 'regular or namespace or editable or wheel or zip or loader or alias or reexport or getattr' -q
uv run basedpyright tests/integration/test_discovery_imports.py tests/fixtures/discovery_imports/regular tests/fixtures/discovery_imports/namespace
uv run mypy tests/integration/test_discovery_imports.py tests/fixtures/discovery_imports/regular tests/fixtures/discovery_imports/namespace
```

**Dependencies:** Tasks 3–8.

**Objective completion criterion:** All layouts yield identical explicit record order; only named modules contribute; alias/reexport `is` identity holds; no finder enumeration or package walk is observed; the trap `__getattr__` counter stays zero; namespace portions not imported by the manifest contribute nothing.

- [ ] Add the failing imports before their fixture packages.
- [ ] Create the minimal explicit-import fixtures and archive builders.
- [ ] Run focused pytest and both local type checkers.
- [ ] Commit with `test: cover declarative import layouts`.

### Task 10: Cover cycles, partial initialization, and reload snapshots

**Observable result:** Python-supported cycles succeed only after named values exist; early cyclic access and partial import failure propagate their original exceptions; reload creates new identities without changing existing builders or frozen containers.

**Files under responsibility:** Extend `tests/integration/test_discovery_imports.py`; create `tests/fixtures/discovery_imports/cycles/supported/`, `early/`, and `partial/`; modify `depin/_core/discovery.py` only for a proven snapshot/provenance defect.

**Test that must fail first:** Import tests reference each absent cycle fixture and fail at collection/import before the corresponding fixture tree is added.

**Minimum expected change:** Add only ordinary Python modules with explicit imports and deterministic sentinels/events. Use `importlib.reload` and isolated `sys.modules` cleanup in tests; add no lazy string reference or import wrapper.

**Focused validation:**

```bash
uv run pytest tests/integration/test_discovery_imports.py -k 'cycle or partial or reload' -q
uv run basedpyright tests/integration/test_discovery_imports.py tests/fixtures/discovery_imports/cycles
uv run mypy tests/integration/test_discovery_imports.py tests/fixtures/discovery_imports/cycles
```

**Dependencies:** Task 9.

**Objective completion criterion:** Supported cycle records are complete; early cycle raises the original import exception with cause intact; partial failure publishes no manifest to depin and mutates no receiver; old manifest/builder/plan identities and records remain unchanged after reload while a newly imported manifest uses new target/declaration/catalogue identities.

- [ ] Add the failing cycle/reload imports.
- [ ] Create the three minimal cycle fixture trees and reload isolation.
- [ ] Run focused pytest and both local type checkers.
- [ ] Commit with `test: cover declarative import snapshots`.

**Slice 4 checkpoint:** Run all discovery unit/import tests, confirm they use no sleep/network/clock dependency, overwrite `.codex/progress/current.md`, and end the slice.

## Slice 5 — Five-checker consumer and source contracts

### Task 11: Add the positive discovery typing corpus

**Observable result:** All five consumer checkers accept the four public exports, exact produced types, all seven target forms, exact callable parameters/wrappers, health checks, heterogeneous catalogues, nested manifests, and manifest ingestion.

**Files under responsibility:** Create `conformance/corpus/core/c10_discovery.py`; modify `conformance/coverage.toml`.

**Test that must fail first:** Add the four public-symbol coverage entries pointing to `c10_discovery.py` before creating the fixture; `tests/unit/test_conformance_coverage.py` and the positive runner fail because the mapped fixture is absent.

**Minimum expected change:** Add one consumer-only fixture importing from `depin`, with exact `assert_type`/typed-witness assignments for class, sync, coroutine, generator, async-generator, context-manager, and async-context-manager declarations; include complete metadata, contravariant `object` health check, both `provides()` orders, covariance into a heterogeneous `Catalog`, nested `Manifest`, and `Bindings = manifest`.

**Focused validation:**

```bash
uv run pytest tests/unit/test_conformance_coverage.py -q
uv run python -m scripts.conformance --mode core --only positive
```

**Dependencies:** Tasks 6–10.

**Objective completion criterion:** mypy, Basedpyright, stock Pyright, ty, and Pyrefly each report a non-zero checked-file count where supported and zero diagnostics for both source-tree and wheel consumer modes; all four coverage entries name `corpus/core/c10_discovery.py`.

- [ ] Add the failing coverage-map references.
- [ ] Create the exact positive corpus without suppressions or erasure.
- [ ] Run coverage inventory and the five-checker positive command.
- [ ] Commit with `test: type declarative discovery consumers`.

### Task 12: Add exact negative diagnostics

**Observable result:** Every checker rejects invalid `scope`, `provides`, `tag`, `when`, unrelated `check`, direct `Provider` construction, `Container(catalog)`, and `Registry.include(catalog)` at the intended call site.

**Files under responsibility:** Create `conformance/negative/n08_discovery_scope.py`, `n09_discovery_provides.py`, `n10_discovery_tag.py`, `n11_discovery_when.py`, `n12_discovery_check.py`, `n13_provider_construction.py`, `n14_container_catalog.py`, and `n15_catalog_ingestion.py`; modify `conformance/expected/negative.toml`.

**Test that must fail first:** Add each unsuppressed one-misuse fixture and run the negative corpus before recording expectations; the runner fails because `n08`–`n15` have no exact expected diagnostic entries.

**Minimum expected change:** Record only the observed diagnostic line and rule for each pinned checker. Metadata/catalogue cases must use each checker's argument-type rule; direct construction must use mypy `call-arg`, Pyright/Basedpyright `reportCallIssue`, ty `missing-argument`, and Pyrefly `bad-argument-count`, matching the approved proof unless the pinned tool's actual rule differs.

**Focused validation:**

```bash
uv run python -m scripts.conformance --mode core --only negative
```

**Dependencies:** Task 11.

**Objective completion criterion:** Each fixture produces a non-zero exit and the exact expected rule at one intended line in mypy, Basedpyright, stock Pyright, ty, and Pyrefly; there are no collateral diagnostics, suppressions, baselines, or changes to checker configurations/source registers.

- [ ] Add and run the eight unregistered negative fixtures.
- [ ] Record only measured line/rule expectations.
- [ ] Run the complete five-checker negative command.
- [ ] Commit with `test: reject invalid declarative discovery types`.

**Slice 5 checkpoint:** Run `uv run basedpyright`, `uv run mypy`, and `uv run python -m scripts.conformance --source`; then run `uv run python -m scripts.conformance --mode core`. Require stock Pyright at zero and exact unchanged ty/Pyrefly source registers, overwrite `.codex/progress/current.md`, and end the slice.

## Slice 6 — Public documentation and executable example

### Task 13: Complete public docstrings and generated reference

**Observable result:** Every new public callable/class documents semantics, ordering, ownership, immutability, errors, and a short executable example; the generated reference page builds from those docstrings.

**Files under responsibility:** Modify `depin/_core/discovery.py`, `depin/_core/bindings.py`, `depin/_core/container.py`, `depin/_core/registry.py`, `depin/_core/spec.py`, `depin/errors.py`, and `tests/unit/test_public_api.py`; create `docs/reference/discovery.md`; modify `mkdocs.yml`.

**Test that must fail first:** Extend the public documentation inventory to require meaningful `Raises:`/`Example:` sections and add the reference page to navigation before creating the page; the focused pytest/MkDocs commands fail on missing documentation.

**Minimum expected change:** Write Google-style docstrings without restating types; add `::: depin.provider`, `::: depin.Provider`, `::: depin.Catalog`, and `::: depin.Manifest` to the reference page; update existing shared docstrings only where manifest semantics apply.

**Focused validation:**

```bash
uv run pytest tests/unit/test_public_api.py depin/_core/discovery.py depin/_core/bindings.py depin/_core/container.py depin/_core/registry.py depin/_core/spec.py depin/errors.py -q
uv run --group docs mkdocs build --strict
```

**Dependencies:** Tasks 6–12.

**Objective completion criterion:** Every discovery docstring example executes; every raised discovery error is listed; the reference page contains no handwritten API restatement; strict MkDocs build succeeds without warning.

- [ ] Add the failing documentation inventory/navigation expectations.
- [ ] Complete docstrings and generated-reference directives.
- [ ] Run doctests and strict MkDocs.
- [ ] Commit with `docs: reference declarative discovery`.

### Task 14: Add the declarative discovery guide

**Observable result:** A narrative guide teaches local declaration, catalogue ownership, explicit imports/manifests, inclusion/freeze, manual interleaving, repetition/conflicts, reload snapshots, and the absence of scanning/runtime discovery.

**Files under responsibility:** Create `docs/guide/discovery.md`; modify `docs/guide/composition.md` and `mkdocs.yml`.

**Test that must fail first:** Add the guide navigation entry and composition link before creating the guide file; strict MkDocs fails on the unresolved page/link.

**Minimum expected change:** Add one focused guide with self-contained `pycon` doctests and a short link from composition. Do not duplicate complete signatures or reference prose.

**Focused validation:**

```bash
uv run pytest docs/guide/discovery.md docs/guide/composition.md -q
uv run --group docs mkdocs build --strict
```

**Dependencies:** Task 13.

**Objective completion criterion:** All guide examples execute, navigation/link checks pass, the guide states the exact ownership/composition/runtime boundaries, and no alternate public spelling or implicit import behavior appears.

- [ ] Add the failing navigation/link first.
- [ ] Write the narrative guide and focused composition link.
- [ ] Run guide doctests and strict MkDocs.
- [ ] Commit with `docs: guide declarative discovery`.

### Task 15: Add the executable multi-module example

**Observable result:** `python -m examples.declarative_discovery.main` builds from an explicitly imported manifest, resolves the graph, and is asserted by the integration suite; no container is constructed at module import.

**Files under responsibility:** Create the four `examples/declarative_discovery/` files listed in the file map; modify `examples/README.md` and `tests/integration/test_examples.py`.

**Test that must fail first:** Import and exercise `examples.declarative_discovery.main` from `test_examples.py` before creating the package; collection fails with `ModuleNotFoundError`.

**Minimum expected change:** Add a provider module with at least one class and one configured factory in a `Catalog`, a manifest module with exact imports, and a `main.py` whose `build()` constructs `Container(manifest)` and whose `main()` prints a deterministic result. Keep container construction out of module scope.

**Focused validation:**

```bash
uv run pytest tests/integration/test_examples.py -k declarative_discovery -q
uv run python -m examples.declarative_discovery.main
uv run basedpyright examples/declarative_discovery tests/integration/test_examples.py
uv run mypy examples/declarative_discovery tests/integration/test_examples.py
```

**Dependencies:** Tasks 13–14.

**Objective completion criterion:** The integration assertion and direct module command produce the documented deterministic value; README lists the exact command/concept; imports construct only immutable declarations/catalogue/manifest; `build()` owns the container.

- [ ] Add and run the failing integration import.
- [ ] Create the four example modules and README entry.
- [ ] Run the example, focused test, and both local type checkers.
- [ ] Commit with `docs: add declarative discovery example`.

**Slice 6 checkpoint:** Run all discovery doctests/example tests and strict MkDocs, overwrite `.codex/progress/current.md`, and end the slice.

## Slice 7 — Coverage, structural boundary, and real performance acceptance

### Task 16: Close public error/branch coverage and prove the runtime boundary structurally

**Observable result:** Whole-package coverage remains at least 95%, every new public error/edge branch is exercised, and both tests and diff inspection prove no discovery object or operation survives into frozen execution.

**Files under responsibility:** Extend only `tests/unit/test_discovery.py`, `tests/unit/test_discovery_composition.py`, `tests/unit/test_container.py`, `tests/unit/test_registry.py`, `tests/integration/test_discovery_imports.py`, or `tests/unit/test_errors.py`; production changes are limited to defects exposed by these tests.

**Test that must fail first:** Run the coverage command before adding closing tests; it must identify uncovered branches introduced in `discovery.py`/`bindings.py` or, if percentage already passes, the explicit error inventory must still fail until every new `InvalidProviderError` trigger is represented.

**Minimum expected change:** Add the smallest parametrized tests for uncovered direct construction, missing/mismatched owner, malformed private snapshot/member, invalid metadata, direct catalogue, custom `Bindings`, provenance formatting, and runtime guard paths. Do not add branches only to make them coverable.

**Focused validation:**

```bash
uv run pytest --cov=depin --cov-report=term-missing --cov-fail-under=95
git diff --exit-code origin/main -- depin/_core/providers.py depin/_core/graph.py depin/_core/frozen.py depin/_core/generated.py depin/_core/instructions.py depin/_core/construct.py depin/_core/scope.py depin/_core/overrides.py depin/_core/injection.py depin/_core/teardown.py
```

**Dependencies:** Tasks 1–15.

**Objective completion criterion:** Coverage exits zero at or above 95%; no introduced public branch is missing; monkeypatched discovery fails if touched after inclusion but all frozen operations pass; every listed runtime file is byte-identical to `origin/main`.

- [ ] Run and record the initial coverage/error-inventory failure.
- [ ] Add only the missing behavioral/error tests and any directly exposed correction.
- [ ] Run coverage and the runtime-file diff gate.
- [ ] Commit with `test: close declarative discovery coverage` if tests changed.

### Task 17: Execute the transferred performance gate against the real implementation

**Observable result:** A fresh paired comparison of synchronized `origin/main` against the implemented branch uses equivalent transient three-class graphs and classifies resolution as PASS only when both absolute and relative bounds pass.

**Files under responsibility:** Create `benchmarks/harness/discovery_acceptance.py` and `tests/unit/test_discovery_acceptance.py`. Use `/tmp/depin-discovery-implementation-gate/` only for the detached control worktree, generated fixture environments, raw samples, decision JSON, and seeded classifier proof.

**Test that must fail first:** Importing the absent focused command fails; after its shell exists, a deterministic seeded sample with `head = base + 100 ns` and ratio above `1.05` must exit non-zero and classify FAIL before real timings are allowed.

**Minimum expected change:** Add one repository-owned focused command with four subcommands: `seed-check` proves a known regression is rejected; `preflight` builds both environments and proves normalized structural equivalence; `collect` owns the fixed transient three-class fixture and the transferred sampling protocol; `decide` validates the completed sample document and applies the fixed decision rule. The command reuses existing harness errors, JSON helpers, environment controls, and quantile primitives where their contracts match. It uses fresh processes per side, ten warm-up pairs, non-comparative common-loop calibration to at least 250 ms per side, 192 measured AB/BA-balanced pairs, fixed `PYTHONHASHSEED=0`, lowest-affinity CPU pinning when available, 50,000 paired bootstrap medians, and seed `2026091102`. It records source, fixture, and harness hashes and writes final JSON atomically. Deterministic unit tests cover CLI validation, malformed/non-finite samples, unequal or insufficient pair counts, seeded bootstrap output, PASS/FAIL/INCONCLUSIVE boundaries, preflight mismatch, and exit codes without measuring time. Limits remain explicit command arguments from the closed contract rather than entries in the general calibrated workload budget.

**Focused validation:**

```bash
git fetch --prune origin
mkdir -p /tmp/depin-discovery-implementation-gate
git worktree add --detach /tmp/depin-discovery-implementation-gate/base origin/main
uv run pytest tests/unit/test_discovery_acceptance.py -q
uv run --group bench python -m benchmarks.harness.discovery_acceptance seed-check --delta-ns 100 --ratio 1.06 --absolute-limit-ns 50 --relative-limit 1.05
uv run --group bench python -m benchmarks.harness.discovery_acceptance preflight --base-dir /tmp/depin-discovery-implementation-gate/base --head-dir . --fixture-dir /tmp/depin-discovery-implementation-gate/fixture
uv run --group bench python -m benchmarks.harness.discovery_acceptance collect --base-dir /tmp/depin-discovery-implementation-gate/base --head-dir . --fixture-dir /tmp/depin-discovery-implementation-gate/fixture --warmup-pairs 10 --pairs 192 --minimum-interval-ms 250 --bootstrap-resamples 50000 --seed 2026091102 --out /tmp/depin-discovery-implementation-gate/result.json
uv run --group bench python -m benchmarks.harness.discovery_acceptance decide --input /tmp/depin-discovery-implementation-gate/result.json --absolute-limit-ns 50 --relative-limit 1.05
```

Preflight must prove equal normalized `BindRecord`, `ProviderSpec`, and `ResolutionPlan` observations for the manually built base/candidate graph and for candidate manual/declarative construction, and byte equality of the unchanged resolution modules listed in Task 16. The timed operation is only repeated `FrozenContainer.resolve(Root)` after setup/freeze; import, declaration, catalogue, manifest, staging, graph building, calibration, and teardown are outside the interval.

Decision uses paired `d_i = head_i - base_i` and `r_i = head_i / base_i`. PASS requires point and U95 `<= +50 ns` and `<= 1.05`; FAIL requires point and L95 above either bound; every other outcome is INCONCLUSIVE. One INCONCLUSIVE result permits exactly one complete rerun with `--pairs 384`, without inspecting partial data or changing any other byte/parameter; the second verdict is final. A FAIL blocks merge and may cause one focal runtime-boundary correction followed by one full fresh measurement; it never permits relaxing either limit.

**Dependencies:** Task 16 and a quiet host with synchronized `origin/main`.

**Objective completion criterion:** Deterministic command tests pass; seed check demonstrates rejection; preflight equivalence and structural hashes pass; the real result is PASS under both limits; raw JSON records all fixed parameters/hashes; the command source is committed while the temporary directory is retained only until PR evidence is recorded and then removed.

- [ ] Add the red deterministic command tests, implement the focused command, and prove its seeded failure classification.
- [ ] Run preflight and abort timing on any equivalence/hash failure.
- [ ] Collect the fixed real comparison and run the exact decision command.
- [ ] Record the PASS scalars/bounds and hashes in the implementation PR validation evidence.

**Slice 7 checkpoint:** Record coverage, runtime diff, seeded classifier, preflight hashes, performance point/L95/U95 for both metrics, verdict, and the exact final gate command in `.codex/progress/current.md`; end the slice before final integration.

## Final verification, review, and integration order

Run the repository gates from the implementation worktree in this exact order, without combining or reordering them:

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Then run the complete consumer/source typing evidence:

```bash
uv run python -m scripts.conformance --mode core
uv run python -m scripts.conformance --source
```

Review the exclusive diff against synchronized `origin/main` and require all of the following before commit/push:

- only paths in the locked file map changed;
- `depin/_core/providers.py`, graph/runtime modules, checker configs, source registers, `pyproject.toml`, `uv.lock`, benchmark budgets, and benchmark results are unchanged;
- all four exports match the normative signatures and public spellings;
- every requirement row below has a passing test/gate;
- no untracked temporary fixture, generated wheel/zip, site output, performance harness/result, cache, or journal is staged.

Use one complete correctness/typing/docs/performance review. Fix Critical or Important findings in at most one focal correction round, rerun the affected focused commands plus all six repository gates, and re-review only the corrected diff. If a second material correction round would be required, stop the implementation PR rather than broadening the design.

Commit the final logical remainder with the appropriate conventional prefix, push the feature branch, create a regular PR targeting `main`, and report all six local gates, both conformance commands, coverage, structural runtime diff, and the focused performance verdict. Watch every required GitHub check to completion. Merge only with all required checks green and no unresolved review finding. After merge, synchronize local `main`, verify the merge commit contains the implementation commits, remove the owned worktree, delete local and remote feature branches, prune worktrees/remotes, and remove `/tmp/depin-discovery-implementation-gate/` plus generated archives/site/caches created by the run.

## Requirements traceability matrix

| Requirement | Implementation tasks | Primary tests/evidence | Final gate |
| --- | --- | --- | --- |
| 1. Complete affected-file inventory | 1–17 | Locked production/test/typing/docs/example/performance map; exclusive diff | Scope review |
| 2. Exact `discovery.py` responsibility and closed no-scan/no-global boundary | 1–4, 9–10, 16 | Module boundary tests; import matrix; runtime file comparison | pytest + scope review |
| 3. Private and public `Provider[T]`, `Catalog`, and `Manifest` representation | 1–4 | Immutability/storage tests; `c10_discovery.py` | pytest + five checkers |
| 4. Target identity, `ParamSpec`, produced type, and provenance | 1–2, 7, 11 | Identity/location tests; seven-row parity; positive corpus | pytest + conformance |
| 5. Static and dynamic direct-construction rejection | 1, 12 | Runtime construction matrix; `n13_provider_construction.py` | pytest + negative corpus |
| 6. `configure()` ownership/source retention and full reset | 2 | Cross-module alias and repeated-configuration tests | pytest + five checkers |
| 7. `Catalog`/`Manifest` `__name__`, ownership, metadata, and member validation | 2–4, 10, 12, 16 | Negative unit/import matrix; `n08`–`n12`; coverage inventory | pytest + conformance + coverage |
| 8. `Manifest: Bindings`; `Catalog` non-ingestible | 3–6, 11–12 | Static/runtime protocol tests; positive fixture; `n14`/`n15` | pytest + conformance |
| 9. Complete staging before one receiver mutation | 4–5 | Tracking-list, malformed-source, and failing-generator atomicity tests | pytest |
| 10. Discovery ends before existing `build_specs()` | 4–5, 7, 16–17 | Monkeypatched runtime guard; structural preflight; unchanged runtime files | pytest + performance preflight |
| 11. Container, Registry, exports, and existing-error integration | 5–6 | Container/registry/public API/error tests | pytest + import gate |
| 12. Order, duplicates, conditions, tags, repeated manifests, and manual bindings | 8 | Composition matrix through real containers | pytest |
| 13. Imports, cycles, reload, aliases, reexports, and namespace packages | 9–10 | `test_discovery_imports.py` and enumerated fixtures | pytest |
| 14. Test-first coverage of all seven provider formats | 7, 11 | Runtime parity matrix and positive typing corpus | pytest + five checkers |
| 15. Atomic `BindRecord`, `ProviderSpec`, and `ResolutionPlan` equivalence | 4–5, 7, 17 | Equality matrices and performance preflight | pytest + performance preflight |
| 16. Negative ownership, construction, metadata, and member cases | 1–5, 10, 12, 16 | Unit/import negatives and `n08`–`n15` | pytest + conformance + coverage |
| 17. Positive and negative corpus for all five type checkers | 11–12 and Slice 5 checkpoint | Core/source fixtures and exact expected diagnostics | All conformance commands |
| 18. Docstrings, guide, generated reference, and executable example | 6, 13–15 | Doctests, example integration, direct module run | pytest + strict MkDocs |
| 19. Real-implementation performance at `+50 ns` and `1.05` | 16–17 | Deterministic classifier tests, seeded rejection, structural preflight, paired real result | Focused PASS + CI benchmarks |
| 20. Dependency order, exact commands, and objective completion | Every slice/task | Declared dependencies, task criteria, and checkpoints | Final ordered gates |

Implementation is complete only when every matrix row has its cited evidence, all local and CI gates are green, the focused performance comparison is PASS under both limits, and cleanup leaves synchronized `main` with no implementation worktree, feature branch, or temporary artifact.
