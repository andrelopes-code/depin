# Step 4, cycle 1 — decoration and conditional activation: design

Date: 2026-08-31
Baseline: 0.10.0 at `0ff6e1d`
Target: 0.11.0
Status: approved, pending implementation plan

## Goal

Close the two Step 4 deliverables that change what `freeze()` produces.

**Decoration** wraps a registered provider without touching its registration.
`Container.decorate(Store, with_logging)` makes every consumer of `Store`
receive `with_logging`'s result, while the undecorated binding keeps its
lifetime, its cache entry, and its teardown. Logging, caching, and retry stop
requiring a subclass or a hand-written factory.

**Conditional activation** puts a binding under a predicate. `bind(RedisCache,
when=has_redis)` registers a binding that enters the plan only when the
predicate holds. The predicate runs inside `freeze()` and never at resolution
time, so the validated graph stays static: a plan either contains the node or
does not, and nothing decides per resolution.

The two ship together because both change what the `ResolutionPlan` contains.
Decoration rewrites a node of the plan; conditional activation omits nodes from
it. Both sit between record collection and validation, on the one path
`freeze()` runs, and neither can be validated without the other's interactions —
a decorator over an inactive binding, an inactive binding required by an active
one.

## What changes for an existing graph

| Before | After |
| --- | --- |
| Every record collected becomes a node. | A record carrying `when` becomes a node only when its condition holds. |
| A provider key is a class, a `Token`, a string, or a parameterised generic. | It may also be an `Underlying`, the identity a decorated binding's inner form moves to. |
| `MissingProviderError` names the key and the chain. | It also notes when an inactive conditional binding declares that key. |

All three are widenings. A graph that froze at 0.10.0 freezes unchanged: no
record carries a condition unless one is written, and no `Underlying` key exists
unless `decorate` is called.

## Measurements

Five questions were measured against the tree at `0ff6e1d`, rather than assumed.

**A decorator does not need a new `ProviderShape`.** A wrapper is an ordinary
class or factory. Given a plan in which the undecorated binding sits under one
key and the wrapper sits under the public key taking the undecorated form as a
parameter, `construct.sync` builds it through the `CLASS` / `FUNCTION` /
`GENERATOR` / `CONTEXT_MANAGER` cases it already has. `construct.py`'s match
over `ProviderShape` therefore stays exhaustive with no new case, and
`graph.py`, `frozen.py`, `diagnostics.py`, and `render.py` need no change for
decoration at all. This is the third time the alias pattern composes: a node of
an existing shape whose parameters are what it depends on.

**Two nodes produce one teardown, in the undecorated position.** The shape above
was built from 0.10.0 primitives — a generator provider under one key, a wrapper
factory under another, a lifecycle provider constructed before it and a
lifecycle consumer after it — and the recorded event sequence is byte-identical
to the same graph with the wrapper removed:

```
decorated  : open early, open base, open late, close late, close base, close early
undecorated: open early, open base, open late, close late, close base, close early
```

Resolving the decorated key twice, and resolving it through a consumer as well,
adds no further `open base` or `close base`. The second cache entry the inner
node occupies holds the undecorated value; it is not a second construction, and
teardown count follows construction, not caching. A wrapper that owns a teardown
of its own nests correctly inside the base's:

```
open early, open base, open wrap, open late, close late, close wrap, close base, close early
```

**A `Protocol` passed as the decorated key does not trip mypy's
`type-abstract`.** `decorate(key: ProviderKey, ...)` takes a union, which is the
resolution Step 3 cycle 1 measured for `provides`. `decorate(Store, logged)`
with `Store` a `Protocol`, and with the wrapper given as a class or as a
function, is clean under both `mypy --strict` and `basedpyright --strict`. A
signature spelled `key: type[T]` would not be.

