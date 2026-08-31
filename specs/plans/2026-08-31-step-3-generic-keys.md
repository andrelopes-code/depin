# Step 3, cycle 3 — generic keys: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make any parameterised generic a provider key, so `Repo[User]` and `Repo[Order]` are two bindings — for the 0.10.0 milestone, the last of Step 3's three releases.

**Architecture:** No new module and no signature change. Cycle 2 admitted exactly one generic key, `list[X]`; this cycle replaces that gate with a general one — the origin must be a class other than `types.UnionType`, and every argument must itself be a key. A deprecated `typing` alias is rejected rather than rewritten, because every canonical rebuild that works at runtime fails a checker, and rejecting at `freeze()` is validation rather than a silent rewrite. `fmt_key` widens to match. Three things ride along: a defect where an async factory's parameterised return annotation is unwrapped and mis-keyed, the forward-reference namespace the roadmap routes here, and one union message cycle 2 left half-corrected.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, Hypothesis, mutmut 3.7, pytest-benchmark, mkdocs-material with mkdocstrings, uv.

**Spec:** `specs/2026-08-31-step-3-generic-keys-design.md`

## Global constraints

Every task inherits these requirements from `AGENTS.md`, the approved roadmap, and the spec.

- The core keeps zero runtime dependencies.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `typing.Any`, `typing.cast`, `# type: ignore`, or `# pyright: ignore`. `depin/` carries exactly three suppressions — two in `frozen.py`, one in `markers.py` — and must carry exactly those three when this cycle ends. This constraint is why the spec rejects rather than normalises; do not reopen that by adding a suppression to make a rebuild type-check.
- Every exception raised by library code inherits `DepinError`. No bare `KeyError`, `TypeError`, `ValueError`, or `assert` in `depin/`.
- New behaviour in `depin/_core/` is developed test-first: the failing test is written and observed failing before the implementation.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery.
- Public API additions carry Google-style docstrings that omit types from `Args:` / `Returns:` and include a doctest `Example:`.
- `fmt_key` renders a class by `__qualname__`, so a class declared inside a test function appears as `test_x.<locals>.Name`. A generic declared inside a test function renders as `test_x.<locals>.Repo[test_x.<locals>.User]`.
- Coverage over `depin/` stays at or above 95%; it is 98.63% at the 0.9.0 baseline. The mutation gate is enforced by CI, not locally.
- Before every commit, run in this exact order:

  ```bash
  uv run ruff format
  uv run ruff check
  uv run basedpyright
  uv run mypy
  uv run pytest
  ```

- Any commit that changes prose also runs `uv run --group docs mkdocs build --strict` after the five gates.
- `uv run ruff format` reformats Python inside markdown fences, including under `specs/`. Never revert that reformatting.
- Commits are focused, conventional, at most 72 characters in the subject, and contain no attribution or automation language.

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `depin/_core/typeguards.py` | `is_generic_key` replaces `is_collection_key`; `is_provider_key` widens. | 1 |
| `depin/_core/spec.py` | `fmt_key`'s gate widens, sharing one formatter with the rejection message. | 1 |
| `depin/_core/providers.py` | The canonical-form check in `as_provider_key`. | 1 |
| `tests/unit/test_generic_keys.py` | The key model end to end. | 1 |
| `tests/unit/test_spec.py` | `fmt_key` over generics; the canonical discriminator. | 1 |
| `depin/_core/markers.py` | `provides` accepts a parameterised generic. | 2 |
| `tests/unit/test_markers.py` | That acceptance, and that a non-key is still rejected. | 2 |
| `depin/_core/providers.py` | `ASYNC_FUNCTION` leaves `_UNWRAP_SHAPES`. | 3 |
| `tests/unit/test_providers.py` | The mis-keying defect, red then green. | 3 |
| `depin/_core/providers.py` | `_registered_classes` widens; the second union message. | 4 |
| `tests/unit/test_providers.py` | Forward references to indirectly-registered keys. | 4 |
| `tests/unit/test_graph_validation.py` | Every row of the Errors table. | 5 |
| `tests/unit/test_graph_render.py` | A generic key in the tree and both exports. | 5 |
| `tests/unit/test_graph_properties.py` | Parameterised keys in the generative model. | 5 |
| `tests/typing/test_conformance.py` | The four `assert_type` cases the design rests on. | 5 |
| `docs/guide/resolution.md` | The narrative section. | 6 |
| `examples/generic_keys/` | Runnable program. | 6 |
| `examples/README.md` | Lists it. | 6 |
| `tests/integration/test_examples.py` | Executes it. | 6 |
| `tests/integration/test_fastapi_ext.py` | A route resolving a generic key. | 6 |
| `benchmarks/test_resolution.py` | `freeze()` over generic keys. | 6 |
| `specs/evidence/2026-08-31-step-3-generic-keys.md` | The measured evidence. | 7 |

