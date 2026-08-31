# Step 4, cycle 1 — decoration and conditional activation: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Container.decorate(Store, wrapper)` wrap a registered binding without changing its lifetime, its cache entry, or its teardown position, and make `when=` keep a binding out of the plan entirely — for the 0.11.0 milestone.

**Architecture:** One new module, `depin/_core/decoration.py`. A decorator is not a new provider shape: it is an ordinary node of an existing shape whose parameters are what it depends on, which is the third time the alias pattern composes. `freeze()` moves the registered binding to `Underlying(key, 0)`, gives each wrapper a node of its own at the same scope, and lets the last wrapper occupy the public key; each wrapper's designated parameter is rewritten to point one layer down. `construct.py`, `diagnostics.py`, and every resolution path in `frozen.py` are therefore untouched. Conditional activation is one field on `BindRecord`, evaluated once per record inside `build_plan`, with inactive records dropped before they are introspected at all — that is what makes `when` safe for a binding that cannot be introspected in the deployment that switches it off. Their declared keys are still read, where they can be read without introspecting the provider, so a missing-provider message can say that a binding for the key exists but is inactive.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, Hypothesis, mutmut 3.7, pytest-benchmark, mkdocs-material with mkdocstrings, uv.

**Spec:** `specs/2026-08-31-step-4-decoration-conditional-design.md`

## Global constraints

Every task inherits these requirements from `AGENTS.md`, the approved roadmap, and the spec.

- The core keeps zero runtime dependencies. Nothing here adds a package to `[project.dependencies]` or to any dependency group.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `typing.Any`, `typing.cast`, `# type: ignore`, or `# pyright: ignore`. `depin/` carries exactly three suppressions today — `frozen.py:116`, `frozen.py:139`, `markers.py:129` — and must carry exactly those three when this cycle ends.
- Every exception raised by library code inherits `DepinError`. No bare `KeyError`, `TypeError`, `ValueError`, or `assert` in `depin/`.
- Data structures are `@dataclass(frozen=True, slots=True)`.
- New behaviour in `depin/_core/` is developed test-first: the failing test is written and observed failing before the implementation.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery. `reportPrivateUsage` forbids reading `FrozenContainer._plan` from a test; build plans with `build_plan(container.records())` instead.
- Public API additions carry Google-style docstrings that omit types from `Args:` / `Returns:` and include a doctest `Example:`. Doctests run in the default `pytest` invocation.
- `fmt_key` renders a class by `__qualname__`, so a class declared inside a test function appears as `test_x.<locals>.Name`, and a generic as `test_x.<locals>.Repo[test_x.<locals>.User]`. Print the real string before pinning any text assertion.
- `basedpyright --strict` has `reportUnnecessaryIsInstance`, `reportImplicitOverride`, and `reportMissingTypeArgument` enabled. `mypy --strict` additionally has `warn_unreachable` and `redundant-expr`, so a runtime guard whose annotation already excludes the rejected case must take `object` in a private helper rather than be suppressed, and an `is` comparison between statically unrelated types must bind its operands to `object`-typed locals first.
- `ruff` rejects unused imports; do not copy an import list from a snippet without checking what the file uses. Per-line waivers are acceptable where the test exercises exactly what the rule forbids: `# noqa: UP045` for the `typing.Optional` spelling, `# noqa: B010` for `setattr` on a frozen dataclass.
- Coverage over `depin/` stays at or above 95%. `depin/_core/scope.py`'s line inside `_Flight.wait_sync` reports as uncovered in roughly one run in two on any commit; run coverage twice before attributing a miss to this cycle.
- Property tests in `tests/unit/test_graph_properties.py` need `@settings(deadline=None)`.
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
| `depin/_core/spec.py` | `Condition`; `BindRecord.condition`; then `Underlying`, the `ProviderKey` widening, `fmt_key`; then `DecorateBinding`, `DecorationSpec`, `SpecSet`, `ResolutionPlan.inactive`. | 1, 2, 3, 4 |
| `depin/_core/bindings.py` | `when` on every registration method; then `decorate`. | 1, 4 |
| `depin/_core/providers.py` | Record partitioning and `is_active`; the declared-key reader; `DecorationSpec` construction; `_classes_within` over `Underlying`. | 1, 2, 4 |
| `depin/_core/graph.py` | `build_plan` over `SpecSet`; the inactive note in `format_missing`; the decoration fold. | 1, 2, 5 |
| `tests/unit/test_conditional.py` | Conditional activation end to end. | 1, 2 |
| `tests/unit/test_providers.py` | `build_specs` now returns a `SpecSet`. | 1 |
| `depin/_core/render.py` | `render_tree` and `_render_absent` carry the inactive set. | 2 |
| `depin/_core/frozen.py` | `explain()` passes `ResolutionPlan.inactive` to `render_tree`. | 2 |
| `depin/_core/typeguards.py` | `is_provider_key` admits `Underlying`. | 3 |
| `depin/__init__.py` | Exports `Underlying`. | 3 |
| `tests/unit/test_spec.py` | `Underlying` equality, hashing, and rendering. | 3 |
| `tests/unit/test_typeguards.py` | `is_provider_key` over `Underlying`. | 3 |
| `tests/unit/test_public_api.py` | `Underlying` in `__all__`. | 3 |
| `depin/_core/decoration.py` | **New.** The fold from provider specs plus decorations to plan nodes. | 5 |
| `tests/unit/test_decoration.py` | Decoration end to end, including the teardown-position criterion. | 5, 6 |
| `tests/unit/test_graph_validation.py` | Every row of the spec's Errors table. | 6 |
| `tests/unit/test_graph_render.py` | Decorated nodes in all three renderings; the inactive note in `explain()`. | 7 |
| `tests/unit/test_graph_properties.py` | `decorations` and `inactive` in the generative model. | 7 |
| `tests/typing/test_conformance.py` | `assert_type` over `decorate` and `when`. | 7 |
| `depin/_core/container.py` | `freeze()`'s `Raises:`; the `Container` docstring. | 8 |
| `docs/guide/composition.md` | Decoration and conditional bindings. | 8 |
| `docs/reference/diagnostics.md` | `Underlying`. | 8 |
| `examples/decoration/` | Runnable program. | 8 |
| `examples/conditional/` | Runnable program. | 8 |
| `examples/README.md` | Lists both. | 8 |
| `tests/integration/test_examples.py` | Executes both. | 8 |
| `tests/integration/test_fastapi_ext.py` | A decorated scoped provider and a conditional binding set. | 8 |
| `benchmarks/test_resolution.py` | Resolution through a decoration chain. | 8 |
| `benchmarks/test_diagnostics.py` | `freeze()` over a decorated graph. | 8 |
| `specs/evidence/2026-08-31-step-4-decoration-conditional.md` | The measured evidence. | 9 |

---

### Task 1: A binding under a condition

`when=` on every registration method, evaluated once per record inside `freeze()`. An inactive record is dropped before anything introspects it.

**Files:**

- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/bindings.py`
- Modify: `depin/_core/providers.py`
- Modify: `depin/_core/graph.py`
- Modify: `tests/unit/test_providers.py`
- Create: `tests/unit/test_conditional.py`

**Interfaces:**

- Produces: `Condition` and `BindRecord.condition` in `depin._core.spec`.
- Produces: `SpecSet` in `depin._core.spec` and `build_specs(records) -> SpecSet` in `depin._core.providers`.

- [ ] **Step 1: Write the failing behaviour tests**

Create `tests/unit/test_conditional.py`:

```python
"""Bindings under a predicate, decided inside `freeze()`."""

import pytest

from depin import Container, Registry, Scope, Token
from depin.errors import InvalidProviderError, MissingProviderError


def test_a_binding_with_a_true_condition_is_registered() -> None:
    class Cache: ...

    di = Container().bind(Cache, when=True).freeze()
    assert isinstance(di[Cache], Cache)


def test_a_binding_with_a_false_condition_is_absent() -> None:
    class Cache: ...

    di = Container().bind(Cache, when=False).freeze()
    with pytest.raises(MissingProviderError):
        _ = di[Cache]


def test_an_inactive_binding_is_not_a_node_of_the_graph() -> None:
    class Cache: ...

    di = Container().bind(Cache, when=False).freeze()
    assert di.graph().nodes == ()


def test_a_predicate_is_called_once_per_freeze() -> None:
    class Cache: ...

    calls: list[int] = []

    def predicate() -> bool:
        calls.append(1)
        return True

    container = Container().bind(Cache, when=predicate)
    _ = container.freeze()
    assert len(calls) == 1
    _ = container.freeze()
    assert len(calls) == 2


def test_a_predicate_is_not_called_before_freeze() -> None:
    class Cache: ...

    calls: list[int] = []

    def predicate() -> bool:
        calls.append(1)
        return True

    _ = Container().bind(Cache, when=predicate)
    assert calls == []


def test_two_bindings_for_one_key_are_switched_by_condition() -> None:
    class Store: ...

    class Postgres(Store): ...

    class Memory(Store): ...

    production = False
    di = (
        Container()
        .bind(Postgres, provides=Store, when=lambda: production)
        .bind(Memory, provides=Store, when=lambda: not production)
        .freeze()
    )
    assert isinstance(di.resolve(Store), Memory)


