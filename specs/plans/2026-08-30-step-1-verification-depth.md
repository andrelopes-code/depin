# Step 1 — Verification depth: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that depin's verification detects semantic, concurrency, and teardown defects—not merely that its lines execute—and enforce that proof in CI for the 0.6.0 milestone.

**Architecture:** Add generative graph checks and deterministic fault-injection tests around the existing `Container` and `FrozenContainer`, then use those tests as the target of a scheduled/path-filtered mutation gate. Audit every shared-state assumption in the core, replace the cross-thread `asyncio.Lock` with an event-based single-flight owned by `ScopeFrame`, and record reproducible red/green evidence across the supported interpreter matrix.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, pytest-asyncio, Hypothesis, mutmut 3.7, coverage.py, GitHub Actions, uv.

---

## Global constraints

Every task inherits these requirements from `AGENTS.md` and the approved roadmap.

- The core keeps zero runtime dependencies. Hypothesis and mutmut are development dependencies in the existing `dev` group; the free-threaded `threads` group also receives Hypothesis and pytest-cov because CI runs `tests/unit` and measures coverage there.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `Any`, `typing.cast`, `# type: ignore`, or `# pyright: ignore` shortcuts.
- Tests exercise the real `Container` / `FrozenContainer`; do not mock the DI machinery.
- No timed sleeps. Coordinate threads with `threading.Barrier`, `threading.Event`, or `threading.Condition`, and tasks with asyncio primitives local to one event loop.
- A concurrency guard is accepted only after the corresponding test is observed failing with that guard removed and passing after restoration. Record both commands and their relevant output.
- Run the CI-shaped directory invocation when validating a suite: `pytest tests/unit`, not only an individual test file. Individual node IDs are used only for the mandatory RED and deliberate-sabotage evidence.
- Coverage is measured separately on 3.12, 3.13, 3.14, 3.13t, and 3.14t. The threshold remains at least 95% over the whole `depin/` package; it starts at 98.25% for the complete default suite.
- Leave the advisory `ty` diagnostics unchanged. `ty` remains non-blocking and outside the five gates.
- Before every commit, run in this exact order:

  ```bash
  uv run ruff format
  uv run ruff check
  uv run basedpyright
  uv run mypy
  uv run pytest
  ```

- Any commit that changes prose also runs `uv run --group docs mkdocs build --strict` after the five gates.
- Commits are focused, conventional, at most 72 characters, and contain no attribution or automation language.

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `pyproject.toml` | Adds Hypothesis/mutmut, equips the free-threaded group for property tests and coverage, and configures mutmut over `_core`. | 1, 5 |
| `uv.lock` | Locks the new development tooling. | 1, 5 |
| `tests/unit/test_graph_properties.py` | Generates provider graphs and checks all four roadmap invariants. | 1 |
| `tests/unit/test_teardown.py` | Proves every teardown failure and LIFO order survive sync and async drains. | 2 |
| `tests/unit/test_free_threading.py` | Deterministic lock-table fault injection and cross-event-loop stress on GIL-disabled builds. | 3, 4 |
| `depin/_core/scope.py` | Owns cross-loop-safe async single-flight state under its existing mutex. | 4 |
| `depin/_core/frozen.py` | Waits asynchronously for a thread-safe flight event instead of sharing an `asyncio.Lock` across threads. | 4 |
| `tests/unit/test_frozen_async.py` | Pins cancellation/failure behavior of event-based async single-flight in one loop. | 4 |
| `specs/audits/2026-08-30-free-threading-assumptions.md` | Inventory and disposition of every interpreter/GIL assumption. | 4 |
| `scripts/__init__.py` | Makes the mutation checker importable by tests and type checkers. | 5 |
| `scripts/check_mutation_threshold.py` | Validates mutmut JSON, rejects inconclusive outcomes, and enforces at least 95% killed mutants. | 5 |
| `tests/unit/test_mutation_threshold.py` | Unit tests the mutation-gate parser and threshold boundary. | 5 |
| `.github/workflows/mutation.yml` | Runs mutation testing weekly, manually, and on relevant pull requests. | 5 |
| `.gitignore` | Excludes mutmut's generated `mutants/` tree. | 5 |
| `CONTRIBUTING.md` | Documents local mutation commands, the 5% survivor ceiling, and CI cadence. | 5 |
| `.github/workflows/ci.yml` | Measures unit-suite coverage in both free-threaded matrix jobs. | 6 |
| `specs/evidence/2026-08-30-step-1-verification.md` | Durable commands and red/green output for sabotage, guard removal, mutation seeding, and matrix coverage. | 6 |

