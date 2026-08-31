# Step 4, cycle 2 — eager warmup, health checks, and the named-scopes decision: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `di.warmup()` construct every singleton at boot and refuse an async one, make `bind(Database, check=ping)` declare a verification callable that `di.checks()` exposes and `di.health()` runs, and record the named-scopes rejection — for the 0.12.0 milestone.

**Architecture:** Two new modules, `depin/_core/warmup.py` and `depin/_core/health.py`, each a read over a plan `freeze()` has already validated. Neither adds a `ProviderShape`, a validation rule, or a plan node. `warmup` filters `ResolutionPlan.order` to `Scope.SINGLETON`, refuses the set up front when any needs async, and reports over the `GraphNode` the graph view already exposes. A check is one erased field on `ProviderSpec`, carried from the record through the decoration fold, narrowed at the single boundary that calls it. The container owns resolution, so the two-line walk lives in `FrozenContainer`; the modules own the reports and the rules.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, Hypothesis, mutmut 3.7, pytest-benchmark, mkdocs-material with mkdocstrings, uv.

**Spec:** `specs/2026-08-31-step-4-warmup-health-design.md`

## Global constraints

Every task inherits these requirements from `AGENTS.md`, the approved roadmap, and the spec.

- The core keeps zero runtime dependencies. Nothing here adds a package to `[project.dependencies]` or to any dependency group.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `typing.Any`, `typing.cast`, `# type: ignore`, or `# pyright: ignore`. `depin/` carries exactly three suppressions today — `frozen.py:116`, `frozen.py:139`, `markers.py:132` — and must carry exactly those three when this cycle ends. Confirm the line numbers against the tree before relying on them.
- Every exception raised by library code inherits `DepinError`. No bare `KeyError`, `TypeError`, `ValueError`, or `assert` in `depin/`. An exception is never swallowed: `health()` records a check's failure in its report, which is reporting, not swallowing, and it catches `Exception`, never `BaseException`.
- Data structures are `@dataclass(frozen=True, slots=True)`; a public one is additionally `@final`.
- New behaviour in `depin/_core/` is developed test-first: the failing test is written and observed failing before the implementation.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery. `reportPrivateUsage` forbids reading `FrozenContainer._plan` from a test; build plans with `build_plan(container.records())`.
- Public API additions carry Google-style docstrings that omit types from `Args:` / `Returns:` and include a doctest `Example:`. Doctests run in the default `pytest` invocation.
- `fmt_key` renders a class by `__qualname__`, so a class declared inside a test function appears as `test_x.<locals>.Name`. Print the real string before pinning any text assertion.
- `basedpyright --strict` has `reportUnnecessaryIsInstance`, `reportImplicitOverride`, `reportMissingTypeArgument`, and `reportUnusedClass`. `mypy --strict` additionally has `warn_unreachable` and `redundant-expr`, so a runtime guard whose annotation already excludes the rejected case must take `object` in a private helper rather than be suppressed.
- `ruff` rejects unused imports. Per-line waivers are acceptable where the test exercises exactly what the rule forbids.
- Coverage over `depin/` stays at or above 95%; it is 98.82% at the 0.11.0 baseline. `depin/_core/scope.py`'s line inside `_Flight.wait_sync` reports uncovered in roughly one run in two on any commit; run coverage twice before attributing a miss to this cycle.
- Property tests in `tests/unit/test_graph_properties.py` need `@settings(deadline=None)`.
- Tests are deterministic: no sleeps, no network, no clock dependence.
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
| `depin/_core/spec.py` | `BindRecord.check`; `ProviderSpec.check`. | 1 |
| `depin/_core/bindings.py` | `check=` on `bind` and `value`. | 1 |
| `depin/_core/providers.py` | Carry `check` into the spec; reject a non-callable one at `freeze()`. | 1 |
| `depin/_core/decoration.py` | The fold carries `check` onto the `Underlying` node; wrappers get none. | 1 |
| `depin/_core/graph.py` | `_with_async_flags` carries `check` forward. | 1 |
| `depin/_core/typeguards.py` | `as_check`; `is_awaitable` promoted from `_is_awaitable`. | 1 |
| `tests/unit/test_health_declaration.py` | The check reaches the plan intact, through every rebuild. | 1 |
| `depin/_core/warmup.py` | **New.** `WarmupReport` and the singleton rules. | 2 |
| `depin/_core/frozen.py` | `warmup`, `awarmup`; then `checks`, `health`, `ahealth`. | 2, 3 |
| `tests/unit/test_warmup.py` | Warmup end to end. | 2 |
| `depin/_core/health.py` | **New.** `HealthCheck`, `HealthResult`, `HealthReport`, the runners. | 3 |
| `tests/unit/test_health.py` | Health checks end to end. | 3 |
| `depin/__init__.py` | Exports the four new public types. | 4 |
| `tests/unit/test_public_api.py` | The four new exports. | 4 |
| `tests/typing/test_conformance.py` | `assert_type` over the new surface. | 4 |
| `tests/unit/test_graph_properties.py` | A `checks` field and the metamorphic property over it. | 4 |
| `docs/guide/operations.md` | The narrative page. | 5 |
| `docs/reference/operations.md` | The five reference entries. | 5 |
| `mkdocs.yml` | Nav entries for both. | 5 |
| `examples/warmup/`, `examples/health/` | Runnable programs. | 5 |
| `examples/README.md` | Lists both. | 5 |
| `tests/integration/test_examples.py` | Executes both. | 5 |
| `tests/integration/test_fastapi_ext.py` | `awarmup()` in a lifespan; a readiness route over `ahealth()`. | 5 |
| `benchmarks/test_resolution.py` | `warmup()` over a chain of 1000 singletons. | 5 |
| `specs/2026-08-28-roadmap-1.0-design.md` | The named-scopes decision recorded in the roadmap. | 6 |
| `specs/evidence/2026-08-31-step-4-warmup-health.md` | The measured evidence. | 6 |