---

### Task 1: A parameterised generic is a key

**Files:**

- Modify: `depin/_core/typeguards.py`
- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/providers.py`
- Create: `tests/unit/test_generic_keys.py`
- Modify: `tests/unit/test_spec.py`

**Interfaces:**

- Produces: `is_generic_key(value) -> TypeGuard[ProviderKey]` in `depin._core.typeguards`, replacing `is_collection_key`.
- Produces: `is_canonical_generic(value) -> bool` in `depin._core.typeguards`.
- Produces: `fmt_parameterised(origin, arguments) -> str` in `depin._core.spec`, shared by `fmt_key` and the rejection message.

- [ ] **Step 1: Write the failing key-model tests**

Create `tests/unit/test_generic_keys.py`:

```python
"""A parameterised generic is a provider key, distinguished by equality like any other."""

import typing
from typing import Protocol

import pytest

from depin import Container, ProviderShape, Scope
from depin.errors import InvalidProviderError


class User: ...


class Order: ...


class Repo[T]:
    def __init__(self) -> None:
        self.rows: list[str] = []


class Reader[T](Protocol):
    def read(self) -> str: ...


def _user_repo() -> Repo[User]:
    return Repo()


def _order_repo() -> Repo[Order]:
    return Repo()


def test_two_parameterisations_are_two_bindings() -> None:
    di = Container().bind(_user_repo).bind(_order_repo).freeze()
    assert di.resolve(Repo[User]) is not di.resolve(Repo[Order])


def test_a_parameterisation_is_distinct_from_the_bare_class() -> None:
    def bare() -> Repo:
        return Repo()

    di = Container().bind(bare).bind(_user_repo).freeze()
    assert di.resolve(Repo) is not di.resolve(Repo[User])


def test_a_generic_key_is_injected_by_annotation() -> None:
    class Service:
        def __init__(self, repo: Repo[User]) -> None:
            self.repo = repo

    di = Container().bind(_user_repo).bind(Service).freeze()
    assert di[Service].repo is di.resolve(Repo[User])


def test_a_generic_protocol_is_a_key() -> None:
    class MemReader:
        def read(self) -> str:
            return 'mem'

    di = Container().bind(MemReader, provides=Reader[User]).freeze()
    assert di.resolve(Reader[User]).read() == 'mem'


def test_a_generic_key_nests() -> None:
    def nested() -> Repo[Repo[User]]:
        return Repo()

    di = Container().bind(nested).freeze()
    assert di.graph().node(Repo[Repo[User]]).shape is ProviderShape.FUNCTION


def test_a_generic_key_works_as_an_alias_target() -> None:
    di = Container().bind(_user_repo).alias(Reader[User], to=Repo[User]).freeze()
    assert di.resolve(Reader[User]) is di.resolve(Repo[User])


def test_a_generic_key_works_as_a_collection_element() -> None:
    di = Container().bind(_user_repo).bind(_order_repo).collect(Repo[User], [Repo[User], Repo[Order]]).freeze()
    assert len(di.resolve(list[Repo[User]])) == 2


