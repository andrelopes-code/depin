# Step 5, cycle 1 — the integration contract: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `Host`, `hosted_container`, `optional_hosted_container`, `ContractVersion`, and `CONTRACT_VERSION` as the integration contract; rewrite `depin.ext.fastapi` on top of them so it imports nothing from `depin._core`; make a contract test fail when any integration does; and remove the frame short-circuit the contract's seeding operation would otherwise inherit — for the 0.13.0 milestone.

**Architecture:** One new module, `depin/_core/hosting.py`, holding a `ContextVar[FrozenContainer | None]`, the `Host` that publishes into it, and the two readers. It composes existing public operations — `FrozenContainer.scope` / `ascope`, `ScopeFrame.provide`, `FrozenContainer.resolve` / `aresolve` — and adds no resolution machinery. One behaviour change in `depin/_core/frozen.py`: `_resolve_params_sync` and `_resolve_params_async` consult the plan for every parameter instead of short-circuiting to the active frame. `depin/ext/fastapi.py` is rewritten against `depin`'s public surface only, and a new contract test parses every module under `depin/ext/` to prove it.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, Hypothesis, mutmut 3.7, pytest-benchmark, mkdocs-material with mkdocstrings, uv.

**Spec:** `specs/2026-08-31-step-5-contract-design.md`

## Global constraints

Every task inherits these requirements from `AGENTS.md`, the approved roadmap, and the spec.

- The core keeps zero runtime dependencies. `depin/_core/hosting.py` imports stdlib and `depin` only. Nothing here adds a package to `[project.dependencies]`.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `typing.Any`, `typing.cast`, `# type: ignore`, or `# pyright: ignore`. `depin/` carries exactly three suppressions today — `depin/_core/markers.py:132`, `depin/_core/frozen.py:127`, `depin/_core/frozen.py:150` — and must carry exactly those three when this cycle ends. Confirm the line numbers against the tree before relying on them: `grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin`.
- Every exception raised by library code inherits `DepinError`. No bare `KeyError`, `TypeError`, `ValueError`, or `assert` in `depin/`.
- Data structures are `@dataclass(frozen=True, slots=True)`; a public one is additionally `@final`.
- `basedpyright --strict` sets `reportImplicitOverride`, so a `__str__` on a dataclass carries `@typing.override`. It also sets `reportUnnecessaryIsInstance`, `reportMissingTypeArgument`, and `reportUnusedClass`. `mypy --strict` adds `warn_unreachable` and `redundant-expr`, so a runtime guard whose annotation already excludes the rejected case must take `object` in a private helper rather than be suppressed.
- New behaviour in `depin/_core/` is developed test-first: the failing test is written and observed failing before the implementation.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery. `reportPrivateUsage` forbids reading `FrozenContainer._plan` from a test; build plans with `build_plan(container.records())`.
- Public API additions carry Google-style docstrings that omit types from `Args:` / `Returns:` and include a doctest `Example:`. Doctests run in the default `pytest` invocation. An `async` operation with no runnable one-liner carries prose instead of an `Example:`.
- Mutation budget: `depin/_core/*.py` is what `[tool.mutmut] only_mutate` covers, so `hosting.py` is mutated from the day it lands, and the `mutation` workflow triggers on this cycle's diff. Assert every error message as a **complete** string with `==`, never with `in`: mutmut mutates each fragment of a literal and an `in` assertion leaves them all alive.
- `fmt_key` renders a class by `__qualname__`, so a class declared inside a test function appears as `test_x.<locals>.Name`. Print the real string before pinning any text assertion.
- Coverage over `depin/` stays at or above 95%; it is 98.9% at the 0.12.0 baseline. `depin/_core/scope.py`'s line inside `_Flight.wait_sync` reports uncovered in roughly one run in two on any commit; run coverage twice before attributing a miss to this cycle.
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
- `uv run ruff format` reformats Python inside markdown fences, including under `specs/` and `docs/`, and CI runs `ruff format --check` over the whole repository. Never revert that reformatting.
- Commits are focused, conventional, at most 72 characters in the subject, and contain no attribution or automation language.

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `depin/_core/hosting.py` | **New.** `ContractVersion`, `CONTRACT_VERSION`, `Host`, the ambient variable and its two readers. | 1 |
| `tests/unit/test_hosting.py` | **New.** The contract, end to end. | 1 |
| `depin/_core/frozen.py` | `_resolve_params_sync` / `_resolve_params_async` drop the frame short-circuit. | 2 |
| `tests/unit/test_resolution.py` | A seeded key that also has a binding resolves to its binding. | 2 |
| `tests/unit/test_frozen_async.py` | The same, asynchronously, and the tagged case. | 2 |
| `depin/__init__.py` | Re-exports the five contract symbols. | 3 |
| `depin/errors.py` | `ContainerNotBoundError` documented against the contract. | 3 |
| `tests/unit/test_public_api.py` | The five new exports. | 3 |
| `tests/typing/test_conformance.py` | `assert_type` over the contract. | 3 |
| `depin/ext/fastapi.py` | Rewritten on `Host` and `optional_hosted_container`. | 4 |
| `tests/unit/test_integration_contract.py` | **New.** No integration reaches into `depin._core`. | 4 |
| `docs/guide/integrations.md` | **New.** Writing an integration. | 5 |
| `docs/reference/hosting.md` | **New.** The five reference entries. | 5 |
| `mkdocs.yml` | Nav entries for both. | 5 |
| `examples/integration/` | **New.** A job runner hosting a container. | 5 |
| `examples/README.md` | Lists it. | 5 |
| `tests/integration/test_examples.py` | Executes it. | 5 |
| `benchmarks/test_resolution.py` | A request-shaped graph with a seeded frame value. | 5 |
| `README.md` | The contract in the feature list. | 5 |
| `AGENTS.md` | `hosting.py` in the `_core` module map. | 5 |
| `pyproject.toml` | The `fastapi` extra keeps its floor; no new extra this cycle. | 6 |
| `.github/workflows/ci.yml` | **New job.** `latest-versions`. | 6 |

