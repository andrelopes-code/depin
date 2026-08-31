# Step 3, cycle 1 — `provides` and aliasing: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erase the phantom type parameter from `provides`, removing the last `type-abstract` suppression from the repository, and add `Container.alias(key, to=...)` so one instance is reachable under two keys — for the 0.8.0 milestone.

**Architecture:** No new module. `provides` drops its type parameter, `_ProvidesDecorator` becomes non-generic, and a runtime guard rejects a non-class. An alias is an ordinary provider node: `AliasBinding` joins `ValueBinding` and `FrameBinding` as a marker source, `_record_to_spec` turns it into a `ProviderShape.ALIAS` spec with `Scope.TRANSIENT` and exactly one parameter naming the target, and `construct.sync` returns that resolved parameter. Because the alias caches nothing, the cache identity on both paths is the target's, so a singleton stays a singleton. Every existing check — duplicates, missing, cycles, captive, async propagation — applies to the alias node without modification, and `graph.py`, `frozen.py`, `diagnostics.py`, and `render.py` are not touched.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, Hypothesis, mutmut 3.7, pytest-benchmark, mkdocs-material with mkdocstrings, uv.

**Spec:** `specs/2026-08-31-step-3-provides-aliasing-design.md`

## Global constraints

Every task inherits these requirements from `AGENTS.md`, the approved roadmap, and the spec.

- The core keeps zero runtime dependencies. Nothing in this cycle adds a package to `[project.dependencies]` or to any dependency group.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `typing.Any`, `typing.cast`, `# type: ignore`, or `# pyright: ignore`. This cycle **removes** three suppressions; it adds none.
- Every exception raised inherits `DepinError`. No bare `KeyError`, `TypeError`, or `assert` in library code.
- Data structures are `@dataclass(frozen=True, slots=True)`.
- New behaviour in `depin/_core/` is developed test-first: the failing test is written and observed failing before the implementation.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery.
- Public API additions carry Google-style docstrings that omit types and include a doctest `Example:`. Doctests run in the default `pytest` invocation.
- `fmt_key` renders a class by `__qualname__`, so a class declared inside a test function appears as `test_x.<locals>.Name`. Text assertions must spell it that way.
- Coverage over `depin/` stays at or above 95%. The mutation gate stays at 95% killed.
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
| `depin/_core/markers.py` | `provides` loses `A`; `_ProvidesDecorator` becomes non-generic; runtime guard. | 1 |
| `tests/unit/test_markers.py` | The guard, and that the decorated class is returned unchanged. | 1 |
| `examples/testing/main.py` | Drops its `type-abstract` suppression. | 1 |
| `tests/unit/test_resolution.py` | Drops its `type-abstract` suppression. | 1 |
| `tests/typing/test_conformance.py` | Drops its `type-abstract` suppression; adds `alias`. | 1, 5 |
| `docs/support-policy.md` | Loses the "Known limitation" section. | 1 |
| `AGENTS.md` | Loses the "one documented exception" clause; gains nothing else in this task. | 1 |
| `depin/_core/spec.py` | `ProviderShape.ALIAS`, `AliasBinding`, `is_alias_binding`, `ALIAS_PARAM`. | 2 |
| `tests/unit/test_spec.py` | Pins the enum members and the new marker source. | 2 |
| `depin/_core/typeguards.py` | `as_alias_target`. | 2 |
| `tests/unit/test_construct.py` | Covers `as_alias_target`'s failure path. | 2 |
| `depin/_core/bindings.py` | `BindingCollector.alias`. | 3 |
| `depin/_core/providers.py` | The alias branch of `_record_to_spec`. | 3 |
| `depin/_core/construct.py` | The `ALIAS` case of `sync`. | 3 |
| `tests/unit/test_alias.py` | Identity, lifetimes, tags, chaining, teardown, `scope_value`. | 3 |
| `tests/unit/test_graph_validation.py` | Missing target, duplicate, cycle, captive chain. | 4 |
| `tests/unit/test_frozen_async.py` | An alias to an async target. | 4 |
| `tests/unit/test_graph_render.py` | The alias in all three renderers. | 5 |
| `tests/unit/test_graph_properties.py` | The Hypothesis invariants over graphs with aliases. | 5 |
| `tests/unit/test_public_api.py` | Unchanged `__all__`, restated as a guard. | 5 |
| `docs/guide/composition.md` | The narrative section on aliases. | 6 |
| `examples/aliasing/__init__.py` | Makes the example a package. | 6 |
| `examples/aliasing/main.py` | Runnable program for the concept. | 6 |
| `examples/README.md` | Lists the new example. | 6 |
| `tests/integration/test_examples.py` | Executes the new example. | 6 |
| `tests/integration/test_fastapi_ext.py` | Resolves through an alias in a route. | 6 |
| `benchmarks/test_resolution.py` | Alias indirection against direct resolution. | 6 |
| `specs/evidence/2026-08-31-step-3-provides-aliasing.md` | The measured evidence. | 7 |

---

### Task 1: Erase the phantom type parameter from `provides`

`provides[A]` makes mypy report `type-abstract` in the consumer's own file for the pattern the README teaches, and `A` is observable in no return type a consumer can reach. This task deletes it, adds the runtime guard that the annotation alone no longer implies for an untyped caller, and removes the three suppressions and the support-policy section that documented the limitation.

**Files:**

- Modify: `depin/_core/markers.py`
- Modify: `tests/unit/test_markers.py`
- Modify: `examples/testing/main.py:15`
- Modify: `tests/unit/test_resolution.py:41`
- Modify: `tests/typing/test_conformance.py:138`
- Modify: `docs/support-policy.md`
- Modify: `AGENTS.md:15`

