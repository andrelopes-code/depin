# Step 3, cycle 1 — `provides` and aliasing: design

Date: 2026-08-31
Baseline: 0.7.0 at `a974339`
Target: 0.8.0
Status: approved, pending implementation plan

## Goal

Close the two Step 3 deliverables that do not change what `freeze()` accepts:
the `provides` signature, and key aliasing.

`provides` is a repair. Its type parameter is phantom, and its presence makes
mypy report `type-abstract` in the consumer's own file for exactly the pattern
the README teaches. Erasing the parameter removes the diagnostic and the three
suppressions the repository carries because of it.

Aliasing is an addition. `Container.alias(Store, to=PostgresStore)` makes one
instance reachable under two keys, with no second cache entry and no second
teardown.

Neither deliverable widens the set of graphs `freeze()` accepts. An alias
introduces an ordinary node with an ordinary edge, validated by the checks that
already exist. The other three Step 3 deliverables — optional dependencies,
collection injection, and generic keys — change validation rules and ship in
the two cycles after this one.

## Step 3 is three releases

The roadmap describes Step 3 as one release. It ships as three, each with its
own spec, plan, pull request, and release:

| Cycle | Version | Deliverables |
| --- | --- | --- |
| 1 | 0.8.0 | `provides` signature, aliasing |
| 2 | 0.9.0 | Optional dependencies, collection injection |
| 3 | 0.10.0 | Generic keys |

Cycle 1 is the pair that leaves validation untouched. Cycle 2 is the pair that
changes what an unsatisfied parameter means, so both of its deliverables pass
through `ParamSpec` and the unsatisfied-parameter path and cannot be separated.
Cycle 3 is alone because its hard problem is not the graph: `resolve[T](key:
type[T]) -> T` cannot express `Repo[User]`, since a parameterised generic alias
is not a `type`.

Steps 4, 5, and 6 renumber to 0.11.0, 0.12.0, and 1.0. The roadmap is updated in
this cycle, in its own commit.

## Public surface

### `provides`

```python
def provides(abstract: type[object]) -> _ProvidesDecorator: ...
```

The type parameter `A` is deleted, and `_ProvidesDecorator` becomes
non-generic. Its `__call__` keeps its own parameter, so the decorated class
retains its type:

```python
class _ProvidesDecorator:
    def __call__[C](self, cls: type[C]) -> type[C]: ...
```

Three signatures were measured against mypy at default settings and
`basedpyright --strict`, for a `Protocol` target and an `ABC` target:

| Signature | mypy | basedpyright |
| --- | --- | --- |
| `type[A]`, `A` a type variable | `type-abstract` on both targets | clean |
| `type[A] \| str` | clean | clean |
| `type[object]` | clean | clean |

The roadmap's third option — making `A` load-bearing by binding the decorated
class to it, `__call__[C: A]` — does not work and is withdrawn. mypy rejects
every class passed, including one that satisfies the target (`Value of type
variable "C" of "__call__" of "_ProvidesDecorator" cannot be "Good"`), and
basedpyright rejects the declaration itself (`TypeVar constraint type cannot be
generic`).

`type[object]` is chosen over the union. `A` is observable in no return type a
consumer can reach — `_ProvidesDecorator` is private and unexported — so the
union's only function would be to defeat mypy's rule with a `str` member the
function then rejects at runtime, advertising a parameter shape it does not
accept. `Container.bind`'s own `provides: type[object] | None` parameter already
sets the precedent.

`provides` gains a runtime guard: a non-class argument raises
`InvalidProviderError`. `get_provides` returns the stored object as a `type`,
and `_resolve_key` uses it directly as a provider key, so a caller that reaches
past the annotation must fail at the decorator rather than at `freeze()`.

Three suppressions are removed with the change: `examples/testing/main.py:15`,
`tests/unit/test_resolution.py:41`, and `tests/typing/test_conformance.py:138`.
The "Known limitation" section of `docs/support-policy.md` is removed with them,
and the sentence in `AGENTS.md` that cites it — "with one documented exception
recorded in `docs/support-policy.md`" — drops the exception. After this cycle
the package and its examples carry no `type-abstract` suppression.

### `alias`

One method is added to `BindingCollector`, so `Container` and `Registry` both
carry it.

```python
def alias(
    self,
    key: ProviderKey,
    *,
    to: ProviderKey,
    tag: str | None = None,
    to_tag: str | None = None,
) -> Self: ...
```