---

### Task 1: A binding declares how to verify its value

The declaration and its journey into the plan. Nothing runs a check yet.

**The hazard this task exists to close:** `ProviderSpec` is rebuilt in two places that must be updated in the same change, or the field is silently dropped between `freeze()` and the plan — `graph._with_async_flags`, which rebuilds every spec, and `decoration._chain`, which rebuilds a decorated binding. A test for each is written before the field is added.

**Files:**

- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/bindings.py`
- Modify: `depin/_core/providers.py`
- Modify: `depin/_core/decoration.py`
- Modify: `depin/_core/graph.py`
- Modify: `depin/_core/typeguards.py`
- Create: `tests/unit/test_health_declaration.py`

**Interfaces:**

- Produces: `BindRecord.check` and `ProviderSpec.check` in `depin._core.spec`.
- Produces: `as_check` and `is_awaitable` in `depin._core.typeguards`.

- [ ] **Step 1: Write the failing declaration tests**

Create `tests/unit/test_health_declaration.py`:

```python
"""A `check=` declaration reaches the plan intact, through every rebuild of a spec."""

import pytest

from depin import Container, Token, Underlying
from depin._core.graph import build_plan
from depin.errors import InvalidProviderError


def _spec(container: Container, key: object, tag: str | None = None) -> object:
    plan = build_plan(container.records())
    return plan.by_key[(key, tag)]


def test_a_bind_check_reaches_the_plan() -> None:
    class Database: ...

    def ping(db: Database) -> None: ...

    spec = _spec(Container().bind(Database, check=ping), Database)
    assert getattr(spec, 'check') is ping  # noqa: B009


def test_a_value_check_reaches_the_plan() -> None:
    port = Token[int]('port')

    def positive(value: int) -> bool:
        return value > 0

    spec = _spec(Container().value(port, 8080, check=positive), port)
    assert getattr(spec, 'check') is positive  # noqa: B009


def test_a_check_survives_the_async_flag_pass() -> None:
    class Database: ...

    class Service:
        def __init__(self, db: Database) -> None: ...

    async def build() -> Service:
        return Service(Database())

    def ping(db: Database) -> None: ...

    container = Container().bind(Database, check=ping).bind(build)
    spec = _spec(container, Database)
    assert getattr(spec, 'check') is ping  # noqa: B009


def test_a_check_follows_a_decorated_binding_to_its_undecorated_node() -> None:
    class Database: ...

    class Loud(Database):
        def __init__(self, inner: Database) -> None: ...

    def ping(db: Database) -> None: ...

    container = Container().bind(Database, check=ping).decorate(Database, Loud)
    assert getattr(_spec(container, Underlying(Database, 0)), 'check') is ping  # noqa: B009
    assert getattr(_spec(container, Database), 'check') is None  # noqa: B009


def test_a_binding_without_a_check_carries_none() -> None:
    class Database: ...

    assert getattr(_spec(Container().bind(Database), Database), 'check') is None  # noqa: B009


def test_a_non_callable_check_is_rejected_at_freeze() -> None:
    class Database: ...

    container = Container().bind(Database, check=3)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidProviderError, match='as a health check'):
        _ = container.freeze()
```

`getattr(..., 'check')` with a `# noqa: B009` is used rather than `spec.check` because `_spec` returns `object`; if the file's style allows a typed local instead, prefer that and drop the waivers. Decide once and be consistent.

Run: `uv run pytest tests/unit/test_health_declaration.py`
Expected: every test fails on the missing `check` keyword or attribute.

- [ ] **Step 2: Add the field to the record and the spec**

In `depin/_core/spec.py`, give `BindRecord` and `ProviderSpec` one trailing, defaulted field each:

```python
@dataclass(frozen=True, slots=True)
class BindRecord:
    source: object
    scope: Scope
    provides: type[object] | None
    tag: str | None
    condition: Condition | None = None
    check: object | None = None
```

```python
@dataclass(frozen=True, slots=True)
class ProviderSpec:
    key: ProviderKey
    tag: str | None
    source: object
    scope: Scope
    shape: ProviderShape
    needs_async: bool
    params: tuple[ParamSpec, ...]
    check: object | None = None
```

The field is `object` for the reason `source` is: the callable's parameter type is erased by the time it reaches the plan, and `depin._core.typeguards` narrows it at the one boundary that calls it. Say that in a one-line comment only if the surrounding code does not already make it obvious; do not restate the annotation.

- [ ] **Step 3: Accept the declaration**

In `depin/_core/bindings.py`, add `check: Callable[[T], object] | None = None` as the last keyword-only parameter of `bind` and of `value`, pass `check=check` into the `BindRecord` each appends, and give each docstring one `Args:` line, phrased identically:

```
            check: Callable verifying the produced value, exposed by
                `FrozenContainer.checks` and run by `FrozenContainer.health`.
                It receives the value and is healthy unless it raises or
                returns ``False``.
```

Do not add `check=` to `scope_value`, `alias`, `collect`, or `decorate`; the spec's Out of scope table says why.

- [ ] **Step 4: Carry it into the spec**