**Interfaces:**

- Produces: `provides(abstract: type[object]) -> _ProvidesDecorator` in `depin._core.markers`, replacing `provides[A](abstract: type[A]) -> _ProvidesDecorator[A]`.
- Produces: `_ProvidesDecorator` non-generic, keeping `__call__[C](self, cls: type[C]) -> type[C]`.

- [ ] **Step 1: Write the failing test for the runtime guard**

Append to `tests/unit/test_markers.py`:

```python
def test_provides_rejects_a_non_class_target() -> None:
    with pytest.raises(InvalidProviderError, match='expected a class'):
        _ = provides('Store')  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def test_provides_returns_the_decorated_class_unchanged() -> None:
    class Store: ...

    class MemStore: ...

    assert provides(Store)(MemStore) is MemStore
    assert get_provides(MemStore) is Store
```

Add `InvalidProviderError` to the existing `from depin.errors import DepinError` line, keeping the names sorted.

The suppression on the first test is the repository's sanctioned form for feeding a runtime guard a statically invalid value, the same one `tests/unit/test_resolution.py:31` already uses. It is not a `type-abstract` suppression, which is what this cycle removes.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_markers.py -k provides_rejects`
Expected: FAIL, `DID NOT RAISE`.

- [ ] **Step 3: Rewrite the decorator and the factory**

In `depin/_core/markers.py`, replace the whole `_ProvidesDecorator` class and the `provides` function with:

```python
@final
class _ProvidesDecorator:
    __slots__ = ('_abstract',)

    def __init__(self, abstract: type[object]) -> None:
        self._abstract = abstract

    def __call__[C](self, cls: type[C]) -> type[C]:
        setattr(cls, _PROVIDES_ATTR, self._abstract)
        return cls


def provides(abstract: type[object]) -> _ProvidesDecorator:
    """Tag a class with the abstract type it implements.

    Decorating ``@provides(Abstract)`` records ``Abstract`` as the class's provider
    key, so `Container.bind()` registers the concrete class under the
    abstract type without an explicit ``provides=`` argument. Useful for binding an
    implementation against a `typing.Protocol` or base class.

    The decorated class is returned unchanged and keeps its own type, so nothing
    downstream of the decorator sees a different class.

    Args:
        abstract: The key to register the decorated class under. Any class,
            including a ``Protocol`` and an abstract base class.

    Raises:
        InvalidProviderError: ``abstract`` is not a class, so it could never
            serve as the provider key the decorator promises to record.

    Example:
        ```pycon
        >>> from typing import Protocol
        >>> from depin import Container, provides
        >>> class Store(Protocol):
        ...     def get(self) -> str: ...
        >>> @provides(Store)
        ... class MemStore:
        ...     def get(self) -> str:
        ...         return 'mem'
        >>> di = Container().bind(MemStore).freeze()
        >>> di.resolve(Store).get()
        'mem'

        ```
    """
    if not isinstance(abstract, type):
        raise InvalidProviderError(
            f'cannot use {abstract!r} as a @provides target: expected a class, '
            'a Protocol, or an abstract base class'
        )
    return _ProvidesDecorator(abstract)
```

Add `InvalidProviderError` to the module's `from depin.errors import DepinError` line, keeping the names sorted.

`type[object]` is what makes the signature clean under both checkers: mypy reports `type-abstract` only when a formal parameter is exactly `type[T]` with `T` a type variable. The measurement is recorded in the spec.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_markers.py -k provides`
Expected: PASS.

- [ ] **Step 5: Remove the three `type-abstract` suppressions**

In `examples/testing/main.py`, replace line 15 with:

```python
@provides(Clock)
```

In `tests/unit/test_resolution.py`, replace the comment block and decorator at lines 38–41 with:

```python
    @provides(Store)
```

In `tests/typing/test_conformance.py`, replace line 138 with:

```python
    @provides(Store)
```

- [ ] **Step 6: Verify mypy is clean without them**

Run: `uv run mypy`
Expected: `Success: no issues found`. A `type-abstract` error here means the signature change did not land; do not restore the suppression.

- [ ] **Step 7: Verify no `type-abstract` suppression remains**

Run: `grep -rn "type-abstract" --include='*.py' --include='*.md' . --exclude-dir=.venv --exclude-dir=site --exclude-dir=.git`
Expected: only matches under `specs/`, which are the historical record.

- [ ] **Step 8: Remove the known-limitation section from the support policy**

In `docs/support-policy.md`, delete the whole `### Known limitation: `provides` and `type[T]`` section, from its heading through the sentence ending "changing a public signature." The `## Type checkers` section above it stays.

- [ ] **Step 9: Drop the exception clause from `AGENTS.md`**

In `AGENTS.md`, replace the sentence at line 15 with:

```markdown
The library leans heavily on Python's modern type system — PEP 695 generics, `Protocol`, `Annotated`, `@overload`, `ParamSpec` — to give consumers precise return types without a `# type: ignore` at call sites.
```

- [ ] **Step 10: Run the gates plus the docs build**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add depin/_core/markers.py tests/unit/test_markers.py examples/testing/main.py \
  tests/unit/test_resolution.py tests/typing/test_conformance.py docs/support-policy.md AGENTS.md
git commit -m "fix: erase the phantom type parameter from provides"
```

---

### Task 2: The alias data model

An alias needs a marker source, a shape, a parameter name, and a guard for the one value `construct` reads out of the resolved kwargs. Nothing in this task registers or resolves anything.

**Files:**