### Task 1: Add property-based graph verification

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `tests/unit/test_graph_properties.py`

**Interfaces:**

- `GraphCase` is an immutable test-only model: node count, directed dependency edges, scopes, registered nodes, and duplicate bindings.
- `_materialize(GraphCase) -> Container` creates real dynamically named classes with inspectable constructor signatures and binds them through `Container.bind`.
- Four `@given` tests correspond one-for-one with the four roadmap invariants.

- [ ] **Step 1: Add Hypothesis to both test environments**

Run:

```bash
uv add --dev 'hypothesis>=6.138,<7'
```

Then add the same bound to the existing `threads` dependency group. Add `pytest-cov>=7.1,<8` to `threads` as well so its CI invocation can measure coverage. Do not add either package to `[project.dependencies]`.

- [ ] **Step 2: Write the graph model and strategies**

Create `tests/unit/test_graph_properties.py`. Use this structure; helper names are part of the task contract:

```python
"""Generative checks for the provider-graph validator."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.strategies import DrawFn, SearchStrategy

from depin._core.container import Container
from depin._core.graph import build_plan
from depin._core.scope import Scope
from depin._core.spec import ProviderSpec
from depin.errors import CaptiveDependencyError, CircularDependencyError, DepinError


@dataclass(frozen=True, slots=True)
class GraphCase:
    size: int
    edges: frozenset[tuple[int, int]]
    scopes: tuple[Scope, ...]
    registered: tuple[bool, ...]
    duplicates: frozenset[int]


def _init_for(dependencies: tuple[type[object], ...]) -> Callable[..., None]:
    def initialize(self: object, **values: object) -> None:
        _ = self, values

    parameters = [inspect.Parameter('self', inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    annotations: dict[str, object] = {'return': None}
    for index, dependency in enumerate(dependencies):
        name = f'dep_{index}'
        parameters.append(inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=dependency))
        annotations[name] = dependency
    initialize.__annotations__ = annotations
    setattr(initialize, '__signature__', inspect.Signature(parameters))
    return initialize


def _materialize(case: GraphCase) -> Container:
    nodes: tuple[type[object], ...] = tuple(type(f'Node{index}', (), {}) for index in range(case.size))
    for owner, node in enumerate(nodes):
        dependencies = tuple(nodes[target] for source, target in sorted(case.edges) if source == owner)
        setattr(node, '__init__', _init_for(dependencies))

    container = Container()
    for index, node in enumerate(nodes):
        if not case.registered[index]:
            continue
        container.bind(node, scope=case.scopes[index])
        if index in case.duplicates:
            container.bind(node, scope=case.scopes[index])
    return container
```

If either strict checker rejects assignment to runtime metadata, keep the unsafe runtime operation inside one narrow test helper using `setattr`; do not suppress the diagnostic and do not widen types to `Any`.

Define three composite strategies:

1. `_graphs()` generates 1–8 nodes, arbitrary edges (including self edges), every scope, arbitrary registration, and duplicates restricted to registered nodes.
2. `_acyclic_graphs()` generates only edges `(owner, dependency)` where `dependency < owner`, registers every node, and emits no duplicates.
3. `_non_captive_graphs()` starts from `_graphs()` and filters with a pure reachability helper so no path beginning at a singleton can reach a scoped node. Do not weaken this to direct edges; captive validation follows transient chains.

Use `@settings(max_examples=200, deadline=None)` on each property. `deadline=None` removes a machine-speed deadline, not a correctness check.

- [ ] **Step 3: Write the four properties**

Add these behaviors as distinct tests:

```python
@given(_graphs())
@settings(max_examples=200, deadline=None)
def test_freeze_returns_a_topological_plan_or_a_depin_error(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        container.freeze()
    except DepinError:
        return

    plan = build_plan(container.records())
    positions = {(spec.key, spec.tag): index for index, spec in enumerate(plan.order)}
    for owner in plan.order:
        for parameter in owner.params:
            dependency_position = positions.get((parameter.key, parameter.tag))
            if dependency_position is not None:
                assert dependency_position < positions[(owner.key, owner.tag)]


@given(_graphs())
@settings(max_examples=200, deadline=None)
def test_graph_validation_never_leaks_a_non_depin_exception(case: GraphCase) -> None:
    try:
        _materialize(case).freeze()
    except DepinError:
        pass
    except Exception as exc:
        pytest.fail(f'graph validation leaked {type(exc).__name__}: {exc}')


@given(_acyclic_graphs())
@settings(max_examples=200, deadline=None)
def test_an_acyclic_graph_never_reports_a_cycle(case: GraphCase) -> None:
    try:
        _materialize(case).freeze()
    except CircularDependencyError as exc:
        pytest.fail(f'acyclic graph reported a cycle: {exc}')
    except DepinError:
        pass


@given(_non_captive_graphs())
@settings(max_examples=200, deadline=None)
def test_a_graph_without_a_singleton_to_scoped_path_is_not_captive(case: GraphCase) -> None:
    try:
        _materialize(case).freeze()
    except CaptiveDependencyError as exc:
        pytest.fail(f'non-captive graph reported a captive dependency: {exc}')
    except DepinError:
        pass
```

- [ ] **Step 4: Verify the new properties pass under the full unit invocation**

Run:

```bash
uv run pytest tests/unit
```

Expected: PASS. This is the same directory-level invocation the free-threaded CI job uses.

- [ ] **Step 5: Prove every property detects a deliberate validator defect**

Apply one sabotage at a time to `depin/_core/graph.py`, run only the named property with `-x -vv`, capture Hypothesis's minimized counterexample, and restore the file before the next sabotage:

| Property | Deliberate break | Required failure |
| --- | --- | --- |
| topological plan | Return `tuple(specs)` at the start of `_toposort`. | A dependency position is not before its owner. |
| DepinError hierarchy | Raise `RuntimeError('seeded non-Depin failure')` at the start of `_check_duplicates`. | `pytest.fail` reports leaked `RuntimeError`. |
| acyclic graph | In `_toposort`, raise `CircularDependencyError('seeded false cycle')` when `dep_ident in visited`. | The acyclic property reports a false cycle. |
| non-captive graph | In `_check_captive`, treat `Scope.SINGLETON` as the dependency scope that raises. | The non-captive property reports a false captive edge. |

After each run, append the command, exit code, failing assertion, and minimized `GraphCase` to the Step 1 evidence file created in Task 6. Use `git diff --exit-code depin/_core/graph.py` after restoring; do not carry a sabotage into another run.

- [ ] **Step 6: Run the five gates and commit**

Run the five gates in the required order. Expected: all pass with no warnings. Then:

```bash
git add pyproject.toml uv.lock tests/unit/test_graph_properties.py
git commit -m "test: add generative graph validation"
```

### Task 2: Preserve teardown failures and construction order

**Files:**

- Modify: `tests/unit/test_teardown.py`

**Interfaces:** Test through real singleton and scoped providers. The observable contract is the ordered `ExceptionGroup.exceptions` tuple plus an event list written by provider finalizers.

- [ ] **Step 1: Strengthen the synchronous aggregate test**

Replace the count-only `test_sync_close_aggregates_failures` with a test that constructs three independent singleton generator providers in the order `int`, `str`, `bytes`. Each finalizer appends its name and raises a distinct `RuntimeError`. Resolve all three, call `close()`, and assert:

```python
assert events == ['bytes', 'str', 'int']
assert [str(error) for error in exc.value.exceptions] == ['bytes failed', 'str failed', 'int failed']
```

This verifies both failure preservation and reverse construction order.

- [ ] **Step 2: Add a drain-internal failure alongside provider failures**