In `depin/_core/providers.py`, pass `check=rec.check` in the two branches of `_record_to_spec` whose records can carry one — the `ValueBinding` branch and the general class/factory branch — and reject a non-callable one where the record is converted:

```python
def _checked(rec: BindRecord) -> object | None:
    """The record's check, refused unless it can be called.

    Annotated `object` rather than the declared callable type: the guard exists
    for an untyped caller that broke the promise the annotation makes to a
    checker, and a checker that trusts the annotation reads the raise as
    unreachable.
    """
    check: object = rec.check
    if check is None or callable(check):
        return check
    raise InvalidProviderError(
        f'cannot use {check!r} as a health check: a check is a callable that receives the value '
        'the provider produced, and is healthy unless it raises or returns False.'
    )
```

Call it from both branches. The alias, collection, and frame branches leave `check` at its default, because no registration method gives them one.

- [ ] **Step 5: Carry it through the two rebuilds**

In `depin/_core/graph.py`, `_with_async_flags` rebuilds every spec; add `check=spec.check` to the `ProviderSpec` it yields.

In `depin/_core/decoration.py`, `_chain` rebuilds a decorated binding; the `Underlying(key, 0)` node takes `check=spec.check`, and every wrapper node leaves it at its default. Add one sentence to `_chain`'s docstring: a check verifies the value the binding it was declared on produces, so it stays with that binding rather than moving to the key the wrapper occupies.

- [ ] **Step 6: Add the two narrowing helpers**

In `depin/_core/typeguards.py`, rename `_is_awaitable` to `is_awaitable` (updating `as_awaitable`, its only caller today), and add:

```python
def as_check(source: object, key: object) -> Callable[[object], object]:
    """The health check declared for a provider, as something callable.

    Unreachable through the public API: `Container.freeze()` refuses a check
    that is not callable. The narrowing keeps a defect inside the `DepinError`
    hierarchy instead of surfacing as a `TypeError` with no provider named.
    """
    if callable(source):
        return source
    raise InvalidProviderError(f'health check for {fmt_key(key)} is not callable: {source!r}')
```

- [ ] **Step 7: Run the tests and the gates, then commit**

Run: `uv run pytest tests/unit/test_health_declaration.py`
Expected: all pass. The whole suite still passes: every `ProviderSpec` construction site either sets `check` or defaults it.

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "feat: declare a health check on a binding"
```

---

### Task 2: Eager warmup

**Files:**

- Create: `depin/_core/warmup.py`
- Modify: `depin/_core/frozen.py`
- Create: `tests/unit/test_warmup.py`

**Interfaces:**

- Produces: `WarmupReport`, `singleton_specs`, `reject_async_singletons`, `warmup_report` in `depin._core.warmup`.
- Produces: `FrozenContainer.warmup` and `FrozenContainer.awarmup`.

- [ ] **Step 1: Write the failing behaviour tests**

Create `tests/unit/test_warmup.py`:

```python
"""`warmup()` builds every singleton at boot, and refuses to block an event loop."""

from collections.abc import Generator

import pytest

from depin import Container, Scope, Underlying
from depin.errors import AsyncInSyncContextError


def test_warmup_on_an_empty_container_reports_nothing() -> None:
    report = Container().freeze().warmup()
    assert report.constructed == ()
    assert report.cached == ()


def test_warmup_constructs_every_singleton() -> None:
    built: list[str] = []

    class Config:
        def __init__(self) -> None:
            built.append('config')

    class Service:
        def __init__(self, config: Config) -> None:
            built.append('service')

    di = Container().bind(Config).bind(Service).freeze()
    report = di.warmup()
    assert built == ['config', 'service']
    assert [node.key for node in report.constructed] == [Config, Service]
    assert report.cached == ()


def test_warmup_reports_an_already_built_singleton_as_cached() -> None:
    class Config: ...

    class Service:
        def __init__(self, config: Config) -> None: ...

    di = Container().bind(Config).bind(Service).freeze()
    _ = di[Config]
    report = di.warmup()
    assert [node.key for node in report.cached] == [Config]
    assert [node.key for node in report.constructed] == [Service]


def test_a_second_warmup_constructs_nothing() -> None:
    class Config: ...

    di = Container().bind(Config).freeze()
    _ = di.warmup()
    report = di.warmup()
    assert report.constructed == ()
    assert [node.key for node in report.cached] == [Config]


def test_warmup_leaves_scoped_and_transient_providers_alone() -> None:
    built: list[str] = []

    class Session:
        def __init__(self) -> None:
            built.append('session')

    class Ticket:
        def __init__(self) -> None:
            built.append('ticket')

    di = Container().bind(Session, scope=Scope.SCOPED).bind(Ticket, scope=Scope.TRANSIENT).freeze()
    report = di.warmup()
    assert built == []
    assert report.constructed == ()
    assert report.cached == ()


def test_a_construction_failure_propagates_and_keeps_what_was_built() -> None:
    class Config: ...

    class Broken:
        def __init__(self, config: Config) -> None:
            raise RuntimeError('boom')

    di = Container().bind(Config).bind(Broken).freeze()
    with pytest.raises(RuntimeError, match='boom'):
        _ = di.warmup()
    assert [node.key for node in di.warmup.__self__.warmup().cached] == [Config]  # replaced below


def test_a_lifecycle_singleton_is_entered_once_and_drained_once() -> None:
    events: list[str] = []

    class Pool: ...

    def pool() -> Generator[Pool]:
        events.append('open')
        yield Pool()
        events.append('close')

    di = Container().bind(pool).freeze()
    _ = di.warmup()
    _ = di.warmup()
    di.close()
    assert events == ['open', 'close']


