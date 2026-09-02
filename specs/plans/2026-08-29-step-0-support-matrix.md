# Step 0 — Support matrix and safety net: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the ground truth that every later roadmap step is measured against — a CI matrix that covers free-threaded CPython and the next pre-release, a second type checker with a conformance suite, a benchmark regression gate, a published version-support policy, and signed release provenance.

**Architecture:** No public API changes. The work is CI configuration, dependency groups, three new test modules, a benchmark package, one documentation page, and two workflow edits. Free-threaded and pre-release jobs install the core only — `depin` has zero runtime dependencies, so it runs on any interpreter, while `fastapi` and its compiled transitive dependencies do not ship wheels for every interpreter in the extended matrix. The benchmark gate measures the base branch and the head branch in the same job on the same runner, so it compares code rather than hardware.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `pytest-asyncio`, `pytest-benchmark`, `basedpyright`, `mypy`, `ruff`, GitHub Actions, `release-please`, `mike`/MkDocs.

**Spec:** `specs/2026-08-28-roadmap-1.0-design.md` — Step 0.

## Global Constraints

Copied from the spec and from `AGENTS.md`. Every task's requirements implicitly include this section.

- Python floor is **3.12**. PEP 695 syntax (`def bind[T](...)`, `class Token[T]`, `type X = ...`) is used throughout; do not introduce `TypeVar(...)` forms.
- The core (`depin/`, excluding `depin/ext/`) has **zero runtime dependencies** and must not import any third-party library.
- No `# type: ignore`, no `# pyright: ignore`, no `typing.cast`, no `typing.Any` as a shortcut. A type-checker diagnostic is a design signal, not something to silence.
- Every exception `depin` raises inherits `DepinError`. No bare `TypeError` / `ValueError` / `RuntimeError` / `AssertionError` from library code. `assert` is for test bodies only.
- `ruff`: line length **120**, **single quotes**.
- The four gates must pass with no warnings or waivers, in order: `uv run ruff format`, `uv run ruff check`, `uv run basedpyright`, `uv run pytest`.
- Documentation changes additionally require `uv run --group docs mkdocs build --strict`.
- Conventional commit prefixes; subject ≤ 72 characters, imperative mood. **No co-author trailers, tool attributions, or any reference to automation or AI** in commits, PR descriptions, or code.
- Tests must be deterministic. No sleeps, no network, no clock dependence. Synchronise concurrency with `threading.Barrier`, `asyncio.Event`, or `sys.setswitchinterval` — never a timed sleep.
- A test guarding a concurrency invariant must be shown to fail when the guard is removed.
- No banner or separator comments. No comments restating the code. Inline comments explain *why*.
- New dev tooling goes in `[dependency-groups]` in `pyproject.toml`, pinned conservatively.

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `pyproject.toml` | Adds the `threads` and `bench` dependency groups, `mypy` in `dev`, and the `[tool.mypy]` section. | 1, 4, 6 |
| `.github/workflows/ci.yml` | Adds the `free-threaded`, `prerelease`, and `benchmarks` jobs; per-version type checking; the `mypy` step. | 1, 3, 4, 7 |
| `.github/workflows/scorecard.yml` | OpenSSF Scorecard analysis. | 9 |
| `.github/workflows/release.yml` | Signed provenance attestation and the SBOM artifact on the release. | 9 |
| `tests/unit/test_free_threading.py` | Container invariants under real thread parallelism, skipped when the GIL is enabled. | 2 |
| `tests/typing/test_conformance.py` | Static conformance of the core public API, asserted with `assert_type`. | 5 |
| `tests/typing/test_conformance_fastapi.py` | Static conformance of `Inject[T]`. | 5 |
| `benchmarks/__init__.py` | Marks the benchmark package so `benchmarks.compare` is importable. | 6 |
| `benchmarks/graphs.py` | Builds synthetic provider graphs of a given size. | 6 |
| `benchmarks/test_resolution.py` | The benchmark cases themselves. | 6 |
| `benchmarks/compare.py` | Compares two `pytest-benchmark` JSON reports and fails on regression. | 7 |
| `docs/support-policy.md` | The published version-support policy. | 8 |
| `mkdocs.yml` | Navigation entry for the policy page. | 8 |
| `README.md` | Links the policy; adds the Scorecard badge. | 8, 9 |

---

### Task 1: Extend the CI matrix to free-threaded and pre-release interpreters

**Files:**
- Modify: `pyproject.toml` (`[dependency-groups]`)
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: a `threads` dependency group containing only `pytest` and `pytest-asyncio`, installed with `uv sync --no-default-groups --group threads`. Tasks 2 and 3 rely on that group existing.

- [ ] **Step 1: Add the `threads` dependency group**

In `pyproject.toml`, inside `[dependency-groups]`, after the existing `dev` list and before `docs`:

```toml
# The extended matrix runs free-threaded and pre-release interpreters, where
# `fastapi` and its compiled transitive dependencies have no wheels. The core
# has zero runtime dependencies, so it needs nothing but a test runner.
threads = [
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3",
]
```

- [ ] **Step 2: Verify the group installs and the core suite passes without the dev group**

Run:

```bash
uv sync --no-default-groups --group threads
uv run --no-sync pytest tests/unit
```

Expected: PASS, with no `fastapi` import error. The `tests/integration` directory is excluded because it imports `fastapi`.

Then restore the full environment:

```bash
uv sync --all-extras
```

- [ ] **Step 3: Install a free-threaded interpreter locally and confirm the suite passes on it**

Run:

```bash
uv python install 3.13t
uv venv --python 3.13t /tmp/ft
uv sync --no-default-groups --group threads --python /tmp/ft
uv run --no-sync --python /tmp/ft python -c "import sys; print(sys._is_gil_enabled())"
uv run --no-sync --python /tmp/ft pytest tests/unit
```