- Modify: `depin/_core/spec.py`
- Modify: `tests/unit/test_spec.py`
- Modify: `depin/_core/typeguards.py`
- Modify: `tests/unit/test_construct.py`

**Interfaces:**

- Produces: `ProviderShape.ALIAS` in `depin._core.spec`.
- Produces: `AliasBinding(key, target, target_tag)` and `is_alias_binding` in `depin._core.spec`.
- Produces: `ALIAS_PARAM: Final[str] = 'target'` in `depin._core.spec`.
- Produces: `as_alias_target(kwargs: dict[str, object], key: object) -> object` in `depin._core.typeguards`.

- [ ] **Step 1: Write the failing tests for the data model**

In `tests/unit/test_spec.py`, add `'ALIAS'` to the `expected` set in `test_provider_shape_members`, and append:

```python
def test_alias_binding_is_immutable() -> None:
    class Store: ...

    binding = AliasBinding(key=Store, target=Store, target_tag=None)
    with pytest.raises(FrozenInstanceError):
        setattr(binding, 'target_tag', 'x')  # noqa: B010


def test_is_alias_binding_narrows_only_alias_bindings() -> None:
    class Store: ...

    assert is_alias_binding(AliasBinding(key=Store, target=Store, target_tag=None))
    assert not is_alias_binding(Store)
```

Add `ALIAS_PARAM`, `AliasBinding`, and `is_alias_binding` to the existing `from depin._core.spec import (...)` block, keeping it sorted.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_spec.py -k "alias or shape_members"`
Expected: FAIL, `ImportError: cannot import name 'AliasBinding'`.

- [ ] **Step 3: Add the shape member**

In `depin/_core/spec.py`, add this line to `ProviderShape`, directly after `FRAME`:

```python
    ALIAS = 'alias'
```

and add this entry to the class docstring's `Attributes:` block, directly after the `FRAME:` entry:

```
        ALIAS: A second name for another binding, declared with
            `Container.alias`. Nothing is called and nothing is cached here —
            the target owns the value, its cache entry, and its teardown.
```

- [ ] **Step 4: Add the marker source and the parameter name**

In `depin/_core/spec.py`, insert directly after `is_frame_binding`:

```python
ALIAS_PARAM: Final[str] = 'target'
"""The parameter an alias node declares for the binding it delegates to.

It is a real `ParamSpec` name, so it is what `explain()` prints as the edge
label and what the `dot` and `mermaid` exports write on the arrow.
"""


@dataclass(frozen=True, slots=True)
class AliasBinding:
    """Marker source for `Container.alias(key, to=...)`.

    The alias carries its own key because `BindRecord.provides` admits only a
    class, while an alias key may equally be a `Token` or a string. The alias's
    own tag rides on `BindRecord.tag`, where every other binding's tag rides;
    ``target_tag`` selects among tagged bindings on the other end.
    """

    key: ProviderKey
    target: ProviderKey
    target_tag: str | None


def is_alias_binding(value: object) -> TypeGuard[AliasBinding]:
    return isinstance(value, AliasBinding)
```

Add `Final` to the module's `from typing import ...` line, keeping the names sorted.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_spec.py`
Expected: PASS.

- [ ] **Step 6: Write the failing test for the construct-time guard**

Append to `tests/unit/test_construct.py`:

```python
def test_an_alias_spec_with_no_resolved_target_names_the_provider() -> None:
    class Store: ...

    spec = ProviderSpec(
        key=Store,
        tag=None,
        source=None,
        scope=Scope.TRANSIENT,
        shape=ProviderShape.ALIAS,
        needs_async=False,
        params=(),
    )
    with pytest.raises(InvalidProviderError, match='Store'):
        _ = construct.sync(spec, {}, _no_teardown, _no_frame)
```

Reuse whatever the file already names for its teardown sink and frame reader; if it has none, declare them alongside the test:

```python
def _no_teardown(record: Teardown) -> None:
    raise AssertionError(f'unexpected teardown: {record!r}')


def _no_frame(spec: ProviderSpec) -> object:
    raise AssertionError(f'unexpected frame read: {spec!r}')
```

This spec is unreachable through the public API — `freeze()` gives every alias exactly one required parameter, and `_resolve_params_sync` raises `MissingProviderError` before construction if it cannot be satisfied. The guard exists so a defect surfaces as a `DepinError` naming the provider rather than as a bare `KeyError`.

- [ ] **Step 7: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_construct.py -k alias_spec_with_no_resolved_target`
Expected: FAIL, the `match` does not fire (the shape falls through to the `case _` or raises `KeyError`, depending on ordering).

- [ ] **Step 8: Add the guard**

Append to `depin/_core/typeguards.py`:

```python
def as_alias_target(kwargs: dict[str, object], key: object) -> object:
    """The value an alias node's single parameter resolved to.

    Unreachable through the public API: `Container.freeze()` gives every alias
    exactly one required parameter, and parameter resolution raises
    `MissingProviderError` before construction when it cannot be satisfied.
    The check keeps a defect inside the `DepinError` hierarchy instead of
    surfacing as a `KeyError` with no provider named.
    """
    if ALIAS_PARAM in kwargs:
        return kwargs[ALIAS_PARAM]
    raise InvalidProviderError(f'alias for {fmt_key(key)} resolved no target binding')
```

Add `ALIAS_PARAM` to the module's `from depin._core.spec import ...` line, keeping the names sorted.

The test in Step 6 stays red until Task 3 wires the `ALIAS` case into `construct.sync`; that is the next task's first green.

- [ ] **Step 9: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest tests/unit/test_spec.py tests/unit/test_markers.py
```

Expected: all pass. `tests/unit/test_construct.py -k alias` is still red by design.