**A frozen dataclass keys the plan.** `Underlying(Store, 0)` is hashable,
compares by value, nests, and survives a `GenericAlias` inside it. The PEP 695
alias may name it before it is defined, because a `type` alias is lazy, and the
dataclass may annotate its field with the alias for the same reason.

**The frame short-circuit bypasses a decorator.**
`FrozenContainer._resolve_params_sync` fills a parameter from the active scope
frame whenever `param.key in frame`, before consulting the plan. For a key
seeded with `ScopeFrame.provide`, a parameter would therefore receive the
undecorated value while `resolve(key)` returned the decorated one. That is why
decorating a `Container.scope_value` binding is rejected in this cycle rather
than left half-working; narrowing the short-circuit belongs to a cycle that owns
that path.

## Public surface

Two additions and one widening. No signature changes to existing methods beyond
one new keyword argument.

| Symbol | Role |
| --- | --- |
| `BindingCollector.decorate` | Declares a wrapper over an existing binding. |
| `Underlying` | The key a decorated binding's inner form is registered under; a new `ProviderKey` member. |
| `when=` on every registration method | Conditional activation. |

```python
def decorate(
    self,
    key: ProviderKey,
    wrapper: type[object] | Callable[..., object],
    *,
    tag: str | None = None,
    when: bool | Callable[[], bool] | None = None,
) -> Self: ...
```

`key` and `tag` name the binding to wrap. `wrapper` is a class or a factory of
any non-async or async shape; it declares one parameter whose key and tag are
the decorated ones, which receives the undecorated value, and any number of
further parameters, which are ordinary graph edges.

`when` is added to `bind`, `value`, `scope_value`, `alias`, `collect`,
`decorate`, and the `singleton` / `scoped` / `transient` decorators — every
method that appends a record. A `bool` is read where it is written; a callable
is called once, inside `freeze()`, each time the container is frozen.

```python
@final
@dataclass(frozen=True, slots=True)
class Underlying:
    key: ProviderKey
    applied: int
```

`ProviderKey` gains it as a union member:

```python
type ProviderKey = type[object] | Token[object] | str | GenericAlias | Underlying
```

A user constructs an `Underlying` only to inspect one — `explain()` and
`graph().find()` accept it, and `graph().nodes` contains it for a decorated
binding. `resolve` does not: its signature admits a class or a `Token`, and the
undecorated form is not something a consumer asks for by name.

## Data model

### Decoration

A `decorate` call appends a `BindRecord` whose source is a marker:

```python
@dataclass(frozen=True, slots=True)
class DecorateBinding:
    key: ProviderKey
    wrapper: object
```

`DecorateBinding` carries its own key for the reason `AliasBinding` does:
`BindRecord.provides` admits only a class, while a decorated key may equally be
a `Token`, a string, or a parameterised generic. It carries no second tag,
unlike `AliasBinding`: a decorator has no identity of its own, so the one tag it
has is the decorated binding's, and it rides on `BindRecord.tag` where every
other tag rides.

`build_specs` does not turn a decorate record into a `ProviderSpec`. It produces
a `DecorationSpec` instead, because the spec's key depends on how many other
decorators target the same binding, which is not known record by record:

```python
@dataclass(frozen=True, slots=True)
class DecorationSpec:
    key: ProviderKey
    tag: str | None
    source: object
    shape: ProviderShape
    params: tuple[ParamSpec, ...]
    inner: str
```

`inner` is the name of the parameter that receives the undecorated value.

`depin/_core/decoration.py` folds the decorations over the provider specs. For a
binding with N decorators, in the order they were registered:

| Node | Identity | Source | Scope |
| --- | --- | --- | --- |
| the registered binding | `(Underlying(key, 0), tag)` | unchanged | unchanged |
| decorator *i*, for *i* < N | `(Underlying(key, i + 1), tag)` | wrapper *i* | the binding's |
| decorator N | `(key, tag)` | wrapper N − 1 | the binding's |