Expected: the interpreter prints `False`, and the suite passes. If a test fails here, that is a real finding: record it and stop. Do not weaken the test to make the job green.

- [ ] **Step 4: Add the `free-threaded` job**

In `.github/workflows/ci.yml`, after the `checks` job and before `dependency-review`:

```yaml
  free-threaded:
    name: free-threaded ${{ matrix.python-version }}
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      fail-fast: false
      matrix:
        python-version: ['3.13t', '3.14t']
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Install uv
        uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          python-version: ${{ matrix.python-version }}

      # The core has zero runtime dependencies and installs on any interpreter.
      # `fastapi` and its compiled transitive dependencies do not ship
      # free-threaded wheels for every version here, so the default dev group is
      # excluded and only the core unit suite runs.
      - name: Sync the thread-test group only
        run: uv sync --no-default-groups --group threads

      # Without this, a build that silently re-enabled the GIL would produce a
      # green job that proves nothing about the library's own locks.
      - name: Assert the GIL is disabled
        run: >
          uv run --no-sync python -c
          "import sys; assert sys._is_gil_enabled() is False, 'the GIL is enabled; this job proves nothing'"

      - name: Test
        run: uv run --no-sync pytest tests/unit
```

- [ ] **Step 5: Add the `prerelease` job**

Immediately after the `free-threaded` job:

```yaml
  prerelease:
    name: python 3.15 pre-release
    runs-on: ubuntu-latest
    timeout-minutes: 15
    # Advance warning of an interpreter change, not a merge gate: a pre-release
    # regression is upstream's until it ships.
    continue-on-error: true
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Install uv
        uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          python-version: '3.15'

      - name: Sync the thread-test group only
        run: uv sync --no-default-groups --group threads

      - name: Test
        run: uv run --no-sync pytest tests/unit
```

- [ ] **Step 6: Validate the workflow file parses**

Run:

```bash
uv run python -c "import tomllib,pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text())"
uvx yamllint -d relaxed .github/workflows/ci.yml
```

Expected: no output from the first command, and no errors from the second.

- [ ] **Step 7: Run the four gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run pytest
```

Expected: all four pass.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .github/workflows/ci.yml uv.lock
git commit -m "ci: test free-threaded and pre-release interpreters"
```

---

### Task 2: Prove the container's locks hold without a GIL

**Files:**
- Create: `tests/unit/test_free_threading.py`
- Test: the module is its own test.

**Interfaces:**
- Consumes: the `threads` group from Task 1; `depin._core.container.Container`, `depin._core.scope.Scope`, `depin._core.scope.ScopeFrame`.
- Produces: nothing later tasks depend on.

**Why this is a separate module.** `tests/unit/test_thread_safety.py` relies on `sys.setswitchinterval` to force preemption, which is a GIL concept and a no-op on a free-threaded build. Those tests remain valid and unchanged; this module covers what only true parallelism can reach — concurrent mutation of `ScopeFrame._cache` and `ScopeFrame._sync_locks`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_free_threading.py`:

```python
"""Container invariants under true thread parallelism, on a free-threaded build.

`tests/unit/test_thread_safety.py` forces interleaving with
`sys.setswitchinterval`, which is meaningless without a GIL. These tests instead
rely on threads genuinely running at the same time, and are skipped on a build
where the GIL is enabled.
"""

import sys
import threading
from collections.abc import Callable, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope, ScopeFrame

THREADS = 32


def _gil_enabled() -> bool:
    check: Callable[[], bool] | None = getattr(sys, '_is_gil_enabled', None)
    return True if check is None else check()


pytestmark = pytest.mark.skipif(_gil_enabled(), reason='requires a free-threaded interpreter')


def _run_in_threads(work: Callable[[], None]) -> None:
    threads = [threading.Thread(target=work) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_a_singleton_is_built_once_with_no_gil() -> None:
    class Pool: ...

    built: list[Pool] = []
    resolved: list[Pool] = []
    record = threading.Lock()
    gate = threading.Barrier(THREADS)

    def make() -> Pool:
        pool = Pool()
        with record:
            built.append(pool)
        return pool

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Pool).freeze()

    def worker() -> None:
        _ = gate.wait()
        value = frozen[Pool]
        with record:
            resolved.append(value)

    _run_in_threads(worker)

    assert len(built) == 1
    assert len(resolved) == THREADS
    assert all(value is built[0] for value in resolved)


def test_scopes_stay_isolated_and_every_teardown_runs_with_no_gil() -> None:
    class Session: ...

    torn_down: list[Session] = []
    seen: list[Session] = []
    record = threading.Lock()
    gate = threading.Barrier(THREADS)

    def open_session() -> Generator[Session]:
        session = Session()
        yield session
        with record:
            torn_down.append(session)

    frozen = Container().bind(open_session, scope=Scope.SCOPED).freeze()

    def worker() -> None:
        _ = gate.wait()
        with frozen.scope():
            first = frozen[Session]
            second = frozen[Session]
            assert first is second
            with record:
                seen.append(first)

    _run_in_threads(worker)

    assert len({id(session) for session in seen}) == THREADS
    assert len(torn_down) == THREADS


def test_the_per_key_lock_table_survives_concurrent_creation() -> None:
    frame = ScopeFrame()
    keys = tuple(range(64))
    handed_out: list[tuple[int, int]] = []
    record = threading.Lock()
    gate = threading.Barrier(THREADS)

    def worker() -> None:
        _ = gate.wait()
        pairs = [(key, id(frame.sync_lock_for(key))) for key in keys]
        with record:
            handed_out.extend(pairs)

    _run_in_threads(worker)

    by_key: dict[int, set[int]] = {}
    for key, lock_id in handed_out:
        by_key.setdefault(key, set()).add(lock_id)

    assert len(by_key) == len(keys)
    assert all(len(ids) == 1 for ids in by_key.values())