`key` and `to` are typed `ProviderKey`, not `type[T]`. `type[T]` reproduces the
`type-abstract` diagnostic this cycle exists to remove, and aliasing a concrete
class to a `Protocol` is the primary use. The measured alternative that avoids
the diagnostic while keeping a type parameter, `type[T] | Token[T]`, buys
nothing: `T` joins across both arguments, so `alias(Store, to=Unrelated)` is
accepted by both checkers. A type parameter that constrains nothing is the same
phantom being deleted from `provides`.

`ProviderKey` also admits a `str` key, which matches `explain`,
`DependencyGraph.node`, and `FrozenContainer._lookup`.

`alias` takes no `scope`. An alias has no lifetime of its own; the target keeps
its scope, its cache entry, and its teardown.

One member is added to `ProviderShape`:

```python
ALIAS = 'alias'
```

## Data model

```python
@dataclass(frozen=True, slots=True)
class AliasBinding:
    key: ProviderKey
    target: ProviderKey
    target_tag: str | None
```

`AliasBinding` joins `ValueBinding` and `FrameBinding` as a marker source
carried by `BindRecord.source`, with `is_alias_binding` as its narrowing guard.
It carries its own `key` because `BindRecord.provides` is `type[object] | None`
and an alias key may be a `Token` or a `str`. The alias's own tag rides on
`BindRecord.tag`, where every other binding's tag already rides.

`_record_to_spec` turns the record into a spec with one parameter:

```python
ProviderSpec(
    key=as_provider_key(alias.key),
    tag=rec.tag,
    source=alias,
    scope=Scope.TRANSIENT,
    shape=ProviderShape.ALIAS,
    needs_async=False,
    params=(
        ParamSpec(
            name=ALIAS_PARAM,
            key=as_provider_key(alias.target),
            tag=alias.target_tag,
            has_default=False,
            default=None,
        ),
    ),
)
```

`ALIAS_PARAM` is the string `'target'`, defined once in `_core/spec.py` and read
by `_core/providers.py` and `_core/construct.py`. It is the parameter name
`explain()` prints and the edge label `dot()` and `mermaid()` emit.

## Semantics

An alias is a transient indirection whose single dependency is its target.
Everything else follows from that, with no change to any existing check.

| Property | How it holds |
| --- | --- |
| One instance under both keys | The alias caches nothing, so the cache identity is the target's `(key, tag)` on both paths. |
| Teardown belongs to the target | `construct` registers no teardown for `ALIAS`; only the target's own shape can. |
| Captive validation sees through it | `_check_captive` already walks through transients, and reports the alias in the chain. |
| Async propagates | `_with_async_flags` marks the alias when its target is async, so `resolve` rejects it and names the alias key. |
| Cycles are rejected | `alias(A, to=B)` with `alias(B, to=A)` is an ordinary cycle for `_toposort`. |
| An alias may target an alias | Chained aliases are an ordinary path; the last target owns the instance. |
| A duplicate alias raises | `_check_duplicates` sees the alias identity like any other. |
| An absent target raises | `_check_missing` sees an unsatisfied required parameter. |
| An override substitutes it | `_lookup_optional` consults overrides before the plan, on the alias key and the target key alike. |

The alias's own scope is `Scope.TRANSIENT`, and `explain()` renders it as
`[transient, alias]`. That is precise — the alias node itself caches nothing —
and the guide states it, so a reader does not mistake it for a claim about the
target's lifetime.

Three alternatives were probed against the real `FrozenContainer` before this
one was adopted.

- Registering the target's own `ProviderSpec` under a second identity gives one
  instance, but the alias never enters `ResolutionPlan.order`, so `graph()`,
  `explain()`, `dot()`, and `mermaid()` cannot see it. Step 2 exists to make the
  graph inspectable; a feature invisible to it is not finished.
- Copying the target's `ProviderSpec` under the alias key gives **two**
  instances. The singleton cache is keyed on `(spec.key, spec.tag)`, and the
  copy carries a different key, so the roadmap's "without a second singleton"
  requirement fails outright.
- The adopted form gives one instance — `di[Store] is di[PostgresStore]`, and
  the same object again when reached as another provider's dependency — and
  `_check_captive` reports `Service -> Store -> PostgresStore` for a singleton
  aliased onto a scoped target.

## Errors

No exception type is added to `depin/errors.py`.

| Call | Behaviour |
| --- | --- |
| `provides(x)` where `x` is not a class | `InvalidProviderError`. |
| `alias(key, to=...)` where either is not a valid key | `InvalidProviderError`, from `as_provider_key`, at `freeze()`. |
| `alias` onto an unbound target | `MissingProviderError` at `freeze()`, naming the alias as the requiring owner. |
| Two aliases under one identity, or an alias over a bound key | `DuplicateProviderError` at `freeze()`. |
| An alias participating in a cycle | `CircularDependencyError` at `freeze()`. |
| A singleton reaching a scoped provider through an alias | `CaptiveDependencyError` at `freeze()`, with the alias in the chain. |
| `resolve` on an alias to an async target | `AsyncInSyncContextError`, naming the alias key. |