def test_a_generic_key_is_scoped_like_any_other() -> None:
    di = Container().bind(_user_repo, scope=Scope.SCOPED).freeze()
    with di.scope():
        first = di.resolve(Repo[User])
        assert di.resolve(Repo[User]) is first
    with di.scope():
        assert di.resolve(Repo[User]) is not first


def test_a_parameterisation_does_not_satisfy_a_wider_one() -> None:
    class Service:
        def __init__(self, repo: Repo[object]) -> None:
            del repo

    with pytest.raises(Exception, match='Repo'):
        _ = Container().bind(_user_repo).bind(Service).freeze()


@pytest.mark.parametrize(
    'annotation',
    [typing.List[User], typing.Dict[str, int], typing.Sequence[User]],
)
def test_a_deprecated_typing_alias_is_rejected(annotation: object) -> None:
    with pytest.raises(InvalidProviderError, match='deprecated'):
        _ = Container().alias(annotation, to=User).freeze()  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def test_a_callable_key_is_rejected() -> None:
    from collections.abc import Callable

    with pytest.raises(InvalidProviderError, match='as a provider key'):
        _ = Container().alias(Callable[[int], str], to=User).freeze()  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
```

Print the real message for the widening case before locking `test_a_parameterisation_does_not_satisfy_a_wider_one`; it should be a `MissingProviderError` naming `Repo[object]`. Narrow the `pytest.raises` to that exact type once you have seen it, rather than leaving `Exception`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_generic_keys.py`
Expected: FAIL, mostly `InvalidProviderError: cannot use ... as a provider key`.

- [ ] **Step 3: Write the failing discriminator tests**

Append to `tests/unit/test_spec.py`:

```python
def test_fmt_key_renders_a_user_generic_by_qualified_name() -> None:
    class User: ...

    class Repo[T]: ...

    assert fmt_key(Repo[User]) == f'{fmt_key(Repo)}[{fmt_key(User)}]'


def test_fmt_key_renders_a_nested_generic() -> None:
    class User: ...

    class Repo[T]: ...

    assert fmt_key(Repo[Repo[User]]) == f'{fmt_key(Repo)}[{fmt_key(Repo)}[{fmt_key(User)}]]'
```

and append to `tests/unit/test_typeguards.py`, creating the file if the repository has none, in the style of its neighbours:

```python
def test_the_canonical_generic_spellings_are_accepted() -> None:
    class User: ...

    class Repo[T]: ...

    class Reader[T](Protocol):
        def read(self) -> str: ...

    for key in (list[User], dict[str, int], Sequence[User], Repo[User], Reader[User], Repo[Repo[User]]):
        assert is_canonical_generic(key), key


def test_the_deprecated_typing_aliases_are_not_canonical() -> None:
    class User: ...

    for key in (typing.List[User], typing.Dict[str, int], typing.Sequence[User]):
        assert not is_canonical_generic(key), key
```

These two tests are the measurement the whole design rests on. If a future Python makes a
deprecated alias canonical, or a canonical spelling stop being one, this is what says so.

- [ ] **Step 4: Widen the key predicate**

In `depin/_core/typeguards.py`, replace `is_collection_key` with:

```python
def is_generic_key(value: object) -> TypeGuard[ProviderKey]:
    """Whether ``value`` is a parameterised generic usable as a provider key.

    The origin must be a class and every argument must itself be a key. A union
    is excluded by name: `types.UnionType` is a class, so it would otherwise
    pass, and optionality is a parameter-position feature rather than a key.
    `Callable[[int], str]` and `tuple[X, ...]` fall out of the argument rule,
    carrying a list and an `Ellipsis` respectively, with no special case.
    """
    origin = get_origin(value)
    if not isinstance(origin, type) or origin is UnionType:
        return False
    arguments = get_args(value)
    return bool(arguments) and all(is_provider_key(argument) for argument in arguments)


def is_canonical_generic(value: object) -> bool:
    """Whether a parameterised generic is spelled the way depin keys it.

    A builtin or ABC origin produces a `types.GenericAlias`; a `Generic`
    subclass produces `typing`'s own alias. Everything else with a class origin
    is a deprecated `typing` alias — `typing.List[X]` and its kin — which is a
    different object from `list[X]` and would become a second key that renders
    identically to the first.
    """
    origin = get_origin(value)
    if not isinstance(origin, type):
        return False
    return isinstance(value, GenericAlias) or issubclass(origin, Generic)
```