- [ ] **Step 10: Commit**

```bash
git add depin/_core/spec.py depin/_core/typeguards.py tests/unit/test_spec.py
git commit -m "feat: add the alias shape and its marker source"
```

`tests/unit/test_construct.py` is deliberately left out of this commit: its test is red until the next task, and `AGENTS.md` forbids committing a failing suite.

---

### Task 3: Register, build, and resolve an alias

**Files:**

- Modify: `depin/_core/bindings.py`
- Modify: `depin/_core/providers.py`
- Modify: `depin/_core/construct.py`
- Create: `tests/unit/test_alias.py`
- Modify: `tests/unit/test_construct.py`

**Interfaces:**

- Produces: `BindingCollector.alias(key, *, to, tag=None, to_tag=None) -> Self`, inherited by `Container` and `Registry`.
- Consumes: `AliasBinding`, `is_alias_binding`, `ALIAS_PARAM`, `ProviderShape.ALIAS`, `as_alias_target` from Task 2.

- [ ] **Step 1: Write the failing behaviour tests**

Create `tests/unit/test_alias.py`:

```python
"""`Container.alias`: a second name for a binding, with no second instance."""

from collections.abc import Generator
from typing import Protocol

import pytest

from depin import Container, ProviderShape, Registry, Scope, Token
from depin.errors import MissingProviderError, OutsideScopeError


class Store(Protocol):
    def get(self) -> str: ...


class PostgresStore:
    def get(self) -> str:
        return 'pg'


def test_an_alias_resolves_to_the_same_singleton_instance() -> None:
    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
    assert di.resolve(Store) is di[PostgresStore]


def test_an_alias_does_not_add_a_second_construction() -> None:
    built: list[int] = []

    class Counted:
        def __init__(self) -> None:
            built.append(1)

    di = Container().bind(Counted).alias(Store, to=Counted).freeze()
    _ = di.resolve(Store)
    _ = di[Counted]
    _ = di.resolve(Store)
    assert len(built) == 1


def test_an_alias_reaches_the_same_instance_as_a_nested_dependency() -> None:
    class Service:
        def __init__(self, store: Store) -> None:
            self.store = store

    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).bind(Service).freeze()
    assert di[Service].store is di[PostgresStore]


def test_an_alias_to_a_scoped_target_shares_the_scope_instance() -> None:
    di = Container().bind(PostgresStore, scope=Scope.SCOPED).alias(Store, to=PostgresStore).freeze()
    with di.scope():
        assert di.resolve(Store) is di[PostgresStore]


def test_an_alias_to_a_scoped_target_needs_a_scope() -> None:
    di = Container().bind(PostgresStore, scope=Scope.SCOPED).alias(Store, to=PostgresStore).freeze()
    with pytest.raises(OutsideScopeError):
        _ = di.resolve(Store)


def test_an_alias_to_a_transient_target_builds_each_time() -> None:
    di = Container().bind(PostgresStore, scope=Scope.TRANSIENT).alias(Store, to=PostgresStore).freeze()
    assert di.resolve(Store) is not di.resolve(Store)


def test_an_alias_selects_a_tagged_target() -> None:
    def primary() -> PostgresStore:
        return PostgresStore()

    def backup() -> PostgresStore:
        return PostgresStore()

    di = (
        Container()
        .bind(primary, provides=PostgresStore, tag='primary')
        .bind(backup, provides=PostgresStore, tag='backup')
        .alias(Store, to=PostgresStore, to_tag='backup')
        .freeze()
    )
    assert di.resolve(Store) is di.resolve(PostgresStore, tag='backup')
    assert di.resolve(Store) is not di.resolve(PostgresStore, tag='primary')


def test_an_alias_can_carry_its_own_tag() -> None:
    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore, tag='main').freeze()
    assert di.resolve(Store, tag='main') is di[PostgresStore]
    with pytest.raises(MissingProviderError):
        _ = di.resolve(Store)


def test_an_alias_may_target_another_alias() -> None:
    class Middle(Protocol):
        def get(self) -> str: ...

    di = Container().bind(PostgresStore).alias(Middle, to=PostgresStore).alias(Store, to=Middle).freeze()
    assert di.resolve(Store) is di[PostgresStore]


def test_an_alias_binds_a_token_key() -> None:
    store = Token[PostgresStore]('store')
    di = Container().bind(PostgresStore).alias(store, to=PostgresStore).freeze()
    assert di[store] is di[PostgresStore]


def test_an_alias_binds_a_string_key() -> None:
    di = Container().bind(PostgresStore).alias('store', to=PostgresStore).freeze()
    assert di.graph().node('store').shape is ProviderShape.ALIAS


def test_an_alias_leaves_teardown_with_the_target() -> None:
    events: list[str] = []

    class Pool: ...

    def pool() -> Generator[Pool]:
        events.append('open')
        yield Pool()
        events.append('close')

    di = Container().bind(pool).alias(Store, to=Pool).freeze()
    _ = di.resolve(Store)
    _ = di[Pool]
    di.close()
    assert events == ['open', 'close']


def test_an_alias_reads_a_scope_value_target() -> None:
    class Principal:
        def __init__(self, name: str) -> None:
            self.name = name

    class Actor(Protocol):
        name: str

    di = Container().scope_value(Principal).alias(Actor, to=Principal).freeze()
    with di.scope() as frame:
        frame.provide(Principal, Principal('ana'))
        assert di.resolve(Actor).name == 'ana'


def test_an_alias_is_a_transient_node_in_the_graph() -> None:
    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
    node = di.graph().node(Store)
    assert node.shape is ProviderShape.ALIAS
    assert node.scope is Scope.TRANSIENT
    assert [edge.parameter for edge in node.dependencies] == ['target']


def test_a_registry_carries_aliases_into_a_container() -> None:
    registry = Registry('stores').bind(PostgresStore).alias(Store, to=PostgresStore)
    di = Container(registry).freeze()
    assert di.resolve(Store) is di[PostgresStore]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_alias.py`
