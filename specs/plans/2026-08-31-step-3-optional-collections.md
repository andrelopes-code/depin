# Step 3, cycle 2 — optional dependencies and collection injection: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a `T | None` parameter resolve to `None` when unbound instead of failing at `freeze()`, make `list[Handler]` resolve every member of a declared collection, and close the chain divergence the roadmap carries from Step 2 — for the 0.9.0 milestone.

**Architecture:** No new module. Optionality is one flag carried from the annotation through `AnnotatedMeta` into `ParamSpec`, honoured at three sites: `_any_unsatisfied`, `_collect_missing`, and parameter resolution. A collection is a `Scope.TRANSIENT` node of the new shape `ProviderShape.COLLECTION`, registered under the key `list[element]`, whose parameters are its members — the same construction that made an alias compose in cycle 1, widened from one parameter to N. Because `list[Handler]` written at a call site is statically already a `ProviderKey` and `resolve` already infers `list[Handler]` from it, no signature changes. Two things do widen: the runtime gate `is_provider_key`, narrowly, and the `ProviderKey` alias by one `GenericAlias` member, because building the key from a runtime value is a mypy `valid-type` error in the `list[element]` form and must go through `GenericAlias(list, (element,))`.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, Hypothesis, mutmut 3.7, pytest-benchmark, mkdocs-material with mkdocstrings, uv.

**Spec:** `specs/2026-08-31-step-3-optional-collections-design.md`

## Global constraints

Every task inherits these requirements from `AGENTS.md`, the approved roadmap, and the spec.

- The core keeps zero runtime dependencies. Nothing here adds a package to `[project.dependencies]` or to any dependency group.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `typing.Any`, `typing.cast`, `# type: ignore`, or `# pyright: ignore`. `depin/` carries exactly three suppressions today — `frozen.py:116`, `frozen.py:139`, `markers.py:129` — and must carry exactly those three when this cycle ends.
- Every exception raised by library code inherits `DepinError`. No bare `KeyError`, `TypeError`, `ValueError`, or `assert` in `depin/`.
- Data structures are `@dataclass(frozen=True, slots=True)`.
- New behaviour in `depin/_core/` is developed test-first: the failing test is written and observed failing before the implementation.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery.
- Public API additions carry Google-style docstrings that omit types from `Args:` / `Returns:` and include a doctest `Example:`. Doctests run in the default `pytest` invocation.
- `fmt_key` renders a class by `__qualname__`, so a class declared inside a test function appears as `test_x.<locals>.Name`. Text assertions must account for that.
- `basedpyright --strict` has `reportUnnecessaryIsInstance` and `reportImplicitOverride` enabled. `mypy --strict` additionally has `warn_unreachable` and the `redundant-expr` code, so an `is` comparison between two statically unrelated classes raises `comparison-overlap`; bind such operands to `object`-typed locals rather than suppressing. `ruff` rejects unused imports.
- Coverage over `depin/` stays at or above 95%; it is 98.56% at the 0.8.0 baseline. The mutation gate stays at 95% killed and is enforced by CI, not locally.
- Before every commit, run in this exact order:

  ```bash
  uv run ruff format
  uv run ruff check
  uv run basedpyright
  uv run mypy
  uv run pytest
  ```

- Any commit that changes prose also runs `uv run --group docs mkdocs build --strict` after the five gates.
- `uv run ruff format` reformats Python inside markdown fences, including under `specs/`, and CI runs `ruff format --check` over the whole repository. Never revert that reformatting.
- Commits are focused, conventional, at most 72 characters in the subject, and contain no attribution or automation language.

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `depin/_core/introspect.py` | `AnnotatedMeta.optional`; union normalisation. | 1 |
| `depin/_core/spec.py` | `ParamSpec.optional`; then the `ProviderKey` widening, the collection data model, and the `fmt_key` branch. | 1, 4 |
| `depin/_core/providers.py` | `optional` on extracted parameters; the union message; the collection branch. | 1, 4 |
| `depin/_core/graph.py` | `_any_unsatisfied` honours `optional`; `_collect_missing` honours it and traverses bound-defaulted parameters. | 1, 3 |
| `tests/unit/test_introspect.py` | Union normalisation at the metadata level. | 1 |
| `tests/unit/test_optional.py` | Optional dependencies end to end. | 1, 2 |
| `depin/_core/frozen.py` | An unbound optional parameter resolves to `None`, sync and async. | 2 |
| `tests/unit/test_graph_render.py` | Chain consistency over a bound-and-defaulted intermediate; the new render forms. | 3, 6 |
| `depin/_core/bindings.py` | `BindingCollector.collect`. | 4 |
| `depin/_core/typeguards.py` | `is_provider_key` admits `list[X]`; `as_collection_members`. | 4 |
| `depin/_core/construct.py` | The `COLLECTION` case of `sync`. | 4 |
| `tests/unit/test_collections.py` | Collections end to end. | 4 |
| `tests/unit/test_spec.py` | The shape members, the marker source, `fmt_key` over `list[X]`. | 4 |
| `tests/unit/test_graph_validation.py` | Every row of the spec's Errors table. | 5 |
| `depin/_core/diagnostics.py` | `GraphEdge.optional` and `GraphEdge.has_default`. | 6 |
| `depin/_core/render.py` | `(unbound, optional)` beside `(unbound, default)`. | 6 |
| `tests/unit/test_graph_view.py` | The two new edge fields. | 6 |
| `tests/unit/test_graph_properties.py` | Optional parameters and collections in the generative model. | 6 |
| `tests/typing/test_conformance.py` | `assert_type` over `list[H]` keys and `collect`. | 6 |
| `depin/_core/container.py` | `freeze()`'s `Raises:`; the `Container` docstring. | 7 |
| `docs/guide/resolution.md` | The narrative page for both concepts. | 7 |
| `mkdocs.yml` | Nav entry for it. | 7 |
| `examples/optional_dependencies/` | Runnable program. | 7 |
| `examples/collections/` | Runnable program. | 7 |
| `examples/README.md` | Lists both. | 7 |
| `tests/integration/test_examples.py` | Executes both. | 7 |
| `tests/integration/test_fastapi_ext.py` | A route resolving a collection; a route with an unbound optional. | 7 |
| `benchmarks/test_resolution.py` | Collection resolution at two sizes. | 7 |
| `specs/evidence/2026-08-31-step-3-optional-collections.md` | The measured evidence. | 8 |

---

### Task 1: Optional dependencies reach the plan

A `T | None` parameter is rejected today by `as_provider_key`. This task makes it a key of `T` carrying an `optional` flag, and makes `freeze()` stop treating an unbound optional as missing. Resolution still ignores the flag; Task 2 adds that.

**Files:**

- Modify: `depin/_core/introspect.py`
- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/providers.py`
- Modify: `depin/_core/graph.py`
- Modify: `tests/unit/test_introspect.py`
- Create: `tests/unit/test_optional.py`

**Interfaces:**

- Produces: `AnnotatedMeta.optional: bool` in `depin._core.introspect`.
- Produces: `ParamSpec.optional: bool = False` in `depin._core.spec`.

- [ ] **Step 1: Write the failing metadata tests**

Append to `tests/unit/test_introspect.py`:

```python
def test_an_optional_annotation_reduces_to_its_single_key() -> None:
    class Cache: ...

    meta = extract_annotated_meta(Cache | None)
    assert meta.base is Cache
    assert meta.optional


def test_the_typing_optional_spelling_reduces_the_same_way() -> None:
    class Cache: ...

    meta = extract_annotated_meta(Optional[Cache])
    assert meta.base is Cache
    assert meta.optional