and change `is_provider_key` to:

```python
def is_provider_key(value: object) -> TypeGuard[ProviderKey]:
    return isinstance(value, type | str | Token) or is_generic_key(value)
```

Add `from types import GenericAlias, UnionType` and `Generic` to the `typing` import, keeping both sorted. Remove `GenericAlias` from wherever it is now imported if the line changes shape.

Then update the one call site of the old name: `as_provider_key` in `depin/_core/providers.py` imports and calls `is_collection_key`. Change it to `is_generic_key`, and add the canonical check — Step 6 gives the full replacement.

- [ ] **Step 5: Share one formatter between the renderer and the message**

In `depin/_core/spec.py`, replace `fmt_key` with:

```python
def fmt_key(key: object) -> str:
    if isinstance(key, type):
        return key.__qualname__
    origin = get_origin(key)
    if isinstance(origin, type) and origin is not UnionType:
        return fmt_parameterised(origin, get_args(key))
    return repr(key)


def fmt_parameterised(origin: type[object], arguments: tuple[object, ...]) -> str:
    """Spell a parameterised key as ``Origin[A, B]``, each part through `fmt_key`.

    Shared with the message `as_provider_key` raises for a deprecated `typing`
    alias, so the canonical form it tells the user to write is spelled by the
    same code that will render it once they do.
    """
    return f'{fmt_key(origin)}[{", ".join(fmt_key(argument) for argument in arguments)}]'
```

Add `UnionType` to the `types` import, keeping it sorted. The union guard is what keeps `X | None` printing as itself: its origin is a class, so without the guard it would render as `UnionType[X, NoneType]`.

- [ ] **Step 6: Accept a canonical generic and reject a deprecated alias**

In `depin/_core/providers.py`, replace the `is_collection_key` branch of `as_provider_key` with:

```python
    if is_generic_key(value):
        if is_canonical_generic(value):
            return value
        origin = get_origin(value)
        if isinstance(origin, type):
            raise InvalidProviderError(
                f'cannot use {value} as a provider key: it is the deprecated typing alias for '
                f'{fmt_parameterised(origin, get_args(value))}, and a different object at runtime, '
                f'so the two would be two keys that print alike. Write '
                f'{fmt_parameterised(origin, get_args(value))} instead.'
            )
```

Add `fmt_parameterised`, `is_canonical_generic` and `is_generic_key` to the relevant import blocks, keeping them sorted, and drop `is_collection_key`.

The `isinstance(origin, type)` guard is not redundant to the reader even though `is_generic_key` already established it: it is what lets `fmt_parameterised` take `type[object]` without widening its own parameter. If `basedpyright` reports it as unnecessary, restructure so `is_generic_key` hands the origin back rather than adding a suppression.

- [ ] **Step 7: Run everything to verify it passes**

Run: `uv run pytest tests/unit/test_generic_keys.py tests/unit/test_spec.py tests/unit/test_typeguards.py tests/unit/test_collections.py`
Expected: PASS. The collection suite must be untouched by this change: `list[X]` was already a canonical generic, so widening the gate around it changes nothing for it.

- [ ] **Step 8: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass. An existing test that asserted `Repo[User]` or `dict[str, int]` is rejected is now wrong by design — update it and list every such change in your report.

- [ ] **Step 9: Commit**

```bash
git add depin/_core/typeguards.py depin/_core/spec.py depin/_core/providers.py \
  tests/unit/test_generic_keys.py tests/unit/test_spec.py tests/unit/test_typeguards.py
git commit -m "feat: accept any parameterised generic as a provider key"
```

---

### Task 2: `provides` accepts a generic key

**Files:**