def test_an_inactive_binding_is_an_unsatisfied_dependency() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache) -> None: ...

    with pytest.raises(MissingProviderError):
        _ = Container().bind(Cache, when=False).bind(Service).freeze()


def test_an_inactive_dependency_is_excused_by_a_default() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache | None = None) -> None:
            self.cache = cache

    di = Container().bind(Cache, when=False).bind(Service).freeze()
    assert di[Service].cache is None


def test_an_inactive_dependency_is_excused_by_an_optional_annotation() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Cache, when=False).bind(Service).freeze()
    assert di[Service].cache is None


def test_every_registration_method_takes_a_condition() -> None:
    class Store: ...

    class Handler: ...

    class Request: ...

    port = Token[int]('port')
    container = (
        Container()
        .bind(Store, when=False)
        .value(port, 1, when=False)
        .scope_value(Request, when=False)
        .alias(Handler, to=Store, when=False)
        .collect(Handler, [Store], when=False)
    )
    assert container.freeze().graph().nodes == ()


def test_a_scope_decorator_takes_a_condition() -> None:
    container = Container()

    @container.singleton(when=False)
    class Cache: ...

    @container.scoped(when=False)
    class Session: ...

    @container.transient(when=False)
    class Ticket: ...

    assert container.freeze().graph().nodes == ()


def test_a_registry_carries_conditions_into_a_container() -> None:
    class Cache: ...

    registry = Registry('infra').bind(Cache, when=False)
    assert Container(registry).freeze().graph().nodes == ()


def test_a_condition_that_is_neither_a_bool_nor_a_callable_is_rejected() -> None:
    class Cache: ...

    container = Container().bind(Cache, when=3)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidProviderError, match='binding condition'):
        _ = container.freeze()


def test_an_inactive_binding_is_never_introspected() -> None:
    def broken(dependency: 'Nowhere') -> object:  # noqa: F821
        return dependency

    di = Container().bind(broken, provides=Scope, when=False).freeze()
    assert di.graph().nodes == ()
```

Run: `uv run pytest tests/unit/test_conditional.py`
Expected: every test fails, most on `unexpected keyword argument 'when'`.

- [ ] **Step 2: Add the condition to the record**

In `depin/_core/spec.py`, extend the `collections.abc` import to include `Callable`, then add above `BindRecord`:

```python
type Condition = bool | Callable[[], bool]
"""What `when=` accepts on a registration.

A ``bool`` is read where it is written. A callable is called once per
`Container.freeze()`, with no arguments, and its result is read for truth — so a
predicate over configuration or the environment is evaluated when the graph is
built, not when a value is resolved.
"""
```

and give `BindRecord` a final field:

```python
@dataclass(frozen=True, slots=True)
class BindRecord:
    source: object
    scope: Scope
    provides: type[object] | None
    tag: str | None
    condition: Condition | None = None
```

- [ ] **Step 3: Thread `when` through every registration method**

In `depin/_core/bindings.py`, import `Condition` from `depin._core.spec`, widen the private bind alias, and add the keyword to each method.

```python
type _BindFn = Callable[
    [type[object] | Callable[..., object], Scope, type[object] | None, str | None, Condition | None],
    None,
]
```

`ScopeDecorator` gains a `_when` slot and passes it on:

```python
__slots__ = ('_bind', '_provides', '_scope', '_tag', '_when')


def __init__(
    self,
    bind: _BindFn,
    scope: Scope,
    provides: type[object] | None,
    tag: str | None,
    when: Condition | None,
) -> None:
    self._bind = bind
    self._scope = scope
    self._provides = provides
    self._tag = tag
    self._when = when
```

and in `__call__`, replace the bind call with `self._bind(target, self._scope, self._provides, self._tag, self._when)`.

`_record_bind` gains the same trailing parameter and forwards it to `BindRecord(condition=when)`. `bind`, `value`, `scope_value`, `alias`, and `collect` each take `when: Condition | None = None` as the last keyword-only argument and pass `condition=when` into the `BindRecord` they append. `singleton`, `scoped`, and `transient` each take `when: Condition | None = None` and pass it as the fifth argument of `ScopeDecorator`.

Every one of these docstrings gains one `Args:` line, phrased identically:

```
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.
```

`value` has no `Args:` section today; give it one covering `token`, `value`, and `when`.

- [ ] **Step 4: Add the spec set**

In `depin/_core/spec.py`, below `ProviderSpec`, add:

```python
@dataclass(frozen=True, slots=True)
class SpecSet:
    """What `build_specs` reads out of a set of records.

    Decorations are kept apart from providers because a decorator claims no key
    of its own until `depin._core.decoration` knows how many decorators target
    the same binding. `inactive` names the keys that a condition kept out, so a
    missing-provider message can say so.
    """

    providers: tuple[ProviderSpec, ...]
    inactive: frozenset[Ident]
```

`DecorationSpec` and the `decorations` field arrive in Task 4; leave them out here so this task's tree is green on its own.

Give `ResolutionPlan` the same set:

```python
@dataclass(frozen=True, slots=True)
class ResolutionPlan:
    order: tuple[ProviderSpec, ...]
    by_key: Mapping[tuple[ProviderKey, str | None], ProviderSpec]
    inactive: frozenset[Ident] = frozenset()
```

- [ ] **Step 5: Partition the records**

In `depin/_core/providers.py`, import `SpecSet` and `Ident` from `depin._core.spec`, then replace `build_specs`:

```python
def build_specs(records: Iterable[BindRecord]) -> SpecSet:
    """Convert every active record into a spec, resolving forward references between them.

    A record whose condition does not hold is dropped before anything reads its
    shape or its annotations, which is what makes `when` usable on a binding
    that cannot be introspected in the deployment that switches it off.
    """
    active, inactive = _partition(records)
    localns = _registered_classes(active)
    return SpecSet(
        providers=tuple(_record_to_spec(rec, localns) for rec in active),
        inactive=frozenset(_inactive_idents(inactive, localns)),
    )


def _partition(records: Iterable[BindRecord]) -> tuple[tuple[BindRecord, ...], tuple[BindRecord, ...]]:
    active: list[BindRecord] = []
    inactive: list[BindRecord] = []
    for rec in records:
        target = active if is_active(rec) else inactive
        target.append(rec)
    return tuple(active), tuple(inactive)


def is_active(rec: BindRecord) -> bool:
    """Whether a record's condition admits it into the plan.

    Raises:
        InvalidProviderError: The condition is neither a bool nor a callable.
    """
    # Annotated `object` rather than `Condition | None`: the guard has to reject
    # a value an untyped caller passed, and a checker that trusts the annotation
    # reads the final branch as unreachable.
    condition: object = rec.condition
    if condition is None:
        return True
    if isinstance(condition, bool):
        return condition
    if callable(condition):
        return bool(condition())
    raise InvalidProviderError(
        f'cannot use {condition!r} as a binding condition: `when` takes a bool, or a callable '
        'of no arguments returning one, which depin calls inside freeze().'
    )
```

`_inactive_idents` arrives in Task 2; for now define it as returning nothing, with the comment naming the task that fills it in:

```python
def _inactive_idents(records: Iterable[BindRecord], localns: dict[str, object]) -> Iterable[Ident]:
    return ()
```

Do not leave that stub in place beyond Task 2.

- [ ] **Step 6: Read the spec set in `build_plan`**

In `depin/_core/graph.py`:

```python
def build_plan(records: Iterable[BindRecord]) -> ResolutionPlan:
    specs = build_specs(records)
    _check_duplicates(specs.providers)
    by_key = _index(specs.providers)
    _check_missing(specs.providers, by_key)
    order = _toposort(specs.providers, by_key)
    _check_captive(order, by_key)
    resolved = tuple(_with_async_flags(order, by_key))
    return ResolutionPlan(order=resolved, by_key=_index(resolved), inactive=specs.inactive)
```

Extend the docstring's `Raises:` with:

```
        InvalidProviderError: A binding lacks the type information to infer a key,
            or carries a condition that is neither a bool nor a callable.
```

- [ ] **Step 7: Update the direct callers in the unit suite**

`tests/unit/test_providers.py` calls `build_specs` in 42 places. Each call now yields a `SpecSet`; append `.providers` at every call site and nowhere else. Do not change what any of those tests assert.

Run: `uv run pytest tests/unit/test_providers.py`
Expected: unchanged pass count.

- [ ] **Step 8: Run the new tests**

Run: `uv run pytest tests/unit/test_conditional.py`
Expected: all pass.

- [ ] **Step 9: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "feat: register a binding under a condition"
```

---

### Task 2: Name an inactive binding in the missing-provider message

A key that only an inactive binding declares reads as simply absent. This task makes `freeze()` and `explain()` both say that a binding exists and its condition did not hold.

**Files:**

- Modify: `depin/_core/providers.py`
- Modify: `depin/_core/graph.py`
- Modify: `depin/_core/render.py`
- Modify: `depin/_core/frozen.py`
- Modify: `tests/unit/test_conditional.py`

**Interfaces:**