Expected: FAIL for every test, `AttributeError: 'Container' object has no attribute 'alias'`.

- [ ] **Step 3: Add the registration method**

In `depin/_core/bindings.py`, insert this method into `BindingCollector` directly after `scope_value`:

```python
    def alias(
        self,
        key: ProviderKey,
        *,
        to: ProviderKey,
        tag: str | None = None,
        to_tag: str | None = None,
    ) -> Self:
        """Register ``key`` as a second name for an existing binding.

        Resolving the alias resolves the target and returns its value. The target
        keeps its own lifetime, its own cache entry, and its own teardown, so a
        singleton reached through an alias is still built once and torn down
        once, and both names return the same object.

        The alias caches nothing itself, which is why it takes no scope. It is an
        ordinary node in the validated graph: an unbound target, a duplicate
        alias, a cycle through an alias, and a singleton that reaches a scoped
        provider through one are all rejected by `Container.freeze()`, and the
        alias appears in `FrozenContainer.explain()` and in both graph exports.

        depin does not check that the target satisfies the alias key. A
        ``Protocol`` that is not ``runtime_checkable`` cannot be checked at all,
        and a structural alias between unrelated classes is legitimate.

        Args:
            key: The new name to register. A class, a `Token`, or a string.
            to: The binding to delegate to. May itself be an alias.
            tag: Disambiguator for the alias, matching the ``tag`` of a
                resolution or of an ``Annotated[..., Tag(...)]`` parameter.
            to_tag: The target's tag, when the target is registered under one.

        Returns:
            ``self``, for chaining.

        Example:
            ```pycon
            >>> from typing import Protocol
            >>> from depin import Container
            >>> class Store(Protocol):
            ...     def get(self) -> str: ...
            >>> class PostgresStore:
            ...     def get(self) -> str:
            ...         return 'pg'
            >>> di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
            >>> di.resolve(Store) is di[PostgresStore]
            True

            ```
        """
        self._records.append(
            BindRecord(
                source=AliasBinding(key=key, target=to, target_tag=to_tag),
                scope=Scope.TRANSIENT,
                provides=None,
                tag=tag,
            )
        )
        return self
```

Add `AliasBinding` and `ProviderKey` to the module's `from depin._core.spec import ...` line, keeping the names sorted.

- [ ] **Step 4: Build the spec from the record**

In `depin/_core/providers.py`, insert this branch into `_record_to_spec`, directly after the `is_frame_binding` branch:

```python
    if is_alias_binding(rec.source):
        alias = rec.source
        return ProviderSpec(
            key=as_provider_key(alias.key),
            tag=rec.tag,
            source=alias,
            scope=rec.scope,
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

Add `ALIAS_PARAM` and `is_alias_binding` to the module's `from depin._core.spec import (...)` block, keeping it sorted.

- [ ] **Step 5: Return the resolved target at construction**

In `depin/_core/construct.py`, insert this case into `sync`'s `match`, directly after the `ProviderShape.FRAME` case:

```python
        case ProviderShape.ALIAS:
            return as_alias_target(kwargs, key)
```

Add `as_alias_target` to the module's `from depin._core.typeguards import (...)` block, keeping it sorted.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_alias.py tests/unit/test_construct.py`
Expected: PASS, including the guard test written in Task 2 Step 6.

- [ ] **Step 7: Confirm the doctest on `alias` runs**

Run: `uv run pytest --doctest-modules depin/_core/bindings.py`
Expected: PASS.

- [ ] **Step 8: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add depin/_core/bindings.py depin/_core/providers.py depin/_core/construct.py \
  tests/unit/test_alias.py tests/unit/test_construct.py
git commit -m "feat: add Container.alias for a second name on one binding"
```

---

### Task 4: Prove an alias is validated at `freeze()`

The spec's central claim is that an alias needs no new validation because it is an ordinary node. That is only true if it is tested. This task adds the tests; it changes no library code. If any of them requires a change to `graph.py`, the design is wrong and the task stops to report it rather than patching around it.

**Files:**

- Modify: `tests/unit/test_graph_validation.py`
- Modify: `tests/unit/test_frozen_async.py`

- [ ] **Step 1: Write the validation tests**

Append to `tests/unit/test_graph_validation.py`:

```python
def test_an_alias_to_an_unbound_target_is_rejected_at_freeze() -> None:
    class Store: ...

    class PostgresStore: ...

    with pytest.raises(MissingProviderError, match='PostgresStore'):
        _ = Container().alias(Store, to=PostgresStore).freeze()


def test_two_aliases_under_one_identity_are_rejected() -> None:
    class Store: ...

    class First: ...

    class Second: ...

    builder = Container().bind(First).bind(Second).alias(Store, to=First).alias(Store, to=Second)
    with pytest.raises(DuplicateProviderError, match='Store'):
        _ = builder.freeze()


def test_an_alias_over_a_bound_key_is_rejected() -> None:
    class Store: ...

    class PostgresStore: ...

    builder = Container().bind(Store).bind(PostgresStore).alias(Store, to=PostgresStore)
    with pytest.raises(DuplicateProviderError, match='Store'):
        _ = builder.freeze()