def test_a_decorated_singleton_reports_both_nodes() -> None:
    class Config: ...

    class Loud(Config):
        def __init__(self, inner: Config) -> None: ...

    di = Container().bind(Config).decorate(Config, Loud).freeze()
    report = di.warmup()
    assert [node.key for node in report.constructed] == [Underlying(Config, 0), Config]


def test_warmup_refuses_an_async_singleton_before_constructing_anything() -> None:
    built: list[str] = []

    class Config:
        def __init__(self) -> None:
            built.append('config')

    class Service: ...

    async def service() -> Service:
        return Service()

    di = Container().bind(Config).bind(service).freeze()
    with pytest.raises(AsyncInSyncContextError, match='awarmup'):
        _ = di.warmup()
    assert built == []


async def test_awarmup_constructs_an_async_singleton() -> None:
    class Service: ...

    async def service() -> Service:
        return Service()

    di = Container().bind(service).freeze()
    report = await di.awarmup()
    assert [node.key for node in report.constructed] == [Service]
```

`test_a_construction_failure_propagates_and_keeps_what_was_built`'s last line is written wrong on purpose: `di.warmup.__self__` is not how to reach the container. Write the assertion as a second `di.warmup()` call inside a `pytest.raises` block, or simply assert that `Config` is reported as `cached` by a subsequent call that is itself expected to raise again. Decide, and say in the report which form you used and why.

Run: `uv run pytest tests/unit/test_warmup.py`
Expected: every test fails on the missing `warmup` attribute.

- [ ] **Step 2: Write the module**

Create `depin/_core/warmup.py`:

```python
"""Constructing every singleton at boot, and the report over what was built.

The walk itself belongs to `FrozenContainer`, which owns resolution; this module
owns the rule for which providers a warmup touches, the rule that refuses to
drive an async one without a loop, and the shape of the report.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import final

from depin._core.diagnostics import DependencyGraph, GraphNode
from depin._core.scope import Scope
from depin._core.spec import ProviderSpec, ResolutionPlan, fmt_chain
from depin.errors import AsyncInSyncContextError


@final
@dataclass(frozen=True, slots=True)
class WarmupReport:
    """What a `FrozenContainer.warmup` call did, node by node.

    Both tuples are in resolution order, and both hold the same `GraphNode` the
    dependency graph exposes, so a caller reads a warmed provider's key, scope,
    shape, and dependencies off the node it already has.

    Attributes:
        constructed: Singletons this call built.
        cached: Singletons that were already built when the call began.

    Example:
        ```pycon
        >>> from depin import Container
        >>> class Config: ...
        >>> di = Container().bind(Config).freeze()
        >>> report = di.warmup()
        >>> [node.key.__qualname__ for node in report.constructed]
        ['Config']
        >>> di.warmup().cached == report.constructed
        True

        ```
    """

    constructed: tuple[GraphNode, ...]
    cached: tuple[GraphNode, ...]


def singleton_specs(plan: ResolutionPlan) -> tuple[ProviderSpec, ...]:
    """The providers a warmup builds: the singletons, in resolution order.

    A scoped value belongs to a scope and a transient one is never cached, so
    neither has a boot-time instance to build.
    """
    return tuple(spec for spec in plan.order if spec.scope is Scope.SINGLETON)


def reject_async_singletons(specs: Iterable[ProviderSpec]) -> None:
    """Refuse a synchronous warmup over singletons that need an event loop.

    Raised before anything is constructed, so a refusal leaves the container as
    it was rather than half warm.

    Raises:
        AsyncInSyncContextError: Some singleton needs async resolution.
    """
    pending = tuple(spec.key for spec in specs if spec.needs_async)
    if not pending:
        return
    raise AsyncInSyncContextError(
        f'warmup() cannot construct {fmt_chain(pending)}: they require async resolution. '
        'Call awarmup() instead.'
    )


def warmup_report(
    graph: DependencyGraph,
    constructed: Sequence[ProviderSpec],
    cached: Sequence[ProviderSpec],
) -> WarmupReport:
    return WarmupReport(
        constructed=tuple(graph.node(spec.key, tag=spec.tag) for spec in constructed),
        cached=tuple(graph.node(spec.key, tag=spec.tag) for spec in cached),
    )
```

`fmt_chain` renders the pending keys as `A -> B`, which reads as a sequence rather than a list; if the rendered message reads badly, join `fmt_key` over them with `', '` instead and say so in the report. Print the real message before deciding.

- [ ] **Step 3: Add the container methods**

In `depin/_core/frozen.py`, import what the methods need by name rather than importing the module, so nothing shadows the method names:

```python
from depin._core.warmup import WarmupReport, reject_async_singletons, singleton_specs, warmup_report
```

Add a private predicate beside `_cache_target`:

```python
    def _is_cached(self, spec: ProviderSpec) -> bool:
        return self._root.lookup((spec.key, spec.tag)) is not MISSING
```

and the two methods, after `close` / `aclose`:

```python
    def warmup(self) -> WarmupReport:
        """Construct every singleton now, instead of on first resolution.

        Walks the plan in resolution order, building each singleton that is not
        built already, so a provider that fails does so at startup rather than
        on the first request that needs it. Scoped and transient providers are
        untouched: a scoped value belongs to a scope, and a transient one is
        never cached. Calling it twice constructs nothing the second time.

        A failure propagates unchanged — a container with some singletons built
        and one failed is a startup to abort, not a state to report.

        Raises:
            AsyncInSyncContextError: Some singleton needs async resolution.
                Nothing is constructed before this is raised; use `awarmup()`.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Config: ...
            >>> class Service:
            ...     def __init__(self, config: Config) -> None: ...
            >>> di = Container().bind(Config).bind(Service).freeze()
            >>> report = di.warmup()
            >>> len(report.constructed), len(report.cached)
            (2, 0)

            ```
        """
        specs = singleton_specs(self._plan)
        reject_async_singletons(specs)
        constructed: list[ProviderSpec] = []
        cached: list[ProviderSpec] = []
        for spec in specs:
            if self._is_cached(spec):
                cached.append(spec)
                continue
            _ = self._resolve_any(spec.key, spec.tag)
            constructed.append(spec)
        return warmup_report(self.graph(), constructed, cached)

    async def awarmup(self) -> WarmupReport:
        """Construct every singleton now; the async counterpart to `warmup()`.

        Drives async singletons as well as sync ones, so it is what an ASGI
        lifespan calls. Otherwise identical: resolution order, the same report,
        and a failure that propagates unchanged.
        """
        specs = singleton_specs(self._plan)
        constructed: list[ProviderSpec] = []
        cached: list[ProviderSpec] = []
        for spec in specs:
            if self._is_cached(spec):
                cached.append(spec)
                continue
            _ = await self._aresolve_any(spec.key, spec.tag)
            constructed.append(spec)
        return warmup_report(self.graph(), constructed, cached)
```