---

### Task 1: The contract module

The seam, alone. Nothing consumes it yet.

**The hazard this task exists to close:** an ambient container published and never unpublished leaks across units of work, and the leak is invisible in a single-request test. Every path out of `activated()` — normal exit, exception, and the exception a teardown raises on scope exit — is tested for restoration before the implementation exists.

**Files:**

- Create: `depin/_core/hosting.py`
- Create: `tests/unit/test_hosting.py`

**Interfaces:**

- Produces: `ContractVersion`, `CONTRACT_VERSION`, `Host`, `hosted_container`, `optional_hosted_container` in `depin._core.hosting`.

- [ ] **Step 1: Write the failing contract tests**

Create `tests/unit/test_hosting.py`:

```python
"""The integration contract: publishing a container, scoping a unit of work, reading it back."""

import asyncio
import threading
from collections.abc import AsyncGenerator, Generator

import pytest

from depin import Container, Scope, Token
from depin._core.hosting import (
    CONTRACT_VERSION,
    ContractVersion,
    Host,
    hosted_container,
    optional_hosted_container,
)
from depin.errors import ContainerNotBoundError, OutsideScopeError

REQUEST = Token[str]('request')


def test_the_contract_version_is_one_zero() -> None:
    assert CONTRACT_VERSION == ContractVersion(1, 0)


def test_a_contract_version_renders_as_major_dot_minor() -> None:
    assert str(ContractVersion(2, 7)) == '2.7'


def test_contract_versions_order_by_major_then_minor() -> None:
    assert ContractVersion(1, 0) < ContractVersion(1, 1) < ContractVersion(2, 0)


def test_a_host_keeps_the_container_it_was_given() -> None:
    di = Container().freeze()

    assert Host(di).container is di


def test_nothing_is_hosted_by_default() -> None:
    assert optional_hosted_container() is None


def test_reading_an_unhosted_container_names_both_ways_to_publish_one() -> None:
    with pytest.raises(ContainerNotBoundError) as caught:
        hosted_container()

    assert str(caught.value) == (
        'no container is hosted in this context; open a scope with Host.scope() or Host.ascope(), '
        'or publish one with Host.activated()'
    )


def test_activated_publishes_the_container_and_undoes_it_on_exit() -> None:
    di = Container().freeze()

    with Host(di).activated():
        assert hosted_container() is di

    assert optional_hosted_container() is None


def test_activated_undoes_the_publication_when_the_block_raises() -> None:
    di = Container().freeze()

    with pytest.raises(RuntimeError), Host(di).activated():
        raise RuntimeError('boom')

    assert optional_hosted_container() is None


def test_a_nested_host_wins_and_restores_the_enclosing_one() -> None:
    outer = Container().freeze()
    inner = Container().freeze()

    with Host(outer).activated():
        with Host(inner).activated():
            assert hosted_container() is inner
        assert hosted_container() is outer


def test_activated_opens_no_scope() -> None:
    di = Container().scope_value(REQUEST).freeze()

    with Host(di).activated(), pytest.raises(OutsideScopeError):
        di.resolve(REQUEST)


def test_scope_publishes_seeds_and_resolves() -> None:
    di = Container().scope_value(REQUEST).freeze()
    host = Host(di)

    with host.scope() as frame:
        frame.provide(REQUEST, 'r-1')
        assert hosted_container().resolve(REQUEST) == 'r-1'

    assert optional_hosted_container() is None


def test_scope_drains_its_teardowns_before_unpublishing() -> None:
    seen: list[str | None] = []

    class Session: ...

    def open_session() -> Generator[Session]:
        yield Session()
        seen.append(None if optional_hosted_container() is None else 'hosted')

    di = Container().bind(open_session, scope=Scope.SCOPED).freeze()

    with Host(di).scope():
        _ = di.resolve(Session)

    assert seen == ['hosted']


def test_two_sibling_scopes_get_independent_seeds() -> None:
    di = Container().scope_value(REQUEST).freeze()
    host = Host(di)
    seen: list[str] = []

    for label in ('a', 'b'):
        with host.scope() as frame:
            frame.provide(REQUEST, label)
            seen.append(hosted_container().resolve(REQUEST))

    assert seen == ['a', 'b']


@pytest.mark.asyncio
async def test_ascope_publishes_seeds_and_resolves() -> None:
    class Session: ...

    async def open_session() -> AsyncGenerator[Session]:
        yield Session()

    di = Container().scope_value(REQUEST).bind(open_session, scope=Scope.SCOPED).freeze()
    host = Host(di)

    async with host.ascope() as frame:
        frame.provide(REQUEST, 'r-2')
        container = hosted_container()
        assert await container.aresolve(REQUEST) == 'r-2'
        assert isinstance(await container.aresolve(Session), Session)

    assert optional_hosted_container() is None


@pytest.mark.asyncio
async def test_ascope_undoes_the_publication_when_the_block_raises() -> None:
    di = Container().freeze()

    with pytest.raises(RuntimeError):
        async with Host(di).ascope():
            raise RuntimeError('boom')

    assert optional_hosted_container() is None


@pytest.mark.asyncio
async def test_concurrent_ascopes_do_not_see_each_others_seeds() -> None:
    di = Container().scope_value(REQUEST).freeze()
    host = Host(di)

    async def handle(label: str) -> str:
        entered = host.ascope()
        frame = await entered.__aenter__()
        try:
            frame.provide(REQUEST, label)
            return await hosted_container().aresolve(REQUEST)
        finally:
            await entered.__aexit__(None, None, None)

    assert sorted(await asyncio.gather(handle('a'), handle('b'))) == ['a', 'b']


def test_a_scope_entered_by_hand_publishes_and_unpublishes() -> None:
    di = Container().freeze()
    entered = Host(di).scope()
    _ = entered.__enter__()

    assert hosted_container() is di

    entered.__exit__(None, None, None)

    assert optional_hosted_container() is None


def test_a_host_in_another_thread_does_not_leak_into_this_one() -> None:
    di = Container().freeze()
    seen: list[object] = []

    def run() -> None:
        with Host(di).activated():
            seen.append(hosted_container())

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert seen == [di]
    assert optional_hosted_container() is None
```

