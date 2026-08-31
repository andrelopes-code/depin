# Step 5, cycle 2 — the pytest plugin and singleton eviction: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `FrozenContainer.reset()` / `areset()` drain and drop the singleton cache, ship `depin.ext.pytest` with five fixtures on the `pytest11` entry point, and remove the README's inaccurate overrides caveat — for the 0.14.0 milestone.

**Architecture:** One operation in `depin/_core/scope.py` (`drop_sync` / `drop_async`, module-level because the cache and the teardown list are private to that module), two thin methods on `FrozenContainer`, and one new integration module that imports only `depin` and `pytest`. The plugin is where the contract earns its keep: `tests/unit/test_integration_contract.py` forbids `depin/ext/` from importing `depin._core`, which is precisely why the eviction seam is public.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, Hypothesis, mutmut 3.7, pytest-benchmark, mkdocs-material with mkdocstrings, uv.

**Spec:** `specs/2026-08-31-step-5-pytest-eviction-design.md`

## Global constraints

Every task inherits these requirements from `AGENTS.md`, the approved roadmap, and the spec.

- The core keeps zero runtime dependencies. `pytest` appears only under `depin/ext/` and in `[project.optional-dependencies]`.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `typing.Any`, `typing.cast`, `# type: ignore`, `# pyright: ignore`, or `# noqa`. `depin/` carries exactly three suppressions today — two in `depin/_core/frozen.py`, one in `depin/_core/markers.py` — and must carry exactly those three when this cycle ends. Confirm with `grep -rn "type: ignore\|pyright: ignore\|noqa" --include='*.py' depin`; the `# noqa: B008` inside a docstring in `depin/ext/fastapi.py` is prose, not a waiver.
- Every exception raised by library code inherits `DepinError`. No bare `KeyError`, `TypeError`, `ValueError`, or `assert` in `depin/`. An exception is never swallowed: collecting teardown failures into an `ExceptionGroup` is reporting, not swallowing, and it catches `Exception`, never `BaseException`.
- Data structures are `@dataclass(frozen=True, slots=True)`; a public one is additionally `@final`.
- New behaviour in `depin/_core/` is developed test-first: the failing test is written and observed failing before the implementation.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery. `reportPrivateUsage` forbids reading `FrozenContainer._plan` or `._root` from a test; build plans with `build_plan(container.records())` and drive eviction through the public `reset()`.
- Public API additions carry Google-style docstrings that omit types from `Args:` / `Returns:`, list every exception under `Raises:`, and include a doctest `Example:` in a ```pycon fence. Doctests run in the default `pytest` invocation.
- Mutation budget: `[tool.mutmut] only_mutate` is `depin/_core/*.py`, so `scope.py` and `frozen.py` are mutated at a 95%-killed floor with a small pre-existing margin. Assert every error message as a **complete** string with `==`, never with `in`.
- `fmt_key` renders a class by `__qualname__`, so a class declared inside a test function appears as `test_x.<locals>.Name`. Print the real string before pinning any text assertion.
- Coverage over `depin/` stays at or above 95%. `depin/_core/scope.py`'s line inside `_Flight.wait_sync` reports uncovered in roughly one run in two on any commit; run coverage twice before attributing a miss to this cycle.
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
- `uv run ruff format` reformats Python inside markdown fences, including under `specs/` and `docs/`. Never revert that reformatting.
- Commits are focused, conventional, at most 72 characters in the subject, and contain no attribution or automation language.

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `depin/_core/scope.py` | `drop_sync`, `drop_async` over a frame. | 1 |
| `depin/_core/frozen.py` | `reset`, `areset`. | 1 |
| `tests/unit/test_reset.py` | **New.** Eviction end to end. | 1 |
| `tests/unit/test_overrides.py` | The caveat: a pre-built consumer sees the replacement once the cache is evicted. | 1 |
| `tests/typing/test_conformance.py` | `assert_type` over `reset` / `areset`. | 1 |
| `depin/ext/pytest.py` | **New.** The five fixtures. | 2 |
| `pyproject.toml` | The `pytest` extra and the `pytest11` entry point. | 2 |
| `tests/integration/test_pytest_plugin.py` | **New.** The plugin driven through `pytester`. | 2 |
| `docs/guide/testing.md` | The plugin, and the corrected caveat. | 3 |
| `docs/reference/frozen.md` | Picks up `reset` / `areset`. | 3 |
| `README.md` | The caveat corrected. | 3 |
| `examples/pytest_plugin/` | **New.** A container and the suite that tests it. | 3 |
| `examples/README.md` | Lists it. | 3 |
| `tests/integration/test_examples.py` | Executes it. | 3 |

---

### Task 1: Evicting the singleton cache

**The hazard this task exists to close:** the cache and the teardown list are two structures that must be taken together under one lock. Taking them separately lets a teardown registered between the two steps survive a drop that cleared the value it belongs to, leaking the resource with nothing left that remembers it. The test for the pairing is written before the operation exists.

**Files:**

- Modify: `depin/_core/scope.py`
- Modify: `depin/_core/frozen.py`
- Create: `tests/unit/test_reset.py`
- Modify: `tests/unit/test_overrides.py`
- Modify: `tests/typing/test_conformance.py`

**Interfaces:**

- Produces: `drop_sync` and `drop_async` in `depin._core.scope`.
- Produces: `FrozenContainer.reset` and `FrozenContainer.areset`.

- [ ] **Step 1: Write the failing eviction tests**

Create `tests/unit/test_reset.py`. Cover, one test each, and give each a name that says what it pins:

- A built singleton is dropped: resolving after `reset()` returns a different instance.
- Its teardown ran exactly once, during the `reset()`, in reverse construction order across two generator singletons.
- `reset()` on a container with nothing built runs nothing and raises nothing.
- `reset()` twice in a row is idempotent — the second drains nothing.
- Two failing teardowns collect into an `ExceptionGroup` carrying both, **and the cache is still dropped**: a resolution after the raised group returns a fresh instance. Assert the group's message as a complete string with `==`.
- `reset()` on a graph with an async singleton raises `TeardownError`, and `await areset()` drains it. Assert the message as a complete string.
- A value cached in an *active scope* survives `reset()`: open a scope, resolve a scoped provider, call `reset()`, and assert the scoped instance is unchanged and its teardown has not run.
- `areset()` drains an async generator singleton's teardown and drops it.

Drive everything through the public `FrozenContainer`; `reportPrivateUsage` forbids touching `._root`.

- [ ] **Step 2: Write the failing caveat test**

Append to `tests/unit/test_overrides.py` a test named for what it pins — that a consumer singleton built before an override sees the replacement once the cache is evicted around the block. Build `Clock` and `Report(clock)`, resolve `Report` first, then `reset()`, then enter `override(Clock, FakeClock())` and assert `Report` now renders the fake. Add a second assertion that without the `reset()` the pre-built consumer keeps the real one — that is the behaviour the README describes, and pinning it is what makes the fixture's value legible.

- [ ] **Step 3: Observe every new test fail**

```bash
uv run pytest tests/unit/test_reset.py tests/unit/test_overrides.py -q
```

Record the failure output. The `test_reset.py` tests must fail on the missing method, not on an assertion.

- [ ] **Step 4: Add the drop operation to `depin/_core/scope.py`**

Add two module-level functions beside `push_frame`, after the existing frame helpers. They live here, not in `frozen.py`, because `_cache` and `_teardowns` are private to this module and `reportPrivateUsage` is on.

```python
def _take_all(frame: ScopeFrame) -> tuple[Teardown, ...]:
    """Take the frame's teardowns and drop its cached values, as one atomic step.

    The two must move together: a teardown taken while the value it belongs to
    is still cached would run against a value the frame goes on serving, and a
    value dropped while its teardown is left behind leaks the resource with
    nothing that remembers it.
    """
    with frame._mutex:
        records = tuple(reversed(frame._teardowns))
        frame._teardowns.clear()
        frame._cache.clear()
    return records


def drop_sync(frame: ScopeFrame) -> None:
    errors: list[Exception] = []
    for record in _take_all(frame):
        try:
            teardown.run_sync(record)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup('depin teardown errors', errors)


async def drop_async(frame: ScopeFrame) -> None:
    errors: list[Exception] = []
    for record in _take_all(frame):
        try:
            await teardown.run_async(record)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup('depin teardown errors', errors)
```

Note the ordering the tests pin: the cache is cleared *before* any teardown runs, so a failing teardown still leaves the cache dropped.

- [ ] **Step 5: Add `reset` and `areset` to `FrozenContainer`**

In `depin/_core/frozen.py`, import `drop_async` and `drop_sync` from `depin._core.scope`, and add the two methods immediately after `aclose`, so the lifecycle methods stay together:

```python
    def reset(self) -> None:
        """Tear down every built singleton and drop the cache, so the next resolution rebuilds.

        The difference from `close()` is what happens afterwards: `close()`
        drains the singletons and leaves them cached, while `reset()` drops
        them, so the container is usable again and builds fresh values on
        demand. Scoped and transient providers are untouched — a scoped value
        belongs to its scope, and a transient one is never cached.

        Primarily a testing seam: it is what makes an `override()` reach a
        consumer that was already built, and it is what the `depin.ext.pytest`
        fixtures use.

        Raises:
            TeardownError: A singleton is an async provider; use `areset()`.
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported, and the cache is dropped either way.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Clock: ...
            >>> di = Container().bind(Clock).freeze()
            >>> first = di[Clock]
            >>> di.reset()
            >>> di[Clock] is first
            False

            ```
        """
        drop_sync(self._root)

    async def areset(self) -> None:
        """Tear down every built singleton and drop the cache; the counterpart to `reset()`.

        The one to call when any singleton is an async provider. Otherwise
        identical.

        Raises:
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported, and the cache is dropped either way.
        """
        await drop_async(self._root)
```

- [ ] **Step 6: Add the conformance assertions**

In `tests/typing/test_conformance.py`, append a `test_`-prefixed function asserting `reset()` is `None` and `await areset()` is `None`, matching the file's existing conventions. Every function in that file is `test_`-prefixed and is collected and run.

- [ ] **Step 7: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git commit -m "feat: drop the singleton cache with reset()"
```

---

### Task 2: The pytest plugin

**The hazard this task exists to close:** a plugin tested by importing its fixture functions and calling them is not tested as a plugin. Entry-point registration, fixture visibility without a `conftest` import, and the failure a suite gets when it does not define `depin_container` are all invisible to that style of test. Everything here is driven through pytest's own `pytester` fixture, which runs a generated suite in a subprocess.

**Files:**

- Create: `depin/ext/pytest.py`
- Modify: `pyproject.toml`
- Create: `tests/integration/test_pytest_plugin.py`

**Interfaces:**

- Produces: the fixtures `depin_container`, `depin_override`, `depin_aoverride`, `depin_scope`, `depin_ascope`.

- [ ] **Step 1: Declare the extra and the entry point**

In `pyproject.toml`, extend `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
fastapi = ["fastapi>=0.133", "starlette>=1.1"]
pytest = ["pytest>=9.0.3"]
```

and add, after it:

```toml
# Declared by the distribution rather than by the extra, because that is how
# pytest discovers a plugin. The extra states the floor the plugin is tested
# against; `minimum-versions` and `latest-versions` exercise both ends.
[project.entry-points.pytest11]
depin = "depin.ext.pytest"
```

Run `uv sync --all-extras` and confirm `uv run pytest --trace-config -q --collect-only tests/unit/test_public_api.py 2>&1 | grep -i depin` lists the plugin as registered. Paste the line into your report.

- [ ] **Step 2: Write the plugin**

Create `depin/ext/pytest.py`. It imports `pytest` and `depin`, and nothing else. Every fixture carries a Google-style docstring; the module docstring states that installing `pydepin` registers it and that it adds fixtures only, no hooks and no autouse.

```python
"""pytest integration: fixtures for the container, its overrides, and its scopes.

Registered on the ``pytest11`` entry point, so installing ``pydepin`` makes
these fixtures available with no ``conftest.py`` import. The plugin adds
fixtures only — no hooks, no autouse, no change to collection or reporting.

Define `depin_container` in your own ``conftest.py`` to hand the plugin the
container your suite tests; everything else builds on it.
"""

import contextlib
from collections.abc import AsyncGenerator, Callable, Generator

import pytest

from depin import FrozenContainer, Host, ScopeFrame, Token
from depin.errors import ContainerNotBoundError
```

The five fixtures:

- `depin_container() -> FrozenContainer` — raises `ContainerNotBoundError` with a message that names the fixture to define and shows its shape. Assert that message as a complete string in the test.
- `depin_override(depin_container)` — returns a callable `(key, replacement, *, tag=None)` giving a context manager that calls `depin_container.reset()`, enters `depin_container.override(...)`, yields the container, and on exit calls `reset()` again.
- `depin_aoverride(depin_container)` — the same shape, an async context manager, using `areset()`.
- `depin_scope(depin_container)` — yields the `ScopeFrame` from `Host(depin_container).scope()`.
- `depin_ascope(depin_container)` — the async counterpart.

The typing is the hard part, and no suppression is acceptable. `override` is generic in the key; the factory the fixture returns must stay generic, which means a callback `Protocol` with a generic `__call__`, not a bare `Callable`. Write the `Protocol` in this module, keep it private, and let both checkers confirm that `depin_override(Clock, FakeClock())` types the yielded container as `FrozenContainer`. If you cannot make it type-clean, stop and report rather than widening to `object`.

- [ ] **Step 3: Test the plugin as a plugin**

Create `tests/integration/test_pytest_plugin.py`. Use pytest's `pytester` fixture; it needs `pytest_plugins = ['pytester']` in the module or the `pytester` fixture requested directly, and each test writes a small suite with `pytester.makepyfile(...)` / `makeconftest(...)` then runs it with `pytester.runpytest_subprocess()`.

Cases, one test each:

- A suite that requests `depin_container` without defining it fails, and the output contains the fixture name and the shape to write. Match on the complete message.
- A suite whose `conftest.py` defines `depin_container` gets the fixture with no import of the plugin.
- The evicting override reaches a consumer built before the block: build `Report` first, then use `depin_override(Clock, FakeClock())`, and assert the fake is seen. This is the test that fails without Task 1.
- Values built inside the block do not survive it: after the block, the real graph is back.
- `depin_aoverride` drives an async provider.
- `hosted_container()` returns the container from inside a `depin_scope` block, and the frame yielded can be seeded for a `scope_value` key.

`runpytest_subprocess` is slower than `runpytest`; use it anyway for the entry-point cases, because in-process runs inherit this suite's already-loaded plugin and would pass whether or not registration works.

- [ ] **Step 4: Run the gates and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
git commit -m "feat: add the pytest plugin"
```

---

### Task 3: Document, demonstrate, and correct the caveat

**Files:**

- Modify: `docs/guide/testing.md`
- Modify: `docs/reference/frozen.md`
- Modify: `README.md`
- Create: `examples/pytest_plugin/__init__.py`, `examples/pytest_plugin/main.py`
- Modify: `examples/README.md`
- Modify: `tests/integration/test_examples.py`

- [ ] **Step 1: Correct the README caveat**

The current bullet is wrong on the facts. Replace it with one that states what was measured: the overridden key *is* replaced even when it was already built, and what survives is a consumer that was constructed before the block. Name `reset()` and the `depin.ext.pytest` fixtures as the fix, and keep it to the length of its neighbours.

- [ ] **Step 2: Write the example**

`examples/pytest_plugin/main.py` holds the container and the code under test — a `Clock`, a `Report` that depends on it, and a `build()` returning the frozen container — plus a `main()` that demonstrates the eviction without pytest, so the example runs as `python -m examples.pytest_plugin.main` like every other one. The suite that uses the fixtures belongs in the docs and in `tests/integration/test_pytest_plugin.py`, not in a module the example runner would collect.

Add the row to `examples/README.md` and the test to `tests/integration/test_examples.py`, matching the conventions already there.

- [ ] **Step 3: Document the plugin**

Extend `docs/guide/testing.md`: what the plugin gives, how to define `depin_container`, the evicting override with a worked case, the scope fixtures, and the corrected statement about what an override does and does not replace. Replace the page's existing `!!! warning "Values built before the override are not replaced"` admonition, which is wrong in the same way the README was. Every `pycon` block is executed by the default `pytest` run — paste real output.

Add `reset` and `areset` to `docs/reference/frozen.md` wherever that page lists `FrozenContainer`'s members, following its existing form.

- [ ] **Step 4: Run every gate and commit**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
git commit -m "docs: document the pytest plugin and correct the caveat"
```

---

## Self-review

**Does the plan close the hazards it names?** Task 1's hazard is the cache and the teardown list moving separately; `_take_all` makes them one locked step and the `ExceptionGroup` test asserts the cache is dropped even when teardowns fail, which is the case a two-step implementation gets wrong. Task 2's hazard is a plugin tested as a library; every case runs through `pytester` in a subprocess, and the plan says why in-process runs would pass vacuously.

**Is anything in the plan unproven?** The eviction was prototyped against the real container before the spec was written: the pre-built consumer saw the replacement, and the generator's teardown ran once. A module named `pytest` inside a package was confirmed loadable as a plugin with `import pytest` resolving to the distribution. What is not proven is the generic typing of the `depin_override` factory under both checkers; Task 2 Step 2 says to stop and report rather than widen it, because a suppression there would be the first in `depin/ext/`.

**What could still go wrong at review?** Two things. `reset()` drops the *whole* cache, so a fixture that uses it is coarser than it looks — a test that relies on an expensive singleton surviving will rebuild it, and that cost is real even though the correctness is not in question. And the plugin registers unconditionally for everyone who installs `pydepin`, so an import error inside `depin/ext/pytest.py` would break collection for every suite in that environment; the module's import list is deliberately two names long for that reason.

**What is deliberately not here?** Per-key eviction, any change to `close()`, and any autouse fixture. Each is in the spec's out-of-scope table with the measurement or the reason that put it there.