Create one scoped generator that raises `RuntimeError('provider failed')` after yielding and another that yields twice, causing depin's `_exhaust_sync` to raise `TeardownError`. Construct them in a known order inside `frozen.scope()`. Assert the resulting group contains both errors in reverse construction order and that the `TeardownError` message says the generator yielded more than once.

- [ ] **Step 3: Add the asynchronous counterpart**

Under `frozen.ascope()`, combine a sync generator finalizer failure, an async generator finalizer failure, and an async generator that yields twice. Resolve them in a known order with distinct tags or distinct keys. Assert:

- all three finalizers were attempted;
- `ExceptionGroup.exceptions` is in reverse resolution/construction order;
- both user failures and the depin `TeardownError` survive.

Do not patch `teardown.run_async`; the real drain must create the group.

- [ ] **Step 4: Verify RED against a drain that aborts early**

Temporarily remove the per-record `try` / `except` from `ScopeFrame.drain_sync` and `drain_async`, leaving the first raised exception to abort each loop. Run:

```bash
uv run pytest tests/unit/test_teardown.py -x -vv
```

Expected: FAIL because later finalizers are absent and the group no longer contains every error. Restore `scope.py`, then run:

```bash
uv run pytest tests/unit
```

Expected: PASS.

- [ ] **Step 5: Run the five gates and commit**

```bash
git add tests/unit/test_teardown.py
git commit -m "test: preserve teardown failures in LIFO order"
```

### Task 3: Make the per-key mutex test deterministic

**Files:**

- Modify: `tests/unit/test_free_threading.py`

**Interfaces:** `_RendezvousLockTable` is a test-only mapping injected with `object.__setattr__`. Its `get` waits at a barrier only when `ScopeFrame._mutex` is not held, so the production guard serializes normally and the deliberately unguarded version forces every thread between lookup and write.

- [ ] **Step 1: Replace the probabilistic direct lock-table test**

Add a small test helper with these semantics:

```python
class _RendezvousLockTable:
    def __init__(self, guard: threading.Lock, rendezvous: threading.Barrier) -> None:
        self._guard = guard
        self._rendezvous = rendezvous
        self._values: dict[object, threading.Lock] = {}

    def get(self, key: object) -> threading.Lock | None:
        value = self._values.get(key)
        if value is None and not self._guard.locked():
            _ = self._rendezvous.wait()
        return value

    def __setitem__(self, key: object, value: threading.Lock) -> None:
        self._values[key] = value
```

In `test_the_per_key_lock_table_survives_concurrent_creation`, use one key, retrieve the frame's mutex with `object.__getattribute__`, verify it is a `threading.Lock`, and inject `_RendezvousLockTable` with `object.__setattr__`. Start all workers together and assert every returned lock has the same identity. The helper must not rely on interpreter scheduling or repeat 64 keys.

- [ ] **Step 2: Verify it passes on both free-threaded interpreters**

Install interpreters and create isolated environments:

```bash
uv python install 3.13t 3.14t
uv venv --python 3.13t /tmp/depin-step1-313t
uv venv --python 3.14t /tmp/depin-step1-314t
uv sync --no-default-groups --group threads --python /tmp/depin-step1-313t
uv sync --no-default-groups --group threads --python /tmp/depin-step1-314t
uv run --no-sync --python /tmp/depin-step1-313t pytest tests/unit
uv run --no-sync --python /tmp/depin-step1-314t pytest tests/unit
```

Expected: both directory-level invocations pass and report the free-thread-only tests as executed, not skipped.

- [ ] **Step 3: Remove the guard and prove deterministic failure**

Temporarily replace `sync_lock_for` with the unguarded lookup/create/write body. Run once on each free-threaded interpreter:

```bash
uv run --no-sync --python /tmp/depin-step1-313t pytest \
  tests/unit/test_free_threading.py::test_the_per_key_lock_table_survives_concurrent_creation -vv
uv run --no-sync --python /tmp/depin-step1-314t pytest \
  tests/unit/test_free_threading.py::test_the_per_key_lock_table_survives_concurrent_creation -vv
```

Expected: both invocations FAIL on the identity assertion in one run. Record their relevant output. Restore `scope.py` and repeat `pytest tests/unit` on both environments; both must pass.