- [ ] **Step 2: Observe the tests fail**

```bash
uv run pytest tests/unit/test_hosting.py -q
```

Every test must fail on the missing `depin._core.hosting` module. Record the failure count.

- [ ] **Step 3: Write the module**

Create `depin/_core/hosting.py`:

```python
"""The public seam an integration uses to host a container inside a framework."""

import contextlib
from collections.abc import AsyncGenerator, Generator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, final, override

from depin._core.frozen import FrozenContainer
from depin._core.scope import ScopeFrame
from depin.errors import ContainerNotBoundError


@final
@dataclass(frozen=True, slots=True, order=True)
class ContractVersion:
    """The version of the integration contract a release of depin implements.

    The minor number rises when an operation is added and every existing one
    keeps its meaning; the major number rises when an operation changes meaning
    or is removed. An integration that needs an operation added in ``1.2``
    guards on ``depin.CONTRACT_VERSION >= ContractVersion(1, 2)``.

    Attributes:
        major: Rises on a breaking change to an existing operation.
        minor: Rises when an operation is added.

    Example:
        ```pycon
        >>> from depin import CONTRACT_VERSION, ContractVersion
        >>> CONTRACT_VERSION >= ContractVersion(1, 0)
        True
        >>> str(CONTRACT_VERSION)
        '1.0'

        ```
    """

    major: int
    minor: int

    @override
    def __str__(self) -> str:
        return f'{self.major}.{self.minor}'


CONTRACT_VERSION: Final = ContractVersion(1, 0)
"""The contract version this release of depin implements."""

_hosted: ContextVar[FrozenContainer | None] = ContextVar('depin_hosted_container', default=None)


@final
class Host:
    """A `FrozenContainer` hosted inside a framework.

    An integration builds one `Host` when the application is wired, then opens
    a scope per unit of work — an HTTP request, a CLI invocation, a queue
    message. Inside that scope the container is published to the current
    `contextvars.Context`, so code that carries only an annotation reaches it
    through `hosted_container()`.

    The publication is context-local, so concurrent requests and concurrent
    tasks never see each other's container, and two hosts in one process nest:
    the innermost wins and the enclosing one is restored on exit.

    Example:
        ```pycon
        >>> from depin import Container, Host, Token, hosted_container
        >>> request_id = Token[str]('request_id')
        >>> di = Container().scope_value(request_id).freeze()
        >>> host = Host(di)
        >>> with host.scope() as frame:
        ...     frame.provide(request_id, 'r-1')
        ...     hosted_container().resolve(request_id)
        'r-1'

        ```
    """

    __slots__ = ('_container',)

    def __init__(self, container: FrozenContainer) -> None:
        self._container = container

    @property
    def container(self) -> FrozenContainer:
        """The container this host was built around."""
        return self._container

    @contextlib.contextmanager
    def activated(self) -> Generator[None]:
        """Publish the container for the duration of the block, opening no scope.

        What an integration uses outside a unit of work: an ASGI lifespan, a
        process-wide CLI setup, anything that resolves singletons through
        `hosted_container()` without a scope to open.

        Example:
            ```pycon
            >>> from depin import Container, Host, hosted_container
            >>> di = Container().freeze()
            >>> with Host(di).activated():
            ...     hosted_container() is di
            True

            ```
        """
        token = _hosted.set(self._container)
        try:
            yield
        finally:
            _hosted.reset(token)

    @contextlib.contextmanager
    def scope(self) -> Generator[ScopeFrame]:
        """Publish the container and open one synchronous scope around a unit of work.

        Yields the scope's frame so the caller can seed the framework's own
        objects into it with `ScopeFrame.provide` before anything resolves. On
        exit the scope's teardowns run first and the publication is undone
        after, so a teardown can still reach the container.

        Raises:
            TeardownError: An async provider left a teardown in this sync
                scope. Use `ascope()` instead.

        Example:
            ```pycon
            >>> from depin import Container, Host, Token, hosted_container
            >>> job = Token[str]('job')
            >>> di = Container().scope_value(job).freeze()
            >>> with Host(di).scope() as frame:
            ...     frame.provide(job, 'reindex')
            ...     hosted_container().resolve(job)
            'reindex'

            ```
        """
        with self.activated(), self._container.scope() as frame:
            yield frame

    @contextlib.asynccontextmanager
    async def ascope(self) -> AsyncGenerator[ScopeFrame]:
        """Publish the container and open one asynchronous scope; the counterpart to `scope()`.

        Required when any provider in the scope is async. Otherwise identical:
        the frame is yielded for seeding, teardowns run before the publication
        is undone.
        """
        with self.activated():
            async with self._container.ascope() as frame:
                yield frame


def hosted_container() -> FrozenContainer:
    """Return the container hosted in this context.

    Raises:
        ContainerNotBoundError: No `Host` has published a container here.
            Open a scope with `Host.scope()` / `Host.ascope()`, or publish one
            with `Host.activated()`.

    Example:
        ```pycon
        >>> from depin import Container, Host, hosted_container
        >>> di = Container().freeze()
        >>> with Host(di).activated():
        ...     hosted_container() is di
        True

        ```
    """
    container = _hosted.get()
    if container is None:
        raise ContainerNotBoundError(
            'no container is hosted in this context; open a scope with Host.scope() or Host.ascope(), '
            'or publish one with Host.activated()'
        )
    return container


def optional_hosted_container() -> FrozenContainer | None:
    """Return the container hosted in this context, or ``None`` when there is none.

    The non-raising counterpart to `hosted_container()`. An integration uses it
    to raise its own message, naming the setup step its users actually
    forgot — installing a middleware, registering a plugin — rather than the
    contract-level one.

    Example:
        ```pycon
        >>> from depin import optional_hosted_container
        >>> optional_hosted_container() is None
        True

        ```
    """
    return _hosted.get()
```