Each decorator's `inner` parameter is rewritten to point at the node below it;
its other parameters are untouched. The last decorator registered is the
outermost, so `decorate(Store, metrics)` followed by `decorate(Store, retry)`
resolves `retry(metrics(store))`.

A binding with no decorator is left exactly as it was, under its own key. No
`Underlying` node exists unless a decoration creates one.

### Conditional activation

`BindRecord` gains one field:

```python
@dataclass(frozen=True, slots=True)
class BindRecord:
    source: object
    scope: Scope
    provides: type[object] | None
    tag: str | None
    condition: bool | Callable[[], bool] | None = None
```

`None` means unconditional. The field is last and defaulted, so every existing
construction and every consumer of `Bindings.records()` is unaffected.

`build_specs` partitions the records before it builds anything: an inactive
record is never introspected for its shape or its parameters. That is what makes
`bind(RedisCache, when=has_redis)` safe when the binding is the one that cannot
be introspected in the deployment that switches it off.

An inactive record still contributes its *declared* key to
`ResolutionPlan.inactive`, when that key can be read without introspecting the
provider: a class source, an explicit `provides=`, a `value` token, a
`scope_value` key, an alias key, a collection element, or a factory whose return
annotation resolves. Reading it never raises — a factory with no resolvable
return annotation contributes nothing and is simply not named in the note below.

## Semantics

### Decoration

| Situation | Behaviour |
| --- | --- |
| `resolve(Store)` on a decorated singleton | Returns the wrapper's value. The same object on every call. |
| `resolve(Underlying(Store, 0))` | Returns the undecorated value, the one the wrapper received. |
| A provider taking `store: Store` | Receives the decorated value. Decoration is not a top-level-only substitution. |
| Teardown of the decorated binding | Runs once, in the position the undecorated binding would have occupied. |
| Teardown of a wrapper that owns one | Runs immediately before the binding's, because it was constructed after it. |
| The decorated binding is async | The wrapper node inherits `needs_async` by ordinary propagation; `resolve` rejects it, `aresolve` drives it. |
| The wrapper is async over a sync binding | Same: the wrapper's own shape sets the flag. |
| The wrapper's own dependencies | Ordinary edges, validated for existence, cycles, captivity, and async propagation like any others. |
| `override(Store, fake)` | Replaces the decorated key, so the wrapper and the inner node are both bypassed. Unchanged behaviour: an override replaces whatever occupies the key. |
| The decorator's scope | The decorated binding's. A decorator does not choose its own lifetime. |
| Two decorators on one binding | Both apply, outermost last registered. |
| The decorated binding is an alias, a collection, or a value | Decorated like any other. Nothing in those shapes reads its own key. |
| The decorated binding is a `scope_value` | Rejected. See the Errors table. |

### Conditional activation

| Situation | Behaviour |
| --- | --- |
| `when=None` | Unconditional. The default. |
| `when=True` / `when=False` | Read at the call that appends the record. |
| `when=predicate` | Called once per `freeze()`, with no arguments; its result is read for truth. |
| An inactive record | Contributes no node. It appears in no plan, no `graph()`, no export, and is validated as nothing. |
| A parameter requiring an inactive binding | Unsatisfied. It escapes only through a default or a `T \| None` annotation, exactly as any unbound key does. |
| Two bindings for one key, one active | No duplicate. This is the deployment switch the feature exists for. |
| Two bindings for one key, both active | `DuplicateProviderError`, unchanged. |
| A decorator whose target is inactive | The decoration finds no binding and raises. Give the decorator the same condition. |
| Freezing twice | Predicates are called again. A container is a builder, and two freezes of the same builder may legitimately differ. |

## Errors