Both resolve through `_resolve_any` / `_aresolve_any` rather than `_resolve_sync(spec)`, so an active `override()` is honoured exactly as it is everywhere else. Put that reason in a comment only if the code does not carry it; a reader who knows `_lookup_optional` will see it.

- [ ] **Step 4: Run the tests, then the gates, and commit**

Run: `uv run pytest tests/unit/test_warmup.py`
Expected: all pass.

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "feat: construct every singleton with warmup"
```

---

### Task 3: Health checks

**Files:**

- Create: `depin/_core/health.py`
- Modify: `depin/_core/frozen.py`
- Create: `tests/unit/test_health.py`

**Interfaces:**

- Produces: `HealthCheck`, `HealthResult`, `HealthReport`, `checked_specs`, `declared_checks`, `reject_async_checks`, `run_check`, `run_check_async` in `depin._core.health`.
- Produces: `FrozenContainer.checks`, `health`, `ahealth`.

- [ ] **Step 1: Write the failing behaviour tests**

Create `tests/unit/test_health.py` covering, one test each: a check that returns `None` is healthy; one that returns `True` is healthy; one that returns `False` is unhealthy with no error; one that raises is unhealthy with the exception on `HealthResult.error`; every check runs even when an earlier one failed; `checks()` resolves nothing, proved by a provider whose construction appends to a list; `HealthReport.healthy` over all-healthy, mixed, and empty; `checks()` reports `needs_async` for an async provider and for an `async def` check; `health()` raises `AsyncInSyncContextError` for each of those two reasons, naming `ahealth`; `ahealth()` runs both; a sync check returning an awaitable raises `InvalidProviderError`; a check on a scoped binding runs inside a scope and raises `OutsideScopeError` outside one; a check on a decorated binding is keyed `Underlying(key, 0)`; an inactive conditional binding declares no check; a `value()` check runs against the bound value.

Write each test against the real `Container` / `FrozenContainer`. Where a test needs the exact text of a message, print it first.

Run: `uv run pytest tests/unit/test_health.py`
Expected: every test fails on the missing `checks` attribute.

- [ ] **Step 2: Write the module**

Create `depin/_core/health.py`:

```python
"""Running the verification callables a graph's bindings declared.

`Container.bind(..., check=...)` records a callable; this module says what a
check's outcome means, which checks a synchronous run may drive, and what a run
reports. Resolution belongs to `FrozenContainer`, which hands each check the
value it verifies.
"""

import inspect
from collections.abc import Iterable
from dataclasses import dataclass
from typing import final

from depin._core.spec import ProviderKey, ProviderSpec, ResolutionPlan, fmt_chain, fmt_key
from depin._core.typeguards import as_check, is_awaitable
from depin.errors import AsyncInSyncContextError, InvalidProviderError


@final
@dataclass(frozen=True, slots=True)
class HealthCheck:
    """A verification callable a binding declared, as data.

    Attributes:
        key: The provider whose value the check verifies.
        tag: That provider's tag, when it has one.
        needs_async: Whether running it requires an event loop, because the
            provider needs async resolution or the check is a coroutine
            function.
    """

    key: ProviderKey
    tag: str | None
    needs_async: bool


@final
@dataclass(frozen=True, slots=True)
class HealthResult:
    """What one check said.

    Attributes:
        key: The provider whose value was verified.
        tag: That provider's tag, when it has one.
        healthy: False when the check raised or returned ``False``.
        error: The exception the check raised, when it raised one.
    """

    key: ProviderKey
    tag: str | None
    healthy: bool
    error: Exception | None


@final
@dataclass(frozen=True, slots=True)
class HealthReport:
    """Every check's outcome, in resolution order.

    Example:
        ```pycon
        >>> from depin import Container
        >>> class Database:
        ...     ready = True
        >>> def ping(db: Database) -> bool:
        ...     return db.ready
        >>> di = Container().bind(Database, check=ping).freeze()
        >>> report = di.health()
        >>> report.healthy, len(report.results)
        (True, 1)

        ```
    """

    results: tuple[HealthResult, ...]

    @property
    def healthy(self) -> bool:
        """Whether every check passed. An empty report is healthy."""
        return all(result.healthy for result in self.results)