def test_an_optional_annotation_keeps_its_annotated_metadata() -> None:
    class Cache: ...

    meta = extract_annotated_meta(Annotated[Cache | None, Tag('primary')])
    assert meta.base is Cache
    assert meta.optional
    assert meta.tag == 'primary'


def test_a_union_without_none_is_not_optional() -> None:
    class Cache: ...

    class Logger: ...

    meta = extract_annotated_meta(Cache | Logger)
    assert not meta.optional
    assert meta.base == Cache | Logger


def test_a_union_of_several_providers_and_none_is_not_reduced() -> None:
    class Cache: ...

    class Logger: ...

    meta = extract_annotated_meta(Cache | Logger | None)
    assert not meta.optional
    assert meta.base == Cache | Logger | None


def test_a_plain_annotation_is_not_optional() -> None:
    class Cache: ...

    assert not extract_annotated_meta(Cache).optional
```

Add `Optional` to the file's `typing` import, and `Annotated` and `Tag` if it does not already have them.

The last-but-one case is deliberate: stripping `None` from `Cache | Logger | None` leaves two candidates and no single key, so the annotation stays as written and `as_provider_key` reports it.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_introspect.py -k optional`
Expected: FAIL, `AttributeError: 'AnnotatedMeta' object has no attribute 'optional'`.

- [ ] **Step 3: Carry the flag on the metadata**

In `depin/_core/introspect.py`, add the field to `AnnotatedMeta`, after `named`:

```python
    optional: bool
```

and add, below `_split_annotated`:

```python
def _reduce_optional(annotation: object) -> tuple[object, bool]:
    """Read ``T`` out of ``T | None``, reporting whether the union admitted None.

    Both spellings reach here: ``T | None`` carries a `types.UnionType` origin and
    `typing.Optional[T]` carries `typing.Union`. A union that names no ``None``,
    or that names two or more providers besides it, is returned unchanged — there
    is no single key to reduce it to, and `as_provider_key` reports it.
    """
    if get_origin(annotation) not in (UnionType, Union):
        return annotation, False
    members = tuple(arg for arg in get_args(annotation) if arg is not NoneType)
    if len(members) == len(get_args(annotation)) or len(members) != 1:
        return annotation, False
    return members[0], True
```

Add `from types import NoneType, UnionType` and `Union` to the `typing` import at the top of the module, keeping both sorted.

- [ ] **Step 4: Apply the reduction where the base is read**

In `depin/_core/introspect.py`, change the tail of `extract_annotated_meta` from

```python
    return AnnotatedMeta(base=base, token=token, tag=tag, named=named)
```

to

```python
    reduced, optional = _reduce_optional(base)
    return AnnotatedMeta(base=reduced, token=token, tag=tag, named=named, optional=optional)
```

- [ ] **Step 5: Run the metadata tests to verify they pass**

Run: `uv run pytest tests/unit/test_introspect.py`
Expected: PASS.

- [ ] **Step 6: Write the failing freeze-level tests**

Create `tests/unit/test_optional.py`:

```python
"""A `T | None` parameter resolves to the bound provider, or to None when unbound."""

from typing import Annotated, Optional

import pytest

from depin import Container, Named, Scope, Tag, Token
from depin.errors import InvalidProviderError


class Cache:
    def get(self) -> str:
        return 'cached'


def test_an_unbound_optional_dependency_freezes() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Service).freeze()
    assert di.graph().node(Service).dependencies[0].key is Cache


def test_a_union_of_two_providers_is_still_rejected() -> None:
    class Logger: ...

    class Service:
        def __init__(self, dep: Cache | Logger) -> None:
            del dep

    with pytest.raises(InvalidProviderError, match='names no single key'):
        _ = Container().bind(Service).freeze()


def test_a_union_of_two_providers_and_none_is_still_rejected() -> None:
    class Logger: ...

    class Service:
        def __init__(self, dep: Cache | Logger | None) -> None:
            del dep

    with pytest.raises(InvalidProviderError, match='names no single key'):
        _ = Container().bind(Service).freeze()
```

- [ ] **Step 7: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_optional.py`
Expected: FAIL — the first with `InvalidProviderError: cannot use ... as a provider key`, the other two with the old wording, which the `match` rejects.

- [ ] **Step 8: Carry the flag on the parameter**

In `depin/_core/spec.py`, add to `ParamSpec`, last, because it is the only field with a default:

```python
    optional: bool = False
```

- [ ] **Step 9: Set it where parameters are built**

In `depin/_core/providers.py`, in `_extract_params`, change the final `params.append(...)` to pass the flag:

```python
        params.append(
            ParamSpec(
                name=name,
                key=param_key_from_meta(meta),
                tag=meta.tag,
                has_default=has_default,
                default=param.default if has_default else None,
                optional=meta.optional,
            )
        )
```

Leave the other two `ParamSpec` constructions in that module alone: the unannotated-parameter branch is keyed `object` and is never optional, and the alias branch declares a required target.

- [ ] **Step 10: Report an irreducible union properly**

In `depin/_core/providers.py`, replace the raise at the end of `as_provider_key` with:

```python
    if get_origin(value) in (UnionType, Union):
        raise InvalidProviderError(
            f'cannot use {value} as a provider key: depin reads `T | None` as an optional '
            'dependency, but a union of two or more providers names no single key. Annotate '
            'the parameter with the one you want, or select it with Annotated[..., Tag(...)].'
        )
    raise InvalidProviderError(f'cannot use {value!r} as a provider key: a key must be a class, a Token, or a string')
```

Add `from types import UnionType` and `Union` to that module's imports, keeping them sorted. `get_origin` is already imported there.

The union branch interpolates `{value}` rather than `{value!r}` because a union's `str` is the spelling the author wrote, `Cache | Logger`, while its `repr` is the same text — using `str` states the intent.

- [ ] **Step 11: Stop counting an unbound optional as missing**

In `depin/_core/graph.py`, change the comprehension in `_any_unsatisfied` to:

```python
    return any(
        not param.has_default and not param.optional and (param.key, param.tag) not in by_key
        for spec in specs
        for param in spec.params
    )
```

and, in `_collect_missing`, change

```python
            if param.has_default:
                continue
```

to

```python
            if param.has_default or param.optional:
                continue
```

Task 3 restructures this loop further; this step only stops it reporting an optional.

Update the docstring sentence in `_any_unsatisfied` that says "a parameter is unsatisfied where it stands" to name both escapes — a default and an optional annotation — so the comment does not go stale against the code below it.

- [ ] **Step 12: Run the freeze-level tests to verify they pass**

Run: `uv run pytest tests/unit/test_optional.py tests/unit/test_introspect.py`
Expected: PASS.

- [ ] **Step 13: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass. If an existing test asserted that `T | None` raises, it is now wrong by design — update it to the new behaviour and say so in your report rather than reverting the change.

- [ ] **Step 14: Commit**

```bash
git add depin/_core/introspect.py depin/_core/spec.py depin/_core/providers.py \
  depin/_core/graph.py tests/unit/test_introspect.py tests/unit/test_optional.py
git commit -m "feat: accept an optional dependency at freeze time"
```

---

### Task 2: An unbound optional resolves to None

**Files:**

- Modify: `depin/_core/frozen.py`
- Modify: `tests/unit/test_optional.py`

- [ ] **Step 1: Write the failing resolution tests**

Append to `tests/unit/test_optional.py`:

```python
def test_an_unbound_optional_dependency_resolves_to_none() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Service).freeze()
    assert di[Service].cache is None