- Produces: `format_missing(..., inactive: bool)` in `depin._core.graph`.
- Consumes: `ResolutionPlan.inactive` from Task 1.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_conditional.py`:

```python
def test_a_missing_inactive_key_is_named_as_inactive() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache) -> None: ...

    container = Container().bind(Cache, when=False).bind(Service)
    with pytest.raises(MissingProviderError) as error:
        _ = container.freeze()
    assert 'registered but inactive' in str(error.value)


def test_a_missing_key_with_no_inactive_binding_is_not_named_as_inactive() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache) -> None: ...

    with pytest.raises(MissingProviderError) as error:
        _ = Container().bind(Service).freeze()
    assert 'registered but inactive' not in str(error.value)


def test_explain_and_freeze_report_an_inactive_key_alike() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache) -> None: ...

    container = Container().bind(Cache, when=False).bind(Service)
    with pytest.raises(MissingProviderError) as error:
        _ = container.freeze()
    frozen = Container().bind(Cache, when=False).freeze()
    assert 'registered but inactive' in frozen.explain(Cache)
    assert fmt_key(Cache) in str(error.value)


def test_an_inactive_factory_key_is_named_from_its_return_annotation() -> None:
    class Cache: ...

    def build_cache() -> Cache:
        return Cache()

    frozen = Container().bind(build_cache, when=False).freeze()
    assert 'registered but inactive' in frozen.explain(Cache)


def test_an_inactive_alias_key_is_named() -> None:
    class Store: ...

    class Reader: ...

    frozen = Container().bind(Store).alias(Reader, to=Store, when=False).freeze()
    assert 'registered but inactive' in frozen.explain(Reader)


def test_an_inactive_value_token_is_named() -> None:
    port = Token[int]('port')
    frozen = Container().value(port, 1, when=False).freeze()
    assert 'registered but inactive' in frozen.explain(port)


def test_an_inactive_collection_key_is_named() -> None:
    class Handler: ...

    frozen = Container().collect(Handler, [], when=False).freeze()
    assert 'registered but inactive' in frozen.explain(list[Handler])
```

Add `from depin._core.spec import fmt_key` to the module's imports.

Run: `uv run pytest tests/unit/test_conditional.py -k inactive`
Expected: the seven new tests fail.

- [ ] **Step 2: Read the declared key of an inactive record**

Replace the `_inactive_idents` stub in `depin/_core/providers.py`:

```python
def _inactive_idents(records: Iterable[BindRecord], localns: dict[str, object]) -> Iterable[Ident]:
    for rec in records:
        key = _declared_key(rec, localns)
        if key is not None:
            yield (key, rec.tag)


def _declared_key(rec: BindRecord, localns: dict[str, object]) -> ProviderKey | None:
    """The key an inactive record would have claimed, where it is readable without introspecting the provider.

    Used only to tell a caller that a key they are missing is registered behind
    a condition that did not hold. It never raises: a record whose key could
    only come from an annotation that does not resolve contributes nothing, and
    is simply not named in the note.
    """
    source = rec.source
    if is_value_binding(source):
        return source.token
    if is_frame_binding(source):
        return source.key
    if is_alias_binding(source):
        return source.key if is_provider_key(source.key) else None
    if is_collection_binding(source):
        element = source.element
        return collection_key(element) if is_provider_key(element) else None
    if rec.provides is not None:
        return rec.provides
    if isinstance(source, type):
        attr = get_provides(source)
        return attr if attr is not None else source
    if not callable(source):
        return None
    returned = _safe_type_hints(source, localns).get('return')
    if detect_shape(source) in _UNWRAP_SHAPES:
        arguments = get_args(returned)
        returned = arguments[0] if arguments else None
    return returned if is_provider_key(returned) else None
```

`detect_shape` is reached only after `callable(source)` holds, so it cannot raise here. Import `ProviderKey` and `is_provider_key` if they are not already imported in the module.

- [ ] **Step 3: Carry the note into the shared message**

In `depin/_core/graph.py`, give `format_missing` a keyword-only flag and thread the set through `_check_missing`:

```python
def format_missing(
    key: ProviderKey,
    chain: tuple[ProviderKey, ...],
    owner: ProviderKey,
    param_name: str,
    *,
    inactive: bool = False,
) -> str:
    """The message `build_plan` raises for an unsatisfied parameter.

    Also used by `depin._core.render` for a key that `explain()` is asked about
    and no binding provides, so the two paths report one chain in one wording —
    the note about an inactive conditional binding included.
    """
    suggestions = suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    note = '; a conditional binding for this key is registered but inactive' if inactive else ''
    return (
        f'no provider for {fmt_key(key)} '
        f'(required by {fmt_key(owner)}.{param_name}; '
        f'resolution chain: {fmt_chain((*chain, key))}){note}{extra}'
    )
```

`_check_missing` gains a third parameter `inactive: frozenset[Ident]`, defaulting to nothing, and passes `inactive=ident in inactive` when it builds each line. `build_plan` passes `specs.inactive`.

- [ ] **Step 4: Carry the note into `explain()`**

In `depin/_core/render.py`, `render_tree` and `_render_absent` each gain a trailing `inactive: frozenset[Ident]` parameter. `_render_absent` passes `inactive=(key, tag) in inactive` to `format_missing`, and appends the same note to the bare line it produces when no provider requires the key:

```python
def _render_absent(
    graph: DependencyGraph,
    key: ProviderKey,
    tag: str | None,
    inactive: frozenset[Ident],
) -> str:
    is_inactive = (key, tag) in inactive
    required = _deepest_requirement(graph, key, tag)
    if required is not None:
        chain, owner, parameter = required
        return format_missing(key, chain, owner, parameter, inactive=is_inactive)
    suggestions = suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    note = '; a conditional binding for this key is registered but inactive' if is_inactive else ''
    return f'no provider for {fmt_key(key)} (tag={tag!r}){note}{extra}'
```

The note text appears in two places. Bind it once, as a module-level constant in `depin/_core/graph.py`, and import it into `render.py`:

```python
INACTIVE_NOTE: Final[str] = '; a conditional binding for this key is registered but inactive'
```

Use it in both functions rather than repeating the literal.

- [ ] **Step 5: Pass the set from the container**

In `depin/_core/frozen.py`, `explain()` ends with

```python
        return render_tree(self.graph(), key, tag, self._plan.inactive)
```

and its docstring gains one sentence after the paragraph about an absent key:

```
        When the key is registered behind a condition that did not hold, the
        line says so, in the same wording `Container.freeze()` uses.
```

- [ ] **Step 6: Run the tests and gates, then commit**

Run: `uv run pytest`
Expected: all pass.

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "feat: name an inactive binding in the missing-provider message"
```

---

### Task 3: `Underlying`, the key an inner form moves to

**Files:**

- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/typeguards.py`
- Modify: `depin/__init__.py`
- Modify: `tests/unit/test_spec.py`
- Modify: `tests/unit/test_typeguards.py`
- Modify: `tests/unit/test_public_api.py`

**Interfaces:**

- Produces: `depin.Underlying`, and `ProviderKey` widened by one member.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_spec.py`:

```python
def test_underlying_compares_and_hashes_by_value() -> None:
    class Store: ...

    assert Underlying(Store, 0) == Underlying(Store, 0)
    assert hash(Underlying(Store, 0)) == hash(Underlying(Store, 0))
    assert Underlying(Store, 0) != Underlying(Store, 1)


def test_underlying_nests() -> None:
    class Store: ...

    assert Underlying(Underlying(Store, 0), 1) == Underlying(Underlying(Store, 0), 1)


def test_an_undecorated_key_renders_as_undecorated() -> None:
    class Store: ...

    assert fmt_key(Underlying(Store, 0)) == f'{Store.__qualname__} (undecorated)'


def test_an_intermediate_layer_renders_with_its_depth() -> None:
    class Store: ...

    assert fmt_key(Underlying(Store, 2)) == f'{Store.__qualname__} (decorated x2)'


def test_an_underlying_generic_key_renders_through_fmt_key() -> None:
    class Handler: ...

    rendered = fmt_key(Underlying(list[Handler], 0))
    assert rendered == f'list[{Handler.__qualname__}] (undecorated)'
```

Append to `tests/unit/test_typeguards.py`:

```python
def test_an_underlying_key_is_a_provider_key() -> None:
    class Store: ...

    assert is_provider_key(Underlying(Store, 0))
```

In `tests/unit/test_public_api.py`, add `'Underlying'` to `EXPECTED_EXPORTS`, between `'Token'` and `'injected'`.

Run: `uv run pytest tests/unit/test_spec.py tests/unit/test_typeguards.py tests/unit/test_public_api.py`
Expected: import errors and failures.

- [ ] **Step 2: Define the key**

In `depin/_core/spec.py`, add `final` to the `typing` import, then define `Underlying` immediately above the `ProviderKey` alias:

```python
@final
@dataclass(frozen=True, slots=True)
class Underlying:
    """The key a decorated binding's inner form is registered under.

    `Container.decorate` leaves the wrapper on the public key and moves what it
    wraps here, so both are ordinary nodes of the validated graph: the wrapper
    reaches its inner form over a real edge, and the inner form keeps the
    lifetime, the cache entry, and the teardown it had undecorated.

    ``applied`` counts the decorators already applied below the public key, so
    the registered binding is ``Underlying(key, 0)`` and a second decorator over
    the same key sees ``Underlying(key, 1)``. Construct one to inspect a
    decorated binding — `FrozenContainer.explain` and `DependencyGraph.find`
    accept it — not to register anything.

    Example:
        ```pycon
        >>> from depin import Container, Underlying
        >>> class Store:
        ...     def get(self) -> str:
        ...         return 'plain'
        >>> class Loud:
        ...     def __init__(self, inner: Store) -> None:
        ...         self.inner = inner
        ...     def get(self) -> str:
        ...         return self.inner.get().upper()
        >>> di = Container().bind(Store).decorate(Store, Loud).freeze()
        >>> di[Store].get()
        'PLAIN'
        >>> di.graph().node(Underlying(Store, 0)).shape.value
        'class'

        ```
    """

    key: 'ProviderKey'
    applied: int
```

The alias below it gains the member:

```python
type ProviderKey = type[object] | Token[object] | str | GenericAlias | Underlying
```

Extend the alias's docstring with a sentence naming the new member:

```
An `Underlying` is the fifth: the identity `Container.decorate` moves a
decorated binding's inner form to, so the wrapper can occupy the public key.
```

- [ ] **Step 3: Render it**

In `depin/_core/spec.py`, add the branch to `fmt_key` and the helper below it:

```python
def fmt_key(key: object) -> str:
    if isinstance(key, type):
        return key.__qualname__
    if isinstance(key, Underlying):
        return fmt_underlying(key)
    origin = get_origin(key)
    if isinstance(origin, type) and origin is not UnionType:
        return fmt_parameterised(origin, get_args(key))
    return repr(key)


def fmt_underlying(key: Underlying) -> str:
    """Spell a decoration layer as ``Store (undecorated)`` or ``Store (decorated x2)``.

    The wrapped key goes through `fmt_key` itself, so a decorated `Token`,
    string, or parameterised key renders the way it does everywhere else.
    """
    layer = 'undecorated' if key.applied == 0 else f'decorated x{key.applied}'
    return f'{fmt_key(key.key)} ({layer})'
```

- [ ] **Step 4: Admit it as a key**

In `depin/_core/typeguards.py`, import `Underlying` from `depin._core.spec` and widen the guard:

```python
def is_provider_key(value: object) -> TypeGuard[ProviderKey]:
    return isinstance(value, type | str | Token | Underlying) or is_generic_key(value)
```

- [ ] **Step 5: Export it**

In `depin/__init__.py`, import `Underlying` alongside `Bindings`, `ProviderKey`, and `ProviderShape` from `depin._core.spec`, and add `'Underlying'` to `__all__` between `'Token'` and `'injected'`.

- [ ] **Step 6: Run and commit**

The doctest in Step 2 uses `decorate`, which does not exist yet. Mark the `Example:` block's first two lines to be added in Task 5 instead: write the docstring now **without** the `Example:` section, and add the section in Task 5 Step 8, where `decorate` exists. Note this explicitly in the commit body so the missing example is not read as an oversight.

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "feat: add Underlying, the key a decorated form moves to"
```

---

### Task 4: `decorate` and the decoration spec

The registration surface and the record-to-spec half. Nothing rewrites the plan yet; Task 5 does that.

**Files:**

- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/bindings.py`
- Modify: `depin/_core/providers.py`
- Create: `tests/unit/test_decoration.py`

**Interfaces:**

- Produces: `BindingCollector.decorate`, `DecorateBinding`, `is_decorate_binding`, `DecorationSpec`, `SpecSet.decorations`.

- [ ] **Step 1: Write the failing spec-level tests**

Create `tests/unit/test_decoration.py`:

```python
"""Decoration: a wrapper node over a binding that keeps its own identity."""

import pytest

from depin import Container
from depin._core.providers import build_specs
from depin.errors import InvalidProviderError


def test_a_decorate_record_becomes_a_decoration_not_a_provider() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    specs = build_specs(Container().bind(Store).decorate(Store, Loud).records())
    assert len(specs.providers) == 1
    assert len(specs.decorations) == 1
    assert specs.decorations[0].key is Store
    assert specs.decorations[0].inner == 'inner'


def test_a_decorator_with_no_parameter_for_its_key_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self) -> None: ...

    container = Container().bind(Store).decorate(Store, Loud)
    with pytest.raises(InvalidProviderError, match='declares no parameter'):
        _ = container.freeze()


def test_a_decorator_with_two_parameters_for_its_key_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self, first: Store, second: Store) -> None: ...

    container = Container().bind(Store).decorate(Store, Loud)
    with pytest.raises(InvalidProviderError, match='declares 2 parameters'):
        _ = container.freeze()


def test_a_tagged_decorator_matches_the_tagged_parameter() -> None:
    from typing import Annotated

    from depin import Tag

    class Store: ...

    class Loud:
        def __init__(self, inner: Annotated[Store, Tag('primary')]) -> None: ...

    specs = build_specs(Container().bind(Store, tag='primary').decorate(Store, Loud, tag='primary').records())
    assert specs.decorations[0].tag == 'primary'
    assert specs.decorations[0].inner == 'inner'
```

Run: `uv run pytest tests/unit/test_decoration.py`
Expected: failures on the missing `decorate` method.

- [ ] **Step 2: Add the marker and the decoration spec**

In `depin/_core/spec.py`, below `CollectionBinding`'s helpers:

```python
@dataclass(frozen=True, slots=True)
class DecorateBinding:
    """Marker source for `Container.decorate(key, wrapper)`.

    The binding carries its own key because `BindRecord.provides` admits only a
    class, while a decorated key may equally be a `Token`, a string, or a
    parameterised generic. It carries no tag of its own: a decorator has no
    identity to tag, so the tag on `BindRecord` is the decorated binding's.
    """

    key: ProviderKey
    wrapper: object


def is_decorate_binding(value: object) -> TypeGuard[DecorateBinding]:
    return isinstance(value, DecorateBinding)
```

and below `ProviderSpec`:

```python
@dataclass(frozen=True, slots=True)
class DecorationSpec:
    """One wrapper over one binding, before it is given a key of its own.

    `depin._core.decoration` decides the key: it depends on how many decorators
    target the same binding, which no single record knows. ``inner`` names the
    parameter that receives the value being wrapped.
    """

    key: ProviderKey
    tag: str | None
    source: object
    shape: ProviderShape
    params: tuple[ParamSpec, ...]
    inner: str
```

Add `decorations: tuple[DecorationSpec, ...]` to `SpecSet`, between `providers` and `inactive`.

- [ ] **Step 3: Add the registration method**

In `depin/_core/bindings.py`, import `DecorateBinding` and add, after `collect`:

```python
    def decorate(
        self,
        key: ProviderKey,
        wrapper: type[object] | Callable[..., object],
        *,
        tag: str | None = None,
        when: Condition | None = None,
    ) -> Self:
        """Wrap an existing binding without changing its registration.

        Every consumer of ``key`` receives what ``wrapper`` returns, including
        consumers deep in the graph. The binding that was registered keeps its
        lifetime, its cache entry, and its teardown: it is built once, in the
        position it would have occupied undecorated, and the wrapper is built
        after it and torn down before it.

        ``wrapper`` declares one parameter whose key and tag are the decorated
        ones — that parameter receives the value being wrapped — and any number
        of further parameters, which are ordinary dependencies resolved from the
        graph. The wrapper takes no scope of its own: it runs at the lifetime of
        the binding it wraps.

        Decorators stack. Two calls over one key apply in registration order, so
        the last registered is the outermost.

        Args:
            key: The binding to wrap. A class, a `Token`, a string, or a
                parameterised generic.
            wrapper: A class or factory producing the decorated value. Any
                provider shape is accepted, async ones included; an async
                wrapper makes the key resolvable only through
                `FrozenContainer.aresolve`.
            tag: The decorated binding's tag, when it has one.
            when: Condition deciding whether this decorator enters the plan.
                A callable is evaluated inside `Container.freeze()`.

        Returns:
            ``self``, for chaining.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Store:
            ...     def get(self) -> str:
            ...         return 'plain'
            >>> class Loud:
            ...     def __init__(self, inner: Store) -> None:
            ...         self.inner = inner
            ...     def get(self) -> str:
            ...         return self.inner.get().upper()
            >>> di = Container().bind(Store).decorate(Store, Loud).freeze()
            >>> di[Store].get()
            'PLAIN'

            ```
        """
        self._records.append(
            BindRecord(
                source=DecorateBinding(key=key, wrapper=wrapper),
                scope=Scope.TRANSIENT,
                provides=None,
                tag=tag,
                condition=when,
            )
        )
        return self
```

The `scope` recorded here is never read: `depin._core.decoration` gives every wrapper node the scope of the binding it wraps. Say so in a one-line comment above the `BindRecord`.

- [ ] **Step 4: Build the decoration spec**

In `depin/_core/providers.py`, split the decorate records out in `build_specs`:

```python
def build_specs(records: Iterable[BindRecord]) -> SpecSet:
    active, inactive = _partition(records)
    localns = _registered_classes(active)
    providers: list[ProviderSpec] = []
    decorations: list[DecorationSpec] = []
    for rec in active:
        source = rec.source
        if is_decorate_binding(source):
            decorations.append(_decoration_spec(rec, source, localns))
        else:
            providers.append(_record_to_spec(rec, localns))
    return SpecSet(
        providers=tuple(providers),
        decorations=tuple(decorations),
        inactive=frozenset(_inactive_idents(inactive, localns)),
    )


def _decoration_spec(rec: BindRecord, binding: DecorateBinding, localns: dict[str, object]) -> DecorationSpec:
    key = as_provider_key(binding.key)
    shape = detect_shape(binding.wrapper)
    params = _extract_params(binding.wrapper, shape, localns)
    return DecorationSpec(
        key=key,
        tag=rec.tag,
        source=binding.wrapper,
        shape=shape,
        params=params,
        inner=_inner_param(params, key, rec.tag, binding.wrapper),
    )


def _inner_param(params: tuple[ParamSpec, ...], key: ProviderKey, tag: str | None, wrapper: object) -> str:
    """The parameter of a decorator that receives the value it wraps.

    Identified by key and tag rather than by position, so a decorator reads like
    any other provider: the parameter annotated with what it decorates is the one
    that gets it.
    """
    matches = tuple(param.name for param in params if (param.key, param.tag) == (key, tag))
    if not matches:
        raise InvalidProviderError(
            f'the decorator {wrapper!r} declares no parameter for {fmt_key(key)} (tag={tag!r}): a '
            'decorator receives the value it wraps through a parameter annotated with the key it '
            'decorates. Annotate one parameter with it.'
        )
    if len(matches) > 1:
        raise InvalidProviderError(
            f'the decorator {wrapper!r} declares {len(matches)} parameters for {fmt_key(key)} '
            f'(tag={tag!r}): {", ".join(matches)}. Exactly one parameter receives the value being '
            'wrapped, and depin cannot tell which of these it is.'
        )
    return matches[0]
```

Also extend `_classes_reachable_from`, so a forward reference to a key named only by a `decorate` call resolves:

```python
    elif is_decorate_binding(source):
        candidates += (source.key, source.wrapper)
```

and give `_classes_within` the `Underlying` branch:

```python
    if isinstance(value, Underlying):
        return _classes_within(value.key)
```

- [ ] **Step 5: Run the tests and the gates, then commit**

Run: `uv run pytest tests/unit/test_decoration.py`
Expected: all four pass. Every other test still passes, because `SpecSet.decorations` is not read yet.

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "feat: accept a decorator registration"
```

---

### Task 5: The decoration fold

Where a decorated binding becomes a chain of ordinary nodes.

**Files:**

- Create: `depin/_core/decoration.py`
- Modify: `depin/_core/graph.py`
- Modify: `depin/_core/spec.py`
- Modify: `tests/unit/test_decoration.py`

**Interfaces:**

- Produces: `depin._core.decoration.apply(providers, decorations)`.

- [ ] **Step 1: Write the failing behaviour tests**

Append to `tests/unit/test_decoration.py`:

```python
def test_a_decorated_singleton_resolves_through_its_wrapper() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return self.inner.get().upper()

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    assert di.resolve(Store).get() == 'PLAIN'


def test_a_decorated_singleton_keeps_one_identity() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    assert di.resolve(Store) is di.resolve(Store)


def test_the_undecorated_form_is_reachable_under_underlying() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    decorated = di.resolve(Store)
    assert isinstance(decorated, Loud)
    assert di.graph().node(Underlying(Store, 0)).shape is ProviderShape.CLASS


def test_a_consumer_receives_the_decorated_value() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    class Service:
        def __init__(self, store: Store) -> None:
            self.store = store

    di = Container().bind(Store).bind(Service).decorate(Store, Loud).freeze()
    assert isinstance(di[Service].store, Loud)


def test_decorators_stack_in_registration_order() -> None:
    class Store:
        def get(self) -> str:
            return 'a'

    class Upper:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return self.inner.get().upper()

    class Bracket:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return f'[{self.inner.get()}]'

    di = Container().bind(Store).decorate(Store, Upper).decorate(Store, Bracket).freeze()
    assert di.resolve(Store).get() == '[A]'


def test_a_factory_decorator_is_accepted() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return self.inner.get().upper()

    def wrap(inner: Store) -> Store:
        return Loud(inner)

    di = Container().bind(Store).decorate(Store, wrap).freeze()
    assert di.resolve(Store).get() == 'PLAIN'


def test_a_decorator_resolves_its_own_dependencies() -> None:
    class Prefix:
        text = '>'

    class Store:
        def get(self) -> str:
            return 'a'

    class Loud:
        def __init__(self, inner: Store, prefix: Prefix) -> None:
            self.inner = inner
            self.prefix = prefix

        def get(self) -> str:
            return f'{self.prefix.text}{self.inner.get()}'

    di = Container().bind(Prefix).bind(Store).decorate(Store, Loud).freeze()
    assert di.resolve(Store).get() == '>a'


def test_a_decorated_scoped_binding_is_rebuilt_per_scope() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store, scope=Scope.SCOPED).decorate(Store, Loud).freeze()
    with di.scope():
        first = di.resolve(Store)
        assert di.resolve(Store) is first
    with di.scope():
        assert di.resolve(Store) is not first


def test_a_decorated_transient_binding_is_rebuilt_per_resolution() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store, scope=Scope.TRANSIENT).decorate(Store, Loud).freeze()
    assert di.resolve(Store) is not di.resolve(Store)


def test_a_decorated_alias_resolves_through_the_wrapper() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Reader: ...

    class Loud:
        def __init__(self, inner: Reader) -> None:
            self.inner = inner

    di = Container().bind(Store).alias(Reader, to=Store).decorate(Reader, Loud).freeze()
    assert isinstance(di.resolve(Reader), Loud)


def test_a_decorated_value_resolves_through_the_wrapper() -> None:
    from typing import Annotated

    from depin import Named

    port = Token[int]('port')

    def double(inner: Annotated[int, Named(port)]) -> int:
        return inner * 2

    di = Container().value(port, 21).decorate(port, double).freeze()
    assert di[port] == 42


def test_a_tagged_binding_is_decorated_under_its_tag() -> None:
    from typing import Annotated

    from depin import Tag

    class Store:
        def get(self) -> str:
            return 'primary'

    class Loud:
        def __init__(self, inner: Annotated[Store, Tag('primary')]) -> None:
            self.inner = inner

    di = Container().bind(Store, tag='primary').decorate(Store, Loud, tag='primary').freeze()
    assert isinstance(di.resolve(Store, tag='primary'), Loud)


def test_an_override_replaces_the_decorated_key_whole() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    class Fake:
        def get(self) -> str:
            return 'fake'

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    with di.override(Store, Fake()):
        assert di.resolve(Store).get() == 'fake'
    assert isinstance(di.resolve(Store), Loud)
```

Add the imports these need: `Named`, `ProviderShape`, `Scope`, `Tag`, `Token`, `Underlying` from `depin`.

Run: `uv run pytest tests/unit/test_decoration.py`
Expected: the new tests fail, because nothing reads `SpecSet.decorations`.

- [ ] **Step 2: Write the fold**

Create `depin/_core/decoration.py`:

```python
"""Rewrites a decorated binding into the chain of nodes that resolves it.