- [ ] **Step 4: Observe the tests pass and the gates hold**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest tests/unit/test_hosting.py -q
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add the public integration contract"
```

---

### Task 2: Resolution consults the plan for every parameter

The frame short-circuit goes. This is the one behaviour change in the cycle.

**The hazard this task exists to close:** `_resolve_params_sync` and `_resolve_params_async` are duplicated bodies. Changing one and not the other leaves the sync and async paths disagreeing about what a seeded key means, and the existing suite would not notice, because the async cases it covers are the ones both paths already agree on. A test is written for each path before either changes.

**Files:**

- Modify: `depin/_core/frozen.py`
- Modify: `tests/unit/test_resolution.py`
- Modify: `tests/unit/test_frozen_async.py`

- [ ] **Step 1: Write the failing resolution tests**

Append to `tests/unit/test_resolution.py`:

```python
def test_a_seeded_key_that_also_has_a_binding_resolves_to_its_binding() -> None:
    class Clock:
        def __init__(self, label: str = 'bound') -> None:
            self.label = label

    class Report:
        def __init__(self, clock: Clock) -> None:
            self.clock = clock

    frozen = Container().bind(Clock).bind(Report, scope=Scope.SCOPED).freeze()

    with frozen.scope() as frame:
        frame.provide(Clock, Clock('seeded'))
        report = frozen.resolve(Report)

    assert report.clock.label == 'bound'
    assert frozen.resolve(Clock).label == 'bound'


def test_a_tagged_parameter_ignores_a_frame_value_seeded_under_the_bare_key() -> None:
    class Store:
        def __init__(self, label: str) -> None:
            self.label = label

    class Page:
        def __init__(self, store: Annotated[Store, Tag('primary')]) -> None:
            self.store = store

    frozen = (
        Container()
        .bind(lambda: Store('primary'), provides=Store, tag='primary')
        .bind(Page, scope=Scope.SCOPED)
        .freeze()
    )

    with frozen.scope() as frame:
        frame.provide(Store, Store('seeded'))
        page = frozen.resolve(Page)

    assert page.store.label == 'primary'
```

`Annotated` and `Tag` must be imported in that module; add them to the existing imports if absent.

Append to `tests/unit/test_frozen_async.py`:

```python
@pytest.mark.asyncio
async def test_an_async_seeded_key_that_also_has_a_binding_resolves_to_its_binding() -> None:
    class Clock:
        def __init__(self, label: str = 'bound') -> None:
            self.label = label

    class Report:
        def __init__(self, clock: Clock) -> None:
            self.clock = clock

    frozen = Container().bind(Clock).bind(Report, scope=Scope.SCOPED).freeze()

    async with frozen.ascope() as frame:
        frame.provide(Clock, Clock('seeded'))
        report = await frozen.aresolve(Report)

    assert report.clock.label == 'bound'