`construct` narrows the resolved alias parameter through a guard in
`_core/typeguards.py` rather than indexing `kwargs` directly, so a defect that
delivered an alias spec with no resolved target raises `InvalidProviderError`
naming the provider instead of a bare `KeyError`. Every other value in that
module is narrowed the same way.

## Module layout

No new module. The change lands where each concern already lives.

| Module | Change |
| --- | --- |
| `_core/markers.py` | `provides` loses `A`; `_ProvidesDecorator` becomes non-generic; the runtime guard. |
| `_core/spec.py` | `ProviderShape.ALIAS`, `AliasBinding`, `is_alias_binding`, `ALIAS_PARAM`. |
| `_core/bindings.py` | `BindingCollector.alias`. |
| `_core/providers.py` | `_record_to_spec` grows the alias branch. |
| `_core/construct.py` | `sync` grows the `ALIAS` case. |
| `_core/typeguards.py` | `as_alias_target`. |
| `depin/__init__.py` | Nothing. `alias` is a method; `ProviderShape` is already exported. |

`graph.py`, `frozen.py`, `diagnostics.py`, and `render.py` are not touched. That
they need no change is the evidence that the design composes with what exists.

## Verification

- `tests/unit/test_markers.py`: `provides` stores the target, returns the class
  unchanged, and rejects a non-class with `InvalidProviderError`.
- `tests/unit/test_alias.py`: identity under both keys for each scope; identity
  as a nested dependency; a tagged target; a chained alias; a `Token` key; a
  `str` key; teardown running once and owned by the target; an alias to a
  `scope_value` binding.
- `tests/unit/test_graph_validation.py`: the alias cases in the error table
  above — missing target, duplicate identity, cycle, captive chain.
- `tests/unit/test_frozen_async.py`: an alias to an async target resolves under
  `aresolve` and is rejected by `resolve`.
- `tests/unit/test_graph_render.py`: an alias node renders as
  `[transient, alias]` with a `target:` edge, in all three renderers.
- `tests/unit/test_graph_properties.py`: the existing Hypothesis invariants hold
  over graphs containing aliases.
- `tests/typing/test_conformance.py`: the two `provides` suppressions are gone
  and `assert_type` still holds; `alias` returns `Self`.
- `tests/unit/test_public_api.py`: `ProviderShape` gains exactly one member.
- `benchmarks/`: resolution through an alias against direct resolution of the
  same target, so the indirection's cost is measured rather than assumed.
- `examples/aliasing/main.py`, listed in `examples/README.md` and executed by
  `tests/integration/test_examples.py`.
- `tests/integration/test_fastapi_ext.py`: a route resolves a dependency through
  an alias, per the roadmap's cross-cutting rule.
- `docs/guide/composition.md` gains an aliasing section with `pycon` doctests;
  `docs/support-policy.md` loses the known-limitation section.
- The mutation gate at 95% covers the changed modules.

## Acceptance criteria

- No `type-abstract` suppression remains anywhere in the repository, and
  `uv run mypy` is clean without one.
- `di[Alias] is di[Target]` for a singleton target, and the target is
  constructed once.
- An alias participates in duplicate, missing, cycle, and captive validation at
  `freeze()`, not at resolution time.
- An alias is visible in `graph()`, `explain()`, `dot()`, and `mermaid()`.
- The five gates and `mkdocs build --strict` pass with no warnings or waivers.
- Coverage over `depin/` stays at or above 95%.
- No regression against the benchmark baseline.

## Out of scope

| Item | Reason |
| --- | --- |
| Verifying that an alias target satisfies the alias key | Not checkable. A `Protocol` that is not `@runtime_checkable` has no runtime `issubclass`, and a structural alias between unrelated classes is legitimate. Neither checker catches it statically either, under any signature measured. |
| `alias(key, to=...)` with a `scope` argument | An alias has no lifetime. Accepting a scope would let a caller state one that the target then contradicts. |
| Aliasing several targets under one key | That is collection injection, and it needs the multi-binding registration cycle 2 introduces. |
| Widening `provides` to accept a `Token` or a `str` | A feature addition, not part of the repair. `bind(provides=...)` has the same restriction, and changing both belongs with deliberate work on the key model. |
| Optional dependencies, collection injection, generic keys | Cycles 2 and 3. |