```

- [ ] **Step 2: Run the tests on the default interpreter and confirm they skip**

Run:

```bash
uv run pytest tests/unit/test_free_threading.py -v
```

Expected: 3 skipped, reason `requires a free-threaded interpreter`.

- [ ] **Step 3: Run the tests on a free-threaded interpreter and confirm they pass**

```bash
uv run --no-sync --python /tmp/ft pytest tests/unit/test_free_threading.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Prove the guard is real by removing it**

Temporarily edit `depin/_core/scope.py`, in `sync_lock_for`, replacing the body's `with self._mutex:` guard with an unguarded lookup:

```python
    def sync_lock_for(self, key: object) -> threading.Lock:
        """Return a per-key mutex, created on first use, for single-flight construction."""
        lock = self._sync_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            self._sync_locks[key] = lock
        return lock
```

Run:

```bash
uv run --no-sync --python /tmp/ft pytest tests/unit/test_free_threading.py::test_the_per_key_lock_table_survives_concurrent_creation -v
```

Expected: FAIL — at least one key hands out more than one lock object. If it passes, the test does not guard anything; raise `THREADS` and the key count until it fails, then keep those values.

- [ ] **Step 5: Restore the guard and confirm the test passes again**

```bash
git checkout -- depin/_core/scope.py
uv run --no-sync --python /tmp/ft pytest tests/unit/test_free_threading.py -v
```

Expected: 3 passed, and `git status` shows `depin/_core/scope.py` unmodified.

- [ ] **Step 6: Run the four gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run pytest
```

Expected: all four pass; the new module's 3 tests are skipped on the default interpreter.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_free_threading.py
git commit -m "test: cover container invariants under free threading"
```

---

### Task 3: Type-check against every interpreter in the matrix

**Files:**
- Modify: `.github/workflows/ci.yml` (the `Type check` step of the `checks` job)

**Interfaces:**
- Consumes: the existing `checks` matrix, whose `matrix.python-version` values are `3.12`, `3.13`, `3.14`.
- Produces: nothing later tasks depend on.

**Why.** `[tool.basedpyright]` pins `pythonVersion = "3.12"`, so the current CI type-checks 3.12 semantics three times while the tests run on three different interpreters. A construct valid on 3.12 and rejected on 3.14 would pass today.

- [ ] **Step 1: Verify the newer versions type-check cleanly before changing CI**

```bash
uv run basedpyright --pythonversion 3.13
uv run basedpyright --pythonversion 3.14
```

Expected: `0 errors, 0 warnings, 0 notes` from both. If either reports a diagnostic, fix the source — do not add a suppression.

- [ ] **Step 2: Point the CI step at the matrix version**

In `.github/workflows/ci.yml`, in the `checks` job, replace:

```yaml
      - name: Type check
        run: uv run basedpyright
```

with:

```yaml
      # The `pythonVersion` pinned in pyproject.toml is the floor; the matrix
      # entry is what this job actually runs, and it is what gets checked here.
      - name: Type check
        run: uv run basedpyright --pythonversion ${{ matrix.python-version }}
```

- [ ] **Step 3: Run the four gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run pytest
```

Expected: all four pass.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: type check against each interpreter in the matrix"
```

---

### Task 4: Add mypy in strict mode

**Files:**
- Modify: `pyproject.toml` (`[dependency-groups]` `dev`, and a new `[tool.mypy]` section)
- Modify: `.github/workflows/ci.yml` (a step in the `checks` job)

**Interfaces:**
- Consumes: nothing.
- Produces: `uv run mypy` as a repository command, referenced by Task 5 and by `CONTRIBUTING.md` in Task 8.

**Why.** The README claims no `# type: ignore` is needed at call sites. That claim is currently verified by one checker. A large share of the user base runs mypy, and the claim becomes a support commitment at 1.0.

- [ ] **Step 1: Add the dependency**

```bash
uv add --group dev 'mypy>=1.18'
```

- [ ] **Step 2: Add the configuration**

In `pyproject.toml`, immediately after the `[tool.basedpyright]` section:

```toml
# The file list mirrors `[tool.basedpyright] include` exactly. The two checkers
# must see the same code, or "both are clean" means nothing.
[tool.mypy]
python_version = "3.12"
files = ["depin", "tests", "examples"]
strict = true
warn_unreachable = true
enable_error_code = ["redundant-expr", "possibly-undefined", "truthy-bool", "ignore-without-code"]
```

- [ ] **Step 3: Run it and read the diagnostics**

```bash
uv run mypy
```

Expected on the first run: a non-empty diagnostic list.

- [ ] **Step 4: Fix every diagnostic in the source**

Resolve each one by changing the code, narrowing a type, or introducing a `Protocol`. Do not add `# type: ignore`. If a diagnostic turns out to be a genuine mypy limitation with no code-level resolution, stop and report it with the exact message rather than suppressing it — the decision of how to record such a case belongs to the maintainer, not to this task.

Re-run until clean:

```bash
uv run mypy
```

Expected: `Success: no issues found`.

- [ ] **Step 5: Confirm basedpyright is still clean after the fixes**

```bash
uv run basedpyright
```

Expected: `0 errors, 0 warnings, 0 notes`. A change that satisfies one checker must not break the other.

- [ ] **Step 6: Add the CI step**

In `.github/workflows/ci.yml`, in the `checks` job, immediately after the `Type check` step:

```yaml
      - name: Type check with mypy
        run: uv run mypy
```