- [ ] **Step 4: Run the five gates and commit**

```bash
git add tests/unit/test_free_threading.py
git commit -m "test: force the per-key lock creation race"
```

### Task 4: Audit and remove free-threading assumptions

**Files:**

- Modify: `depin/_core/scope.py`
- Modify: `depin/_core/frozen.py`
- Modify: `tests/unit/test_free_threading.py`
- Modify: `tests/unit/test_frozen_async.py`
- Create: `specs/audits/2026-08-30-free-threading-assumptions.md`

**Interfaces:**

- Replace `ScopeFrame.async_lock_for` with two private operations:
  - `start_async_flight(key) -> tuple[threading.Event, bool]`, where `bool` means this caller constructs;
  - `finish_async_flight(key, event) -> None`, which removes that exact flight and wakes every waiter.
- `_resolve_async` loops until it becomes the constructor or observes a cached value. Followers await `asyncio.to_thread(event.wait)`, which blocks no event loop and works across event loops in different OS threads.
- A failed or cancelled constructor always finishes its flight in `finally`; a follower then retries under a new flight instead of hanging.

- [ ] **Step 1: Write the cross-event-loop RED test**

Add a free-threaded test that shares one frozen container across `THREADS` OS threads, creates one event loop per thread with `asyncio.run`, and races `aresolve` for the same async singleton. Use a barrier before every resolution, a provider-side `threading.Event` to hold the constructor open, and a condition/counter to let a coordinator release it only after all workers have entered the resolution attempt. Assert exactly one instance was constructed and every worker received it.

Run on 3.13t and 3.14t with `PYTHONASYNCIODEBUG=1`:

```bash
PYTHONASYNCIODEBUG=1 uv run --no-sync --python /tmp/depin-step1-313t pytest \
  tests/unit/test_free_threading.py::test_async_singleton_is_single_flight_across_event_loops -vv
PYTHONASYNCIODEBUG=1 uv run --no-sync --python /tmp/depin-step1-314t pytest \
  tests/unit/test_free_threading.py::test_async_singleton_is_single_flight_across_event_loops -vv
```

Expected before implementation: FAIL with cross-thread/event-loop `asyncio.Lock` behavior or duplicate construction. Capture both results. A hang is not an acceptable RED; refine only the test synchronization until it terminates deterministically.

- [ ] **Step 2: Implement event-based async single-flight**

In `ScopeFrame`:

- replace `_async_locks: dict[object, asyncio.Lock]` with `_async_flights: dict[object, threading.Event]`;
- update `__slots__` and remove the `asyncio` import;
- implement `start_async_flight` entirely under `_mutex`;
- in `finish_async_flight`, remove only when the stored event `is event`, then call `event.set()` after releasing `_mutex`.

In `FrozenContainer._resolve_async`, keep the current cache fast path, then:

```python
while True:
    cached = frame.lookup(cache_id)
    if cached is not MISSING:
        return cached
    event, constructs = frame.start_async_flight(cache_id)
    if not constructs:
        await asyncio.to_thread(event.wait)
        continue
    try:
        cached = frame.lookup(cache_id)
        if cached is not MISSING:
            return cached
        value = await self._construct_async(spec)
        frame.provide(cache_id, value)
        return value
    finally:
        frame.finish_async_flight(cache_id, event)
```

Do not hold a `threading.Lock` across `await`, and do not create one `asyncio.Lock` per event loop; either would permit deadlock or duplicate singleton construction.

- [ ] **Step 3: Pin failure and cancellation semantics in one event loop**

In `tests/unit/test_frozen_async.py`, add:

1. two tasks race an async singleton whose first construction raises; the waiting task retries and succeeds, with no hang;
2. the constructor task is cancelled while a follower waits; the follower becomes the next constructor and succeeds;
3. many tasks racing a successful singleton still construct exactly once.

Coordinate with `asyncio.Event`; do not use `asyncio.sleep`.

- [ ] **Step 4: Complete the assumption inventory**