def test_a_bound_optional_dependency_resolves_to_the_provider() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Cache).bind(Service).freeze()
    assert di[Service].cache is di[Cache]


def test_the_typing_optional_spelling_behaves_the_same() -> None:
    class Service:
        def __init__(self, cache: Optional[Cache]) -> None:  # noqa: UP045
            self.cache = cache

    assert Container().bind(Service).freeze()[Service].cache is None


def test_an_explicit_default_wins_over_optionality() -> None:
    fallback = Cache()

    class Service:
        def __init__(self, cache: Cache | None = fallback) -> None:
            self.cache = cache

    assert Container().bind(Service).freeze()[Service].cache is fallback


def test_an_optional_token_dependency_resolves_to_none_when_unbound() -> None:
    url = Token[str]('db.url')

    class Service:
        def __init__(self, dsn: Annotated[str | None, Named(url)]) -> None:
            self.dsn = dsn

    assert Container().bind(Service).freeze()[Service].dsn is None


def test_an_optional_tagged_dependency_resolves_to_none_when_that_tag_is_unbound() -> None:
    class Service:
        def __init__(self, cache: Annotated[Cache | None, Tag('primary')]) -> None:
            self.cache = cache

    di = Container().bind(Cache).bind(Service).freeze()
    assert di[Service].cache is None


def test_an_optional_dependency_of_a_scoped_provider_resolves_to_none() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Service, scope=Scope.SCOPED).freeze()
    with di.scope():
        assert di[Service].cache is None


@pytest.mark.asyncio
async def test_an_unbound_optional_resolves_to_none_in_an_async_provider() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    async def make() -> Service:
        return Service(None)

    class Wrapper:
        def __init__(self, service: Service, cache: Cache | None) -> None:
            self.service = service
            self.cache = cache

    di = Container().bind(make, provides=Service).bind(Wrapper).freeze()
    resolved = await di.aresolve(Wrapper)
    assert resolved.cache is None
```

The tagged case is the sharp one: `Cache` is bound, but not under the tag the parameter asks for, so the identity `(Cache, 'primary')` is unbound and the parameter must still receive `None`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_optional.py -k resolve or none`
Expected: FAIL with `MissingProviderError: missing provider for parameter 'cache' of Service`.

- [ ] **Step 3: Resolve an unbound optional to None, synchronously**

In `depin/_core/frozen.py`, in `_resolve_params_sync`, replace

```python
            dep = self._lookup_optional(param.key, param.tag)
            if dep is None:
                if param.has_default:
                    continue
                raise MissingProviderError(f"missing provider for parameter '{param.name}' of {fmt_key(spec.key)}")
```

with

```python
            dep = self._lookup_optional(param.key, param.tag)
            if dep is None:
                if param.has_default:
                    continue
                if param.optional:
                    out[param.name] = None
                    continue
                raise MissingProviderError(f"missing provider for parameter '{param.name}' of {fmt_key(spec.key)}")
```

The `has_default` branch stays first: an author who wrote a default meant it, and depin must not replace it with `None`.

- [ ] **Step 4: Do the same asynchronously**

Apply the identical change in `_resolve_params_async`, immediately below.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_optional.py`
Expected: PASS.

- [ ] **Step 6: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add depin/_core/frozen.py tests/unit/test_optional.py
git commit -m "feat: resolve an unbound optional dependency to None"
```

---

### Task 3: One chain for the error and the diagnostic

`_collect_missing` skips a parameter carrying a default, including for traversal, while `_deepest_requirement` in `render.py` traverses every satisfied edge. When an intermediate is both bound and defaulted the two report different chains. Measured on `main` at `ad33482`:

```
freeze  : no provider for C (required by B.c; resolution chain: B -> C)
explain : no provider for C (required by B.c; resolution chain: A -> B -> C)
```

The fix is to decide on the binding rather than on the default: skip a parameter with no binding when it has a default or is optional, and always traverse one that has a binding.

**Files:**

- Modify: `depin/_core/graph.py`
- Modify: `tests/unit/test_graph_render.py`

- [ ] **Step 1: Reproduce the divergence and record it**

Run this and paste both lines into your report; they are the before half of the evidence.

```bash
uv run python - <<'PY'
from depin import Container
from depin.errors import MissingProviderError


class C: ...


class B:
    def __init__(self, c: C) -> None: ...


class A:
    def __init__(self, b: B = None) -> None: ...


try:
    Container().bind(A).bind(B).freeze()
except MissingProviderError as exc:
    print('freeze :', str(exc).replace('__main__.', ''))


class C2: ...


class B2:
    def __init__(self, c: C2 = None) -> None: ...


class A2:
    def __init__(self, b: B2 = None) -> None: ...


di = Container().bind(A2).bind(B2).freeze()
print('explain:', di.explain(C2).replace('__main__.', ''))
PY
```

- [ ] **Step 2: Write the failing consistency test**

In `tests/unit/test_graph_render.py`, add a fixture beside `_chain_with_unbound_leaf`, in the same style — annotations assigned rather than written, so both variants agree on every part of the message except the one under test:

```python
def _chain_through_a_bound_and_defaulted_intermediate() -> tuple[Container, Container, type[object]]:
    """The same chain, with the outer provider's bound parameter also carrying a default.

    `_collect_missing` used to skip such a parameter for traversal as well as for
    reporting, so the freeze error named a shorter chain than `explain()` did.
    """
    missing = type('Missing', (), {})
    inner = type('Inner', (), {})
    outer = type('Outer', (), {})

    def make_inner_required(dep: object) -> object:
        del dep
        return inner()

    def make_inner_defaulted(dep: object = None) -> object:
        del dep
        return inner()

    def make_outer(dep: object = None) -> object:
        del dep
        return outer()

    for factory in (make_inner_required, make_inner_defaulted):
        factory.__annotations__ = {'dep': missing, 'return': inner}
    make_outer.__annotations__ = {'dep': inner, 'return': outer}

    required = Container().bind(make_inner_required).bind(make_outer)
    defaulted = Container().bind(make_inner_defaulted).bind(make_outer)
    return required, defaulted, missing


def test_a_bound_and_defaulted_intermediate_does_not_shorten_the_chain() -> None:
    required, defaulted, missing = _chain_through_a_bound_and_defaulted_intermediate()

    with pytest.raises(MissingProviderError) as raised:
        _ = required.freeze()

    graph = build_graph(build_plan(defaulted.records()))

    assert 'Outer' in str(raised.value)
    assert render_tree(graph, missing, None) == str(raised.value)
```

The `'Outer'` assertion is what makes the test discriminate: the two strings were already required to match on the shorter chain in one direction, so equality alone would not catch a regression that shortened both.

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_graph_render.py -k bound_and_defaulted`
Expected: FAIL — the freeze error names `Inner -> Missing` while the tree names `Outer -> Inner -> Missing`.

- [ ] **Step 4: Decide on the binding, not on the default**

In `depin/_core/graph.py`, replace the body of the `for param in spec.params` loop inside `_collect_missing` with:

```python
        for param in spec.params:
            dep = by_key.get((param.key, param.tag))
            if dep is None:
                if param.has_default or param.optional:
                    continue
                ident = (param.key, param.tag)
                if ident not in missing or len(current_chain) > len(missing[ident][0]):
                    missing[ident] = (current_chain, spec, param.name)
                continue
            if id(dep) in chain_specs:
                continue
            stack.append((dep, (*current_chain, dep)))