def checked_specs(plan: ResolutionPlan) -> tuple[ProviderSpec, ...]:
    """The providers that declared a check, in resolution order."""
    return tuple(spec for spec in plan.order if spec.check is not None)


def declared_checks(specs: Iterable[ProviderSpec]) -> tuple[HealthCheck, ...]:
    return tuple(
        HealthCheck(key=spec.key, tag=spec.tag, needs_async=_needs_async(spec)) for spec in specs
    )


def reject_async_checks(specs: Iterable[ProviderSpec]) -> None:
    """Refuse a synchronous run over checks that need an event loop.

    Raised before any check runs, so a refusal reports nothing rather than a
    partial set of outcomes.

    Raises:
        AsyncInSyncContextError: Some check needs async resolution or is itself
            a coroutine function.
    """
    pending = tuple(spec.key for spec in specs if _needs_async(spec))
    if not pending:
        return
    raise AsyncInSyncContextError(
        f'health() cannot run the checks for {fmt_chain(pending)}: they require an event loop, '
        'because the provider is async or the check is. Call ahealth() instead.'
    )


def _needs_async(spec: ProviderSpec) -> bool:
    return spec.needs_async or inspect.iscoroutinefunction(spec.check)


def run_check(spec: ProviderSpec, value: object) -> HealthResult:
    """Call one check without an event loop.

    Raises:
        InvalidProviderError: The check returned an awaitable, which a
            synchronous run has no loop to await.
    """
    check = as_check(spec.check, spec.key)
    try:
        outcome = check(value)
    except Exception as error:
        return HealthResult(key=spec.key, tag=spec.tag, healthy=False, error=error)
    if is_awaitable(outcome):
        raise InvalidProviderError(
            f'the health check for {fmt_key(spec.key)} returned an awaitable; an asynchronous '
            'check runs under ahealth(), never under health().'
        )
    return _outcome(spec, outcome)


async def run_check_async(spec: ProviderSpec, value: object) -> HealthResult:
    """Call one check inside an event loop; awaits an asynchronous one."""
    check = as_check(spec.check, spec.key)
    try:
        outcome = check(value)
        if is_awaitable(outcome):
            outcome = await outcome
    except Exception as error:
        return HealthResult(key=spec.key, tag=spec.tag, healthy=False, error=error)
    return _outcome(spec, outcome)


def _outcome(spec: ProviderSpec, outcome: object) -> HealthResult:
    """A check is healthy unless it returned exactly ``False``.

    Identity against `False` rather than truthiness: a check returning ``0`` or
    an empty string returned a value, not a verdict, and reading it as a failure
    would make a working check fail for the shape of what it happened to return.
    """
    return HealthResult(key=spec.key, tag=spec.tag, healthy=outcome is not False, error=None)
```

- [ ] **Step 3: Add the container methods**

In `depin/_core/frozen.py`, import by name:

```python
from depin._core.health import (
    HealthCheck,
    HealthReport,
    checked_specs,
    declared_checks,
    reject_async_checks,
    run_check,
    run_check_async,
)
```

and add three methods after `awarmup`:

```python
    def checks(self) -> tuple[HealthCheck, ...]:
        """Return the verification callables the bindings declared, as data.

        Resolves nothing and runs nothing: this is the declaration, in
        resolution order. `health()` and `ahealth()` are what run them.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Database: ...
            >>> def ping(db: Database) -> None: ...
            >>> di = Container().bind(Database, check=ping).freeze()
            >>> [check.key.__qualname__ for check in di.checks()]
            ['Database']

            ```
        """
        return declared_checks(checked_specs(self._plan))

    def health(self) -> HealthReport:
        """Run every declared check and report what each said.

        Each check receives the value its provider resolves to, and is healthy
        unless it raises or returns ``False``. Every check runs: one failure
        never hides another, and a raised exception is carried on its
        `HealthResult` rather than propagating. An error raised while
        *resolving* a provider does propagate — a container that cannot build a
        provider is misused, not unhealthy.

        Raises:
            AsyncInSyncContextError: Some check needs an event loop, because its
                provider is async or the check is. Nothing runs before this is
                raised; use `ahealth()`.
            InvalidProviderError: A check returned an awaitable.
            OutsideScopeError: A check's provider is scoped and no scope is active.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Database:
            ...     ready = False
            >>> def ping(db: Database) -> bool:
            ...     return db.ready
            >>> di = Container().bind(Database, check=ping).freeze()
            >>> di.health().healthy
            False

            ```
        """
        specs = checked_specs(self._plan)
        reject_async_checks(specs)
        return HealthReport(tuple(run_check(spec, self._resolve_any(spec.key, spec.tag)) for spec in specs))

    async def ahealth(self) -> HealthReport:
        """Run every declared check inside an event loop; the counterpart to `health()`.

        Drives async providers and `async def` checks. Otherwise identical.
        """
        specs = checked_specs(self._plan)
        results = [run_check_async(spec, await self._aresolve_any(spec.key, spec.tag)) for spec in specs]
        return HealthReport(tuple([await result for result in results]))
```

`ahealth`'s two-step form is deliberate: each provider is resolved and each check called in order, and the coroutines are awaited as they are produced. If the comprehension form does not type-check or does not preserve that order, write it as an explicit `for` loop appending to a list — correctness of order first, brevity second.

- [ ] **Step 4: Run the tests, then the gates, and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "feat: run the health checks a graph declares"
```