Create `specs/audits/2026-08-30-free-threading-assumptions.md` with a table containing: site, shared state, previous assumption, 3.13t/3.14t finding, disposition, and pinning test. Cover every item below explicitly:

- `ScopeFrame._cache`, `_sync_locks`, `_async_flights`, and `_teardowns`;
- synchronous and asynchronous single-flight across OS threads;
- `ContextVar` scope behavior in sibling tasks, sibling threads, and a child thread created inside an active context (`thread_inherit_context` differs by build);
- override-stack inheritance and isolation;
- interaction between `threading.Lock` and event-loop waits;
- all graph/build dictionaries and lists (call-local, not shared);
- immutable post-freeze `ResolutionPlan` reads;
- `sys.modules` and module-namespace snapshots used by missing-provider suggestions;
- the FastAPI integration's container `ContextVar`;
- the removed `gc.get_objects()` assumption from Step 0, as historical evidence rather than live code.

Reference the official Python pages directly:

- `https://docs.python.org/3/howto/free-threading-python.html`
- `https://docs.python.org/3/library/asyncio-threading.html`
- `https://docs.python.org/3/library/asyncio-sync.html`
- `https://docs.python.org/3/library/contextvars.html`

Every non-local assumption either cites a pre-existing test or adds a focused test in `test_free_threading.py`. No row may say only “safe” without evidence.

- [ ] **Step 5: Verify the original claim, not just the tests**

Run a standalone scenario on both free-threaded interpreters that shares one `FrozenContainer`, creates one event loop per thread, races 32 calls to `aresolve`, and prints the construction count. Expected: `constructed=1`, 32 identical result identities, no debug warnings with `PYTHONASYNCIODEBUG=1`.

Then run `pytest tests/unit` on 3.13t and 3.14t. Expected: PASS.

- [ ] **Step 6: Run the gates, docs build, and commit**

Run the five gates, then `uv run --group docs mkdocs build --strict`. Commit:

```bash
git add depin/_core/scope.py depin/_core/frozen.py \
  tests/unit/test_free_threading.py tests/unit/test_frozen_async.py \
  specs/audits/2026-08-30-free-threading-assumptions.md
git commit -m "fix: single-flight async providers across event loops"
```

### Task 5: Enforce mutation depth

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.gitignore`
- Create: `scripts/__init__.py`
- Create: `scripts/check_mutation_threshold.py`
- Create: `tests/unit/test_mutation_threshold.py`
- Create: `.github/workflows/mutation.yml`
- Modify: `CONTRIBUTING.md`

**Interfaces:**

- mutmut mutates only `depin/_core/**/*.py`, but `source_paths = ['depin']` copies the whole package so imports resolve from the mutated tree.
- The mutation checker accepts one stats JSON path and exits nonzero unless all results are conclusive and killed-mutant score is at least 95.0% (equivalently, survivors are at most 5.0% of killed + survived).
- `mutants/` is generated, ignored, and uploaded as a CI artifact; it is never committed.

- [ ] **Step 1: Add and configure mutmut**

Run:

```bash
uv add --dev 'mutmut>=3.7,<4'
```

Add:

```toml
[tool.mutmut]
source_paths = ["depin"]
only_mutate = ["depin/_core/*.py"]
pytest_add_cli_args_test_selection = ["tests/unit"]
```

Do not enable `type_check_command`: the purpose is to measure whether tests kill behavior changes, not let a checker hide them. Add `mutants/` under “Tooling caches” in `.gitignore`.

- [ ] **Step 2: Write the threshold-checker tests first**

Create `tests/unit/test_mutation_threshold.py` around pure functions imported from `scripts.check_mutation_threshold`. Cover:

- 95 killed and 5 survived passes exactly at the boundary;
- 94 killed and 6 survived fails and reports both score and allowed survivor ratio;
- any `no_tests`, `skipped`, `suspicious`, `timeout`, interrupted, or segfault result fails even with a high score;
- malformed JSON, missing fields, non-integer fields, negative values, and inconsistent totals fail actionably;
- zero decided mutants fails rather than dividing by zero or reporting success.

Run the file and confirm RED because the module does not exist.

- [ ] **Step 3: Implement the checker**

Create an immutable `MutationStats` dataclass with the exact keys emitted by mutmut 3.7:

```python
killed
survived
total
no_tests
skipped
suspicious
timeout
check_was_interrupted_by_user
segfault
```

Use `json.loads` at one private boundary, immediately narrow to `dict[str, object]` with `isinstance`, validate exact integer fields (reject `bool`), and return typed data. Expose:

```python
MINIMUM_KILLED_PERCENT = 95.0