- Modify: `depin/_core/markers.py`
- Modify: `tests/unit/test_markers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_markers.py`:

```python
def test_provides_accepts_a_parameterised_generic() -> None:
    class User: ...

    class Repo[T]: ...

    @provides(Repo[User])
    class SqlRepo: ...

    assert get_provides(SqlRepo) == Repo[User]


def test_provides_still_rejects_a_non_key() -> None:
    with pytest.raises(InvalidProviderError, match='expected a class'):
        _ = provides(42)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
```

- [ ] **Step 2: Run them to verify the first fails**

Run: `uv run pytest tests/unit/test_markers.py -k provides`
Expected: the first FAILS with `InvalidProviderError: cannot use ... as a @provides target`; the second passes already.

- [ ] **Step 3: Widen the guard**

In `depin/_core/markers.py`, `_reject_non_class` rejects anything that is not a class, which now excludes a legitimate key. Rename it `_reject_invalid_key` and change the condition to accept a provider key, keeping the same exception type and the same shape of message:

```python
def _reject_invalid_key(value: object, /) -> None:
    """Raise unless ``value`` can serve as a provider key.

    Takes ``object`` rather than the annotated type so the check still runs for
    an untyped caller that breaks the promise the annotation makes to a checker.
    """
    if not is_provider_key(value):
        raise InvalidProviderError(
            f'cannot use {value!r} as a @provides target: expected a class, a Protocol, '
            'an abstract base class, or a parameterised generic such as Repo[User]'
        )
```

Import `is_provider_key` from `depin._core.typeguards`. Check for an import cycle first: `typeguards` imports `Token` from `markers`, so `markers` importing from `typeguards` at module level would close a loop. If it does, move the guard's predicate rather than the import — the narrowest fix is for `markers` to keep its own local check spelled the same way `is_provider_key` spells it, with a comment naming the cycle as the reason. Report which you did and why.

`get_provides` returns `type | None` today; a generic key is not a `type`, so widen its return to `ProviderKey | None` and follow the change through `_resolve_key` in `providers.py`, which uses it.

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_markers.py tests/unit/test_generic_keys.py`
Expected: PASS.

- [ ] **Step 5: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add depin/_core/markers.py depin/_core/providers.py tests/unit/test_markers.py
git commit -m "feat: let provides target a parameterised generic"
```

---

### Task 3: An async factory is keyed by its return annotation

**Files:**

- Modify: `depin/_core/providers.py`
- Modify: `tests/unit/test_providers.py`

- [ ] **Step 1: Record the defect**

Run and paste the output into your report; it is the before half of the evidence.

```bash
uv run python - <<'PY'
from depin import Container


class Handler: ...


class User: ...


class Repo[T]: ...


async def make_list() -> list[Handler]:
    return []


async def make_repo() -> Repo[User]:
    return Repo()


def make_sync() -> list[Handler]:
    return []


for factory in (make_list, make_repo, make_sync):
    di = Container().bind(factory).freeze()
    print(factory.__name__, '->', [str(node.key) for node in di.graph().nodes])
PY
```

Expected before the fix: `make_list` keyed `Handler`, `make_repo` keyed `User`, `make_sync` keyed `list[Handler]`. The first two are wrong.

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/test_providers.py`:

```python
def test_an_async_factory_is_keyed_by_its_whole_return_annotation() -> None:
    class Handler: ...

    async def make() -> list[Handler]:
        return []

    plan = build_plan(Registry().bind(make).records())
    assert [spec.key for spec in plan.order] == [list[Handler]]


def test_an_async_factory_returning_a_generic_keeps_its_parameter() -> None:
    class User: ...

    class Repo[T]: ...

    async def make() -> Repo[User]:
        return Repo()

    plan = build_plan(Registry().bind(make).records())
    assert [spec.key for spec in plan.order] == [Repo[User]]


def test_a_generator_factory_still_unwraps_its_container() -> None:
    class Conn: ...

    def connect() -> Generator[Conn]:
        yield Conn()

    plan = build_plan(Registry().bind(connect).records())
    assert [spec.key for spec in plan.order] == [Conn]
