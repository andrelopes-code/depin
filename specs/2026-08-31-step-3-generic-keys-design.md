# Step 3, cycle 3 — generic keys: design

Date: 2026-08-31
Baseline: 0.9.0 at `ec65dcb`
Target: 0.10.0
Status: approved, pending implementation plan

## Goal

Make a parameterised generic a provider key. `Repo[User]` and `Repo[Order]` become two
bindings, distinguished the way every other key is: by equality.

```python
di = Container().bind(SqlRepo, provides=Repo[User]).bind(OrderRepo, provides=Repo[Order]).freeze()
di.resolve(Repo[User])
```

Cycle 2 admitted exactly one generic key, `list[X]`, because collection injection needed it and
nothing else was ready. This cycle removes that restriction and adds the three things the wider
surface needs: normalisation, rendering, and registration.

It also closes the two items the roadmap routes here, and one defect found while measuring.

## The roadmap's premise for this cycle is false

The roadmap gives generic keys their own release because "`resolve[T](key: type[T]) -> T`
cannot express `Repo[User]`, since a parameterised generic alias is not a `type`". The second
half is true at runtime — `isinstance(Repo[User], type)` is `False` — and the conclusion does
not follow. Measured on the 0.9.0 tree, under mypy at default settings and
`basedpyright --strict`, all four of these pass:

```python
assert_type(di.resolve(Repo[User]), Repo[User])
assert_type(di[Repo[User]], Repo[User])
assert_type(di.resolve(Reader[User]), Reader[User])  # a generic Protocol
assert_type(di.resolve(list[Repo[User]]), list[Repo[User]])
```

In expression position `Repo[User]` has the static type `type[Repo[User]]`, which satisfies the
existing `type[T]` parameter and solves `T` to `Repo[User]`.

**No signature changes, and no overload.** This cycle is runtime and diagnostic work. The four
assertions above become conformance tests, so the claim is checked on every build rather than
believed.

## Measurements

Four questions were measured rather than assumed.

**Normalisation must re-subscript the origin.** `typing.List[User]` and `list[User]` are not
equal, so a provider annotated with one and a binding registered under the other would not
match. Rebuilding through `types.GenericAlias(origin, args)` fixes that for `list` — but
`types.GenericAlias(Repo, (User,)) != Repo[User]` for a user-defined PEP 695 generic, and the
same for a generic `Protocol`, even though both spell identically and differ only in hash and
equality. Re-subscripting the origin, `origin[args]`, preserves equality and hash in every case
measured, builtin and user-defined alike. That is the form this cycle uses, and cycle 2's
`collection_key` is migrated onto it — it is correct today only because its origin is always
the builtin `list`.

**A union's origin is a class, so unions must be excluded by name.** `X | None` has
`get_origin` of `types.UnionType`, which is itself a class, so a rule of "the origin is a
class" would admit it. `typing.Optional[X]` has `get_origin` of `typing.Union`, which is not a
class, so the two spellings need different treatment and both must be rejected here —
optionality is a parameter-position feature, decided in cycle 2, not a key.

**`Callable` and `tuple[X, ...]` fall out without a special case.** `Callable[[int], str]`
carries a `list` among its arguments and `tuple[User, ...]` carries `Ellipsis`. Requiring every
argument to be itself a provider key excludes both. `Literal['a']` has a non-class origin.

**An async factory's return annotation is already the value type.** See the defect below.

## Public surface

No new symbol, no signature change. Three widenings.

| Symbol | Change |
| --- | --- |
| `is_provider_key` | Admits any parameterised generic whose origin is a class other than `types.UnionType`, and whose every argument is itself a provider key. Replaces cycle 2's `list[X]`-only gate. |
| `ProviderKey` | Its `GenericAlias` member widens to cover `typing`'s alias form as well, so a key written `Repo[User]` has a type. |
| `provides` | Accepts a parameterised generic, so `@provides(Repo[User])` works. |

`ProviderKey` is a union, and adding to a union is compatible with every consumer already
written against it — the same argument Step 2 made when it promoted the alias, and cycle 2 made
when it added `GenericAlias`.

## Semantics