- [ ] **Step 7: Run the four gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run pytest
```

Expected: all four pass.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock .github/workflows/ci.yml depin tests examples
git commit -m "build: check types with mypy in strict mode"
```

---

### Task 5: Add the type-conformance suite

**Files:**
- Create: `tests/typing/test_conformance.py`
- Create: `tests/typing/test_conformance_fastapi.py`

**Interfaces:**
- Consumes: `uv run mypy` from Task 4; the existing `[tool.basedpyright] include = ["depin", "tests", "examples"]`, which already covers `tests/typing`.
- Produces: nothing later tasks depend on.

**How this suite works.** `typing.assert_type` is a no-op at runtime. Its value is what the two checkers report while checking the file: an inference regression in the public API becomes a type-check failure. The functions are also collected by `pytest`, so a change that makes the module unimportable still fails the test run.

- [ ] **Step 1: Write the core conformance module**

Create `tests/typing/test_conformance.py`:

```python
"""Static conformance of the public API under both type checkers.

`assert_type` is a no-op at runtime; what this module buys is the diagnostic a
checker emits when an inferred type drifts. `pytest` collects the functions too,
so a change that breaks the import still fails the suite.
"""

from collections.abc import Awaitable
from typing import assert_type

from depin import Container, FrozenContainer, Scope, ScopeFrame, Token, injected


class Config:
    value: int = 1


class Service:
    def __init__(self, config: Config) -> None:
        self.config = config


port = Token[int]('port')


def test_resolve_returns_the_requested_type() -> None:
    di = Container().bind(Config).bind(Service).value(port, 8080).freeze()
    assert_type(di, FrozenContainer)
    assert_type(di.resolve(Service), Service)
    assert_type(di[Service], Service)
    assert_type(di.resolve(port), int)
    assert_type(di[port], int)


def test_tagged_resolution_keeps_the_requested_type() -> None:
    di = Container().bind(Config, tag='primary').freeze()
    assert_type(di.resolve(Config, tag='primary'), Config)


def test_inject_preserves_the_wrapped_signature() -> None:
    di = Container().bind(Config).freeze()

    @di.inject
    def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    assert_type(handler(label='n'), str)


def test_inject_preserves_an_async_signature() -> None:
    di = Container().bind(Config).freeze()

    @di.inject
    async def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    # Nested and never called: `assert_type` is checked statically, and calling
    # the wrapper here would leave an un-awaited coroutine behind.
    def call_site() -> None:
        assert_type(handler(label='n'), Awaitable[str])

    _ = call_site


def test_injected_takes_the_type_of_its_key() -> None:
    assert_type(injected(Config), Config)
    assert_type(injected(port), int)


def test_scope_yields_a_frame() -> None:
    di = Container().bind(Config).freeze()
    with di.scope() as frame:
        assert_type(frame, ScopeFrame)


def test_override_yields_the_container() -> None:
    di = Container().bind(Config).freeze()
    with di.override(Config, Config()) as overridden:
        assert_type(overridden, FrozenContainer)


def test_scope_marker_is_an_enum_member() -> None:
    assert_type(Scope.SINGLETON, Scope)
```

- [ ] **Step 2: Write the FastAPI conformance module**

Create `tests/typing/test_conformance_fastapi.py`:

```python
"""Static conformance of `Inject[T]`: the parameter's static type is `T` itself."""

from typing import assert_type

from depin.ext.fastapi import Inject


class UserService:
    def name(self) -> str:
        return 'u'


def test_inject_annotates_the_parameter_as_the_service_itself() -> None:
    # The route is nested and never called: a module-level function with an
    # `Inject[...]` parameter would be collected by pytest as a test wanting a
    # fixture named `svc`. `assert_type` is checked statically either way.
    def route(svc: Inject[UserService]) -> str:
        assert_type(svc, UserService)
        return svc.name()

    _ = route
```

- [ ] **Step 3: Run both checkers over the new files**

```bash
uv run basedpyright
uv run mypy
```

Expected: both clean. A failure here means the public API's inferred types do not match what the README promises — fix the library, not the assertion.

- [ ] **Step 4: Prove the suite catches a regression**

Temporarily change the first assertion in `test_resolve_returns_the_requested_type` to `assert_type(di.resolve(Service), Config)` and run:

```bash
uv run basedpyright
uv run mypy
```

Expected: both report a type mismatch on that line. Revert the change afterwards and confirm both are clean again.

- [ ] **Step 5: Run the four gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run pytest
```

Expected: all four pass.

- [ ] **Step 6: Commit**

```bash
git add tests/typing
git commit -m "test: assert the public API's inferred types"
```

---

### Task 6: Add the benchmark suite

**Files:**
- Create: `benchmarks/__init__.py`
- Create: `benchmarks/graphs.py`
- Create: `benchmarks/test_resolution.py`
- Modify: `pyproject.toml` (`[dependency-groups]`, and `files` under `[tool.mypy]` if it was trimmed in Task 4)

**Interfaces:**
- Consumes: `depin.Container`, `depin.Scope`.
- Produces: `benchmarks.graphs.build_chain(size: int) -> tuple[Container, type[object]]`, used by `benchmarks/test_resolution.py`. Task 7 consumes the JSON report these benchmarks emit.

**Why the benchmarks live outside `testpaths`.** `[tool.pytest.ini_options] testpaths = ["tests", "depin", "docs"]`, so `benchmarks/` is not collected by a plain `uv run pytest`. It runs only when named explicitly, which keeps the four gates fast.

- [ ] **Step 1: Add the dependency group**

In `pyproject.toml`, inside `[dependency-groups]`, after `threads`:

```toml
bench = [
    "pytest>=9.0.3",
    "pytest-benchmark>=5.1",
]
```

Then:

```bash
uv sync --all-extras --group bench
```

- [ ] **Step 2: Create the package marker**

Create `benchmarks/__init__.py` with a single line:

```python
"""Benchmarks for depin. Not part of the distribution; run explicitly, never by the default suite."""
```

- [ ] **Step 3: Write the graph builder**

Create `benchmarks/graphs.py`:

```python
"""Synthetic provider graphs of a controlled size."""