```

- [ ] **Step 2: Observe the three tests fail**

```bash
uv run pytest tests/unit/test_resolution.py tests/unit/test_frozen_async.py -q
```

All three must fail on the seeded value winning. Record the assertion messages.

- [ ] **Step 3: Remove the short-circuit from both paths**

In `depin/_core/frozen.py`, replace the opening of `_resolve_params_sync`:

```python
    def _resolve_params_sync(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        frame = optional_frame()
        for param in spec.params:
            if frame is not None and param.key in frame:
                out[param.name] = frame.get(param.key)
                continue
            dep = self._lookup_optional(param.key, param.tag)
```

with:

```python
    def _resolve_params_sync(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        for param in spec.params:
            dep = self._lookup_optional(param.key, param.tag)
```

and make the identical replacement in `_resolve_params_async`.

- [ ] **Step 4: Drop the now-unused import**

In `depin/_core/frozen.py`, change:

```python
from depin._core.scope import MISSING, Scope, ScopeFrame, active_frame, optional_frame, push_frame
```

to:

```python
from depin._core.scope import MISSING, Scope, ScopeFrame, active_frame, push_frame
```

`optional_frame` stays in `depin/_core/scope.py`; `tests/unit/test_free_threading.py` uses it.

- [ ] **Step 5: Observe the whole suite pass**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest -q
```

The count must be 832 existing tests plus everything added so far, with no failures. `test_async_scope_values_do_not_skip_later_tagged_dependencies` is the test written against the removed branch; it must still pass, because the plan reaches the same values by the declared route.

- [ ] **Step 6: Commit**

```bash
git commit -m "fix: resolve a parameter from the plan before the frame"
```

---

### Task 3: The public surface

**Files:**

- Modify: `depin/__init__.py`
- Modify: `depin/errors.py`
- Modify: `tests/unit/test_public_api.py`
- Modify: `tests/typing/test_conformance.py`

- [ ] **Step 1: Extend the expected export list**

In `tests/unit/test_public_api.py`, `EXPECTED_EXPORTS` becomes, in this exact order:

```python
EXPECTED_EXPORTS = (
    'Bindings',
    'CONTRACT_VERSION',
    'Condition',
    'Container',
    'ContractVersion',
    'DependencyGraph',
    'FrozenContainer',
    'GraphEdge',
    'GraphNode',
    'HealthCheck',
    'HealthReport',
    'HealthResult',
    'Host',
    'Named',
    'ProviderKey',
    'ProviderShape',
    'Registry',
    'Scope',
    'ScopeDecorator',
    'ScopeFrame',
    'Tag',
    'Token',
    'Underlying',
    'WarmupReport',
    'hosted_container',
    'injected',
    'optional_hosted_container',
    'provides',
)
```

Run `uv run pytest tests/unit/test_public_api.py -q` and observe it fail.

- [ ] **Step 2: Export the five symbols**

In `depin/__init__.py`, add the import in alphabetical position among the existing `from depin._core...` block:

```python
from depin._core.hosting import (
    CONTRACT_VERSION,
    ContractVersion,
    Host,
    hosted_container,
    optional_hosted_container,
)
```

and set `__all__` to the tuple above.

- [ ] **Step 3: Document `ContainerNotBoundError` against the contract**

In `depin/errors.py`, replace the `ContainerNotBoundError` docstring body:

```python
class ContainerNotBoundError(DepinError, RuntimeError):
    """No container is hosted in the context a dependency was resolved from.

    Raised by `depin.hosted_container()` when no `depin.Host` has published a
    container here, and by an integration that reads the host itself — the
    FastAPI integration raises it when ``Inject[T]`` is evaluated outside a
    `RequestScope`, naming the middleware to install.

    Resolve it by opening a scope with ``Host.scope()`` / ``Host.ascope()``
    around the unit of work, or by publishing the container with
    ``Host.activated()``.

    Inherits ``RuntimeError``, so existing ``except RuntimeError`` handlers keep
    working.
    """
```

- [ ] **Step 4: Add the conformance assertions**

In `tests/typing/test_conformance.py`, extend the `from depin import (...)` list with `CONTRACT_VERSION`, `ContractVersion`, `Host`, `hosted_container`, `optional_hosted_container`, and append:

```python
def check_the_integration_contract() -> None:
    di = Container().bind(Config).freeze()
    host = Host(di)
    assert_type(host.container, FrozenContainer)
    assert_type(CONTRACT_VERSION, ContractVersion)
    assert_type(CONTRACT_VERSION.major, int)
    with host.scope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(hosted_container(), FrozenContainer)
        assert_type(hosted_container().resolve(Config), Config)
    assert_type(optional_hosted_container(), FrozenContainer | None)


async def check_the_integration_contract_async() -> None:
    di = Container().bind(Config).freeze()
    async with Host(di).ascope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(await hosted_container().aresolve(Config), Config)
```

- [ ] **Step 5: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest -q
git commit -m "feat: export the integration contract from depin"
```

---

### Task 4: The FastAPI rewrite and the contract test

**The hazard this task exists to close:** a rewrite that keeps the integration working but quietly keeps one `depin._core` import proves nothing, and no existing check would catch it. The contract test is written and observed passing against the *unrewritten* module's replacement first, so the assertion is known to be capable of failing.

**Files:**

- Create: `tests/unit/test_integration_contract.py`
- Modify: `depin/ext/fastapi.py`

- [ ] **Step 1: Write the contract test**

Create `tests/unit/test_integration_contract.py`:

```python
"""No integration under `depin/ext/` may reach into `depin._core`."""

import ast
from pathlib import Path

import pytest

import depin
import depin.ext

_EXT_PACKAGE = 'depin.ext'


def _absolute(module: str | None, level: int, package: str) -> str:
    if level == 0:
        return module or ''
    parts = package.split('.')
    base = '.'.join(parts[: len(parts) - level + 1])
    return f'{base}.{module}' if module else base


def imported_modules(source: str, package: str) -> tuple[str, ...]:
    """Every module name a source file imports, with relative imports made absolute."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(_absolute(node.module, node.level, package))
    return tuple(names)


def public_names_imported_from_depin(source: str, package: str) -> tuple[str, ...]:
    """Every name imported directly out of the `depin` package."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and _absolute(node.module, node.level, package) == 'depin':
            names.extend(alias.name for alias in node.names)
    return tuple(names)


def reaches_into_core(source: str, package: str) -> tuple[str, ...]:
    return tuple(
        name for name in imported_modules(source, package) if name == 'depin._core' or name.startswith('depin._core.')
    )


def _integration_modules() -> list[Path]:
    return sorted(path for path in Path(depin.ext.__file__).parent.glob('*.py'))


def test_the_scanner_reports_a_module_that_imports_depin_core() -> None:
    source = 'from depin._core.frozen import FrozenContainer\n'

    assert reaches_into_core(source, _EXT_PACKAGE) == ('depin._core.frozen',)


def test_the_scanner_reports_a_relative_reach_into_depin_core() -> None:
    source = 'from .._core.scope import ScopeFrame\n'

    assert reaches_into_core(source, _EXT_PACKAGE) == ('depin._core.scope',)


def test_the_scanner_reports_a_plain_import_of_depin_core() -> None:
    source = 'import depin._core.frozen\n'

    assert reaches_into_core(source, _EXT_PACKAGE) == ('depin._core.frozen',)


def test_the_scanner_accepts_the_public_package() -> None:
    source = 'from depin import Host, hosted_container\n'

    assert reaches_into_core(source, _EXT_PACKAGE) == ()


@pytest.mark.parametrize('path', _integration_modules(), ids=lambda path: path.name)
def test_no_integration_reaches_into_depin_core(path: Path) -> None:
    assert reaches_into_core(path.read_text(), _EXT_PACKAGE) == ()


@pytest.mark.parametrize('path', _integration_modules(), ids=lambda path: path.name)
def test_no_integration_names_depin_core_at_all(path: Path) -> None:
    """Catches an attribute walk (`depin._core.frozen`) that the import scan cannot see."""
    assert '_core' not in path.read_text()


@pytest.mark.parametrize('path', _integration_modules(), ids=lambda path: path.name)
def test_every_name_an_integration_imports_from_depin_is_public(path: Path) -> None:
    imported = public_names_imported_from_depin(path.read_text(), _EXT_PACKAGE)

    assert [name for name in imported if name not in depin.__all__] == []
```

- [ ] **Step 2: Observe it fail on the unrewritten integration**

```bash
uv run pytest tests/unit/test_integration_contract.py -q
```

`test_no_integration_reaches_into_depin_core[fastapi.py]` and
`test_no_integration_names_depin_core_at_all[fastapi.py]` must fail, naming
`depin._core.frozen`. That failure is the proof the test can fail; record it.

- [ ] **Step 3: Rewrite the integration**

Replace the imports and the `RequestScope` body in `depin/ext/fastapi.py`:

```python
"""FastAPI integration: per-request scoping and type-level injection.

Importing this module requires the ``fastapi`` extra (``pip install
'pydepin[fastapi]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract — `depin.Host`
and `depin.optional_hosted_container` — so it is also the worked example the
"writing an integration" guide points at.
"""

from typing import TYPE_CHECKING, Annotated

from fastapi import Request
from fastapi.params import Depends
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as ASGIScope

from depin import FrozenContainer, Host, optional_hosted_container
from depin.errors import ContainerNotBoundError
```

`RequestScope` keeps its docstring, and its body becomes:

```python
__slots__ = ('_app', '_host')


def __init__(self, app: ASGIApp, container: FrozenContainer) -> None:
    self._app = app
    self._host = Host(container)


async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
    if scope['type'] not in ('http', 'websocket'):
        await self._app(scope, receive, send)
        return
    async with self._host.ascope() as frame:
        if scope['type'] == 'http':
            frame.provide(Request, Request(scope))
        await self._app(scope, receive, send)
```

The module-level `_active_container` `ContextVar` is deleted; the contract owns
that variable now. `Inject`'s resolver becomes:

```python
        def __class_getitem__(cls, key: object) -> object:
            async def resolver() -> object:
                container = optional_hosted_container()
                if container is None:
                    raise ContainerNotBoundError(
                        'Inject[...] resolved outside a RequestScope; install the middleware with '
                        'app.add_middleware(RequestScope, container=...).'
                    )
                return await container.aresolve(key)

            return Annotated[key, Depends(dependency=resolver)]
```

Add one sentence to the `RequestScope` docstring, after the paragraph about
lifespan scopes: "The container is published to the request's context for the
duration of the scope, so `depin.hosted_container()` reaches it from anywhere
inside the request."

- [ ] **Step 4: Observe the contract test pass and the integration suite pass unchanged**

```bash
uv run pytest tests/unit/test_integration_contract.py tests/integration -q
```

`tests/integration/test_fastapi_ext.py` and `test_fastapi_robustness.py` must
pass with no edit. If either needed one, stop: the rewrite changed behaviour
and the change has to be understood before it is accepted.

- [ ] **Step 5: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest -q
git commit -m "refactor: rewrite the FastAPI integration on the contract"
```

---

### Task 5: Document, demonstrate, and benchmark

**Files:**

- Create: `docs/guide/integrations.md`
- Create: `docs/reference/hosting.md`
- Modify: `mkdocs.yml`
- Create: `examples/integration/__init__.py`, `examples/integration/main.py`
- Modify: `examples/README.md`
- Modify: `tests/integration/test_examples.py`
- Modify: `benchmarks/test_resolution.py`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write the runnable example**

Create `examples/integration/__init__.py` (empty) and `examples/integration/main.py`:

```python
"""Hosting a container in a framework depin does not ship.

A job runner is the smallest host there is: it has a unit of work, an object of
its own to hand to providers, and a place to put setup and teardown. The same
four operations serve a web framework, a CLI, and a queue consumer.

Run with ``python -m examples.integration.main``.
"""

from collections.abc import Generator
from dataclasses import dataclass

from depin import Container, FrozenContainer, Host, Scope, hosted_container

LOG: list[str] = []


@dataclass(frozen=True, slots=True)
class Job:
    """The runner's own object, seeded into the scope it opens for each job."""

    name: str


class Metrics:
    """A singleton: one per process, outliving every job."""

    def __init__(self) -> None:
        self.completed = 0


class Workspace:
    """Scoped, with a teardown: one per job, cleaned up when the job ends."""

    def __init__(self, job: Job) -> None:
        self.job = job


def open_workspace(job: Job) -> Generator[Workspace]:
    LOG.append(f'open {job.name}')
    yield Workspace(job)
    LOG.append(f'close {job.name}')


def build() -> FrozenContainer:
    return Container().scope_value(Job).bind(Metrics).bind(open_workspace, scope=Scope.SCOPED).freeze()


class JobRunner:
    """The integration: it owns a `Host` and opens one scope per unit of work."""

    def __init__(self, container: FrozenContainer) -> None:
        self._host = Host(container)

    def run(self, name: str) -> str:
        with self._host.scope() as frame:
            frame.provide(Job, Job(name))
            return handle()


def handle() -> str:
    """A handler that carries no container reference, only the contract."""
    di = hosted_container()
    workspace = di.resolve(Workspace)
    metrics = di.resolve(Metrics)
    metrics.completed += 1
    return f'{workspace.job.name} (completed={metrics.completed})'


def main() -> None:
    LOG.clear()
    di = build()
    runner = JobRunner(di)

    print(runner.run('reindex'))
    print(runner.run('vacuum'))
    print('log:', LOG)

    # The singleton outlived both jobs; the workspaces did not.
    print('completed:', di[Metrics].completed)
    di.close()


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Exercise the example**

Append to `tests/integration/test_examples.py`, with the import added to the existing block in alphabetical position:

```python
def test_integration_example_opens_one_scope_per_job() -> None:
    INTEGRATION_LOG.clear()
    di = build_integration()
    runner = JobRunner(di)

    assert runner.run('reindex') == 'reindex (completed=1)'
    assert runner.run('vacuum') == 'vacuum (completed=2)'
    assert INTEGRATION_LOG == ['open reindex', 'close reindex', 'open vacuum', 'close vacuum']
    assert di[IntegrationMetrics].completed == 2
    di.close()


def test_integration_example_leaves_no_container_hosted() -> None:
    di = build_integration()
    _ = JobRunner(di).run('reindex')

    assert optional_hosted_container() is None
    di.close()
```

Imports to add:

```python
from depin import optional_hosted_container
from examples.integration.main import LOG as INTEGRATION_LOG
from examples.integration.main import JobRunner
from examples.integration.main import Metrics as IntegrationMetrics
from examples.integration.main import build as build_integration
```

Run `uv run python -m examples.integration.main` and paste the real output nowhere but the terminal; the example prints for a human, and the test is what pins its behaviour.

- [ ] **Step 3: List the example**

Add one row to the table in `examples/README.md`, immediately before the `fastapi_app` row:

```markdown
| [`integration`](integration/main.py) | `python -m examples.integration.main` | `Host` opening one scope per unit of work, a seeded frame value, and `hosted_container()` in a handler that holds no container. |
```

- [ ] **Step 4: Write the reference page**

Create `docs/reference/hosting.md`:

```markdown
# Integration contract

The seam an integration uses to host a container inside a framework. See
[Writing an integration](../guide/integrations.md) for the narrative.

::: depin.Host

::: depin.hosted_container

::: depin.optional_hosted_container

::: depin.ContractVersion
```

- [ ] **Step 5: Write the guide**

Create `docs/guide/integrations.md`. It is the normative reference for a third
party, so it states the contract, then works one integration end to end. Its
`pycon` blocks are doctests run by the default `pytest`, so every output is
pasted from a real run.

Required sections, in order:

1. **What an integration does** — the four operations, as a table: publish the
   container (`Host.activated`), open a scope per unit of work (`Host.scope` /
   `Host.ascope`), seed the framework's objects (`ScopeFrame.provide` on the
   yielded frame, against a key declared with `Container.scope_value`), and
   read the container back (`hosted_container` /
   `optional_hosted_container`).
2. **A worked integration** — the job runner from `examples/integration/`,
   built up in `pycon` blocks: the container, the `Host`, the scope, the seed,
   the handler.
3. **Hosts whose lifecycle is a pair of hooks** — `Host.scope()` returns an
   ordinary context-manager object, so a framework that gives `before` and
   `after` hooks instead of a block stores it and calls `__enter__` /
   `__exit__` (or `__aenter__` / `__aexit__`) itself. Show it.
4. **Sync or async** — `scope()` for a WSGI or CLI host, `ascope()` when any
   provider in the scope is async, matching the `resolve` / `aresolve` rule.
5. **Startup and shutdown** — `Host.container` reaches `warmup()` / `awarmup()`
   and `close()` / `aclose()`; a lifespan hook is where they belong.
6. **Raising your own error** — use `optional_hosted_container()` and raise
   `ContainerNotBoundError` naming the setup step your users forgot, the way
   `depin.ext.fastapi` names the middleware.
7. **The version** — `CONTRACT_VERSION`, and the rule: minor rises on an added
   operation, major on a changed or removed one.
8. **What not to import** — nothing under `depin._core`. The repository's own
   integrations are held to it by `tests/unit/test_integration_contract.py`,
   and a third party gets the same guarantee: `depin._core` carries no
   compatibility promise, `depin` does.

- [ ] **Step 6: Add both pages to the nav**

In `mkdocs.yml`, add `- Writing an integration: guide/integrations.md` to the
`Guide` section immediately before the `FastAPI` entry, and
`- Integration contract: reference/hosting.md` to the `Reference` section
immediately before the `FastAPI` entry.

- [ ] **Step 7: Benchmark both sides of the resolution change**

Append to `benchmarks/test_resolution.py`, matching the surrounding style:

```python
def test_open_a_request_shaped_scope(benchmark: Benchmark) -> None:
    """A scope opened, seeded, and resolved from — the shape every integration runs per request."""
    request = Token[str]('request')

    class Session:
        def __init__(self, incoming: Annotated[str, request]) -> None:
            self.incoming = incoming

    class Handler:
        def __init__(self, session: Session, incoming: Annotated[str, request]) -> None:
            self.session = session
            self.incoming = incoming

    di = Container().scope_value(request).bind(Session, scope=Scope.SCOPED).bind(Handler, scope=Scope.SCOPED).freeze()

    def run() -> object:
        with di.scope() as frame:
            frame.provide(request, 'r-1')
            return di.resolve(Handler)

    _ = benchmark(run)
```

Add whatever imports the file lacks (`Annotated`, `Token`, `Scope`). Run
`uv run --group bench pytest benchmarks -q --benchmark-only -k request_shaped`
and confirm it reports a time.

- [ ] **Step 8: Put the contract in the README**

In `README.md`, add one bullet to the feature list, in the position that keeps
the list reading as a progression:

```markdown
- **A public integration contract**: `Host`, `hosted_container`, and a version
  constant. `depin.ext.fastapi` is written on it, and so is any integration you
  write yourself — no `depin._core` import required.
  [Writing an integration](https://andrelopes-code.github.io/depin/latest/guide/integrations/).
```

- [ ] **Step 9: Record the new module in `AGENTS.md`**

In the `_core` map table in `AGENTS.md`, insert a row after `frozen.py`:

```markdown
| `hosting.py` | The public integration contract: `Host` and the ambient container. |
```

- [ ] **Step 10: Run every gate and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
git commit -m "docs: document and demonstrate the integration contract"
```

---

### Task 6: The two-sided version matrix

Each integration must be exercised at its declared floor and at the current
release of its framework. The floor is already covered: `minimum-versions` runs
`uv sync --all-extras --resolution lowest-direct`, and every integration is an
extra. The current release is not: `checks` runs `uv sync --locked`, which
pins whatever the lockfile holds.

**Files:**

- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add the job**

Insert after the `minimum-versions` job:

```yaml
  latest-versions:
    name: latest released versions
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Install uv
        uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          python-version: '3.12'

      # `minimum-versions` holds the declared floor of every integration extra
      # honest; this holds the other end. `checks` installs what `uv.lock`
      # pins, which is current only as of the last time the lock was
      # refreshed, so neither of the other two jobs would notice a framework
      # release that breaks an integration. A break here is depin's to fix,
      # not upstream's, which is why this job gates rather than advising.
      - name: Sync at the latest released versions
        run: uv sync --upgrade --all-extras

      - name: Test
        run: uv run --no-sync pytest
```

- [ ] **Step 2: Prove the command works locally**

```bash
uv sync --upgrade --all-extras --dry-run
```

It must resolve. Restore the lockfile afterwards with `git checkout uv.lock` if
`--dry-run` is unavailable in the installed `uv` and the real command was run
instead.

- [ ] **Step 3: Commit**

```bash
git commit -m "ci: test every integration extra at its latest release"
```

---

## Self-review

**Does the plan close the hazards it names?** Task 1's hazard is a leaked
publication; three tests cover normal exit, exception exit, and nesting, and
one covers a hand-entered scope, which is the path the worker probe used and
the one a `with` statement would never exercise. Task 2's hazard is the two
duplicated parameter loops; a test exists for each before either changes.
Task 4's hazard is a contract test that cannot fail; Step 2 observes it failing
against the unrewritten module, which is the only moment in the cycle when that
proof is available.

**Is anything in the plan unproven?** The `Host` shape was prototyped against
Flask, Click, and a hook-pair worker before the spec was written, so Task 1
implements a measured design rather than a guess. The short-circuit removal was
run against the whole suite and timed on both graph shapes. What is not
measured is the mutation score with `hosting.py` in scope; the module has no
branch without a test and every message is asserted whole, which is the
condition the Step 4 cycle found sufficient, but the CI job is the authority
and the pull request is where it runs.

**What could still go wrong at review?** Two things. `Host.scope()` composing
`activated()` with `container.scope()` means an exception raised by a teardown
propagates *before* the publication is undone — `contextlib`'s stacking makes
that correct, and the test asserting a teardown can read
`optional_hosted_container()` pins it, but the reverse order would be a silent
regression that no other test would catch. And `_absolute` in the contract test
computes a relative import's base from the package name; the two relative-import
tests fix its behaviour at level 1 and level 2, which are the only levels a
module directly under `depin/ext/` can use.

**What is deliberately not here?** No shared ASGI module, no eviction seam, no
new extra, no `Seed` type. Each is recorded in the spec's out-of-scope table
with the cycle or the measurement that put it there.