```

Use whatever this file already imports to build a plan; if it has no such helper, use `build_plan(Registry().bind(...).records())` as above and add the imports. The third test is the guard: the fix must remove only `ASYNC_FUNCTION` from the unwrap set, leaving the four container shapes unwrapping as before.

- [ ] **Step 3: Run them to verify the first two fail**

Run: `uv run pytest tests/unit/test_providers.py -k "async_factory or generator_factory_still"`
Expected: the two async tests FAIL, the generator test passes.

- [ ] **Step 4: Stop unwrapping an async factory's return annotation**

In `depin/_core/providers.py`, remove `ProviderShape.ASYNC_FUNCTION` from `_UNWRAP_SHAPES`, leaving the four shapes whose annotation genuinely wraps the value. Replace the set's definition with the four remaining members and add a comment above it saying why an async function is not among them: `async def f() -> X` already means the awaited value is `X`, so there is nothing to unwrap, while `Generator[X]` and its kin name a container around it.

- [ ] **Step 5: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_providers.py tests/unit/test_frozen_async.py tests/unit/test_generators.py`
Expected: PASS. If another test depended on the old unwrap for an async factory, it was asserting the defect — update it and say so in your report.

- [ ] **Step 6: Record the after half**

Re-run the script from Step 1 and paste the output. All three factories must now be keyed by their whole annotation.

- [ ] **Step 7: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add depin/_core/providers.py tests/unit/test_providers.py
git commit -m "fix: key an async factory by its whole return annotation"
```

---

### Task 4: Forward references to an indirectly-registered key

**Files:**

- Modify: `depin/_core/providers.py`
- Modify: `tests/unit/test_providers.py`

- [ ] **Step 1: Write the failing tests**

`_registered_classes` builds the namespace annotations resolve against from records whose `source` is a class, so a class registered only as an alias key or target, only through `scope_value`, or only as a collection element or member never enters it. Append to `tests/unit/test_providers.py` one test per role, in the shape the file already uses for forward references — assign the annotation as a string and bind the class only in the indirect role.

Each test binds a provider whose parameter annotation is the string name of a class that is registered only indirectly, and asserts `build_plan` succeeds and keys the parameter to that class. Cover: an alias key, an alias target, a `scope_value` key, a collection element, and a collection member.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_providers.py -k forward`
Expected: FAIL with `InvalidProviderError: the annotation on parameter ... could not be resolved`.

- [ ] **Step 3: Widen the namespace**

In `depin/_core/providers.py`, extend `_registered_classes` to add every class reachable from a record, whatever role it plays: the source when it is a class, and for each marker source, the classes among its keys — `ValueBinding.token` is a `Token` and contributes nothing, `FrameBinding.key`, `AliasBinding.key` and `.target`, `CollectionBinding.element` and each member. Add only values that are classes; a `Token`, a string, or a parameterised generic has no `__name__` to key the namespace by.

Update the docstring to say what it now covers, and keep it one sentence.

- [ ] **Step 4: Correct the advice the error gives**

The message `_extract_params` raises for an unresolvable annotation ends "or bind the class so depin can resolve the forward reference". That advice is wrong for a `Protocol`: binding it would register a bogus provider rather than resolve anything. Reword the final clause to point at importing the name at module level, or registering it in any role — which is now true.

- [ ] **Step 5: Correct the second union message**

Cycle 2 split `as_provider_key`'s union message in two and fixed the single-member branch for callers outside parameter position. The two-or-more branch still says "Annotate the parameter with the one you want", which has no meaning when the union is an alias target or a collection element. Reword it so it is true wherever it is reached, in one or two sentences, keeping it actionable. Update any test that pins the old text.

- [ ] **Step 6: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_providers.py tests/unit/test_alias.py tests/unit/test_collections.py`
Expected: PASS.

- [ ] **Step 7: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add depin/_core/providers.py tests/unit/test_providers.py
git commit -m "fix: resolve forward references to indirectly-bound keys"
```