| Property | How it holds |
| --- | --- |
| `Repo[User]` and `Repo[Order]` are different keys | They compare and hash differently, and `by_key` is a plain dictionary. |
| `Repo` and `Repo[User]` are different keys | The bare class and the parameterisation are unequal. Binding both is legal and means two providers. |
| `typing.List[X]` and `list[X]` are one key | Every key is normalised on the way into a `ProviderSpec`, so both reach the same identity. |
| A generic `Protocol` is a key | `Reader[User]` behaves exactly as `Repo[User]` does; depin never instantiates a key. |
| Nesting works | `Repo[Repo[User]]` normalises recursively, and `list[Repo[User]]` is an ordinary collection key. |
| A generic key is an ordinary node | Duplicates, missing dependencies, cycles, captive validation, async propagation, aliases, and collections all apply unchanged, because none of them inspects the shape of a key. |
| `Repo[User]` does not satisfy `Repo[object]` | depin matches keys by equality, never by assignability. Stated as a limitation, not a bug — see Out of scope. |

Normalisation happens in `as_provider_key`, which every key already passes through: a
provider's inferred key, an explicit `provides=`, a parameter's annotation, an alias key and
target, and a collection's element and members. A key that needs no normalisation is returned
unchanged, so the common path is one `get_origin` call.

## The defect this cycle fixes

`_UNWRAP_SHAPES` in `_core/providers.py` includes `ProviderShape.ASYNC_FUNCTION`, so
`_resolve_key` unwraps the first type argument out of an async factory's return annotation.
That is wrong: `async def f() -> X` already means the awaited value is `X`, and there is nothing
to unwrap. It is right for the other four members — `Generator[X]`, `AsyncIterator[X]`,
`AbstractContextManager[X]` and their kin genuinely wrap the value.

Measured on the 0.9.0 tree:

```
async def make() -> list[Handler]    keyed  Handler          wrong
async def make() -> Repo[User]       keyed  User             wrong
def make() -> list[Handler]          keyed  list[Handler]    right
```

The defect was latent until cycle 2. Before it, a parameterised return annotation raised at
`as_provider_key`, so the unwrap only ever saw annotations with no origin, where it does
nothing. Cycle 2 made `list[X]` a key and activated it. This cycle removes `ASYNC_FUNCTION`
from `_UNWRAP_SHAPES`.

No correct graph changes meaning: the only annotations affected are parameterised ones on an
async factory, which raised before 0.9.0 and are keyed wrongly in it.

## The two items carried here

**Forward references to a key that is only registered indirectly.** `_registered_classes`
builds the namespace annotations resolve against from records whose `source` is a class, so a
class registered only as an alias key or target, only through `scope_value`, or only as a
collection element or member never enters it. A provider naming that class as a string forward
reference then fails at `freeze()` with "bind the class so depin can resolve the forward
reference" — advice that is wrong for a `Protocol`, because binding it would register a bogus
provider rather than resolve anything. This cycle widens the namespace to include every class
reachable from a record, whatever role it plays in it, and corrects the advice.

**The union message reached from a non-parameter position.** Cycle 2 split
`as_provider_key`'s union message in two and fixed the single-member branch for callers outside
parameter position. The two-or-more branch still says "Annotate the parameter with the one you
want", which has no meaning when the union is an alias target or a collection element. It gets
the same treatment as its sibling.

## Errors

No exception type is added.

| Call | Behaviour |
| --- | --- |
| A key whose origin is not a class (`Literal`, `typing.Optional`) | `InvalidProviderError`, naming the value and what a key may be. |
| A key with an argument that is not itself a key (`Callable[[int], str]`, `tuple[X, ...]`) | `InvalidProviderError`, naming the offending argument. |
| `X \| None` or `X \| Y` as a key | The two union messages, each true of the position it was reached from. |
| `@provides(Repo[User])` | Accepted. |
| `@provides(42)` | `InvalidProviderError`, as now. |

## Key rendering

`fmt_key` renders a `types.GenericAlias` as `origin[args]` today, gated on that concrete class,
so `Repo[User]` — a `typing._GenericAlias` — falls through to `repr` and prints module-qualified
as `app.repos.Repo[app.models.User]`, unlike every other key in every message. The gate widens
to any parameterised generic, giving `Repo[User]`, with each argument rendered through `fmt_key`
so nesting stays qualified-name-consistent.

