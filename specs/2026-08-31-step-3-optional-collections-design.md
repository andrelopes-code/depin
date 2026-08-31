# Step 3, cycle 2 — optional dependencies and collection injection: design

Date: 2026-08-31
Baseline: 0.8.0 at `ad33482`
Target: 0.9.0
Status: approved, pending implementation plan

## Goal

Close the two Step 3 deliverables that change what `freeze()` accepts.

An **optional dependency** is a parameter annotated `T | None`. Today that
annotation is rejected outright — `as_provider_key` raises `cannot use X | None
as a provider key`. After this cycle it resolves to the bound `T` when one
exists, and to `None` when none does, decided at `freeze()` and recorded in the
plan.

**Collection injection** gathers several providers under one parameter. A
parameter annotated `list[Handler]` receives every member of a collection
declared with `Container.collect(Handler, [...])`. The declaration is what gates
it: members stay bound under their own keys, so an accidental duplicate
registration still raises `DuplicateProviderError`, and the collection itself
occupies a distinct key that nothing else can claim twice.

Both deliverables pass through `ParamSpec` and the unsatisfied-parameter path,
which is why they ship together. The cycle also closes the finding the roadmap
carries from Step 2 under `Chain divergence on a bound-and-defaulted
intermediate`, because that finding is about the same code and its fix changes
the same error text.

## What changes for an existing graph

Three behaviours change for graphs that already freeze today, and each is
deliberate.

| Before | After |
| --- | --- |
| A `T \| None` parameter raises `InvalidProviderError` at `freeze()`. | It is an optional dependency. |
| A `list[T]` parameter, or a factory returning `list[T]`, raises `InvalidProviderError`. | `list[T]` is a valid provider key. |
| A missing-provider chain stops at the nearest requiring provider, skipping bound-and-defaulted intermediates. | The chain runs from the root, matching what `explain()` already prints. |

The first two are widenings: a graph that froze before still freezes. The third
changes the text of an existing error message, which is why it belongs here
rather than in a diagnostics release.

## Measurements

Four questions were measured rather than assumed, against mypy at default
settings and `basedpyright --strict`.

**A parameterised generic written at a call site is already a valid
`ProviderKey`.** `list[Handler]` in expression position has the static type
`type[list[Handler]]`, which is assignable to the `type[object]` member of the
existing alias. Nothing a consumer writes needs the alias to change.

**Building that key from a runtime value does need the alias to change.**
`list[element]`, where `element` is a parameter rather than a literal type, is
`error: Variable "element" is not valid as a type [valid-type]` under mypy. The
construction that works is `types.GenericAlias(list, (element,))`, which
produces an object equal to, and hashing as, `list[Handler]` — same type, same
equality, same hash. Its static type is `GenericAlias`, so `ProviderKey` gains
one union member:

```python
type ProviderKey = type[object] | Token[object] | str | GenericAlias
```

This is the widening Step 2's spec anticipated when it promoted `ProviderKey`
to the public surface: adding a member to a union is compatible with every
consumer already written against it. It widens what may be *passed*;
`is_provider_key` remains the validation, and it still admits only `list[X]`
over a key. `explain(dict[str, int])` therefore type-checks and raises
`MissingProviderError` for an invalid key type, which is the same treatment any
other unusable value gets.

**`resolve` needs no new overload.** `resolve[T](key: type[T] | Token[T]) -> T`
already infers `list[Handler]` from `resolve(list[Handler])`. So do
`__getitem__`, `aresolve`, `override`, and `injected`. A dedicated
`type[list[T]] -> list[T]` overload was written and also works, but it is
redundant and is not added: a second overload that never changes an inferred
type is surface with no contract behind it.

**`Optional[X]` and `X | None` are different objects.** `X | None` has
`get_origin` of `types.UnionType`; `typing.Optional[X]` has `typing.Union`.
Detection handles both. `list[X]` and `typing.List[X]` both have `get_origin`
of `list`, so the collection key needs no such special case — but they are not
equal to each other, which cycle 3 owns.

## Public surface

No signature changes. Three additions and one widening.

| Symbol | Role |
| --- | --- |
| `BindingCollector.collect` | Declares a collection and its members. |
| `ProviderShape.COLLECTION` | The shape of a collection node. |
| `ProviderKey` | Gains a `GenericAlias` member, so a key built at runtime has a type. |
| `GraphEdge.optional`, `GraphEdge.has_default` | What a consumer needs to tell why an edge is unsatisfied. |