---

### Task 5: Validation, diagnostics, and the type surface

This task changes no library code. If any test requires one, stop and report it.

**Files:**

- Modify: `tests/unit/test_graph_validation.py`
- Modify: `tests/unit/test_graph_render.py`
- Modify: `tests/unit/test_graph_properties.py`
- Modify: `tests/typing/test_conformance.py`

- [ ] **Step 1: Cover the Errors table**

Append to `tests/unit/test_graph_validation.py` one test per row of the spec's Errors table that Task 1 did not already cover: a key whose origin is not a class, a key with an argument that is not itself a key, and both union spellings reaching a key position. Assert on the message fragment each raises, not only the exception type.

- [ ] **Step 2: Cover the diagnostics**

Append to `tests/unit/test_graph_render.py` a test that a generic key renders in `explain()` and in both exports as `Repo[User]` rather than by `repr`. Print the real output first and lock the assertion to it.

- [ ] **Step 3: Extend the generative model**

In `tests/unit/test_graph_properties.py`, make some generated nodes carry a parameterised key. Follow the precedent the file already sets for aliases and collections: a new `GraphCase` field declared last with a default, drawn in `_graphs`, materialised in `_materialize`. The existing invariants then cover generic keys with no new property test. If the model's node classes cannot be parameterised without restructuring, wrap each chosen node's key in a generic container class declared once at module level, and say so in your report.

- [ ] **Step 4: Pin the four conformance assertions**

Append to `tests/typing/test_conformance.py`:

```python
def test_a_generic_key_keeps_its_parameterisation() -> None:
    class User: ...

    class Repo[T]: ...

    class Reader[T](Protocol):
        def read(self) -> str: ...

    def make() -> Repo[User]:
        return Repo()

    di = Container().bind(make).freeze()
    assert_type(di.resolve(Repo[User]), Repo[User])
    assert_type(di[Repo[User]], Repo[User])
    assert_type(di.resolve(Reader[User]), Reader[User])
    assert_type(di.resolve(list[Repo[User]]), list[Repo[User]])
```

These four are the measurement the cycle's whole shape rests on: `resolve` needs no overload because `type[T]` already infers a parameterised generic. If a checker ever stops inferring them, this is what fails.

- [ ] **Step 5: Run and commit**

```bash
uv run pytest
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
git add tests
git commit -m "test: cover generic keys across validation and diagnostics"
```

---

### Task 6: Document, demonstrate, integrate, and benchmark

**Files:**

- Modify: `docs/guide/resolution.md`
- Create: `examples/generic_keys/__init__.py`, `examples/generic_keys/main.py`
- Modify: `examples/README.md`
- Modify: `tests/integration/test_examples.py`
- Modify: `tests/integration/test_fastapi_ext.py`
- Modify: `benchmarks/test_resolution.py`

- [ ] **Step 1: Add the guide section**

Add a "Generic keys" section to `docs/guide/resolution.md`, after the collections section, with `pycon` doctests covering: two parameterisations resolving to two providers; a generic key as a parameter annotation; and `explain()` over one, showing how it renders. State in one sentence each that the bare class and a parameterisation are different keys, that matching is by equality so `Repo[User]` does not satisfy `Repo[object]`, and that a deprecated `typing.List[X]` spelling is rejected with the canonical one named.

Print every block's real output before writing it down.

- [ ] **Step 2: Write the example**

`examples/generic_keys/main.py`: two repositories over two entity types, bound under `Repo[User]` and `Repo[Order]`, and a service taking both. Print what each returns and then `explain()` for one of the keys, so the reader sees the parameterisation in the graph. No container at module level; a `build()` function the integration test calls.

- [ ] **Step 3: List and execute it**

Add a row to `examples/README.md` after the collections row, and a test to `tests/integration/test_examples.py` asserting on the built container.

- [ ] **Step 4: Exercise it through the FastAPI extension**

Append to `tests/integration/test_fastapi_ext.py` a route resolving a generic key through `Inject[...]`, with a real `httpx.AsyncClient` against a real app behind `RequestScope`, matching the file's existing shape.