```

Replace the comment above the loop's `while` with one that states the new rule: the walk decides on whether a binding exists, so a parameter that is satisfied is traversed whether or not it also carries a default, which is what keeps this walk and `render._deepest_requirement` on one chain.

- [ ] **Step 5: Run the consistency tests to verify they pass**

Run: `uv run pytest tests/unit/test_graph_render.py tests/unit/test_graph_diagnostics.py tests/unit/test_graph_validation.py`
Expected: PASS. If an existing assertion pinned one of the now-longer chains, update it to the longer chain and list every such change in your report — the lengthening is the deliverable, not a regression.

- [ ] **Step 6: Record the after half of the evidence**

Re-run the script from Step 1 and paste both lines into your report. The two must now name the same chain.

- [ ] **Step 7: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add depin/_core/graph.py tests/unit/test_graph_render.py
git commit -m "fix: report one chain from freeze and explain"
```

---

### Task 4: Collections

**Files:**

- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/typeguards.py`
- Modify: `depin/_core/bindings.py`
- Modify: `depin/_core/providers.py`
- Modify: `depin/_core/construct.py`
- Modify: `tests/unit/test_spec.py`
- Create: `tests/unit/test_collections.py`

**Interfaces:**

- Produces: `ProviderShape.COLLECTION`, `CollectionBinding`, `is_collection_binding`, `collection_key`, `collection_param` in `depin._core.spec`, and widens `ProviderKey` by a `GenericAlias` member.
- Produces: `is_collection_key`, `as_collection_members` in `depin._core.typeguards`.
- Produces: `BindingCollector.collect(element, members, *, tag=None) -> Self`.

- [ ] **Step 1: Write the failing behaviour tests**

Create `tests/unit/test_collections.py`:

```python
"""`Container.collect` gathers several providers under one `list[Element]` key."""

from collections.abc import Generator
from typing import Annotated, Protocol

import pytest

from depin import Container, ProviderShape, Registry, Scope, Tag
from depin.errors import DuplicateProviderError, MissingProviderError


class Handler(Protocol):
    def run(self) -> str: ...


class EmailHandler:
    def run(self) -> str:
        return 'email'


class SmsHandler:
    def run(self) -> str:
        return 'sms'


def _both() -> Container:
    return Container().bind(EmailHandler).bind(SmsHandler).collect(Handler, [EmailHandler, SmsHandler])


def test_a_collection_resolves_its_members_in_declaration_order() -> None:
    di = _both().freeze()
    assert [handler.run() for handler in di.resolve(list[Handler])] == ['email', 'sms']


def test_a_collection_holds_the_same_instances_as_direct_resolution() -> None:
    di = _both().freeze()
    first, second = di.resolve(list[Handler])
    assert first is di[EmailHandler]
    assert second is di[SmsHandler]


def test_a_collection_is_injected_into_a_provider() -> None:
    class Dispatcher:
        def __init__(self, handlers: list[Handler]) -> None:
            self.handlers = handlers

    di = _both().bind(Dispatcher).freeze()
    assert [handler.run() for handler in di[Dispatcher].handlers] == ['email', 'sms']


def test_each_resolution_returns_a_fresh_list_over_shared_members() -> None:
    di = _both().freeze()
    first = di.resolve(list[Handler])
    second = di.resolve(list[Handler])
    assert first is not second
    assert first[0] is second[0]


def test_an_empty_collection_resolves_to_an_empty_list() -> None:
    di = Container().collect(Handler, []).freeze()
    assert di.resolve(list[Handler]) == []


def test_a_collection_carries_its_own_tag() -> None:
    di = (
        Container()
        .bind(EmailHandler)
        .bind(SmsHandler)
        .collect(Handler, [EmailHandler], tag='fast')
        .collect(Handler, [SmsHandler], tag='slow')
        .freeze()
    )
    assert [h.run() for h in di.resolve(list[Handler], tag='fast')] == ['email']
    assert [h.run() for h in di.resolve(list[Handler], tag='slow')] == ['sms']


def test_a_tagged_collection_is_selected_by_annotation() -> None:
    class Dispatcher:
        def __init__(self, handlers: Annotated[list[Handler], Tag('fast')]) -> None:
            self.handlers = handlers

    di = Container().bind(EmailHandler).collect(Handler, [EmailHandler], tag='fast').bind(Dispatcher).freeze()
    assert [h.run() for h in di[Dispatcher].handlers] == ['email']


def test_a_collection_member_may_be_an_alias() -> None:
    di = Container().bind(EmailHandler).alias(Handler, to=EmailHandler).collect(Handler, [Handler]).freeze()
    assert di.resolve(list[Handler])[0] is di[EmailHandler]


def test_a_scoped_member_is_rebuilt_per_scope() -> None:
    di = Container().bind(EmailHandler, scope=Scope.SCOPED).collect(Handler, [EmailHandler], tag='scoped').freeze()
    with di.scope():
        first = di.resolve(list[Handler], tag='scoped')[0]
        assert di.resolve(list[Handler], tag='scoped')[0] is first
    with di.scope():
        assert di.resolve(list[Handler], tag='scoped')[0] is not first


def test_each_member_is_torn_down_once() -> None:
    events: list[str] = []

    class First: ...

    class Second: ...

    def first() -> Generator[First]:
        events.append('first open')
        yield First()
        events.append('first close')

    def second() -> Generator[Second]:
        events.append('second open')
        yield Second()
        events.append('second close')

    di = Container().bind(first).bind(second).collect(object, [First, Second]).freeze()
    _ = di.resolve(list[object])
    _ = di.resolve(list[object])
    di.close()
    assert events == ['first open', 'second open', 'second close', 'first close']


def test_a_collection_appears_in_the_graph_as_a_transient_node() -> None:
    node = _both().freeze().graph().node(list[Handler])
    assert node.shape is ProviderShape.COLLECTION
    assert node.scope is Scope.TRANSIENT
    assert [edge.parameter for edge in node.dependencies] == ['member_0', 'member_1']


def test_a_registry_carries_a_collection_into_a_container() -> None:
    registry = Registry('handlers').bind(EmailHandler).collect(Handler, [EmailHandler])
    di = Container(registry).freeze()
    assert di.resolve(list[Handler])[0] is di[EmailHandler]


def test_binding_two_implementations_under_one_key_still_raises() -> None:
    builder = (
        Container()
        .bind(EmailHandler, provides=Handler)
        .bind(SmsHandler, provides=Handler)
        .collect(Handler, [EmailHandler])
    )
    with pytest.raises(DuplicateProviderError):
        _ = builder.freeze()


def test_a_collection_over_an_unbound_member_is_rejected() -> None:
    with pytest.raises(MissingProviderError, match='EmailHandler'):
        _ = Container().collect(Handler, [EmailHandler]).freeze()
```

The teardown test uses `object` as the element key on purpose: it exercises a collection whose members are two unrelated classes, which is the shape a plugin registry takes, and it pins the reverse construction order that `close()` guarantees.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_collections.py`
Expected: FAIL for every test, `AttributeError: 'Container' object has no attribute 'collect'`.

- [ ] **Step 3: Add the shape and the marker source**

In `depin/_core/spec.py`, add to `ProviderShape` after `ALIAS`:

```python
    COLLECTION = 'collection'
```

and to the class docstring's `Attributes:` block, after the `ALIAS:` entry:

```
        COLLECTION: A list of several bindings, declared with
            `Container.collect`. Nothing is cached here — each member keeps its
            own lifetime, and every resolution returns a new list over them.
```

Then widen the key alias in the same module, so a key built at runtime has a
type. Replace the `ProviderKey` declaration with:

```python
type ProviderKey = type[object] | Token[object] | str | GenericAlias
"""What a provider can be bound and resolved under: a class, a `Token`, a name, or a `list[...]` of one."""
```

The `GenericAlias` member exists because `collection_key` below builds its key
from a runtime value, and every construction that type-checks there produces a
`GenericAlias`. It widens what may be *passed*; `is_provider_key` stays the
validation and still admits only `list[X]` over a key, so `explain(dict[str,
int])` type-checks and then raises `MissingProviderError` for an invalid key
type, exactly as any other unusable value does. Adding a member to a union is
compatible with every consumer already written against the alias, which is the
widening Step 2's spec anticipated when it promoted `ProviderKey` to the public
surface.

Then, below `is_alias_binding`, add:

```python
COLLECTION_PARAM_PREFIX: Final[str] = 'member_'
"""Prefix of the parameter names a collection node declares, one per member.

The names must be distinct because they key the resolved arguments, and they are
what `explain()` prints and what the `dot` and `mermaid` exports write on each
edge.
"""


@dataclass(frozen=True, slots=True)
class CollectionBinding:
    """Marker source for `Container.collect(element, members)`.

    The collection's own tag rides on `BindRecord.tag`. Members are ordinary
    provider keys and stay bound under them, which is why an accidental duplicate
    registration still raises `DuplicateProviderError`.
    """

    element: ProviderKey
    members: tuple[ProviderKey, ...]


def is_collection_binding(value: object) -> TypeGuard[CollectionBinding]:
    return isinstance(value, CollectionBinding)


def collection_key(element: ProviderKey) -> ProviderKey:
    """The key a collection over ``element`` is registered under.

    Built through `types.GenericAlias` rather than written as ``list[element]``:
    subscripting a runtime value is `Variable "element" is not valid as a type`
    under mypy. The result is the same object a consumer writes by hand — equal
    to ``list[Element]``, hashing as it, and of the same type.
    """
    return GenericAlias(list, (element,))


def collection_param(index: int) -> str:
    return f'{COLLECTION_PARAM_PREFIX}{index}'
```

`GenericAlias` accepts a `Token` or a string as its argument as readily as a class, and the result hashes and compares by its argument, so it serves as a dictionary key for every kind of element.

- [ ] **Step 4: Render a generic alias by qualified name**

Still in `depin/_core/spec.py`, replace `fmt_key` with:

```python
def fmt_key(key: object) -> str:
    if isinstance(key, type):
        return key.__qualname__
    if isinstance(key, GenericAlias):
        arguments = ', '.join(fmt_key(argument) for argument in get_args(key))
        return f'{fmt_key(get_origin(key))}[{arguments}]'
    return repr(key)
```

`GenericAlias` is imported by the previous step; add `from typing import get_args, get_origin` to the module, keeping the imports sorted.

The branch is gated on `GenericAlias` rather than on `get_origin` being non-`None` so that a union never takes it: `Cache | Logger` must keep printing as itself in the message Task 1 added, and its origin is `types.UnionType`, which is a class.

- [ ] **Step 5: Admit `list[X]` as a runtime key**

In `depin/_core/typeguards.py`, replace `is_provider_key` with:

```python
def is_provider_key(value: object) -> TypeGuard[ProviderKey]:
    return isinstance(value, type | str | Token) or is_collection_key(value)


def is_collection_key(value: object) -> TypeGuard[ProviderKey]:
    """Whether ``value`` is a ``list[X]`` over something that is itself a key.

    Deliberately narrow. Widening `ProviderKey` to every parameterised generic is
    cycle 3's deliverable; a collection needs only this one origin, and admitting
    more now would ship the wider surface without the validation and rendering
    that go with it.
    """
    if not isinstance(value, GenericAlias) or get_origin(value) is not list:
        return False
    arguments = get_args(value)
    return len(arguments) == 1 and is_provider_key(arguments[0])
```

Add `from types import GenericAlias` and `from typing import get_args, get_origin` to that module, keeping the imports sorted.

- [ ] **Step 6: Guard the members `construct` reads**

Append to `depin/_core/typeguards.py`:

```python
def as_collection_members(kwargs: dict[str, object], names: tuple[str, ...], key: object) -> list[object]:
    """The resolved members of a collection, in declaration order.

    Unreachable through the public API for the same reason `as_alias_target` is:
    every member is a required parameter, and parameter resolution raises
    `MissingProviderError` before construction when one cannot be satisfied. The
    check keeps a defect inside the `DepinError` hierarchy.
    """
    missing = tuple(name for name in names if name not in kwargs)
    if missing:
        raise InvalidProviderError(f'collection for {fmt_key(key)} resolved no value for {", ".join(missing)}')
    return [kwargs[name] for name in names]
```

- [ ] **Step 7: Build the spec from the record**

In `depin/_core/providers.py`, insert this branch into `_record_to_spec`, directly after the `is_alias_binding` branch:

```python
    if is_collection_binding(rec.source):
        collection = rec.source
        _reject_repeated_members(collection)
        return ProviderSpec(
            key=collection_key(as_provider_key(collection.element)),
            tag=rec.tag,
            source=collection,
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
                )
                for index, member in enumerate(collection.members)
            ),
        )
```

and add, below `_record_to_spec`:

```python
def _reject_repeated_members(collection: CollectionBinding) -> None:
    seen: set[ProviderKey] = set()
    for member in collection.members:
        if member in seen:
            raise DuplicateProviderError(
                f'{fmt_key(member)} is listed twice in the collection for {fmt_key(collection.element)}: '
                'a member resolves to one value, so listing it again only repeats that value. Remove the duplicate.'
            )
        seen.add(member)
```

Add `CollectionBinding`, `collection_key`, `collection_param`, `fmt_key`, and `is_collection_binding` to the `depin._core.spec` import block, and `DuplicateProviderError` to the `depin.errors` import, keeping both sorted.

- [ ] **Step 8: Return the members at construction**

In `depin/_core/construct.py`, insert into `sync`'s `match`, directly after the `ProviderShape.ALIAS` case:

```python
        case ProviderShape.COLLECTION:
            return as_collection_members(kwargs, tuple(param.name for param in spec.params), key)
```

Add `as_collection_members` to that module's `depin._core.typeguards` import, keeping it sorted.

- [ ] **Step 9: Add the registration method**

In `depin/_core/bindings.py`, insert into `BindingCollector` directly after `alias`:

```python
    def collect(
        self,
        element: ProviderKey,
        members: Sequence[ProviderKey],
        *,
        tag: str | None = None,
    ) -> Self:
        """Register a list of existing bindings under the key ``list[element]``.

        Resolving that key returns each member's value, in the order given here.
        Members keep their own lifetimes, cache entries, and teardowns, so a
        singleton member is built once however many collections name it, and a
        scoped member is rebuilt per scope. Every resolution returns a new list,
        so no caller can mutate another's.

        The declaration is what makes a multi-binding explicit. Members stay bound
        under their own keys, so registering two implementations under one key by
        accident still raises `DuplicateProviderError`, and the collection
        occupies `list[element]`, which no ordinary binding claims.

        A collection is an ordinary node in the validated graph: an unbound
        member, a member listed twice, two collections over one element and tag,
        a cycle through a collection, and a singleton that reaches a scoped
        member through one are all rejected by `Container.freeze()`. An empty
        collection is legal and resolves to an empty list.

        Args:
            element: The key each member provides. The collection is registered
                under a list of it.
            members: The bindings to gather, in the order they should appear.
            tag: Disambiguator when several collections share an element.

        Returns:
            ``self``, for chaining.

        Example:
            ```pycon
            >>> from typing import Protocol
            >>> from depin import Container
            >>> class Handler(Protocol):
            ...     def run(self) -> str: ...
            >>> class Email:
            ...     def run(self) -> str:
            ...         return 'email'
            >>> class Sms:
            ...     def run(self) -> str:
            ...         return 'sms'
            >>> di = Container().bind(Email).bind(Sms).collect(Handler, [Email, Sms]).freeze()
            >>> [handler.run() for handler in di.resolve(list[Handler])]
            ['email', 'sms']

            ```
        """
        self._records.append(
            BindRecord(
                source=CollectionBinding(element=element, members=tuple(members)),
                scope=Scope.TRANSIENT,
                provides=None,
                tag=tag,
            )
        )
        return self
```