```python
def collect(
    self,
    element: ProviderKey,
    members: Sequence[ProviderKey],
    *,
    tag: str | None = None,
) -> Self: ...
```

`collect` registers a provider under the key `list[element]`, whose value is a
list of the resolved `members` in the order given. It takes no `scope`: like an
alias, a collection node caches nothing, and each member keeps its own lifetime,
cache entry, and teardown.

Members are given as provider keys, not as tagged identities. depin's idiom is
one key per implementation — `bind(EmailHandler)`, `bind(SmsHandler)`,
`collect(Handler, [EmailHandler, SmsHandler])` — and a member form carrying a
tag is a compatible widening of the element type if a case for it appears.

## Data model

### Optional dependencies

`ParamSpec` gains one field:

```python
@dataclass(frozen=True, slots=True)
class ParamSpec:
    name: str
    key: ProviderKey
    tag: str | None
    has_default: bool
    default: object
    optional: bool = False
```

`AnnotatedMeta` gains the same flag. `extract_annotated_meta` strips
`Annotated`, then normalises the base:

- `T | None` and `Optional[T]` reduce to `T` with `optional=True`;
- a union with no `None` member is left alone, and `as_provider_key` rejects it;
- a union of two or more non-`None` members plus `None` is left alone and
  rejected too, because stripping `None` leaves no single key.

The flag is orthogonal to the parameter's key, so
`Annotated[str | None, Named(db_url)]` is an optional dependency on a token.

### Collections

```python
@dataclass(frozen=True, slots=True)
class CollectionBinding:
    element: ProviderKey
    members: tuple[ProviderKey, ...]
```

`CollectionBinding` joins `ValueBinding`, `FrameBinding`, and `AliasBinding` as
a marker source on `BindRecord.source`, with `is_collection_binding` as its
guard. `_record_to_spec` turns it into one spec:

```python
ProviderSpec(
    key=collection_key(binding.element),
    tag=rec.tag,
    source=binding,
    scope=rec.scope,
    shape=ProviderShape.COLLECTION,
    needs_async=False,
    params=tuple(
        ParamSpec(
            name=collection_param(index),
            key=as_provider_key(member),
            tag=None,
            has_default=False,
            default=None,
            optional=False,
        )
        for index, member in enumerate(binding.members)
    ),
)
```

`rec.scope` reads as `Scope.TRANSIENT` here: `BindingCollector.collect` always
records the binding with that scope, and `CollectionBinding` is not exported,
so no caller can construct one with another.

`collection_key(element)` is `GenericAlias(list, (element,))`, which is the
`list[element]` a consumer writes by hand — equal to it, hashing as it, and of
the same type — built in the one form that type-checks from a runtime value.
`collection_param(index)` is
`f'member_{index}'`; the names must be distinct because they are dictionary keys
in the resolved arguments, and they are what `explain()` prints and what `dot()`
and `mermaid()` write on each edge.

A collection is a node whose parameters are its members. Everything that follows
is a consequence, in the same way it was for an alias in cycle 1.

## Semantics

### Optional dependencies

At `freeze()`, an optional parameter whose key is unbound is not a missing
provider. At resolution, it receives `None`.

An explicit default wins over optionality. For
`cache: Cache | None = FALLBACK` with `Cache` unbound, the parameter is omitted
from the resolved arguments and Python applies `FALLBACK`; depin never
substitutes `None` for a value the author wrote. The two orderings are
observationally identical only when the default is itself `None`.

An optional parameter whose key **is** bound resolves normally, and its edge
participates in ordering, cycle detection, and captive validation like any
other. Optionality changes what happens when a binding is absent; it changes
nothing when one is present.

### Collections