- [ ] **Step 5: Benchmark**

Append a case to `benchmarks/test_resolution.py` timing `freeze()` over a graph whose keys are parameterised, against the existing plain-key case at the same size, so the canonical-form check's cost on the freeze path is visible.

- [ ] **Step 6: Run the gates plus the docs build, then commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
git add docs examples benchmarks tests/integration
git commit -m "docs: document and demonstrate generic keys"
```

Record every benchmark mean in your report.

---

### Task 7: Final verification and the evidence record

**Files:**

- Create: `specs/evidence/2026-08-31-step-3-generic-keys.md`

- [ ] **Step 1: Run the full gate sequence**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

- [ ] **Step 2: Measure coverage**

Run: `uv run pytest --cov=depin --cov-report=term-missing`. Attribute every uncovered line in a changed module against `main` at `ec65dcb` in a throwaway worktree before calling it new.

- [ ] **Step 3: Do not run the mutation gate locally**

`[tool.mutmut] only_mutate` covers all of `depin/_core/*.py`, so a local run is the full run. The CI `mutation` job is the authority. Record the decision and its reason.

- [ ] **Step 4: Confirm the suppression count**

Run: `grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin`
Expected: exactly three lines, two in `frozen.py` and one in `markers.py`, byte-identical to `ec65dcb`.

- [ ] **Step 5: Record the evidence**

Create `specs/evidence/2026-08-31-step-3-generic-keys.md` in the shape of `specs/evidence/2026-08-31-step-3-optional-collections.md`. It must carry: every command with its output; the coverage figure with each miss attributed; the suppression count; the four checker measurements the design rests on, restated from the spec; the canonical-form discriminator table; the before-and-after key inference from Task 3; and the benchmark means. The evidence file is part of the commit it documents, so no sentence in it may assert anything false about its own state.

- [ ] **Step 6: Commit**

```bash
git add specs/evidence/2026-08-31-step-3-generic-keys.md
git commit -m "docs: record cycle 3 verification evidence"
```

## Self-review

**Spec coverage.** The false premise — Task 5 Step 4 turns it into a test. Measurements: the canonical discriminator — Task 1 Step 3; the union exclusion and the `Callable` rule — Task 1 Step 4 and Task 5 Step 1. Public surface: `is_provider_key` — Task 1; `provides` — Task 2. Semantics table — Task 1 Step 1 covers every row. The defect — Task 3. The two carried items — Task 4. Errors table — Task 1 Step 1 and Task 5 Step 1. Key rendering — Task 1 Steps 3 and 5. Module layout — Tasks 1 to 4; that `graph.py`, `frozen.py`, `diagnostics.py`, `render.py`, `bindings.py`, `construct.py` and `scope.py` stay untouched is asserted by Task 5 passing without a library change. Verification — Tasks 1 to 7. Acceptance criteria — Task 1, Task 3 Step 6, Task 4, Task 5, Task 6 Step 6, Task 7.

**Type consistency.** `is_generic_key`, `is_canonical_generic`, `fmt_parameterised` and `_reject_invalid_key` are spelled the same in every task that uses them. `is_collection_key` is removed in Task 1 and referenced nowhere after it.

**Known verification points.** Four assertions depend on values measured at run time: the widening-rejection error type in Task 1 Step 1, the rendered generic in Task 5 Step 2, the guide blocks in Task 6 Step 1, and the key inference in Task 3. Each carries a step that prints the real value first.

**Ordering risk.** Task 1 removes `is_collection_key`, which `as_provider_key` calls; both are in the same task and the same commit. Task 2 widens `get_provides`'s return type, which `_resolve_key` consumes — also in that task. Task 3 and Task 4 both edit `providers.py` but different functions. Every task commits a green tree.

**Smallest-cycle note.** This is the smallest of Step 3's three cycles, because its hardest stated problem turned out not to exist. What remains is real but narrow: one predicate, one formatter, one rejection, one defect, and two carried items.