Add `Sequence` to the `collections.abc` import and `CollectionBinding` to the `depin._core.spec` import, keeping both sorted.

- [ ] **Step 10: Pin the new data model**

In `tests/unit/test_spec.py`, add `'COLLECTION'` to the `expected` set in `test_provider_shape_members`, and append:

```python
def test_collection_binding_is_immutable() -> None:
    class Handler: ...

    binding = CollectionBinding(element=Handler, members=(Handler,))
    with pytest.raises(FrozenInstanceError):
        setattr(binding, 'members', ())  # noqa: B010


def test_collection_key_is_a_list_of_the_element() -> None:
    class Handler: ...

    assert collection_key(Handler) == list[Handler]


def test_collection_params_are_distinct_and_ordered() -> None:
    assert [collection_param(index) for index in range(3)] == ['member_0', 'member_1', 'member_2']


def test_fmt_key_renders_a_collection_key_by_qualified_name() -> None:
    class Handler: ...

    assert fmt_key(list[Handler]) == f'list[{fmt_key(Handler)}]'


def test_fmt_key_leaves_a_union_alone() -> None:
    class Cache: ...

    class Logger: ...

    assert fmt_key(Cache | Logger) == repr(Cache | Logger)
```

Add the names the new tests use to the `depin._core.spec` import block, keeping it sorted.

- [ ] **Step 11: Run the collection tests to verify they pass**

Run: `uv run pytest tests/unit/test_collections.py tests/unit/test_spec.py`
Expected: PASS.

- [ ] **Step 12: Confirm the doctest on `collect` runs**

Run: `uv run pytest --doctest-modules depin/_core/bindings.py`
Expected: PASS.

- [ ] **Step 13: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 14: Commit**

```bash
git add depin/_core/spec.py depin/_core/typeguards.py depin/_core/bindings.py \
  depin/_core/providers.py depin/_core/construct.py \
  tests/unit/test_spec.py tests/unit/test_collections.py
git commit -m "feat: add Container.collect for multi-binding injection"
```

---

### Task 5: Prove a collection is validated at `freeze()`

This task adds tests and changes no library code. If any test here requires a change under `depin/`, the design is wrong: stop and report it rather than patching around it.

**Files:**

- Modify: `tests/unit/test_graph_validation.py`

- [ ] **Step 1: Write the validation tests**

Append to `tests/unit/test_graph_validation.py`:

```python
def test_two_collections_over_one_element_are_rejected() -> None:
    class Handler: ...

    class First: ...

    class Second: ...

    builder = Container().bind(First).bind(Second).collect(Handler, [First]).collect(Handler, [Second])
    with pytest.raises(DuplicateProviderError, match='list'):
        _ = builder.freeze()


def test_a_member_listed_twice_is_rejected() -> None:
    class Handler: ...

    class Only: ...

    builder = Container().bind(Only).collect(Handler, [Only, Only])
    with pytest.raises(DuplicateProviderError, match='listed twice'):
        _ = builder.freeze()


def test_a_cycle_through_a_collection_is_rejected() -> None:
    class Handler: ...

    class Member:
        def __init__(self, handlers: list[Handler]) -> None:
            del handlers

    builder = Container().bind(Member).collect(Handler, [Member])
    with pytest.raises(CircularDependencyError, match='cycle detected'):
        _ = builder.freeze()


def test_a_singleton_over_a_collection_with_a_scoped_member_is_captive() -> None:
    class Handler: ...

    class Session: ...

    class Dispatcher:
        def __init__(self, handlers: list[Handler]) -> None:
            del handlers

    builder = (
        Container()
        .bind(Session, scope=Scope.SCOPED)
        .collect(Handler, [Session])
        .bind(Dispatcher, scope=Scope.SINGLETON)
    )
    with pytest.raises(CaptiveDependencyError) as excinfo:
        _ = builder.freeze()
    assert 'Session' in str(excinfo.value)
    assert 'list[' in str(excinfo.value)


def test_an_invalid_collection_element_is_rejected() -> None:
    with pytest.raises(InvalidProviderError, match='not a valid key type|as a provider key'):
        _ = Container().collect(42, []).freeze()  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
```

Add any of `CaptiveDependencyError`, `CircularDependencyError`, `DuplicateProviderError`, `InvalidProviderError`, `Scope` the file does not already import.

- [ ] **Step 2: Write the async-propagation tests**

Append to `tests/unit/test_frozen_async.py`:

```python
@pytest.mark.asyncio
async def test_a_collection_with_an_async_member_resolves_under_aresolve() -> None:
    class Handler: ...

    class Backend: ...

    async def make() -> Backend:
        return Backend()

    di = Container().bind(make, provides=Backend).collect(Handler, [Backend]).freeze()
    members = await di.aresolve(list[Handler])
    assert len(members) == 1


def test_a_collection_with_an_async_member_is_rejected_by_resolve() -> None:
    class Handler: ...

    class Backend: ...

    async def make() -> Backend:
        return Backend()

    di = Container().bind(make, provides=Backend).collect(Handler, [Backend]).freeze()
    with pytest.raises(AsyncInSyncContextError, match=r'list\['):
        _ = di.resolve(list[Handler])
```

- [ ] **Step 3: Run them**

Run: `uv run pytest tests/unit/test_graph_validation.py tests/unit/test_frozen_async.py`
Expected: PASS with no change under `depin/`. A failure here is a design defect; report it.

- [ ] **Step 4: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_graph_validation.py tests/unit/test_frozen_async.py
git commit -m "test: pin freeze-time validation of collections"
```

---

### Task 6: Diagnostics and the type surface

**Files:**

- Modify: `depin/_core/diagnostics.py`
- Modify: `depin/_core/render.py`
- Modify: `tests/unit/test_graph_view.py`
- Modify: `tests/unit/test_graph_render.py`
- Modify: `tests/unit/test_graph_properties.py`
- Modify: `tests/typing/test_conformance.py`
- Modify: `tests/unit/test_public_api.py`

- [ ] **Step 1: Write the failing view and render tests**

Append to `tests/unit/test_graph_view.py`. Note the default is a real instance, not `None`: `cache: Cache = None` is an `assignment` error under `mypy --strict`, and this cycle adds no suppression.

```python
def test_an_unbound_optional_edge_reports_why_it_is_unsatisfied() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache | None) -> None:
            del cache

    edge = Container().bind(Service).freeze().graph().node(Service).dependencies[0]
    assert not edge.satisfied
    assert edge.optional
    assert not edge.has_default


def test_an_unbound_defaulted_edge_reports_why_it_is_unsatisfied() -> None:
    class Cache: ...

    fallback = Cache()

    class Service:
        def __init__(self, cache: Cache = fallback) -> None:
            del cache

    edge = Container().bind(Service).freeze().graph().node(Service).dependencies[0]
    assert not edge.satisfied
    assert not edge.optional
    assert edge.has_default