def test_a_cycle_through_an_alias_is_rejected() -> None:
    class First: ...

    class Second: ...

    builder = Container().alias(First, to=Second).alias(Second, to=First)
    with pytest.raises(CircularDependencyError, match='cycle detected'):
        _ = builder.freeze()


def test_a_singleton_reaching_a_scoped_target_through_an_alias_is_captive() -> None:
    class Store: ...

    class Session: ...

    class Service:
        def __init__(self, store: Store) -> None:
            del store

    builder = (
        Container().bind(Session, scope=Scope.SCOPED).alias(Store, to=Session).bind(Service, scope=Scope.SINGLETON)
    )
    with pytest.raises(CaptiveDependencyError) as excinfo:
        _ = builder.freeze()
    assert 'Service -> Store -> Session' in str(excinfo.value).replace(
        'test_a_singleton_reaching_a_scoped_target_through_an_alias_is_captive.<locals>.', ''
    )
```

`fmt_key` renders a class declared inside a function by `__qualname__`, so the raw chain reads `test_….<locals>.Service -> test_….<locals>.Store -> …`. The assertion strips that prefix rather than restating it three times.

Add any of `CaptiveDependencyError`, `CircularDependencyError`, `DuplicateProviderError`, `MissingProviderError`, `Scope` that the file does not already import.

- [ ] **Step 2: Run them**

Run: `uv run pytest tests/unit/test_graph_validation.py -k alias`
Expected: PASS with no library change. A failure here is a design defect: report it, do not patch `graph.py` to accommodate the alias.

- [ ] **Step 3: Write the async-propagation tests**

Append to `tests/unit/test_frozen_async.py`:

```python
@pytest.mark.asyncio
async def test_an_alias_to_an_async_target_resolves_under_aresolve() -> None:
    class Store: ...

    class Backend: ...

    async def make() -> Backend:
        return Backend()

    di = Container().bind(make, provides=Backend).alias(Store, to=Backend).freeze()
    assert await di.aresolve(Store) is await di.aresolve(Backend)


def test_an_alias_to_an_async_target_is_rejected_by_resolve() -> None:
    class Store: ...

    class Backend: ...

    async def make() -> Backend:
        return Backend()

    di = Container().bind(make, provides=Backend).alias(Store, to=Backend).freeze()
    with pytest.raises(AsyncInSyncContextError, match='Store requires async resolution'):
        _ = di.resolve(Store)
```

The second assertion is the point: the error names the alias, not the target, because `_with_async_flags` marks the alias node itself.

- [ ] **Step 4: Run them**

Run: `uv run pytest tests/unit/test_frozen_async.py -k alias`
Expected: PASS with no library change.

- [ ] **Step 5: Run the gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_graph_validation.py tests/unit/test_frozen_async.py
git commit -m "test: pin freeze-time validation of alias bindings"
```

---

### Task 5: The alias in the diagnostics and the type surface

**Files:**

- Modify: `tests/unit/test_graph_render.py`
- Modify: `tests/unit/test_graph_properties.py`
- Modify: `tests/typing/test_conformance.py`
- Modify: `tests/unit/test_public_api.py`

- [ ] **Step 1: Write the renderer tests**

Append to `tests/unit/test_graph_render.py`:

```python
def test_explain_renders_an_alias_and_its_target() -> None:
    class Store: ...

    class PostgresStore: ...

    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
    prefix = 'test_explain_renders_an_alias_and_its_target.<locals>.'
    assert di.explain(Store).replace(prefix, '') == (
        'Store  [transient, alias]\n  target: PostgresStore  [singleton, class]'
    )


def test_the_exports_carry_the_alias_edge() -> None:
    class Store: ...

    class PostgresStore: ...

    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
    assert '[label="target"]' in di.graph().dot()
    assert '-->|target|' in di.graph().mermaid()
    assert 'transient, alias' in di.graph().mermaid()
```

Print the real value once before locking the first assertion:

Run: `uv run python -c "$(cat <<'PY'
from depin import Container
class Store: ...
class PostgresStore: ...
print(Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze().explain(Store))
PY
)"`

and correct the expected string to what it prints if the two differ.

- [ ] **Step 2: Run them**

Run: `uv run pytest tests/unit/test_graph_render.py -k alias`
Expected: PASS.

- [ ] **Step 3: Extend the generative model with aliases**

Read `tests/unit/test_graph_properties.py` and locate the Hypothesis strategy that builds a random `Container`. Add an alias to the generated graph: for a graph of `n` bound keys, draw a subset of indices and register `alias(AliasKey_i, to=Key_i)` for each, where `AliasKey_i` is a fresh class created for the purpose. The existing invariants then cover aliases without a new property being written:

- `freeze()` either raises a `DepinError` or returns a valid topological order;
- every spec in the plan appears as exactly one node;
- every edge either indexes a node or has `satisfied=False`;
- each export emits exactly `len(nodes)` node declarations.

If the file's strategy does not admit a second key per node without restructuring, add a separate, smaller strategy for aliased graphs rather than reshaping the existing one.

- [ ] **Step 4: Run the property suite**

Run: `uv run pytest tests/unit/test_graph_properties.py`
Expected: PASS. A falsifying example here is a real defect in the alias design; report it rather than narrowing the strategy.

- [ ] **Step 5: Add the conformance cases**

Append to `tests/typing/test_conformance.py`:

```python
def test_alias_keeps_the_builder_type_and_the_resolved_type() -> None:
    class Store(Protocol):
        def get(self) -> str: ...

    class MemStore:
        def get(self) -> str:
            return 'v'

    builder = Container().bind(MemStore)
    assert_type(builder.alias(Store, to=MemStore), Container)
    di = builder.freeze()
    assert_type(di.resolve(Store), Store)
    assert_type(di[Store], Store)
```