| Property | How it holds |
| --- | --- |
| An accidental duplicate still raises | Members stay bound under their own keys. A collection occupies `list[E]`, which no ordinary binding claims. |
| Two collections over one element are rejected | `_check_duplicates` sees `(list[E], tag)` like any other identity. |
| An unbound member is rejected at `freeze()` | It is an unsatisfied required parameter of the collection node. |
| A repeated member is rejected at `freeze()` | Checked when the record is built; a member listed twice is a mistake, and the two entries would resolve to one instance. |
| Captive validation covers every member | The node is transient, so `_check_captive` walks through it to each member. A singleton consuming `list[Handler]` where one handler is scoped is captive. |
| Async propagates | `_with_async_flags` marks the collection when any member is async, so `resolve` rejects it and names `list[E]`. |
| Cycles are rejected | A member that depends on the collection is an ordinary cycle for `_toposort`. |
| Order is the declaration order | `members` is a sequence and the parameters are built from it in order, so the resolved list is reproducible. |
| A fresh list per resolution | The node is transient, so no caller receives a list another caller can mutate. The members themselves keep their own caches, so the elements are shared. |
| An empty collection is legal | `collect(Handler, [])` resolves to `[]`. A plugin point with nothing plugged in is a real state, not an error. |

### The carried Step 2 finding

`_collect_missing` skips a parameter that carries a default, including for
traversal, while `_deepest_requirement` in `_core/render.py` traverses every
satisfied edge. Measured on the current tree, for a graph where an intermediate
is both bound and defaulted:

```
freeze  : no provider for C (required by B.c; resolution chain: B -> C)
explain : no provider for C (required by B.c; resolution chain: A -> B -> C)
```

The wording and the owner agree; only the chain differs, and `explain()`'s is
the more informative one. `_collect_missing` is changed to decide on the
binding, not on the default: a parameter with no binding is skipped when it has
a default or is optional, and a parameter **with** a binding is always
traversed. The two walks then report the same chain by construction, and the
existing chain-consistency test is extended to the bound-and-defaulted case.

This changes the text of existing `MissingProviderError` messages, which is the
reason the roadmap routes it here. Its label there is corrected from Step 6 to
Step 3 in cycle 1.

## Errors

No exception type is added.

| Call | Behaviour |
| --- | --- |
| A parameter annotated `X \| Y`, or `X \| Y \| None` | `InvalidProviderError`, naming the union and pointing at `T \| None`, `Tag`, or `Named`. |
| `collect` with a member bound nowhere | `MissingProviderError` at `freeze()`, naming the collection as the requiring owner. |
| `collect` listing one member twice | `DuplicateProviderError` at `freeze()`, naming the member. |
| Two `collect` calls over one element and tag | `DuplicateProviderError` at `freeze()`, naming `list[E]`. |
| `collect` with an element or member that is not a valid key | `InvalidProviderError`. |
| A singleton consuming a collection with a scoped member | `CaptiveDependencyError`, with the collection in the chain. |
| `resolve` on a collection with an async member | `AsyncInSyncContextError`, naming `list[E]`. |

`as_provider_key` gains a union-specific message, because the old one — `a key
must be a class, a Token, or a string` — is now wrong about `T | None`, which
*is* accepted:

```
cannot use Cache | Logger as a provider key: depin reads `T | None` as an
optional dependency, but a union of two or more providers names no single key.
Annotate the parameter with the one you want, or select it with
Annotated[..., Tag(...)].
```

`construct` reads a collection's members through a guard in `_core/typeguards.py`
rather than indexing the resolved arguments directly, so a defect raises
`InvalidProviderError` naming the provider instead of a bare `KeyError`.

## Key rendering

`fmt_key` renders a class by `__qualname__` and everything else by `repr`, so
`list[Handler]` currently prints as `list[app.handlers.Handler]` — module-
qualified, unlike every other key in every message. It gains one branch: a
`types.GenericAlias` renders as its origin followed by its arguments, each
through `fmt_key`, giving `list[Handler]`.

The branch is gated on `types.GenericAlias` specifically, not on `get_origin`
being non-`None`, so a union never takes it — `X | None` must keep printing as
`X | None` in the message above.

## Module layout

No new module. Both features land where each concern already lives.