A decorator is not a shape of its own. `Container.decorate` leaves the wrapper
on the public key and moves what it wraps to an `Underlying` key one layer
below, so every node in the chain is an ordinary provider whose parameters are
what it depends on. Nothing downstream of here — validation, ordering, caching,
construction, teardown, or rendering — needs to know a decoration happened.
"""

from collections.abc import Iterable, Sequence

from depin._core.providers import LIFECYCLE_SHAPES
from depin._core.scope import Scope
from depin._core.spec import (
    DecorationSpec,
    Ident,
    ParamSpec,
    ProviderKey,
    ProviderShape,
    ProviderSpec,
    Underlying,
    fmt_key,
)
from depin.errors import InvalidProviderError, InvalidScopeError, MissingProviderError


def apply(
    providers: tuple[ProviderSpec, ...],
    decorations: tuple[DecorationSpec, ...],
) -> tuple[ProviderSpec, ...]:
    """Return the specs with every decorated binding replaced by its chain.

    Raises:
        MissingProviderError: A decorator names a key that nothing binds.
        InvalidProviderError: The decorated binding is a `Container.scope_value`.
        InvalidScopeError: A lifecycle decorator wraps a transient binding.
    """
    if not decorations:
        return providers
    grouped = _group(decorations)
    _check_targets(grouped, {(spec.key, spec.tag): spec for spec in providers})
    out: list[ProviderSpec] = []
    for spec in providers:
        layers = grouped.get((spec.key, spec.tag))
        if layers is None:
            out.append(spec)
            continue
        out.extend(_chain(spec, layers))
    return tuple(out)


def _group(decorations: Iterable[DecorationSpec]) -> dict[Ident, list[DecorationSpec]]:
    """Decorations by the binding they target, each list in registration order."""
    grouped: dict[Ident, list[DecorationSpec]] = {}
    for decoration in decorations:
        grouped.setdefault((decoration.key, decoration.tag), []).append(decoration)
    return grouped


def _check_targets(grouped: dict[Ident, list[DecorationSpec]], index: dict[Ident, ProviderSpec]) -> None:
    for ident, layers in grouped.items():
        key, tag = ident
        spec = index.get(ident)
        if spec is None:
            raise MissingProviderError(
                f'cannot decorate {fmt_key(key)} (tag={tag!r}): no binding is registered for it. A '
                'decorator wraps an existing binding, so bind the key, drop the decorator, or give '
                'the decorator the same condition as the binding it wraps.'
            )
        if spec.shape is ProviderShape.FRAME:
            raise InvalidProviderError(
                f'cannot decorate {fmt_key(key)} (tag={tag!r}): it is declared with scope_value(), '
                'and a value supplied by whoever opens the scope is read from the active frame '
                'before the plan is consulted, so a parameter would receive the undecorated value. '
                'Wrap the value where the scope is opened instead.'
            )
        for layer in layers:
            if layer.shape in LIFECYCLE_SHAPES and spec.scope is Scope.TRANSIENT:
                raise InvalidScopeError(
                    f'cannot decorate transient {fmt_key(key)} with {layer.source!r}: a generator or '
                    'context-manager decorator owns a teardown, and a transient value is never '
                    'cached, so nothing would drain it. Bind the key as singleton or scoped.'
                )


def _chain(spec: ProviderSpec, layers: Sequence[DecorationSpec]) -> Iterable[ProviderSpec]:
    """The registered binding one layer down, then one node per wrapper above it."""
    key = spec.key
    tag = spec.tag
    yield ProviderSpec(
        key=Underlying(key, 0),
        tag=tag,
        source=spec.source,
        scope=spec.scope,
        shape=spec.shape,
        needs_async=spec.needs_async,
        params=spec.params,
    )
    outermost = len(layers) - 1
    for depth, layer in enumerate(layers):
        yield ProviderSpec(
            key=key if depth == outermost else Underlying(key, depth + 1),
            tag=tag,
            source=layer.source,
            scope=spec.scope,
            shape=layer.shape,
            needs_async=False,
            params=tuple(_rewrite(param, layer.inner, Underlying(key, depth), tag) for param in layer.params),
        )


def _rewrite(param: ParamSpec, inner: str, key: ProviderKey, tag: str | None) -> ParamSpec:
    """Point a decorator's designated parameter one layer down.

    The rewritten parameter is required and not optional whatever it was
    written as: the node below it always exists, so a default or a `T | None`
    on it could only hide a defect in the fold.
    """
    if param.name != inner:
        return param
    return ParamSpec(name=param.name, key=key, tag=tag, has_default=False, default=None, optional=False)
```

- [ ] **Step 3: Apply it inside `freeze()`**

In `depin/_core/graph.py`, import `decoration` and fold between the duplicate check and the index:

```python
def build_plan(records: Iterable[BindRecord]) -> ResolutionPlan:
    specs = build_specs(records)
    _check_duplicates(specs.providers)
    providers = decoration.apply(specs.providers, specs.decorations)
    by_key = _index(providers)
    _check_missing(providers, by_key, specs.inactive)
    order = _toposort(providers, by_key)
    _check_captive(order, by_key)
    resolved = tuple(_with_async_flags(order, by_key))
    return ResolutionPlan(order=resolved, by_key=_index(resolved), inactive=specs.inactive)
```

The order matters and is not arbitrary: duplicates are checked against the keys the user wrote, before the fold moves any of them, so `DuplicateProviderError` still names `Store` and not `Store (undecorated)`. Everything after the fold sees ordinary nodes. Put that sentence in `build_plan`'s docstring, and extend its `Raises:` with the three errors `decoration.apply` adds.

- [ ] **Step 4: Run the behaviour tests**

Run: `uv run pytest tests/unit/test_decoration.py`
Expected: all pass.

- [ ] **Step 5: Prove the teardown criterion**

This is the roadmap's acceptance criterion stated as a test. Append to `tests/unit/test_decoration.py`:

```python
def test_a_decorated_provider_is_torn_down_once_in_its_undecorated_position() -> None:
    events: list[str] = []

    class Early: ...

    class Store: ...

    class Late:
        def __init__(self, store: Store, early: Early) -> None: ...

    def early() -> Generator[Early]:
        events.append('open early')
        yield Early()
        events.append('close early')

    def store(early: Early) -> Generator[Store]:
        events.append('open store')
        yield Store()
        events.append('close store')

    def late(store: Store, early: Early) -> Generator[Late]:
        events.append('open late')
        yield Late(store, early)
        events.append('close late')

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    undecorated = Container().bind(early).bind(store).bind(late).freeze()
    _ = undecorated[Late]
    undecorated.close()
    baseline = list(events)

    events.clear()
    decorated = Container().bind(early).bind(store).bind(late).decorate(Store, Loud).freeze()
    _ = decorated[Late]
    _ = decorated[Store]
    decorated.close()

    assert events == baseline
    assert events.count('close store') == 1


def test_a_decorator_that_owns_a_teardown_is_drained_before_what_it_wraps() -> None:
    events: list[str] = []

    class Store: ...

    def store() -> Generator[Store]:
        events.append('open store')
        yield Store()
        events.append('close store')

    def loud(inner: Store) -> Generator[Store]:
        events.append('open loud')
        yield inner
        events.append('close loud')

    di = Container().bind(store).decorate(Store, loud).freeze()
    _ = di[Store]
    di.close()
    assert events == ['open store', 'open loud', 'close loud', 'close store']
```

Add `from collections.abc import Generator` to the test module.

Run: `uv run pytest tests/unit/test_decoration.py -k teardown`
Expected: both pass. If `assert events == baseline` fails, print both lists before changing anything: the fold is what must be corrected, never the assertion.

- [ ] **Step 6: Cover the async rules**

Append:

```python
async def test_an_async_decorator_over_a_sync_binding_needs_aresolve() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return self.inner.get().upper()

    async def loud(inner: Store) -> Store:
        return Loud(inner)

    di = Container().bind(Store).decorate(Store, loud).freeze()
    with pytest.raises(AsyncInSyncContextError):
        _ = di.resolve(Store)
    assert (await di.aresolve(Store)).get() == 'PLAIN'


async def test_a_sync_decorator_over_an_async_binding_needs_aresolve() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud(Store):
        def __init__(self, inner: Store) -> None:
            self.inner = inner

        def get(self) -> str:
            return self.inner.get().upper()

    async def store() -> Store:
        return Store()

    di = Container().bind(store).decorate(Store, Loud).freeze()
    with pytest.raises(AsyncInSyncContextError):
        _ = di.resolve(Store)
    assert (await di.aresolve(Store)).get() == 'PLAIN'


async def test_a_consumer_of_a_decorated_async_binding_needs_aresolve() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    class Service:
        def __init__(self, store: Store) -> None:
            self.store = store

    async def loud(inner: Store) -> Store:
        return Store()

    di = Container().bind(Store).bind(Service).decorate(Store, loud).freeze()
    assert di.graph().node(Service).needs_async
    with pytest.raises(AsyncInSyncContextError):
        _ = di.resolve(Service)
```

Import `AsyncInSyncContextError` from `depin.errors`.

Run: `uv run pytest tests/unit/test_decoration.py`
Expected: all pass. `asyncio_mode = "auto"` means no marker is needed.

- [ ] **Step 7: Give `Underlying` its doctest**

Add the `Example:` block from Task 3 Step 2 to `Underlying`'s docstring now that `decorate` exists, and check it runs:

Run: `uv run pytest --doctest-modules depin/_core/spec.py`
Expected: passes.

- [ ] **Step 8: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "feat: resolve a decorated binding through its wrappers"
```

---

### Task 6: Every error the design names

**Files:**

- Modify: `tests/unit/test_graph_validation.py`
- Modify: `tests/unit/test_decoration.py`

- [ ] **Step 1: Cover the decoration errors**

Append to `tests/unit/test_graph_validation.py`, matching the file's existing style:

```python
def test_decorating_an_unbound_key_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().decorate(Store, Loud)
    with pytest.raises(MissingProviderError, match='cannot decorate'):
        _ = container.freeze()


def test_decorating_a_key_bound_under_another_tag_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().bind(Store, tag='primary').decorate(Store, Loud)
    with pytest.raises(MissingProviderError, match='cannot decorate'):
        _ = container.freeze()


def test_decorating_a_scope_value_is_rejected() -> None:
    class Request: ...

    class Loud:
        def __init__(self, inner: Request) -> None: ...

    container = Container().scope_value(Request).decorate(Request, Loud)
    with pytest.raises(InvalidProviderError, match='scope_value'):
        _ = container.freeze()


def test_a_lifecycle_decorator_over_a_transient_binding_is_rejected() -> None:
    class Store: ...

    def loud(inner: Store) -> Generator[Store]:
        yield inner

    container = Container().bind(Store, scope=Scope.TRANSIENT).decorate(Store, loud)
    with pytest.raises(InvalidScopeError, match='never cached'):
        _ = container.freeze()


def test_a_decorator_that_is_not_callable_is_rejected() -> None:
    class Store: ...

    container = Container().bind(Store).decorate(Store, 3)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidProviderError, match='cannot determine how to call'):
        _ = container.freeze()


def test_decorating_a_key_that_is_not_a_provider_key_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().bind(Store).decorate(3, Loud)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidProviderError, match='as a provider key'):
        _ = container.freeze()


def test_a_cycle_through_a_decorator_dependency_is_rejected() -> None:
    class Store: ...

    class Sidecar:
        def __init__(self, store: Store) -> None: ...

    class Loud:
        def __init__(self, inner: Store, sidecar: Sidecar) -> None: ...

    container = Container().bind(Store).bind(Sidecar).decorate(Store, Loud)
    with pytest.raises(CircularDependencyError):
        _ = container.freeze()


def test_a_decorator_capturing_a_scoped_dependency_is_rejected() -> None:
    class Store: ...

    class Session: ...

    class Loud:
        def __init__(self, inner: Store, session: Session) -> None: ...

    container = Container().bind(Store).bind(Session, scope=Scope.SCOPED).decorate(Store, Loud)
    with pytest.raises(CaptiveDependencyError):
        _ = container.freeze()


def test_a_decorator_with_an_unbound_dependency_is_rejected() -> None:
    class Store: ...

    class Missing: ...

    class Loud:
        def __init__(self, inner: Store, missing: Missing) -> None: ...

    container = Container().bind(Store).decorate(Store, Loud)
    with pytest.raises(MissingProviderError):
        _ = container.freeze()


def test_a_duplicate_binding_is_still_reported_under_its_own_key() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().bind(Store).bind(Store).decorate(Store, Loud)
    with pytest.raises(DuplicateProviderError, match='undecorated') as error:
        _ = container.freeze()
    assert 'undecorated' not in str(error.value)
```

The last test is written wrong on purpose in one respect: `pytest.raises(..., match='undecorated')` would pass only if the message *did* name the internal key. Write it as `pytest.raises(DuplicateProviderError)` and keep the negative assertion. Fix that before running.

Add whatever imports the file lacks — `Generator`, `Scope`, `InvalidScopeError`, `CaptiveDependencyError`, `CircularDependencyError`, `DuplicateProviderError` — and remove none.

- [ ] **Step 2: Cover the interaction with conditions**

Append to `tests/unit/test_decoration.py`:

```python
def test_an_inactive_decorator_leaves_the_binding_bare() -> None:
    class Store:
        def get(self) -> str:
            return 'plain'

    class Loud:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    di = Container().bind(Store).decorate(Store, Loud, when=False).freeze()
    assert di.resolve(Store).get() == 'plain'
    assert di.graph().find(Underlying(Store, 0)) is None


def test_a_decorator_over_an_inactive_binding_is_rejected() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    container = Container().bind(Store, when=False).decorate(Store, Loud)
    with pytest.raises(MissingProviderError, match='same condition'):
        _ = container.freeze()


def test_a_decorator_sharing_its_binding_condition_disappears_with_it() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    di = Container().bind(Store, when=False).decorate(Store, Loud, when=False).freeze()
    assert di.graph().nodes == ()
```

- [ ] **Step 3: Run and commit**

Run: `uv run pytest tests/unit/test_graph_validation.py tests/unit/test_decoration.py`
Expected: all pass.

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "test: cover every decoration and condition error"
```

---

### Task 7: Diagnostics, the generative model, and the type surface

**Files:**

- Modify: `tests/unit/test_graph_render.py`
- Modify: `tests/unit/test_graph_properties.py`
- Modify: `tests/typing/test_conformance.py`

- [ ] **Step 1: Pin the rendered forms**

Append to `tests/unit/test_graph_render.py`. Print each rendered string before pinning it — the `<locals>` qualnames make these easy to get wrong:

```python
def test_explain_shows_the_decoration_chain() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    rendered = di.explain(Store)
    assert rendered.splitlines()[0].startswith(f'{Store.__qualname__}  [singleton, class]')
    assert f'inner: {Store.__qualname__} (undecorated)  [singleton, class]' in rendered


def test_explain_shows_two_decoration_layers() -> None:
    class Store: ...

    class Upper:
        def __init__(self, inner: Store) -> None: ...

    class Bracket:
        def __init__(self, inner: Store) -> None: ...

    di = Container().bind(Store).decorate(Store, Upper).decorate(Store, Bracket).freeze()
    rendered = di.explain(Store)
    assert f'{Store.__qualname__} (decorated x1)' in rendered
    assert f'{Store.__qualname__} (undecorated)' in rendered


def test_the_exports_carry_a_decorated_node() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    graph = Container().bind(Store).decorate(Store, Loud).freeze().graph()
    assert '(undecorated)' in graph.mermaid()
    assert '(undecorated)' in graph.dot()
    assert '|inner|' in graph.mermaid()


def test_explain_names_an_inactive_binding() -> None:
    class Cache: ...

    di = Container().bind(Cache, when=False).freeze()
    assert di.explain(Cache).endswith('registered but inactive')
```

- [ ] **Step 2: Extend the generative model**

In `tests/unit/test_graph_properties.py`, add two fields to `GraphCase`, both last and both defaulted, following the precedent `aliases`, `optionals`, `collections`, and `generics` set:

```python
    decorations: frozenset[int] = frozenset()
    inactive: frozenset[int] = frozenset()
```

Add the wrapper builder next to `_bind_consumer`:

```python
def _bind_decorator(container: Container, name: str, key: object) -> None:
    """Decorate `key` with a generated class taking the undecorated value as its one parameter."""
    parameters = [
        inspect.Parameter('self', inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter('inner', inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=key),
    ]

    def initialize(self: object, **values: object) -> None:
        return None

    _set_dynamic_attribute(initialize, '__annotations__', {'inner': key})
    _set_dynamic_attribute(initialize, '__signature__', inspect.Signature(parameters))
    wrapper = type(name, (), {})
    _set_dynamic_attribute(wrapper, '__init__', initialize)
    _ = container.decorate(key, wrapper)
```

In `_materialize`, after the collections loop:

```python
    for index in case.decorations:
        _bind_decorator(container, f'GraphDecorator{index}', keys[index])
    for index in case.inactive:
        _ = container.bind(type(f'GraphInactive{index}', (), {}), provides=keys[index], when=False)
```

In `_graphs`, draw both from the same pools the neighbouring fields use, last, and pass them positionally in the same order the dataclass declares:

```python
    decorations = draw(st.sets(st.sampled_from(registered_nodes))) if registered_nodes else frozenset[int]()
    unregistered = tuple(index for index, is_registered in enumerate(registered) if not is_registered)
    inactive = draw(st.sets(st.sampled_from(unregistered))) if unregistered else frozenset[int]()
```

A node is drawn for `inactive` only when it is *not* registered, so an inactive binding never collides with a live one and the property below stays about the condition alone.

- [ ] **Step 3: Add the metamorphic property**

Add to `tests/unit/test_graph_properties.py`:

```python
@settings(deadline=None)
@given(_graphs())
def test_an_inactive_binding_leaves_the_plan_as_if_it_were_never_written(case: GraphCase) -> None:
    """A `when=False` binding must produce exactly the plan that omitting it produces.

    Only the note naming the key as inactive may differ, which is the one thing
    an omitted binding cannot say.
    """
    with_inactive = _freeze_result(case).replace(INACTIVE_NOTE, '')
    without = _freeze_result(replace(case, inactive=frozenset()))
    assert with_inactive == without
```

Import `replace` from `dataclasses` and `INACTIVE_NOTE` from `depin._core.graph`.

- [ ] **Step 4: Confirm the model exercises the new fields**

Run: `uv run pytest tests/unit/test_graph_properties.py`
Expected: all pass. Then run once with `--hypothesis-show-statistics` and confirm from the output that cases with a non-empty `decorations` and a non-empty `inactive` are being generated; record the observation for the evidence file. Do not weaken any invariant to make a generated case pass — a failure here is a defect in the fold.

- [ ] **Step 5: Pin the static surface**

Append to `tests/typing/test_conformance.py`, in the file's existing style:

```python
def test_decorate_returns_the_same_builder() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    assert_type(Container().bind(Store).decorate(Store, Loud), Container)


def test_a_protocol_is_a_decoration_key() -> None:
    class Store(Protocol):
        def get(self) -> str: ...

    class Impl:
        def get(self) -> str:
            return 'x'

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    assert_type(Container().bind(Impl, provides=Store).decorate(Store, Loud), Container)


def test_a_condition_takes_both_spellings() -> None:
    class Cache: ...

    assert_type(Container().bind(Cache, when=True), Container)
    assert_type(Container().bind(Cache, when=lambda: True), Container)


def test_an_underlying_key_is_an_explain_argument() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    assert_type(di.explain(Underlying(Store, 0)), str)
```

Import `Protocol`, `assert_type`, and `Underlying` as the file requires.

- [ ] **Step 6: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "test: cover decoration in diagnostics and the generative model"
```

---

### Task 8: Document, demonstrate, integrate, and benchmark

**Files:**

- Modify: `depin/_core/container.py`
- Modify: `docs/guide/composition.md`
- Modify: `docs/reference/diagnostics.md`
- Create: `examples/decoration/__init__.py`, `examples/decoration/main.py`
- Create: `examples/conditional/__init__.py`, `examples/conditional/main.py`
- Modify: `examples/README.md`
- Modify: `tests/integration/test_examples.py`
- Modify: `tests/integration/test_fastapi_ext.py`
- Modify: `benchmarks/test_resolution.py`
- Modify: `benchmarks/test_diagnostics.py`

- [ ] **Step 1: Update the container docstrings**

In `depin/_core/container.py`, add `decorate()` to the list of registration methods in the `Container` class docstring, and extend `freeze()`'s `Raises:` so each new trigger is named under the exception it raises:

- `MissingProviderError`: a decorator names a key nothing binds.
- `InvalidProviderError`: a decorator declares no parameter for the key it decorates, or two; the decorated binding is a `scope_value`; a `when` value is neither a bool nor a callable.
- `InvalidScopeError`: a generator or context-manager decorator wraps a transient binding.

Add one sentence to `freeze()`'s opening paragraph: conditions are evaluated here, and a binding whose condition does not hold is not validated at all.

- [ ] **Step 2: Write the guide sections**

Add two sections to `docs/guide/composition.md`, after `## Aliases` and before `## Where to freeze`. Each opens with what the feature is for, then a `pycon` block that the test run executes.

`## Decoration` covers: the shape of a wrapper, that the wrapper sits on the public key while what it wraps keeps its lifetime and teardown, stacking order, a decorator with its own dependencies, and `explain()` showing the chain. Include this block, and verify its output by running it before committing:

```pycon
>>> from depin import Container
>>> class Store:
...     def get(self) -> str:
...         return 'row'
>>> class Cached:
...     def __init__(self, inner: Store) -> None:
...         self.inner = inner
...         self.hits = 0
...
...     def get(self) -> str:
...         self.hits += 1
...         return self.inner.get()
>>> di = Container().bind(Store).decorate(Store, Cached).freeze()
>>> di[Store].get()
'row'

```

`## Conditional bindings` covers: `when` as a bool and as a callable, that a callable runs inside `freeze()`, the two-implementations-one-key switch, and that a parameter needing an inactive binding is unsatisfied unless it has a default or admits `None`.

Both sections state the caveat that belongs to them: a decorator over a conditional binding needs the same condition, and a `scope_value` cannot be decorated.

- [ ] **Step 3: Document the key**

Add `::: depin.Underlying` to `docs/reference/diagnostics.md`, beside `::: depin.ProviderKey`, in the file's existing format.

- [ ] **Step 4: Write the examples**

`examples/decoration/main.py`: a `Store` protocol with a real implementation, a caching decorator and a logging decorator stacked over it, a service consuming the decorated key, and `explain()` printed. `examples/conditional/main.py`: two implementations of one key selected by a predicate over a settings object, and a binding switched off entirely, with `explain()` showing the inactive note. Both follow the shape of `examples/aliasing/main.py`: a `main()` function, no module-level container construction, and a `if __name__ == '__main__':` guard.

Add both rows to the table in `examples/README.md` and both entries to whatever list `tests/integration/test_examples.py` iterates.

Run: `uv run python -m examples.decoration.main && uv run python -m examples.conditional.main`
Expected: both run and print.

- [ ] **Step 5: Exercise both through FastAPI**

Add to `tests/integration/test_fastapi_ext.py`, following the file's existing fixtures: a route whose `Inject[T]` resolves a scoped provider that is decorated, asserting the response reflects the wrapper; and an app built from a container whose binding set differs by condition, asserting the route sees the active implementation. Use a real `httpx.AsyncClient` against a real app, as the file already does.

- [ ] **Step 6: Add the benchmarks**

Read `benchmarks/test_resolution.py` and `benchmarks/test_diagnostics.py` first and match their fixtures and naming. Add: resolving a singleton through a two-deep decoration chain, and `freeze()` over a graph where every node is decorated once, at the size the neighbouring `freeze()` benchmarks already use. Benchmarks are outside `testpaths`; run them with `uv run --group bench pytest benchmarks` to confirm they execute.

- [ ] **Step 7: Run every gate including the docs build, then commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
git add -A
git commit -m "docs: document decoration and conditional bindings"
```

---

### Task 9: Final verification and the evidence record

**Files:**

- Create: `specs/evidence/2026-08-31-step-4-decoration-conditional.md`

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
Expected: at or above 95%. Name every uncovered line in a module this cycle changed, and check each against `main` at `0ff6e1d` in a throwaway worktree before calling it new. `scope.py`'s line inside `_Flight.wait_sync` appears in roughly one run in two on any commit; run coverage twice rather than attributing it here.

- [ ] **Step 3: Do not run the mutation gate locally**

`[tool.mutmut] only_mutate` covers all of `depin/_core/*.py`, so there is no changed-modules subset; a local run is the full run. The CI `mutation` job is the authority. Record that, and its reason, in the evidence file instead of a score.

- [ ] **Step 4: Confirm the suppression count is unchanged**

Run: `grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin`
Expected: exactly three lines — `frozen.py:116`, `frozen.py:139`, `markers.py:129` — byte-identical to `0ff6e1d`.

- [ ] **Step 5: Confirm what did not change**

Run: `git diff --stat 0ff6e1d -- depin/_core/construct.py depin/_core/diagnostics.py depin/_core/scope.py depin/_core/teardown.py depin/_core/injection.py depin/_core/overrides.py depin/_core/introspect.py depin/_core/markers.py`
Expected: empty. The design rests on decoration needing no new provider shape; an unexpected diff in `construct.py` in particular means the fold went wrong, not that the file needed touching.

- [ ] **Step 6: Record the evidence**

Create `specs/evidence/2026-08-31-step-4-decoration-conditional.md` in the shape of `specs/evidence/2026-08-31-step-3-optional-collections.md`. It carries: every command above with its relevant output; the coverage figure with each miss attributed to this cycle or to `main`; the suppression count; the empty diff from Step 5; the benchmark means; the five checker and runtime measurements the design rests on, restated from the spec rather than re-derived; the teardown event sequences from Task 5 Step 5; and the Hypothesis statistics from Task 7 Step 4.

The evidence file is part of the commit it documents, so every claim it makes about the tree must be true after it lands.

- [ ] **Step 7: Commit**

```bash
git add specs/evidence/2026-08-31-step-4-decoration-conditional.md
git commit -m "docs: record cycle 1 verification evidence"
```

## Self-review

**Spec coverage.** Measurements — Task 5 Step 5 pins the teardown sequence, Task 7 Step 5 pins the checker measurements, Task 9 Step 5 pins the untouched-module claim. Public surface: `decorate` — Task 4 Step 3; `Underlying` — Task 3; `when` — Task 1 Step 3. Data model: `DecorateBinding` and `DecorationSpec` — Task 4 Step 2; `BindRecord.condition` and `SpecSet` — Task 1 Steps 2 and 4; `ResolutionPlan.inactive` — Task 1 Step 4. Semantics: the decoration table — Task 5 Steps 1, 5, 6 and Task 6 Step 2; the conditional table — Task 1 Step 1 and Task 6 Step 2. Errors table — Task 4 Step 1, Task 6 Step 1, Task 1 Step 1. Key rendering — Task 3 Step 1 and Task 7 Step 1. Module layout — Tasks 1 to 5 and 8. Verification — Tasks 1 to 9. Acceptance criteria — Task 5 Step 5 (teardown), Task 1 Step 1 and Task 7 Step 3 (inactive), Task 9 (suppressions, coverage, gates).

**Type consistency.** `DecorateBinding(key, wrapper)`, `is_decorate_binding`, `DecorationSpec(key, tag, source, shape, params, inner)`, `SpecSet(providers, decorations, inactive)`, `Underlying(key, applied)`, `Condition`, and `INACTIVE_NOTE` are spelled the same in every task that uses them. The decorator's designated parameter is `inner` in `DecorationSpec.inner`, in every test, in the guide, and in both examples. `applied` counts decorators already applied, so the registered binding is always `Underlying(key, 0)`, in the fold, in the renderer, and in every assertion.

**Known verification points.** Five assertions depend on exact rendered text: the three `explain()` trees in Task 7 Step 1, the guide block in Task 8 Step 2, and the teardown event lists in Task 5 Step 5. Each carries an instruction to print the real value first. Task 6 Step 1 contains one test written deliberately wrong, with the correction stated inline, so a worker who copies the block without reading it is caught by the step rather than by CI.

**Ordering risk.** Task 1 leaves `_inactive_idents` as a stub that Task 2 replaces; Task 2 must replace it wholesale rather than edit around it. Task 3's `Underlying` docstring omits its `Example:` until Task 5 Step 7, because the example calls `decorate`, which Task 4 introduces — the commit body in Task 3 says so. Task 4 adds `SpecSet.decorations` but nothing reads it until Task 5, so Task 4's tree is green with a field that is written and not yet consumed; that is deliberate and keeps each commit's diff readable. Every task commits a green tree.

**Blast radius.** Eight modules under `depin/_core/` change, one of them new. `construct.py` and `diagnostics.py` do not, and Task 9 Step 5 fails if they do. The one existing message whose text changes is `MissingProviderError`, and only for a key an inactive binding declares — the metamorphic property in Task 7 Step 3 is what proves nothing else about that message moved.