def evaluate(stats: MutationStats) -> str | None: ...
def main(arguments: list[str] | None = None) -> int: ...
```

`evaluate` returns `None` on success or one actionable error string. `main` prints a one-line summary and returns 0/1. Do not use `argparse`'s untyped namespace; accept exactly one positional path with a small typed parser.

- [ ] **Step 4: Run the real mutation suite and close survivors to the declared ceiling**

Start clean and run:

```bash
rm -rf mutants
uv run mutmut run
uv run mutmut export-cicd-stats
uv run python -m scripts.check_mutation_threshold mutants/mutmut-cicd-stats.json
uv run mutmut results
```

Expected final state:

- no inconclusive results;
- killed-mutant score at least 95.0%;
- survivors no more than 5.0% of decided mutants.

For every survivor above the ceiling, inspect with `uv run mutmut show <name>`, add the smallest behavior test, observe that named mutant die, then rerun the complete mutation command. Do not add `# pragma: no mutate` waivers merely to meet the number. If a genuinely equivalent mutant exists, document the proof in the evidence file and keep it within the 5% ceiling.

- [ ] **Step 5: Seed a mutation-gate regression**

Temporarily invoke the checker with a copied stats fixture whose score is 94%, and run the workflow command locally. Expected: exit 1 with the declared 95% threshold in the message. Then restore the real stats path and confirm exit 0. Record both outputs.

- [ ] **Step 6: Add the scheduled and path-filtered workflow**

Create `.github/workflows/mutation.yml` with:

```yaml
name: Mutation testing

on:
  pull_request:
    paths:
      - 'depin/_core/**'
      - 'tests/**'
      - 'scripts/check_mutation_threshold.py'
      - 'pyproject.toml'
      - 'uv.lock'
      - '.github/workflows/mutation.yml'
  schedule:
    - cron: '23 4 * * 1'
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: mutation-${{ github.ref }}
  cancel-in-progress: true
```

The single Ubuntu/Python 3.12 job has a 60-minute timeout, uses the repository's already pinned checkout/setup-uv action SHAs, runs `uv sync --locked`, then the four commands from Step 4. Upload `mutants/mutmut-cicd-stats.json` with `actions/upload-artifact` under `if: always()` so a failure remains diagnosable. Pin the upload action by full SHA, following the existing workflows.

- [ ] **Step 7: Document the gate**

Add “Mutation testing” under the testing section of `CONTRIBUTING.md`:

- local commands from Step 4;
- `_core` scope;
- at least 95% killed / at most 5% surviving;
- zero inconclusive results;
- weekly, manual, and relevant-PR cadence;
- `mutants/` is disposable generated state.

- [ ] **Step 8: Run gates, docs build, and commit**

Run the five gates and strict MkDocs build. Then:

```bash
git add pyproject.toml uv.lock .gitignore scripts tests/unit/test_mutation_threshold.py \
  .github/workflows/mutation.yml CONTRIBUTING.md
git commit -m "build: enforce mutation testing for the core"
```

### Task 6: Measure the full matrix and record verification evidence

**Files:**

- Modify: `.github/workflows/ci.yml`
- Create: `specs/evidence/2026-08-30-step-1-verification.md`

**Interfaces:** The evidence file is not a hand-written claim. It contains exact commands, interpreter versions/GIL state, exit codes, relevant failure/pass output, and coverage totals from this implementation.

- [ ] **Step 1: Make free-threaded coverage visible in CI**

Change only the `free-threaded` job's Test step to:

```yaml
      - name: Test with coverage
        run: uv run --no-sync pytest tests/unit --cov=depin --cov-report=term
```

This preserves the CI-shaped directory invocation and enforces the existing `[tool.coverage.report] fail_under = 95` on both GIL-disabled versions.