`Container` rather than `Self` is what `assert_type` sees at a concrete call site, because `Self` binds to the receiver's type.

- [ ] **Step 6: Pin the shape enum on the public surface**

Append to `tests/unit/test_public_api.py`:

```python
def test_provider_shape_is_exported_with_the_alias_member() -> None:
    assert depin.ProviderShape.ALIAS.value == 'alias'
    assert len(depin.ProviderShape) == 10
```

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
git add tests/unit/test_graph_render.py tests/unit/test_graph_properties.py \
  tests/typing/test_conformance.py tests/unit/test_public_api.py
git commit -m "test: cover aliases in the diagnostics and type surface"
```

---

### Task 6: Document, demonstrate, integrate, and benchmark

**Files:**

- Modify: `docs/guide/composition.md`
- Create: `examples/aliasing/__init__.py`
- Create: `examples/aliasing/main.py`
- Modify: `examples/README.md`
- Modify: `tests/integration/test_examples.py`
- Modify: `tests/integration/test_fastapi_ext.py`
- Modify: `benchmarks/test_resolution.py`

- [ ] **Step 1: Add the guide section**

In `docs/guide/composition.md`, insert this section directly before the `## Where to freeze` heading:

````markdown
## Aliases

`provides=` and `@provides` register a class *under* another key. An alias goes
the other way: it adds a second name to a binding that already exists.

```pycon
>>> from typing import Protocol
>>> from depin import Container
>>> class Store(Protocol):
...     def get(self) -> str: ...
>>> class PostgresStore:
...     def get(self) -> str:
...         return 'pg'
>>> di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
>>> di.resolve(Store) is di[PostgresStore]
True

```

Both names reach one instance. The target keeps its lifetime, its cache entry,
and its teardown, so a singleton is still built once and closed once no matter
which name asked for it.

The alias itself is a transient indirection, and `explain()` says so:

```pycon
>>> print(di.explain(Store))
Store  [transient, alias]
  target: PostgresStore  [singleton, class]

```

`transient` describes the alias node, which caches nothing — not the target,
which is the singleton on the line below it. Because the alias is a real node,
it participates in validation like any other: an unbound target, a duplicate
name, a cycle, and a singleton that reaches a scoped provider through an alias
are all rejected by `freeze()`.

depin does not verify that the target satisfies the alias key. A `Protocol` that
is not `runtime_checkable` cannot be checked at runtime, and a structural alias
between two unrelated classes is a legitimate thing to write.
````

- [ ] **Step 2: Verify the guide's doctests**

Run: `uv run pytest --doctest-glob='*.md' docs/guide/composition.md`
Expected: PASS. A mismatch means the documented output is wrong; correct the document against the renderer, not the other way round.

- [ ] **Step 3: Write the example**

Create `examples/aliasing/__init__.py`, empty.

Create `examples/aliasing/main.py`:

```python
"""One instance under two names, and what the graph says about it.

Run with ``python -m examples.aliasing.main``.
"""

from typing import Protocol

from depin import Container, FrozenContainer


class Store(Protocol):
    def get(self, key: str) -> str: ...


class Cache(Protocol):
    def get(self, key: str) -> str: ...


class RedisStore:
    """Serves both roles in this application, and is built exactly once."""

    def __init__(self) -> None:
        self.reads: list[str] = []

    def get(self, key: str) -> str:
        self.reads.append(key)
        return f'value-for-{key}'


class Page:
    def __init__(self, store: Store, cache: Cache) -> None:
        self.store = store
        self.cache = cache

    def render(self) -> str:
        return f'{self.cache.get("head")} + {self.store.get("body")}'


def build() -> FrozenContainer:
    return Container().bind(RedisStore).alias(Store, to=RedisStore).alias(Cache, to=RedisStore).bind(Page).freeze()


def main() -> None:
    di = build()
    page = di[Page]

    print(page.render())

    # Two names, one object: the alias node caches nothing, so the cache
    # identity on both paths is RedisStore's own.
    print('same instance:', page.store is page.cache is di[RedisStore])
    print(di[RedisStore].reads)

    print(di.explain(Page))


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run the example**

Run: `uv run python -m examples.aliasing.main`
Expected: it prints the rendered page, `same instance: True`, the two recorded reads, and the resolution tree.

- [ ] **Step 5: List the example**

In `examples/README.md`, add this row to the table, after the `testing` row:

```markdown
| [`aliasing`](aliasing/main.py) | `python -m examples.aliasing.main` | `alias()` giving one instance two names, and `explain()` on the result. |
```

- [ ] **Step 6: Execute the example from the suite**

Append to `tests/integration/test_examples.py`:

```python
def test_aliasing_example_serves_one_instance_under_both_names() -> None:
    di = build_aliasing()
    page = di[Page]
    assert page.store is page.cache is di[RedisStore]
    assert page.render() == 'value-for-head + value-for-body'
    assert di[RedisStore].reads == ['head', 'body']