from collections.abc import Callable

from depin import Container, Scope


def _provider(node: type[object], dependency: type[object] | None) -> Callable[..., object]:
    """Return a factory for `node`, annotated so depin resolves `dependency` into it.

    The annotations are assigned rather than written, because the graph's size is
    a parameter of the benchmark and the node types do not exist until runtime.
    """
    if dependency is None:

        def make() -> object:
            return node()

        make.__annotations__ = {'return': node}
        return make

    def make_with_dependency(upstream: object) -> object:
        del upstream
        return node()

    make_with_dependency.__annotations__ = {'upstream': dependency, 'return': node}
    return make_with_dependency


def build_chain(size: int, *, scope: Scope = Scope.SINGLETON) -> tuple[Container, type[object]]:
    """A linear chain of `size` providers, each depending on the one before it.

    Returns the unfrozen container and the key at the deep end of the chain, so a
    benchmark can time `freeze()` and resolution independently.
    """
    container = Container()
    previous: type[object] | None = None
    leaf: type[object] = object
    for index in range(size):
        leaf = type(f'Node{index}', (), {})
        container = container.bind(_provider(leaf, previous), provides=leaf, scope=scope)
        previous = leaf
    return container, leaf
```

- [ ] **Step 4: Write the benchmark cases**

Create `benchmarks/test_resolution.py`:

```python
"""The scenarios the regression gate watches: graph validation, resolution, scopes, injection."""

import asyncio
from collections.abc import Callable
from typing import Protocol

import pytest

from benchmarks.graphs import build_chain
from depin import Container, Scope, injected


class Benchmark(Protocol):
    """The subset of pytest-benchmark's fixture these cases use.

    Declared locally so the benchmarks do not depend on the plugin shipping
    accurate type information.
    """

    def __call__[T](self, function: Callable[[], T]) -> T: ...


@pytest.mark.parametrize('size', [10, 100, 1000])
def test_freeze_a_chain(benchmark: Benchmark, size: int) -> None:
    container, _ = build_chain(size)
    _ = benchmark(container.freeze)


def test_resolve_a_cached_singleton(benchmark: Benchmark) -> None:
    container, leaf = build_chain(100)
    frozen = container.freeze()
    _ = frozen.resolve(leaf)

    def resolve() -> object:
        return frozen.resolve(leaf)

    _ = benchmark(resolve)


def test_resolve_a_transient_chain(benchmark: Benchmark) -> None:
    container, leaf = build_chain(20, scope=Scope.TRANSIENT)
    frozen = container.freeze()

    def resolve() -> object:
        return frozen.resolve(leaf)

    _ = benchmark(resolve)


def test_open_and_close_a_scope(benchmark: Benchmark) -> None:
    container, leaf = build_chain(20, scope=Scope.SCOPED)
    frozen = container.freeze()

    def cycle() -> None:
        with frozen.scope():
            _ = frozen.resolve(leaf)

    _ = benchmark(cycle)


def test_call_through_an_inject_wrapper(benchmark: Benchmark) -> None:
    class Repo:
        def count(self) -> int:
            return 3

    frozen = Container().bind(Repo).freeze()

    @frozen.inject
    def handler(repo: Repo = injected(Repo)) -> int:
        return repo.count()

    _ = benchmark(handler)


def test_resolve_an_async_singleton(benchmark: Benchmark) -> None:
    class Pool: ...

    async def make() -> Pool:
        return Pool()

    frozen = Container().bind(make, provides=Pool, scope=Scope.SINGLETON).freeze()
    # One loop for the whole measurement: creating a loop per iteration would
    # benchmark asyncio's startup instead of depin's resolution.
    loop = asyncio.new_event_loop()
    try:
        _ = loop.run_until_complete(frozen.aresolve(Pool))

        def resolve() -> Pool:
            return loop.run_until_complete(frozen.aresolve(Pool))

        _ = benchmark(resolve)
    finally:
        loop.close()
```

- [ ] **Step 5: Run the benchmarks**

```bash
uv run --group bench pytest benchmarks --benchmark-only
```

Expected: 8 benchmarks report timings, no failures. If `pytest-benchmark` reports "no benchmarks collected", the `--benchmark-only` flag is filtering everything — confirm each test takes the `benchmark` fixture.

- [ ] **Step 6: Confirm the default suite still ignores `benchmarks/`**

```bash
uv run pytest --collect-only -q | grep -c benchmarks || echo 'not collected'
```

Expected: `not collected`.

- [ ] **Step 7: Confirm `benchmarks/` stays outside both type checkers**

`[tool.basedpyright] include` is `["depin", "tests", "examples"]` and `[tool.mypy] files` mirrors it. Neither list gains `benchmarks`. The package is not shipped, is never imported by the library, and its correctness is established by Task 7's seeded-regression check rather than by a type checker. `ruff format` and `ruff check` still cover it, because ruff has no include list.

Verify the exclusion holds:

```bash
uv run basedpyright 2>&1 | grep -c benchmarks || echo 'not type-checked'
uv run mypy 2>&1 | grep -c benchmarks || echo 'not type-checked'
```

Expected: `not type-checked` from both.

- [ ] **Step 8: Run the four gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run pytest
```

Expected: all four pass.

- [ ] **Step 9: Commit**

```bash
git add benchmarks pyproject.toml uv.lock
git commit -m "test: add the benchmark suite"
```