| Trigger | Error | Message names |
| --- | --- | --- |
| `decorate` names a key nothing binds | `MissingProviderError` | the key, the tag, and that a decorator requires an existing binding |
| The wrapper declares no parameter of the decorated key and tag | `InvalidProviderError` | the wrapper, the key, and that one parameter must be annotated with it |
| The wrapper declares two or more such parameters | `InvalidProviderError` | the wrapper, the key, and both parameter names |
| The wrapper is neither a class nor a callable | `InvalidProviderError` | through `detect_shape`, unchanged |
| The wrapper is a generator or context manager and the binding is transient | `InvalidScopeError` | the wrapper, and that a transient value is never cached so nothing would drain it |
| The decorated binding is a `scope_value` | `InvalidProviderError` | the key, and that a scope-supplied value is read from the frame before the plan is consulted |
| `decorate`'s key is not a provider key | `InvalidProviderError` | through `as_provider_key`, unchanged |
| `when` is neither a `bool` nor a callable | `InvalidProviderError` | the value and the two accepted forms |
| A parameter requires a key that only an inactive binding declares | `MissingProviderError` | the existing chain, plus `; a conditional binding for this key is registered but inactive` |

The last row is the one addition to an existing message. It is produced by
`graph.format_missing`, which both `freeze()` and `explain()` already share, so
the note appears identically in the error and in the diagnostic.
`FrozenContainer.explain()` reads the set off `ResolutionPlan.inactive` and
hands it to `render_tree`, rather than `DependencyGraph` carrying it: the graph
view describes nodes, and an inactive binding is precisely a node that does not
exist.

## Key rendering

`fmt_key` gains one branch:

| Key | Rendered |
| --- | --- |
| `Underlying(Store, 0)` | `Store (undecorated)` |
| `Underlying(Store, 1)` | `Store (decorated x1)` |
| `Underlying(list[Handler], 0)` | `list[Handler] (undecorated)` |

The inner key is rendered by `fmt_key` itself, so a decorated generic, `Token`,
or string key renders the way it does everywhere else. A tree over a binding
with two decorators therefore reads:

```
Store  [singleton, function]
  inner: Store (decorated x1)  [singleton, function]
    inner: Store (undecorated)  [singleton, class]
```

## Module layout

One new module. Everything else lands where the concern already lives.

| Module | Change |
| --- | --- |
| `_core/spec.py` | `Underlying`; the `ProviderKey` widening; `DecorateBinding` and `is_decorate_binding`; `DecorationSpec`; `BindRecord.condition`; `ResolutionPlan.inactive`; the `fmt_key` branch. |
| `_core/typeguards.py` | `is_provider_key` admits `Underlying`. |
| `_core/bindings.py` | `decorate`; `when` on every registration method; `ScopeDecorator` carries it. |
| `_core/providers.py` | Record partitioning by condition; `DecorationSpec` construction; the declared-key reader for the inactive note; `_classes_within` recurses into an `Underlying`. |
| `_core/decoration.py` | **New.** Folds decorations over the provider specs. |
| `_core/graph.py` | `build_plan` applies the fold and carries `inactive`; `format_missing` takes the note. |
| `_core/render.py` | `render_tree` and `_render_absent` take the inactive set and pass the note through. |
| `_core/frozen.py` | `explain()` hands `ResolutionPlan.inactive` to `render_tree`. |
| `_core/container.py` | `freeze()`'s `Raises:`; the `Container` docstring lists `decorate()`. |
| `depin/__init__.py` | Exports `Underlying`. |

`construct.py`, `diagnostics.py`, `scope.py`, `teardown.py`, `injection.py`,
`overrides.py`, `introspect.py`, and `markers.py` are unchanged. `frozen.py`
changes by one argument, on the `explain()` line alone; no resolution path is
touched.

## Verification

- `tests/unit/test_decoration.py`: a decorated singleton's identity; a decorated
  scoped and transient binding; a consumer receiving the decorated value; the
  undecorated node reachable under `Underlying`; two decorators and their order;
  a class wrapper; a generator wrapper and its teardown position; a wrapper with
  its own dependencies; a wrapper over an alias, a collection, and a `value`;
  a tagged binding; an async wrapper over a sync binding and the reverse; an
  `override` over a decorated key.