---

### Task 4: The public surface

**Files:**

- Modify: `depin/__init__.py`
- Modify: `tests/unit/test_public_api.py`
- Modify: `tests/typing/test_conformance.py`
- Modify: `tests/unit/test_graph_properties.py`

- [ ] **Step 1: Export the four types**

In `depin/__init__.py`, import `HealthCheck`, `HealthReport`, `HealthResult` from `depin._core.health` and `WarmupReport` from `depin._core.warmup`, and add all four to `__all__` in sorted position. `__all__` is asserted sorted and complete by `tests/unit/test_public_api.py`; update `EXPECTED_EXPORTS` in the same change.

- [ ] **Step 2: Pin the static surface**

Append to `tests/typing/test_conformance.py`, in the file's existing style: `assert_type` over `warmup()` returning `WarmupReport`, `checks()` returning `tuple[HealthCheck, ...]`, `health()` returning `HealthReport`, and `bind(Database, check=ping)` returning `Container` with `ping` annotated to take the bound type. Add one case where the check's parameter type does not match the binding, marked with the sanctioned ignore pair, proving the inference is load-bearing rather than accidental.

- [ ] **Step 3: Extend the generative model**

In `tests/unit/test_graph_properties.py`, add one field to `GraphCase`, last and defaulted, following the precedent `aliases`, `optionals`, `collections`, `generics`, `decorations`, and `inactive` set:

```python
    checks: frozenset[int] = frozenset()
```

Draw it from `registered_nodes` in `_graphs`, and in `_materialize` register the drawn nodes with a check. The check must be a plain function taking one argument; build it the way `_bind_consumer` builds its synthetic classes, or use a module-level `def _always_healthy(value: object) -> None: return None` if a single shared function suffices — it does, since the property below is about the plan, not about what any check returns.

Add the metamorphic property, with `@settings(deadline=None)`:

```python
@settings(deadline=None)
@given(_graphs())
def test_declaring_a_check_changes_nothing_about_the_plan(case: GraphCase) -> None:
    """A check is a value the plan carries, not a rule it applies."""
    assert _freeze_result(case) == _freeze_result(replace(case, checks=frozenset()))
```

Add a second property asserting that for any case that freezes, `checks()` reports exactly the drawn nodes that survived into the plan — that is, that a check is neither lost nor invented by validation, decoration, or the async pass. Derive the expected set from the plan rather than from `case.checks` alone, since a duplicated or unregistered node never reaches the plan.

- [ ] **Step 4: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git add -A
git commit -m "test: pin the warmup and health surface"
```

---

### Task 5: Document, demonstrate, integrate, and benchmark

**Files:**

- Create: `docs/guide/operations.md`, `docs/reference/operations.md`
- Modify: `mkdocs.yml`
- Create: `examples/warmup/__init__.py`, `examples/warmup/main.py`, `examples/health/__init__.py`, `examples/health/main.py`
- Modify: `examples/README.md`, `tests/integration/test_examples.py`, `tests/integration/test_fastapi_ext.py`, `benchmarks/test_resolution.py`

- [ ] **Step 1: Write the guide**

`docs/guide/operations.md` covers warmup and health checks, in that order, in the voice of `docs/guide/composition.md`. Every `pycon` block is executed as a doctest by the default `pytest` run, so paste real output.

Warmup: what it constructs and what it leaves alone; the report's two tuples; the async rule and why it refuses before constructing anything; that a failure aborts startup rather than being reported. Health: how a check is declared; the healthy-unless-it-raises-or-returns-`False` rule; that every check runs; that `checks()` runs nothing; the async rule; that a resolution error propagates while a check's own error does not; that a check on a scoped binding needs a scope.

Add both pages to `mkdocs.yml`'s nav — the guide entry after `Inspecting the graph`, the reference entry after `Graph diagnostics`.

- [ ] **Step 2: Write the reference page**

`docs/reference/operations.md` carries `::: depin.WarmupReport`, `::: depin.HealthCheck`, `::: depin.HealthResult`, and `::: depin.HealthReport`, in the format the other reference pages use.

- [ ] **Step 3: Write the examples**

`examples/warmup/main.py`: a graph with two singletons whose construction is observable, a scoped provider that warmup leaves alone, and a `build()` returning the frozen container. `examples/health/main.py`: a database-shaped provider with a passing check and one with a failing check, printing the report. Both follow `examples/aliasing/main.py`: a `build()` function, a `main()`, no module-level container construction, and an `if __name__ == '__main__':` guard.

Add both to the table in `examples/README.md` and to `tests/integration/test_examples.py`, with assertions that fail if warmup or the check stopped working — not merely that the module runs.

- [ ] **Step 4: Exercise both through FastAPI**

In `tests/integration/test_fastapi_ext.py`, add an app whose lifespan calls `await di.awarmup()` and asserts the singleton was constructed before the first request, and a readiness route returning `(await di.ahealth())` serialised, asserting the response reflects a failing check. Use a real `httpx.AsyncClient` against a real app, as the file already does.

- [ ] **Step 5: Add the benchmark**

Add `warmup()` over `build_chain(1000)` to `benchmarks/test_resolution.py`, matching the neighbouring cases' fixtures and naming. Confirm with `uv run --group bench pytest benchmarks`.

- [ ] **Step 6: Run every gate including the docs build, then commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
git add -A
git commit -m "docs: document warmup and health checks"
```