```

Append to `tests/unit/test_graph_render.py`:

```python
def test_explain_marks_an_unbound_optional() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache | None) -> None:
            del cache

    prefix = 'test_explain_marks_an_unbound_optional.<locals>.'
    tree = Container().bind(Service).freeze().explain(Service).replace(prefix, '')
    assert tree == 'Service  [singleton, class]\n  cache: Cache  (unbound, optional)'


def test_explain_renders_a_collection_and_its_members() -> None:
    class Handler: ...

    class First: ...

    class Second: ...

    di = Container().bind(First).bind(Second).collect(Handler, [First, Second]).freeze()
    prefix = 'test_explain_renders_a_collection_and_its_members.<locals>.'
    assert di.explain(list[Handler]).replace(prefix, '') == (
        'list[Handler]  [transient, collection]\n'
        '  member_0: First  [singleton, class]\n'
        '  member_1: Second  [singleton, class]'
    )


def test_the_exports_carry_the_collection_edges() -> None:
    class Handler: ...

    class First: ...

    di = Container().bind(First).collect(Handler, [First]).freeze()
    assert '[label="member_0"]' in di.graph().dot()
    assert '-->|member_0|' in di.graph().mermaid()
    assert 'transient, collection' in di.graph().mermaid()
```

Before locking the two exact strings, print the real values and use what they print:

```bash
uv run python - <<'PY'
from depin import Container


class Cache: ...


class Service:
    def __init__(self, cache: Cache | None) -> None:
        del cache


class Handler: ...


class First: ...


class Second: ...


print(Container().bind(Service).freeze().explain(Service))
print(Container().bind(First).bind(Second).collect(Handler, [First, Second]).freeze().explain(list[Handler]))
PY
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_graph_view.py tests/unit/test_graph_render.py -k "optional or collection"`
Expected: FAIL, `AttributeError: 'GraphEdge' object has no attribute 'optional'` and a mismatched tree.

- [ ] **Step 3: Carry both facts on the edge**

In `depin/_core/diagnostics.py`, add to `GraphEdge`, after `satisfied`:

```python
    optional: bool
    has_default: bool
```

Neither takes a default: `GraphEdge` is a public view type whose only construction site is `_node_for`, and a silent default would let a future field go unset there.

Extend the class docstring: `satisfied` is false for a parameter that no binding provides, which `Container.freeze()` allows only when the parameter carries a default or admits `None`; `has_default` and `optional` say which, and `has_default` wins when both hold, because depin never replaces a value the author wrote.

In `_node_for`, pass them:

```python
        GraphEdge(
            parameter=param.name,
            key=param.key,
            tag=param.tag,
            satisfied=(param.key, param.tag) in plan.by_key,
            optional=param.optional,
            has_default=param.has_default,
        )
```

- [ ] **Step 4: Render the distinction**

In `depin/_core/render.py`, `render_tree` currently renders an unbound target as:

```python
            lines.append(f'{indent}{label}{fmt_key(target)}  (unbound, default)')
```

The renderer needs the edge, not just its key, to say why. Change the stack's third element from `GraphNode | ProviderKey` to `GraphNode | GraphEdge`, push `edge` instead of `edge.key` when the child is absent, and render:

```python
        if not isinstance(target, GraphNode):
            reason = 'default' if target.has_default else 'optional'
            lines.append(f'{indent}{label}{fmt_key(target.key)}  (unbound, {reason})')
            continue
```

The root push becomes `[(0, '', root)]` unchanged, because a root that is absent is handled by `_render_absent` before the walk. Import `GraphEdge` from `depin._core.diagnostics`.

`has_default` is tested first, matching resolution: a parameter with both a default and an optional annotation receives its default.

- [ ] **Step 5: Run the view and render tests to verify they pass**

Run: `uv run pytest tests/unit/test_graph_view.py tests/unit/test_graph_render.py`
Expected: PASS.

- [ ] **Step 6: Extend the generative model**

In `tests/unit/test_graph_properties.py`, extend `GraphCase` and `_materialize` so the existing invariants cover both features, keeping every new field last with a default so the file's hand-written cases keep working:

- `optionals: frozenset[tuple[int, int]] = frozenset()` — a subset of `edges` whose parameter is annotated `nodes[dependency] | None` instead of `nodes[dependency]`.
- `collections: frozenset[int] = frozenset()` — for each index, a collection over a fresh element class gathering `nodes[index]`, registered only when that node is registered.

Draw both in `_graphs`. Then make a generated node **consume** what earlier cycles only registered: give each collection's element class a consumer node depending on `list[element]`, so a generated collection appears on a real path. This also closes the finding the roadmap carries from Step 3 under `Generated aliases are never consumed`, so extend the alias generation the same way while you are in the file, and say in your report that you did.

Add no new property test. The file's existing invariants — `freeze()` either raises a `DepinError` or returns a valid topological order, every spec appears as exactly one node, every edge either indexes a node or is unsatisfied, each export emits exactly `len(nodes)` declarations — are what must now hold over the wider model.

- [ ] **Step 7: Run the property suite**

Run: `uv run pytest tests/unit/test_graph_properties.py`
Expected: PASS. A falsifying example is a real defect in this cycle's design; report it rather than narrowing the strategy.

- [ ] **Step 8: Pin the inferred types**

Append to `tests/typing/test_conformance.py`:

```python
def test_a_collection_key_keeps_its_element_type() -> None:
    class Handler(Protocol):
        def run(self) -> str: ...

    class Email:
        def run(self) -> str:
            return 'email'

    builder = Container().bind(Email)
    assert_type(builder.collect(Handler, [Email]), Container)
    di = builder.freeze()
    assert_type(di.resolve(list[Handler]), list[Handler])
    assert_type(di[list[Handler]], list[Handler])
    assert_type(injected(list[Handler]), list[Handler])
```

These pin the measurement the whole collection design rests on: `resolve` needs no new overload because `type[T]` already infers `list[Handler]` from `list[Handler]`. If a checker ever stops inferring it, this test is what says so.

Append to `tests/unit/test_public_api.py`:

```python
def test_provider_shape_is_exported_with_the_collection_member() -> None:
    assert depin.ProviderShape.COLLECTION.value == 'collection'
```

- [ ] **Step 9: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add depin/_core/diagnostics.py depin/_core/render.py tests/unit/test_graph_view.py \
  tests/unit/test_graph_render.py tests/unit/test_graph_properties.py \
  tests/typing/test_conformance.py tests/unit/test_public_api.py
git commit -m "feat: show why an edge is unsatisfied in the graph view"
```

---

### Task 7: Document, demonstrate, integrate, and benchmark

**Files:**

- Modify: `depin/_core/container.py`
- Create: `docs/guide/resolution.md`
- Modify: `mkdocs.yml`
- Create: `examples/optional_dependencies/__init__.py`, `examples/optional_dependencies/main.py`
- Create: `examples/collections/__init__.py`, `examples/collections/main.py`
- Modify: `examples/README.md`
- Modify: `tests/integration/test_examples.py`
- Modify: `tests/integration/test_fastapi_ext.py`
- Modify: `benchmarks/test_resolution.py`

- [ ] **Step 1: Update the container's own documentation**

In `depin/_core/container.py`, add `collect()` to the `Container` class docstring's enumeration of the registration surface, beside `alias()`.

In `freeze()`'s `Raises:` block, extend the `InvalidProviderError` entry to cover a parameter annotated with a union that names two or more providers, and extend the `DuplicateProviderError` entry to cover a member listed twice in one collection. Keep both to one added clause each; the block documents triggers, not mechanics.