- `tests/unit/test_decoration.py`: teardown position asserted against the
  undecorated graph, event sequence for event sequence, which is the roadmap's
  acceptance criterion stated as a test.
- `tests/unit/test_conditional.py`: active and inactive bindings; a predicate
  called exactly once per freeze and again on a second freeze; `when` on every
  registration method; two bindings for one key switched by condition; an
  inactive binding required by an active one; the same escaped by a default and
  by `T | None`; an inactive decorator; a decorator over an inactive binding.
- `tests/unit/test_graph_validation.py`: every row of the Errors table.
- `tests/unit/test_graph_render.py`: `fmt_key` over `Underlying` at both
  depths; a decorated node in `explain()`, `dot`, and `mermaid`; the inactive
  note appearing identically in `freeze()`'s error and in `explain()`.
- `tests/unit/test_graph_properties.py`: the generative model gains a
  `decorations` field and a `conditions` field, drawn and materialised last with
  defaults, following the precedent `aliases`, `collections`, and `optionals`
  set. The existing invariants — acyclicity, ordering, captivity, and the
  agreement between `freeze()` and `explain()` — then cover decorated and
  conditional graphs.
- `tests/typing/test_conformance.py`: `assert_type` over `decorate` returning
  `Self`, `decorate` with a `Protocol` key, `when` in both spellings, and
  `Underlying` as an `explain()` argument.
- `tests/unit/test_public_api.py`: `Underlying` in `__all__`.
- `benchmarks/`: `freeze()` over a graph with a decorated node, and resolution
  through a two-deep decoration chain.
- `examples/decoration/main.py` and `examples/conditional/main.py`, listed in
  `examples/README.md` and executed by `tests/integration/test_examples.py`.
- `tests/integration/test_fastapi_ext.py`: a route resolving a decorated scoped
  provider, and an app whose binding set differs by condition.
- `docs/guide/composition.md` gains a `## Decoration` and a `## Conditional
  bindings` section, both with `pycon` doctests.
- The mutation gate in CI covers every changed module under `depin/_core/`.

## Acceptance criteria

- A decorated provider is torn down exactly once, in the position its
  undecorated form would have occupied.
- Conditional bindings that are inactive do not appear in the plan and are not
  validated as dependencies.
- Every addition is validated at `freeze()`, not at resolution time.
- `depin/` carries exactly the three suppressions it carries at `0ff6e1d`.
- The five gates and `mkdocs build --strict` pass with no warnings or waivers.
- Coverage over `depin/` stays at or above 95%.
- No regression against the benchmark baseline.

## Out of scope

| Item | Reason |
| --- | --- |
| A decorator with a lifetime of its own | A decorator that outlived or under-lived what it wraps would need its own captivity rule, and no consumer is identified. Inheriting the binding's scope is the only shape with one obvious answer. |
| Decorating a `scope_value` binding | The frame short-circuit in `_resolve_params_sync` would hand a parameter the undecorated value while `resolve` returned the decorated one. Narrowing that short-circuit changes an existing resolution rule and belongs to a cycle that owns it. |
| Decorating by predicate over many keys | `decorate(matching(...))` needs a matching language and makes the plan depend on registration order in a way `freeze()` cannot report simply. One key per call keeps every decoration nameable in an error. |
| `include(source, when=...)` | Plain Python already expresses it, and combining an outer condition with a record's own would need a precedence rule for no new capability. |
| A predicate taking arguments | A zero-argument callable closes over whatever it needs. Passing the container would let a predicate observe a half-built plan. |
| Reporting inactive bindings as public data | The plan carries them only to keep `explain()` and `freeze()` phrased alike. A public accessor is surface with no identified consumer; the note is what a user acts on. |
| Narrowing `MissingProviderError` to a dedicated inactive error | The failure is the same one — a parameter has no provider. A second exception type would split an `except` that should stay one. |