---

### Task 6: The named-scopes decision, and the evidence

**Files:**

- Modify: `specs/2026-08-28-roadmap-1.0-design.md`
- Create: `specs/evidence/2026-08-31-step-4-warmup-health.md`

- [ ] **Step 1: Record the decision in the roadmap**

The roadmap's Step 4 deliverable reads "**Custom named scopes** *(cycle 2)*. Decided at this step against a stated criterion: it ships only if Steps 3 and 4 surface a concrete use case that the three fixed scopes cannot express. If no such case appears, it is recorded as rejected, with the reasoning, before the freeze."

Replace the conditional wording with the decision taken, in the roadmap's voice: rejected, because neither step surfaced such a case; a one-sentence summary of why decoration was the one place a fourth lifetime could plausibly have been needed and was measured not to be; and a pointer to `specs/2026-08-31-step-4-warmup-health-design.md`'s "Custom named scopes — rejected" section for the full reasoning. Do not duplicate that section into the roadmap.

Commit alone, as `docs: record the named-scopes rejection`.

- [ ] **Step 2: Run the full gate sequence from a clean tree**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

- [ ] **Step 3: Measure coverage**

Run: `uv run pytest --cov=depin --cov-report=term-missing`
Expected: at or above 95%. Name every uncovered line in a module this cycle changed, and check each against `main` at `d2b8ceb` in a throwaway worktree before calling it new. Run coverage twice before attributing `scope.py`'s `_Flight.wait_sync` line to this cycle.

- [ ] **Step 4: Do not run the mutation gate locally**

`[tool.mutmut] only_mutate` covers all of `depin/_core/*.py`, so there is no changed-modules subset; a local run is the full run. The CI `mutation` job is the authority. Record that, and its reason, in the evidence file instead of a score.

- [ ] **Step 5: Confirm the suppression count and what did not change**

```bash
grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin
git diff --stat d2b8ceb -- depin/_core/construct.py depin/_core/diagnostics.py depin/_core/render.py depin/_core/scope.py depin/_core/teardown.py depin/_core/injection.py depin/_core/overrides.py depin/_core/introspect.py depin/_core/markers.py depin/_core/container.py depin/_core/registry.py
```

Expected: exactly three suppressions, byte-identical to `d2b8ceb`; the diff empty. This cycle adds no validation rule, so `graph.py` changes by one line and everything downstream of it not at all.

- [ ] **Step 6: Record the evidence**

Create `specs/evidence/2026-08-31-step-4-warmup-health.md` in the shape of `specs/evidence/2026-08-31-step-4-decoration-conditional.md`. It carries: every command above with its relevant output; the coverage figure with each miss attributed to this cycle or to `main`; the suppression count; the empty diff from Step 5; the benchmark means; the four design measurements, restated from the spec rather than re-derived; and the named-scopes decision with the criterion that produced it.

The evidence file is part of the commit it documents, so every claim it makes about the tree must be true after it lands.

- [ ] **Step 7: Commit**

```bash
git add specs/evidence/2026-08-31-step-4-warmup-health.md
git commit -m "docs: record cycle 2 verification evidence"
```

## Self-review

**Spec coverage.** Measurements — Task 2 Step 1 pins the cache and async rules as tests, Task 4 Step 2 pins the checker measurement, Task 6 Step 5 pins the untouched-module claim. Public surface: `warmup` / `awarmup` — Task 2 Step 3; `checks` / `health` / `ahealth` — Task 3 Step 3; `check=` — Task 1 Step 3; the four types — Task 4 Step 1. Data model: `BindRecord.check` and `ProviderSpec.check` — Task 1 Step 2; `WarmupReport` — Task 2 Step 2; the three health records — Task 3 Step 2. Semantics: the warmup table — Task 2 Step 1; the health table — Task 3 Step 1. Errors table — Task 1 Step 1, Task 2 Step 1, Task 3 Step 1. Named scopes — Task 6 Step 1. Module layout — Tasks 1 to 3. Verification — Tasks 1 to 6.

**Type consistency.** `check` is the field on `BindRecord` and on `ProviderSpec`, the keyword on `bind` and `value`, and the noun in every message; `checks()` is the plural that describes and `health()` the verb that runs, and the two are never used for each other. `HealthCheck`, `HealthResult`, `HealthReport`, and `WarmupReport` are spelled the same in every task. `needs_async` means the same thing on `ProviderSpec` and on `HealthCheck`.

**Known verification points.** Two error messages are rendered from keys and pinned by tests: the `warmup()` refusal and the `health()` refusal, both built with `fmt_chain`, whose output must be printed before either assertion is written — Task 2 Step 2 says so explicitly and offers the alternative rendering. Task 2 Step 1 contains one test written wrong on purpose, with the correction stated inline, so a worker who copies the block without reading it is caught by the step rather than by CI.

**Ordering risk.** Task 1 must land the two carry-forward sites — `graph._with_async_flags` and `decoration._chain` — in the same change as the field, or Tasks 2 and 3 build on a plan that silently drops every check; Task 1 Step 1 writes a test for each before the field exists. Task 3 depends on Task 1 for `ProviderSpec.check` and on nothing in Task 2. Task 4 depends on both. Every task commits a green tree.

**Blast radius.** Two new modules, and one new field threaded through four existing ones. No `ProviderShape`, no validation rule, no plan node: `graph.py` changes by a single argument and `construct.py`, `diagnostics.py`, and `render.py` not at all, which Task 6 Step 5 fails on if untrue.