| Module | Change |
| --- | --- |
| `_core/spec.py` | `ParamSpec.optional`; `ProviderShape.COLLECTION`; the `ProviderKey` widening; `CollectionBinding`, `is_collection_binding`, `collection_key`, `collection_param`; the `fmt_key` branch. |
| `_core/introspect.py` | `AnnotatedMeta.optional` and the union normalisation. |
| `_core/providers.py` | The collection branch of `_record_to_spec`; `optional` on extracted parameters; the union message in `as_provider_key`. |
| `_core/bindings.py` | `BindingCollector.collect`. |
| `_core/typeguards.py` | `is_provider_key` admits `list[X]`; `as_collection_members`. |
| `_core/construct.py` | The `COLLECTION` case of `sync`. |
| `_core/graph.py` | `_any_unsatisfied` and `_collect_missing` honour `optional`; `_collect_missing` traverses bound-and-defaulted parameters. |
| `_core/frozen.py` | An unbound optional parameter resolves to `None`, in both the sync and the async path. |
| `_core/diagnostics.py` | `GraphEdge.optional` and `GraphEdge.has_default`. |
| `_core/render.py` | `(unbound, optional)` beside `(unbound, default)`. |
| `_core/container.py` | `freeze()`'s `Raises:` covers the new triggers; the `Container` docstring lists `collect()`. |

## Verification

- `tests/unit/test_optional.py`: bound and unbound; an explicit non-`None`
  default winning over optionality; `Optional[T]` alongside `T | None`;
  optional on a `Token` through `Named`; optional with a `Tag`; an optional
  parameter of a scoped provider; an unbound optional in an async provider.
- `tests/unit/test_collections.py`: order; identity of members against direct
  resolution; an empty collection; a fresh list per resolution with shared
  elements; a tagged collection; a collection consumed by another provider;
  a collection whose member is an alias; teardown running once per member.
- `tests/unit/test_graph_validation.py`: every row of the Errors table.
- `tests/unit/test_graph_render.py`: `(unbound, optional)`; a collection node
  and its `member_N` edges in all three renderers; `fmt_key` over `list[X]`.
- `tests/unit/test_graph_render.py`: the chain-consistency test extended to a
  bound-and-defaulted intermediate, asserting `freeze()` and `explain()` produce
  the same string. Existing chain assertions that the fix lengthens are updated,
  and the change is called out in the plan so it is not mistaken for a
  regression.
- `tests/unit/test_graph_properties.py`: the generative model gains optional
  parameters and collections, so the existing invariants cover them. This also
  closes the finding the roadmap carries from Step 3 about generated aliases
  never being consumed, by making generated nodes consume them.
- `tests/typing/test_conformance.py`: `assert_type(di.resolve(list[H]), list[H])`,
  the same for `di[list[H]]` and `injected(list[H])`, and `collect` returning
  `Self`. These pin the measurement this design rests on.
- `benchmarks/`: resolving a collection of 10 and 100 members, and `freeze()`
  over a graph of optional parameters.
- `examples/optional_dependencies/main.py` and `examples/collections/main.py`,
  both listed in `examples/README.md` and executed by
  `tests/integration/test_examples.py`.
- `tests/integration/test_fastapi_ext.py`: a route resolving a collection, and a
  route whose provider takes an unbound optional.
- `docs/guide/resolution.md`, a new page covering both concepts with `pycon`
  doctests, added to the `mkdocs.yml` nav. It is where cycle 3's generic keys
  will land too.
- The mutation gate at 95% covers every changed module.

## Acceptance criteria

- Each addition is validated at `freeze()`, not at resolution time.
- An accidental duplicate registration still raises `DuplicateProviderError`.
- A collection binding participates in captive-dependency validation like any
  other edge.
- `freeze()` and `explain()` report the same chain for a bound-and-defaulted
  intermediate.
- The five gates and `mkdocs build --strict` pass with no warnings or waivers.
- Coverage over `depin/` stays at or above 95%.
- No regression against the benchmark baseline.

## Out of scope

| Item | Reason |
| --- | --- |
| `set[T]`, `tuple[T, ...]`, `Sequence[T]` collections | One container type is enough to establish the mechanism. Each extra origin is a permanent key shape to support at 1.0, and `list` is what the roadmap names. |
| A member carrying a tag | depin's idiom is one key per implementation. Widening the `members` element type later is compatible. |
| Merging collections across registries | Two `collect` calls over one element is a `DuplicateProviderError` by design; a merging form would need its own conflict rule, and no consumer is identified. |
| `injected(...)` growing an optional form | `injected` takes an explicit key and validates it at decoration. "Optional" there means not injecting at all. |
| Generic keys beyond `list[X]` | Cycle 3. `is_provider_key` admits exactly `list[X]` where `X` is itself a key; `Repo[User]` stays rejected. |
| An overload for `resolve(list[T])` | Measured to be redundant: inference already produces `list[T]`. |