- [ ] **Step 2: Measure coverage on all blocking interpreters**

Create isolated environments and run exactly:

```bash
uv python install 3.12 3.13 3.14 3.13t 3.14t

uv run --python 3.12 pytest --cov=depin --cov-report=term
uv run --python 3.13 pytest --cov=depin --cov-report=term
uv run --python 3.14 pytest --cov=depin --cov-report=term
uv run --no-sync --python /tmp/depin-step1-313t pytest tests/unit --cov=depin --cov-report=term
uv run --no-sync --python /tmp/depin-step1-314t pytest tests/unit --cov=depin --cov-report=term
```

For each run record `python --version`, `sys._is_gil_enabled()` when present, total coverage, test count, skips, and exit code. Every total must be at least 95%. Do not infer one version from another.

- [ ] **Step 3: Assemble durable red/green evidence**

Create `specs/evidence/2026-08-30-step-1-verification.md` with these completed sections and no placeholders:

1. four graph-property sabotages and their minimized counterexamples;
2. teardown abort-on-first-failure sabotage;
3. `ScopeFrame._mutex` removal on 3.13t and 3.14t;
4. cross-event-loop async singleton before/after evidence on 3.13t and 3.14t;
5. seeded mutation-threshold failure and real mutation score;
6. the five per-version coverage results;
7. the standalone 32-thread/32-event-loop root-cause scenario.

Keep only relevant output windows, but preserve exact assertions and exit codes. State the commit SHA measured.

- [ ] **Step 4: Re-run every complete local gate**

Run in order:

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
uv run --group bench pytest benchmarks --benchmark-only
uv run mutmut run
uv run mutmut export-cicd-stats
uv run python -m scripts.check_mutation_threshold mutants/mutmut-cicd-stats.json
```

Expected: all exit 0, no warnings/waivers, coverage at least 95%, mutation score at least 95%, and no benchmark regression against the Step 0 local baseline. The five repository gates must remain in their exact order even though additional checks follow.

- [ ] **Step 5: Commit the evidence and CI coverage change**

```bash
git add .github/workflows/ci.yml specs/evidence/2026-08-30-step-1-verification.md
git commit -m "test: record Step 1 verification evidence"
```

### Task 7: Final review and pull request

**Files:** No planned source changes. Reviewer fixes remain in the task/commit that owns them.

- [ ] **Step 1: Review roadmap compliance**

Compare the final diff line by line with `## Step 1 — Verification depth (0.6.0)` and `## Carried from Step 0`. Confirm:

- all four graph properties exist and have deliberate-break evidence;
- mutation threshold and cadence are enforced/documented;
- free-threaded stress has no timed sleeps;
- direct per-key test fails deterministically with `_mutex` removed on both t builds;
- teardown groups preserve every error in LIFO order;
- the assumption audit covers every required site and dispositions have tests;
- advisory `ty` behavior/diagnostics did not change;
- no unrelated Step 3 or Step 6 carried finding was implemented.

- [ ] **Step 2: Request final code-quality review**

Review `origin/main...HEAD`, including maintainability, deterministic tests, workflow safety, threshold semantics, and the cross-loop single-flight cancellation path. Resolve every Critical or Important finding and rerun the owning task's checks.

- [ ] **Step 3: Run the final gates fresh**

Run the five gates, strict docs build, benchmark suite, mutation gate, and `git diff --check`. Confirm `git status --short` is empty and no sabotage remains.

- [ ] **Step 4: Push and open the PR**

Push `test/step-1-verification-depth` and open a PR against `main` with title:

```text
feat: deepen verification for 0.6.0
```

Fill the repository template with a concise summary and the exact verification commands. Do not mention agents, assistants, or automation. Do not merge locally.

- [ ] **Step 5: Inspect real CI**

Wait for every PR check, including the path-triggered mutation workflow, free-threaded 3.13t/3.14t, coverage, benchmark comparison, CodeQL/dependency review where applicable. If a runner reveals a failure, reproduce the same directory-level invocation and interpreter locally before changing code. Update the same PR; never waive a blocking failure.