- [ ] **Step 2: Write the guide page**

Create `docs/guide/resolution.md` covering both concepts, in the register of `docs/guide/composition.md`. It must contain, as `pycon` doctests executed by the normal `pytest` run:

- an unbound `Cache | None` parameter arriving as `None`, and the same parameter arriving as the instance once `Cache` is bound;
- the rule that an explicit default wins over optionality, stated in one sentence;
- `collect` with two members and `di.resolve(list[Handler])`;
- `explain()` over the collection, showing `[transient, collection]` and the `member_N` edges;
- one sentence each on: members keeping their own lifetimes, every resolution returning a fresh list, an empty collection being legal, and an accidental duplicate registration still raising because members stay bound under their own keys.

Print each block's real output before writing it down, the same way Task 6 Step 1 does. A guide that disagrees with the renderer fails the suite.

- [ ] **Step 3: Add it to the nav**

In `mkdocs.yml`, add `- Resolution semantics: guide/resolution.md` under `Guide`, after `Composing bindings`.

- [ ] **Step 4: Write the two examples**

`examples/optional_dependencies/main.py`: one service that works with or without a metrics sink, built twice from two containers — one with the sink bound, one without — printing both outcomes. No container at module level; a `build(with_metrics: bool) -> FrozenContainer` function.

`examples/collections/main.py`: a plugin point. Two or three handlers bound under their own classes, gathered with `collect`, and a dispatcher taking `list[Handler]`. Print each handler's output, then print `explain(list[Handler])` so the reader sees the collection in the graph. No container at module level; a `build()` function.

Each gets an empty `__init__.py`. Run both with `uv run python -m examples.<name>.main` and paste the real output into your report.

- [ ] **Step 5: List and execute them**

Add a row for each to the table in `examples/README.md`, after the `aliasing` row, matching the existing style.

Append to `tests/integration/test_examples.py` one test per example, asserting on the built container rather than on printed text — the shape the file's other tests use. Add the imports to the sorted block at the top.

- [ ] **Step 6: Exercise both through the FastAPI extension**

Append to `tests/integration/test_fastapi_ext.py` two tests, each with a real `httpx.AsyncClient` against a real app behind `RequestScope`, matching the file's existing shape and its `# pyright: ignore[reportUnusedFunction]` on the route function:

- a route whose provider takes `list[Handler]`, asserting the response names every member;
- a route whose request-scoped provider takes an unbound `T | None`, asserting the response reports `None`.

- [ ] **Step 7: Benchmark the collection**

Append to `benchmarks/test_resolution.py` a case resolving a collection of 10 members and one of 100, built from `build_chain`-style synthetic classes. Follow the file's existing `Benchmark` protocol and its habit of warming the resolution once before timing.

- [ ] **Step 8: Run the benchmarks**

Run: `uv run --group bench pytest benchmarks --benchmark-only`
Expected: the pre-existing cases reported, plus the new ones. Record every mean in your report; they feed the evidence file.

- [ ] **Step 9: Run the gates plus the docs build**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add depin/_core/container.py docs mkdocs.yml examples \
  tests/integration/test_examples.py tests/integration/test_fastapi_ext.py \
  benchmarks/test_resolution.py
git commit -m "docs: document optional dependencies and collections"
```

---

### Task 8: Final verification and the evidence record

**Files:**

- Create: `specs/evidence/2026-08-31-step-3-optional-collections.md`

- [ ] **Step 1: Run the full gate sequence from a clean tree**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Expected: all pass with no warnings.

- [ ] **Step 2: Measure coverage**

Run: `uv run pytest --cov=depin --cov-report=term-missing`
Expected: at or above 95%. Name every uncovered line in a module this cycle changed, and check each against `main` at `ad33482` in a throwaway worktree before calling it new — the partial branch on `construct.py`'s `match` and the miss in `providers.py` are both pre-existing, and `scope.py:69` is a thread-scheduling path that appears in roughly one run in two on any commit.

- [ ] **Step 3: Do not run the mutation gate locally**

`[tool.mutmut] only_mutate` covers all of `depin/_core/*.py`, so there is no changed-modules subset to run; a local run is the full run. The CI `mutation` job triggers on `depin/_core/**` and is the authority. Record that, and its reason, in the evidence file instead of a score.

- [ ] **Step 4: Confirm the suppression count is unchanged**

Run: `grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin`
Expected: exactly three lines — `frozen.py:116`, `frozen.py:139`, `markers.py:129` — byte-identical to `ad33482`.

- [ ] **Step 5: Record the evidence**

Create `specs/evidence/2026-08-31-step-3-optional-collections.md` in the shape of `specs/evidence/2026-08-31-step-3-provides-aliasing.md`. It must carry: every command above with its relevant output; the coverage figure with each miss attributed to this cycle or to `main`; the suppression count; the benchmark means; the three checker measurements the design rests on, restated from the spec rather than re-derived; and the before-and-after chain lines from Task 3.

State plainly that the evidence file is itself part of the commit it documents, so any claim about the tree's state must be true after it lands.

- [ ] **Step 6: Commit**

```bash
git add specs/evidence/2026-08-31-step-3-optional-collections.md
git commit -m "docs: record cycle 2 verification evidence"
```

## Self-review

**Spec coverage.** Measurements — Task 6 Step 8 pins them as tests. Public surface: `collect` — Task 4 Step 9; `ProviderShape.COLLECTION` — Task 4 Step 3; the two `GraphEdge` fields — Task 6 Step 3. Data model: optional — Task 1 Steps 3, 8, 9; collection — Task 4 Steps 3, 7. Semantics: optional — Tasks 1 and 2; collections — Task 4 (order, identity, freshness, tags, teardown) and Task 5 (duplicates, missing, cycles, captive, async); the carried Step 2 finding — Task 3. Errors table — Task 1 Step 10, Task 4 Steps 6 and 7, Task 5. Key rendering — Task 4 Step 4. Module layout — Tasks 1 to 7. Verification — Tasks 1 to 8. Acceptance criteria — Task 3 Step 5, Task 5 Step 3, Task 6, Task 7 Step 9, Task 8.

**Type consistency.** `CollectionBinding(element, members)`, `is_collection_binding`, `collection_key`, `collection_param`, `COLLECTION_PARAM_PREFIX`, `is_collection_key`, `as_collection_members`, and `ProviderShape.COLLECTION` are spelled the same in every task that uses them. `ParamSpec.optional` and `AnnotatedMeta.optional` share one name for one fact. The parameter names are `member_0`, `member_1`, … in `collection_param`, in the `explain()` expectations, in the export assertions, and in the guide.

**Known verification points.** Four assertions depend on exact rendered text: the two `explain()` trees in Task 6 Step 1, the guide's blocks in Task 7 Step 2, and the chain lines in Task 3. Each carries a step that prints the real value first. Task 3 and Task 1 both change existing error text; each says so and requires the implementer to list every assertion it updated rather than treating the change as a regression.

**Ordering risk.** Task 1 changes `_collect_missing` in a small way that Task 3 then rewrites. Task 3 must replace the loop wholesale, as written, rather than editing around Task 1's line. Task 4 depends on Task 1 only for `ParamSpec.optional` existing with a default, which it supplies. Every task commits a green tree.

**Blast radius.** This cycle touches ten modules under `depin/_core/`, against cycle 1's five, and it changes the text of existing `MissingProviderError` messages. That is the cost of the two deliverables the roadmap grouped here, and it is why they ship as their own release.