---

### Task 7: Gate pull requests on benchmark regression

**Files:**
- Create: `benchmarks/compare.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `benchmarks/test_resolution.py` from Task 6 and the `--benchmark-json` report `pytest-benchmark` writes.
- Produces: `python -m benchmarks.compare <base.json> <head.json> --max-regression=<ratio>`, exiting non-zero when any shared benchmark's mean time grows by more than the ratio.

**Why the base branch is measured in the same job.** A baseline committed to the repository is measured on one machine and compared on another, so it compares hardware. Measuring both sides back to back on the same runner removes that variable. The threshold is deliberately loose: shared CI runners are noisy, and this gate exists to catch an order-of-magnitude regression, not micro-drift.

- [ ] **Step 1: Write the comparison script**

Create `benchmarks/compare.py`:

```python
"""Compare two pytest-benchmark JSON reports and fail on a regression.

Run as ``python -m benchmarks.compare base.json head.json --max-regression=0.25``.
Exits 1 when any benchmark present in both reports is slower in the second by
more than the given ratio.
"""

import json
import pathlib
import sys


def _means(report: pathlib.Path) -> dict[str, float]:
    """Map each benchmark's full name to its mean time, in seconds."""
    payload = json.loads(report.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise SystemExit(f'{report}: expected a JSON object at the top level')
    entries = payload.get('benchmarks')
    if not isinstance(entries, list):
        raise SystemExit(f'{report}: no "benchmarks" array')

    means: dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get('fullname')
        stats = entry.get('stats')
        if not isinstance(name, str) or not isinstance(stats, dict):
            continue
        mean = stats.get('mean')
        if isinstance(mean, int | float):
            means[name] = float(mean)
    return means


def main(argv: list[str]) -> int:
    limit = 0.25
    positional: list[str] = []
    for argument in argv:
        if argument.startswith('--max-regression='):
            limit = float(argument.split('=', 1)[1])
        else:
            positional.append(argument)

    if len(positional) != 2:
        print('usage: python -m benchmarks.compare BASE.json HEAD.json [--max-regression=RATIO]', file=sys.stderr)
        return 2

    base = _means(pathlib.Path(positional[0]))
    head = _means(pathlib.Path(positional[1]))

    shared = sorted(set(base) & set(head))
    if not shared:
        print('no benchmark appears in both reports; nothing to compare')
        return 1

    regressions: list[str] = []
    for name in shared:
        before, after = base[name], head[name]
        if before <= 0:
            continue
        ratio = (after - before) / before
        marker = 'REGRESSION' if ratio > limit else 'ok'
        print(f'{marker:<11} {ratio:+7.1%}  {name}')
        if ratio > limit:
            regressions.append(f'{name}: {before:.3e}s -> {after:.3e}s ({ratio:+.1%})')

    if regressions:
        print(f'\n{len(regressions)} benchmark(s) regressed past {limit:.0%}:', file=sys.stderr)
        for line in regressions:
            print(f'  - {line}', file=sys.stderr)
        return 1

    print(f'\n{len(shared)} benchmark(s) within {limit:.0%} of the base branch')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 2: Verify the script fails on a seeded regression**

```bash
uv run --group bench pytest benchmarks --benchmark-only --benchmark-json=/tmp/base.json
uv run python - <<'PY'
import json, pathlib
data = json.loads(pathlib.Path('/tmp/base.json').read_text())
for entry in data['benchmarks']:
    entry['stats']['mean'] *= 3
pathlib.Path('/tmp/slow.json').write_text(json.dumps(data))
PY
uv run python -m benchmarks.compare /tmp/base.json /tmp/slow.json --max-regression=0.25
echo "exit=$?"
```

Expected: every line marked `REGRESSION`, and `exit=1`.

- [ ] **Step 3: Verify the script passes when comparing a report to itself**

```bash
uv run python -m benchmarks.compare /tmp/base.json /tmp/base.json --max-regression=0.25
echo "exit=$?"
```

Expected: every line `+0.0%`, and `exit=0`.

- [ ] **Step 4: Add the CI job**

In `.github/workflows/ci.yml`, after the `prerelease` job:

```yaml
  benchmarks:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      # Both sides are measured on this runner, back to back. A baseline stored
      # in the repository would have been measured on a different machine, and
      # the comparison would report hardware rather than code.
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0

      - name: Install uv
        uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          python-version: '3.12'

      - name: Measure the base branch
        env:
          BASE_REF: ${{ github.base_ref }}
        run: |
          set -euo pipefail
          git worktree add /tmp/base "origin/${BASE_REF}"
          cd /tmp/base
          uv sync --group bench
          uv run --no-sync pytest benchmarks --benchmark-only --benchmark-json=/tmp/base.json

      - name: Measure this branch
        run: |
          set -euo pipefail
          uv sync --group bench
          uv run --no-sync pytest benchmarks --benchmark-only --benchmark-json=/tmp/head.json

      - name: Compare
        run: uv run --no-sync python -m benchmarks.compare /tmp/base.json /tmp/head.json --max-regression=0.25
```

- [ ] **Step 5: Validate the workflow parses**

```bash
uvx yamllint -d relaxed .github/workflows/ci.yml
```

Expected: no errors.

- [ ] **Step 6: Run the four gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run pytest
```

Expected: all four pass. `ruff` covers `benchmarks/compare.py`; the type checkers do not, by the decision recorded in Task 6.

- [ ] **Step 7: Commit**

```bash
git add benchmarks/compare.py .github/workflows/ci.yml
git commit -m "ci: fail a pull request that regresses a benchmark"
```

---

### Task 8: Publish the version-support policy

**Files:**
- Create: `docs/support-policy.md`
- Modify: `mkdocs.yml` (`nav`)
- Modify: `README.md` (the `Project status` section)
- Modify: `CONTRIBUTING.md` (the `The four gates` section)

**Interfaces:**
- Consumes: the matrix from Task 1 and the `uv run mypy` command from Task 4.
- Produces: nothing later tasks depend on.

**Constraint.** `[tool.pytest.ini_options] testpaths` includes `docs` and `addopts` carries `--doctest-glob=*.md`, so any `>>>` block in this page is executed as a doctest. This page contains no code examples, so there is nothing to execute — keep it that way.

- [ ] **Step 1: Write the page**

Create `docs/support-policy.md`:

```markdown
# Support policy

## Python versions

depin supports every CPython release that upstream still supports, from 3.12
upward. 3.12 is the floor because the library is written in PEP 695 generic
syntax throughout.

| Version | Status |
| --- | --- |
| 3.12 | Supported. The floor, and the version the type checkers are configured against. |
| 3.13 | Supported, including the free-threaded build. |
| 3.14 | Supported, including the free-threaded build. |
| 3.15 | Tested against the pre-release. Not yet a support commitment. |

A version is dropped in the first minor release after its upstream end of life,
and the removal is announced in the changelog of the release before it. Dropping
a version is a minor release, not a major one, because the alternative is
pinning the project to interpreters that no longer receive security fixes.

## Free-threaded builds

The free-threaded builds of 3.13 and 3.14 run the core test suite on every
change. depin's guarantee that a cached provider is constructed exactly once
under contention comes from its own locks, not from the GIL, and the CI job
asserts the GIL is disabled before it runs so the coverage cannot become
vacuous.

The optional FastAPI integration is not covered on free-threaded builds, because
its dependencies do not publish wheels for those interpreters.

## Operating systems

Linux, macOS, and Windows. The full matrix runs on Linux; macOS and Windows run
the floor version.

## Optional dependencies

`depin.ext.fastapi` declares a minimum for `fastapi` and `starlette`. CI resolves
those at their declared minimum in a dedicated job, so the floor is verified
rather than assumed, and separately at the current release.

## Type checkers

The public API is verified under `basedpyright --strict` and `mypy --strict`, and
a conformance suite asserts the inferred type of every public call site. Neither
checker is treated as authoritative over the other: a change must satisfy both.
```

- [ ] **Step 2: Add it to the navigation**

In `mkdocs.yml`, in `nav`, between the `Guide` and `Reference` sections:

```yaml
  - Support policy: support-policy.md
```

- [ ] **Step 3: Link it from the README**

In `README.md`, in the `Project status` section, replace the sentence:

```markdown
Beta, pre-1.0. CI enforces `ruff`, `basedpyright --strict`, the full test suite
with its embedded doctests, and a 95% coverage floor, on Python 3.12–3.14 across
Linux, macOS, and Windows.
```

with:

```markdown
Beta, pre-1.0. CI enforces `ruff`, `basedpyright --strict`, `mypy --strict`, the
full test suite with its embedded doctests, and a 95% coverage floor, on Python
3.12–3.14 across Linux, macOS, and Windows, plus the free-threaded builds of 3.13
and 3.14. See the
[support policy](https://andrelopes-code.github.io/depin/latest/support-policy/).
```

- [ ] **Step 4: Record the fifth command in CONTRIBUTING**

In `CONTRIBUTING.md`, in `The four gates`, add `uv run mypy` to the command list immediately after `uv run basedpyright`, and change the surrounding prose from "four" to "five" wherever it names the count.

- [ ] **Step 5: Build the site**

```bash
uv run --group docs mkdocs build --strict
```

Expected: build succeeds with no warnings.

- [ ] **Step 6: Run the gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run mypy && uv run pytest
```

Expected: all pass. `pytest` collects `docs/support-policy.md` and finds no doctests in it, which is not an error.

- [ ] **Step 7: Commit**

```bash
git add docs/support-policy.md mkdocs.yml README.md CONTRIBUTING.md
git commit -m "docs: publish the version support policy"
```

---

### Task 9: Sign releases and publish an SBOM and Scorecard

**Files:**
- Modify: `.github/workflows/release.yml` (the `publish` job)
- Create: `.github/workflows/scorecard.yml`
- Modify: `README.md` (badge row)

**Interfaces:**
- Consumes: the existing `publish` job, which already runs in the `pypi` environment with `id-token: write` and uses Trusted Publishing.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Attest the published distributions**

In `.github/workflows/release.yml`, in the `publish` job, replace:

```yaml
    permissions:
      id-token: write
```

with:

```yaml
    permissions:
      id-token: write
      attestations: write
      contents: write
```

and replace:

```yaml
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # release/v1
```

with:

```yaml
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # release/v1
        with:
          attestations: true
```

- [ ] **Step 2: Attach an SBOM to the GitHub Release**

In the same `publish` job, after the publish step:

```yaml
      # The SBOM is generated from an environment with the built wheel and its
      # optional extra installed, so it records what a consumer actually gets
      # rather than what the lockfile happens to hold.
      - name: Generate the SBOM
        run: |
          set -euo pipefail
          uv venv /tmp/sbom
          uv pip install --python /tmp/sbom "$(echo dist/*.whl)[fastapi]"
          uvx --from cyclonedx-bom cyclonedx-py environment /tmp/sbom \
            --output-format JSON --outfile sbom.cdx.json

      - name: Attach it to the release
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ needs.release-please.outputs.tag_name }}
        run: gh release upload "${TAG}" sbom.cdx.json --clobber
```

- [ ] **Step 3: Verify the SBOM command works locally**

```bash
uv build
uv venv /tmp/sbom
uv pip install --python /tmp/sbom "$(echo dist/*.whl)[fastapi]"
uvx --from cyclonedx-bom cyclonedx-py environment /tmp/sbom --output-format JSON --outfile /tmp/sbom.cdx.json
uv run python -c "import json,pathlib; d=json.loads(pathlib.Path('/tmp/sbom.cdx.json').read_text()); print(len(d['components']), 'components')"
```

Expected: a component count greater than zero, including `pydepin`.

- [ ] **Step 4: Add the Scorecard workflow**

Create `.github/workflows/scorecard.yml`:

```yaml
name: scorecard

on:
  branch_protection_rule:
  push:
    branches: [main]
  schedule:
    - cron: '27 4 * * 1'

permissions: read-all

jobs:
  analysis:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      security-events: write
      id-token: write
      contents: read
      actions: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: ossf/scorecard-action@f49aabe0b5af0936a0987cfb85d86b75731b0186 # v2.4.1
        with:
          results_file: results.sarif
          results_format: sarif
          # Publishing is what makes the README badge resolve, and it is what
          # lets consumers check the score without cloning the repository.
          publish_results: true

      - uses: github/codeql-action/upload-sarif@db488ddef3bf6cb639b32c2e9a7c0a7ea8271d28 # v4
        with:
          sarif_file: results.sarif
```

- [ ] **Step 5: Add the badge**

In `README.md`, append to the badge block, after the License badge:

```markdown
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/andrelopes-code/depin/badge)](https://scorecard.dev/viewer/?uri=github.com/andrelopes-code/depin)
```

- [ ] **Step 6: Validate both workflows parse**

```bash
uvx yamllint -d relaxed .github/workflows/release.yml .github/workflows/scorecard.yml
```

Expected: no errors.

- [ ] **Step 7: Run the gates**

```bash
uv run ruff format && uv run ruff check && uv run basedpyright && uv run mypy && uv run pytest
uv run --group docs mkdocs build --strict
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/release.yml .github/workflows/scorecard.yml README.md
git commit -m "build: attest releases and publish an SBOM and Scorecard"
```

---

## Verification for the whole step

Run after the last task, before opening the pull request:

```bash
uv run ruff format --check
uv run ruff check
uv run basedpyright
uv run basedpyright --pythonversion 3.13
uv run basedpyright --pythonversion 3.14
uv run mypy
uv run pytest --cov=depin --cov-report=term-missing
uv run --group docs mkdocs build --strict
uv run --group bench pytest benchmarks --benchmark-only
uv run --no-sync --python /tmp/ft pytest tests/unit
```

Step 0 is complete when all of the following hold:

- CI is green on 3.12, 3.13, 3.14, 3.13t, and 3.14t, and the 3.15 job runs without blocking.
- The free-threaded job fails if the GIL is enabled, rather than passing vacuously.
- `test_the_per_key_lock_table_survives_concurrent_creation` was observed failing with the mutex removed, and passing with it restored.
- `basedpyright --strict` and `mypy --strict` both report zero diagnostics, and the conformance suite was observed failing under both when an assertion was deliberately wrong.
- The benchmark comparison was observed exiting 1 on a seeded 3× regression and 0 on an unchanged report.
- The support policy page is live in the navigation and linked from the README.
- The publish job requests attestations, and the SBOM command was run locally against a built wheel.

## Notes for the executor

- Nothing in this step changes `depin/`'s behaviour. If a task requires editing a module under `depin/_core/`, that is either a mypy fix (Task 4) or a mistake — check which before proceeding.
- Task 4 is the only task that can uncover unbounded work. If mypy reports a diagnostic that cannot be resolved without a suppression, stop and report the exact message; do not invent a workaround and do not add `# type: ignore`.
- Tasks 1 and 2 need a locally installed free-threaded interpreter. `uv python install 3.13t` provides it. If the platform cannot supply one, Task 2's Step 4 cannot be honoured, and the task must not be marked complete on the strength of the CI run alone.

## Deviations (2026-08-29)

Recorded after the fact, against the executed step. The body above is left
unchanged as a historical record of what was planned.

- **`# type: ignore` was not kept at zero.** The Global Constraints section
  above forbids it outright. Fourteen were added across `depin/` and the test
  suite in `6fce208` ("add mypy suppressions beside the existing pyright
  ones"), while bringing the public API to zero diagnostics under
  `mypy --strict` (Task 4): each pairs a rule-named `# type: ignore[<code>]`
  with the existing `# pyright: ignore[...]` at the same site, for a
  limitation only mypy sees. A fifteenth, in `examples/testing/main.py`, is
  the one already documented in `docs/support-policy.md`.
- **"The four gates" is wrong throughout this document.** Task 4 added
  `mypy` as a fifth gate; every occurrence in this file still says "four".
  The file is a historical record and is not corrected in place — `AGENTS.md`,
  `README.md`, and `CONTRIBUTING.md` carry the corrected count.
- **The `ci:` commit prefix used in this plan's own example commit messages
  is not in the allowed set.** `AGENTS.md` allows `feat:`, `fix:`, `chore:`,
  `docs:`, `test:`, `build:`, `refactor:`, `perf:` — no `ci:`. Commits made
  from this plan used an allowed prefix instead (`build:` for CI workflow
  changes), not the prefix this plan's examples show.
- **`depin/_core/graph.py` was edited during this step**, in `653e2d8`
  ("detect missing providers without a walk from every root") and `d7eac99`
  ("stop rebuilding the captive-dependency chain per edge"). The executor
  notes above call an edit under `depin/_core/` "either a mypy fix (Task 4)
  or a mistake". It was neither: the benchmark suite added by Task 6 measured
  `_check_missing` and the captive-chain walk as quadratic in graph size, and
  the rewrite was authorised on that evidence, not on a mypy diagnostic.