The union guard stays: a union must keep printing as `X | None`, and its origin is a class.

## Module layout

No new module.

| Module | Change |
| --- | --- |
| `_core/typeguards.py` | `is_provider_key` widens; `is_collection_key` becomes a use of the general predicate. |
| `_core/spec.py` | `ProviderKey`'s alias member widens; `fmt_key`'s gate widens; `collection_key` moves onto the subscript form. |
| `_core/providers.py` | Normalisation in `as_provider_key`; `ASYNC_FUNCTION` leaves `_UNWRAP_SHAPES`; `_registered_classes` widens; the second union message is corrected. |
| `_core/markers.py` | `provides` accepts a parameterised generic. |

`graph.py`, `frozen.py`, `diagnostics.py`, `render.py`, `bindings.py`, `construct.py`, and
`scope.py` are not touched. None of them inspects the shape of a key, which is why a generic
key is an ordinary node.

## Verification

- `tests/unit/test_generic_keys.py`: `Repo[User]` against `Repo[Order]`; `Repo` against
  `Repo[User]`; a generic `Protocol`; nesting; `typing.List[X]` and `list[X]` reaching one
  binding; a generic key as a parameter annotation, as `provides=`, as an alias key and target,
  and as a collection element and member; `Repo[User]` and `Repo[object]` staying distinct.
- `tests/unit/test_providers.py`: the async-unwrap fix, as a red-then-green pair — an async
  factory returning `list[Handler]` keyed `list[Handler]`, and one returning `Repo[User]` keyed
  `Repo[User]`; the four shapes that still unwrap, unchanged.
- `tests/unit/test_providers.py`: the forward-reference fix for a class registered only as an
  alias key, only through `scope_value`, and only as a collection element.
- `tests/unit/test_spec.py`: `fmt_key` over `Repo[User]`, over `Repo[Repo[User]]`, and still
  leaving a union alone; normalisation preserving equality and hash for a builtin origin and a
  user-defined one, which is the measurement the design rests on.
- `tests/unit/test_graph_validation.py`: every row of the Errors table.
- `tests/unit/test_graph_render.py`: a generic key in the tree and in both exports.
- `tests/unit/test_graph_properties.py`: the generative model gains parameterised keys.
- `tests/typing/test_conformance.py`: the four `assert_type` cases above.
- `benchmarks/`: `freeze()` over a graph of generic keys, and normalisation on the hot path.
- `examples/generic_keys/main.py`, listed in `examples/README.md` and executed by
  `tests/integration/test_examples.py`.
- `tests/integration/test_fastapi_ext.py`: a route resolving a generic key.
- `docs/guide/resolution.md` gains a generic-keys section with `pycon` doctests.
- The mutation gate at 95% covers every changed module.

## Acceptance criteria

- `Repo[User]` and `Repo[Order]` resolve to different providers, validated at `freeze()`.
- `typing.List[X]` and `list[X]` are one key.
- An async factory with a parameterised return annotation is keyed by that annotation.
- A class registered only as an alias key, a `scope_value`, or a collection element resolves a
  forward reference naming it.
- The four conformance assertions hold under both checkers.
- The five gates and `mkdocs build --strict` pass with no warnings or waivers.
- Coverage over `depin/` stays at or above 95%, and `depin/` gains no suppression.
- No regression against the benchmark baseline.

## Out of scope

| Item | Reason |
| --- | --- |
| Variance and assignability | `Repo[User]` will not satisfy a parameter annotated `Repo[object]`. depin matches keys by equality everywhere; introducing assignability for one key shape would make resolution depend on a subtyping relation the container cannot see at runtime for a `Protocol`. |
| `Callable[...]` and `Literal[...]` keys | Neither is a class to key by, and `Token` already names a callable or a value. Both are rejected by the general rule with no special case. |
| An unparameterised `TypeVar` in a key | `Repo[T]` with `T` unbound has no runtime identity a consumer could resolve. |
| Partial or open generic matching | Binding `Repo` and expecting `Repo[User]` to find it. That is assignability again, in a second guise. |
| `set[X]` and `tuple[X, ...]` collections | Still cycle 2's decision, unchanged: one container type establishes the mechanism, and each extra origin is a permanent key shape at 1.0. |