```

Add to the imports at the top of that file, in the sorted block:

```python
from examples.aliasing.main import Page, RedisStore
from examples.aliasing.main import build as build_aliasing
```

- [ ] **Step 7: Exercise an alias through the FastAPI extension**

Append to `tests/integration/test_fastapi_ext.py`:

```python
@pytest.mark.asyncio
async def test_a_route_resolves_a_request_scoped_binding_through_an_alias() -> None:
    class Session:
        def __init__(self) -> None:
            self.label = 'session'

    class Unit(Protocol):
        label: str

    frozen = Container().bind(Session, scope=Scope.SCOPED).alias(Unit, to=Session).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/unit')
    async def _unit(unit: Inject[Unit], session: Inject[Session]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {'same': unit is session}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        assert (await client.get('/unit')).json() == {'same': True}
```

Add `Protocol` to the file's `typing` import if it is not already there. The `reportUnusedFunction` suppression is the shape every route in this file already uses.

- [ ] **Step 8: Benchmark the indirection**

Append to `benchmarks/test_resolution.py`:

```python
def test_resolve_a_cached_singleton_through_an_alias(benchmark: Benchmark) -> None:
    """The alias hop, measured against `test_resolve_a_cached_singleton`.

    The two cases resolve the same target from the same graph; the difference
    between them is the cost of the extra transient node.
    """

    class Aliased(Protocol): ...

    container, leaf = build_chain(100)
    frozen = container.alias(Aliased, to=leaf).freeze()
    _ = frozen.resolve(Aliased)

    def resolve() -> object:
        return frozen.resolve(Aliased)

    _ = benchmark(resolve)
```

`Protocol` is already imported in that file.

- [ ] **Step 9: Run the benchmarks**

Run: `uv run --group bench pytest benchmarks --benchmark-only`
Expected: the pre-existing cases within noise of the 0.7.0 baseline, and the new case reported. Record the mean of the two singleton cases for the evidence file.

- [ ] **Step 10: Run the gates plus the docs build**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add docs/guide/composition.md examples benchmarks/test_resolution.py \
  tests/integration/test_examples.py tests/integration/test_fastapi_ext.py
git commit -m "docs: document and demonstrate key aliasing"
```

---

### Task 7: Final verification and the pull request

**Files:**

- Create: `specs/evidence/2026-08-31-step-3-provides-aliasing.md`

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
Expected: at or above 95% over `depin/`, and no uncovered branch in the changed modules. Cover any gap with a test rather than lowering the bar.

- [ ] **Step 3: Run the mutation gate over the changed modules only**

```bash
uv run mutmut run
uv run python -m scripts.check_mutation_threshold
```

Expected: at least 95% killed. The full run takes tens of minutes and the CI `mutation` job is the authority; if the local baseline collection fails under CPU contention, do not edit `--timeout` in `pyproject.toml` — record the failure and let CI decide. Treat any survivor CI reports as a missing assertion.

- [ ] **Step 4: Confirm the suppression count went down**

Run: `grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin examples | wc -l`
Expected: three fewer than on `main` at `a974339`, and no occurrence of `type-abstract`.

- [ ] **Step 5: Record the evidence**

Create `specs/evidence/2026-08-31-step-3-provides-aliasing.md` in the shape of `specs/evidence/2026-08-30-step-2-diagnostics.md`: the exact commands from Steps 1 to 4 with their relevant output, the coverage figure, the mutation score, the benchmark means for the alias case and the direct case, and the three checker measurements that decided the `provides` signature.

- [ ] **Step 6: Commit and open the pull request**

```bash
git add specs/evidence/2026-08-31-step-3-provides-aliasing.md
git commit -m "docs: record cycle 1 verification evidence"
git push -u origin feat/step-3-provides-aliasing
```

Open the pull request with the title `feat: add key aliasing and repair the provides signature` and a body in the shape the repository's recent pull requests use: a Summary of three or four bullets, a Verification list of every command run, and the checklist from the pull-request template with each box ticked. The title carries `feat:`, which is what makes `release-please` cut 0.8.0.

- [ ] **Step 7: Confirm CI is green**

Run: `gh pr checks --watch`
Expected: all sixteen checks pass, on 3.12, 3.13, 3.14, 3.13t, and 3.14t.

## Self-review

**Spec coverage.** `provides` signature — Task 1. Suppression and documentation removal — Task 1 Steps 5 to 9. `alias` public surface — Task 3 Step 3. Data model — Task 2. Semantics table — Task 3 (identity, lifetimes, tags, chaining, teardown), Task 4 (duplicates, missing, cycles, captive, async). Errors table — Task 1 Step 1, Task 2 Step 6, Task 4. Module layout — Tasks 1 to 3; that `graph.py`, `frozen.py`, `diagnostics.py`, and `render.py` stay untouched is asserted by Task 4 Step 2 and Task 5 Step 2 passing without a library change. Verification — Tasks 1 to 7. Acceptance criteria — Task 1 Steps 6 and 7, Task 3 Step 6, Task 4, Task 5, Task 6 Steps 4 and 9, Task 7.

**Type consistency.** `AliasBinding(key, target, target_tag)`, `is_alias_binding`, `ALIAS_PARAM`, `ProviderShape.ALIAS`, and `as_alias_target` are spelled the same in every task that uses them. The public method is `alias(key, *, to, tag, to_tag)` in the plan, the docstring, the guide, the example, and every test. The alias parameter name is `'target'` in `ALIAS_PARAM`, in the `explain()` expectation, and in both export assertions.

**Known verification points.** Three assertions depend on exact rendered text: the `explain()` tree in Task 5 Step 1, the captive chain in Task 4 Step 1, and the example's printed output in Task 6 Step 4. The first carries a step that prints the real value before the assertion is locked; the second strips the `<locals>` prefix rather than restating it; the third is asserted on structure, not on the printed lines.

**Ordering risk.** Task 2 leaves `tests/unit/test_construct.py` red on purpose and excludes it from its commit, because the `ALIAS` case that turns it green belongs to Task 3. Every other task commits a green tree. If Task 2 and Task 3 are executed by separate workers, Task 3 must not start before Task 2 is committed.
