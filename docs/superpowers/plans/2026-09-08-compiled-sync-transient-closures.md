# Compiled Sync Transient Closures Experiment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide, with correctness and performance evidence, whether freeze-time closure composition is a viable execution strategy for synchronous transient provider chains.

**Architecture:** `FrozenContainer` will precompose immutable zero-argument closures only for shallow, fully synchronous chains made entirely from transient function providers with statically bound dependencies. The normal interpreter remains the oracle and fallback for active overrides, cached or scoped dependencies, resource providers, missing/default/frame-provided parameters, async providers, and plans large enough to require the iterative executor. The prototype is accepted only if the transient-chain workload improves by at least 10% without violating any existing correctness or regression gate.

**Tech Stack:** Python 3.12, PEP 695 typing, pytest, pytest-benchmark, uv, ruff, Basedpyright, mypy, the repository benchmark harness.

---

### Task 1: Specify closure compilation

**Files:**
- Create: `tests/unit/test_compiled_resolution.py`
- Create: `depin/_core/compiled.py`

- [ ] **Step 1: Write the failing compiler tests**

Add tests which build real plans through `Container` and `build_plan`, then require:

```python
import pytest

from depin import Container, Scope
from depin._core.compiled import compile_sync_transients
from depin._core.graph import build_plan


def test_compile_sync_transients_composes_a_function_chain() -> None:
    constructed: list[str] = []

    class Leaf: ...

    class Root: ...

    def leaf() -> Leaf:
        constructed.append('leaf')
        return Leaf()

    def root(leaf: Leaf) -> Root:
        constructed.append('root')
        return Root()

    builder = Container().bind(leaf, scope=Scope.TRANSIENT).bind(root, scope=Scope.TRANSIENT)
    programs = compile_sync_transients(build_plan(builder.records()))

    assert isinstance(programs[(Root, None)](), Root)
    assert constructed == ['leaf', 'root']


@pytest.mark.parametrize('dependency_scope', [Scope.SINGLETON, Scope.SCOPED])
def test_compile_sync_transients_rejects_a_cached_dependency(dependency_scope: Scope) -> None:
    class Dependency: ...

    class Root: ...

    def dependency() -> Dependency:
        return Dependency()

    def root(dependency: Dependency) -> Root:
        return Root()

    builder = Container().bind(dependency, scope=dependency_scope).bind(root, scope=Scope.TRANSIENT)
    programs = compile_sync_transients(build_plan(builder.records()))

    assert (Root, None) not in programs


def test_compile_sync_transients_rejects_non_function_provider_shapes() -> None:
    class Dependency: ...

    class Root:
        def __init__(self, dependency: Dependency) -> None:
            self.dependency = dependency

    builder = Container().bind(Dependency, scope=Scope.TRANSIENT).bind(Root, scope=Scope.TRANSIENT)
    programs = compile_sync_transients(build_plan(builder.records()))

    assert (Root, None) not in programs
```

The completed tests must use real containers and explicit assertions, with no mocks or type suppressions.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/unit/test_compiled_resolution.py -q
```

Expected: collection fails because `depin._core.compiled` does not exist.

- [ ] **Step 3: Implement the minimal compiler**

Create `depin/_core/compiled.py` with this shape:

```python
"""Freeze-time composition of specialized provider execution paths."""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from depin._core.scope import Scope
from depin._core.spec import Ident, ProviderShape, ProviderSpec, ResolutionPlan
from depin._core.typeguards import as_factory

type SyncProgram = Callable[[], object]
type _DependencyPrograms = tuple[tuple[str, SyncProgram], ...]


def compile_sync_transients(plan: ResolutionPlan) -> Mapping[Ident, SyncProgram]:
    programs: dict[Ident, SyncProgram] = {}
    for spec in plan.order:
        dependencies = _dependencies(spec, plan, programs)
        if dependencies is None:
            continue
        factory = as_factory(spec.source, spec.key)
        programs[(spec.key, spec.tag)] = _compose(factory, dependencies)
    return MappingProxyType(programs)


def _dependencies(
    spec: ProviderSpec,
    plan: ResolutionPlan,
    programs: Mapping[Ident, SyncProgram],
) -> _DependencyPrograms | None:
    if spec.scope is not Scope.TRANSIENT or spec.shape is not ProviderShape.FUNCTION or spec.needs_async:
        return None
    dependencies: list[tuple[str, SyncProgram]] = []
    for param in spec.params:
        dependency = plan.by_key.get((param.key, param.tag))
        if dependency is None:
            return None
        program = programs.get((dependency.key, dependency.tag))
        if program is None:
            return None
        dependencies.append((param.name, program))
    return tuple(dependencies)


def _compose(factory: Callable[..., object], dependencies: _DependencyPrograms) -> SyncProgram:
    if not dependencies:
        return factory

    def resolve() -> object:
        return factory(**{name: dependency() for name, dependency in dependencies})

    return resolve
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/unit/test_compiled_resolution.py -q
uv run basedpyright depin/_core/compiled.py tests/unit/test_compiled_resolution.py
uv run mypy depin/_core/compiled.py tests/unit/test_compiled_resolution.py
```

Expected: all commands pass with no warnings or suppressions.

- [ ] **Step 5: Commit the compiler contract**

```bash
git add depin/_core/compiled.py tests/unit/test_compiled_resolution.py
git commit -m 'perf: compose synchronous transient closures'
```

### Task 2: Route eligible resolutions through the compiled program

**Files:**
- Modify: `depin/_core/frozen.py:28-53`
- Modify: `depin/_core/frozen.py:146-154`
- Modify: `depin/_core/frozen.py:202-214`
- Modify: `depin/_core/overrides.py:24-43`
- Modify: `tests/unit/test_compiled_resolution.py`

- [ ] **Step 1: Write failing runtime tests**

Add tests that prove:

1. The no-override path and the interpreter path produce the same value and construction order. Force the interpreter by activating an override for a registered key outside the tested chain.
2. An override of a nested dependency is observed and the original dependency is not constructed.
3. A 1,000-provider transient graph still uses the existing iterative executor and resolves without changing the recursion limit.
4. Optional/default/frame-provided parameters remain on the interpreter path.

The tests must resolve through real `Container` and `FrozenContainer` instances. They may inspect the private compiled-program mapping only to prove eligibility; they must not mock resolution.

- [ ] **Step 2: Verify RED**

```bash
uv run pytest tests/unit/test_compiled_resolution.py tests/unit/test_iterative_resolution.py -q
```

Expected: the assertions about `FrozenContainer`'s compiled mapping fail.

- [ ] **Step 3: Add a constant-time override-stack predicate**

Add to `depin/_core/overrides.py`:

```python
def present() -> bool:
    """Return whether this context carries at least one override frame."""
    return bool(_stack.get())
```

- [ ] **Step 4: Build and use programs in `FrozenContainer`**

Import `SyncProgram` and `compile_sync_transients`, add `_sync_transients` to `__slots__`, and initialize it only when `len(plan.order) < _RECURSIVE_PLAN_LIMIT`:

```python
self._sync_transients: Mapping[Ident, SyncProgram] = (
    compile_sync_transients(plan) if len(plan.order) < _RECURSIVE_PLAN_LIMIT else MappingProxyType({})
)
```

After `_lookup()` and the async rejection in `resolve()`, select the fast path only when no override frame exists:

```python
program = None if overrides.present() else self._sync_transients.get((spec.key, spec.tag))
if program is not None:
    resolved = program()
elif spec.scope is Scope.TRANSIENT:
    if len(self._plan.order) >= _RECURSIVE_PLAN_LIMIT:
        resolved = self._resolve_sync_iterative(spec)
    else:
        kwargs = self._resolve_params_sync(spec) if spec.params else {}
        resolved = construct.sync(spec, kwargs, self._teardown_sink(spec), self._read_frame)
elif spec.scope is Scope.SINGLETON:
    resolved = self._resolve_root_cached_sync(spec)
else:
    resolved = self._resolve_cached_sync(spec, active_frame(self._root))
```

Do not alter async resolution, cache claims, scopes, teardown, lifecycle gating, diagnostics, or public signatures.

- [ ] **Step 5: Verify runtime parity**

```bash
uv run pytest tests/unit/test_compiled_resolution.py tests/unit/test_resolution.py \
    tests/unit/test_iterative_resolution.py tests/unit/test_overrides.py \
    tests/unit/test_runtime_correctness.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the runtime routing**

```bash
git add depin/_core/frozen.py depin/_core/overrides.py tests/unit/test_compiled_resolution.py
git commit -m 'perf: route transient chains through compiled closures'
```

### Task 3: Prove the bounded experiment's correctness envelope

**Files:**
- Modify: `tests/unit/test_compiled_resolution.py`
- Modify if a real contract defect is found: `depin/_core/compiled.py`
- Modify if a real routing defect is found: `depin/_core/frozen.py`

- [ ] **Step 1: Add differential cases**

Parameterize equivalent compiled/interpreted executions over zero, one, and multiple dependencies, tagged dependencies, factory exceptions, nested overrides, and repeated resolutions. Compare result type, construction log, raised exception type/message, and ensure every transient is reconstructed.

- [ ] **Step 2: Run the differential and neighboring suites**

```bash
uv run pytest tests/unit/test_compiled_resolution.py tests/unit/test_resolution.py \
    tests/unit/test_iterative_resolution.py tests/unit/test_overrides.py \
    tests/unit/test_provider_contracts.py tests/integration/test_workload_equivalence.py -q
```

Expected: all cases pass.

- [ ] **Step 3: Run coverage for the new module**

```bash
uv run pytest tests/unit/test_compiled_resolution.py --cov=depin._core.compiled --cov-report=term-missing
```

Expected: every branch in `depin/_core/compiled.py` is exercised.

- [ ] **Step 4: Commit the differential proof**

```bash
git add depin/_core/compiled.py depin/_core/frozen.py tests/unit/test_compiled_resolution.py
git commit -m 'test: prove compiled transient parity'
```

### Task 4: Verify the prototype before timing it

**Files:**
- No source changes expected.

- [ ] **Step 1: Run the repository gates in order**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all five pass with no warnings or waivers.

- [ ] **Step 2: Check the benchmark contracts**

```bash
uv run pytest tests/integration/test_workload_contracts.py \
    tests/integration/test_workload_equivalence.py benchmarks/test_comparison.py -q
```

Expected: the direct baseline, depin observation, and eligible competitors remain equivalent.

### Task 5: Measure and decide the closure experiment

**Files:**
- Modify after measurement: `specs/proposals/2026-09-02-compiled-resolution-runtime-proposal.md`
- Create for retained evidence: `benchmarks/results/2026-09-08-compiled-sync-closures/`

- [ ] **Step 1: Take a quick diagnostic measurement**

```bash
uv run --group bench pytest benchmarks/test_latency.py -k resolve_a_transient_chain \
    --benchmark-only --benchmark-disable-gc
```

Compare with the pre-experiment local median recorded at `33.857 µs` for depin and `2.247 µs` for direct Python. This comparison is diagnostic only, never accepted evidence.

- [ ] **Step 2: Profile Python calls and allocations**

Run:

```bash
uv run --group bench python - <<'PY'
import cProfile
import pstats
import sys

from benchmarks.graphs import build_chain
from depin import Scope

container, leaf = build_chain(20, scope=Scope.TRANSIENT)
frozen = container.freeze()
profile = cProfile.Profile()
profile.runcall(lambda: [frozen.resolve(leaf) for _ in range(1_000)])
pstats.Stats(profile).strip_dirs().sort_stats('tottime').print_stats(30)
programs = frozen._sync_transients
print(f'programs={len(programs)} shallow_bytes={sum(sys.getsizeof(program) for program in programs.values())}')
PY
```

Confirm that per-node `_lookup_optional`, `_resolve_sync`, `_resolve_params_sync`, and `construct.sync` dispatch are absent from the compiled path. Allocation counts come from the paired harness in the next step; do not infer them from `sys.getsizeof`.

- [ ] **Step 3: Collect paired before/after evidence**

Create a detached baseline worktree at commit `a4a7513`, synchronize both benchmark environments with the locked `bench` group, then run:

```bash
BASE_PARENT=$(mktemp -d)
BASE_WORKTREE="$BASE_PARENT/base"
git worktree add --detach "$BASE_WORKTREE" a4a7513
uv sync --locked --no-default-groups --group bench
(cd "$BASE_WORKTREE" && uv sync --locked --no-default-groups --group bench)
uv run --group bench python -m benchmarks.harness.pairs \
    --base-dir "$BASE_WORKTREE" --head-dir . --repetitions 5 \
    --out /tmp/depin-compiled-sync-closures
uv run --group bench python -m benchmarks.harness.gate \
    /tmp/depin-compiled-sync-closures --budgets benchmarks/budgets.toml
uv run --group bench python -m benchmarks.harness.report \
    /tmp/depin-compiled-sync-closures
git worktree remove "$BASE_WORKTREE"
rmdir "$BASE_PARENT"
```

Retain the raw paired results, environment metadata, deterministic work/allocation data, and report together. A clean worktree is required for accepted evidence.

- [ ] **Step 4: Apply the decision rule**

The experiment is GO only if all of these hold:

- `resolve_a_transient_chain` improves by at least 10% with a decisive interval;
- no required workload exceeds its current regression budget;
- calls and allocations do not regress;
- the 1,000-provider sync and async depth guarantees remain green;
- inactive and active overrides remain within their existing budgets;
- freeze-time and retained-memory changes are bounded and reported.

Otherwise it is NO-GO and no prototype code or new budget is retained.

- [ ] **Step 5A: Record a GO**

If every criterion passes, copy the complete evidence directory into `benchmarks/results/2026-09-08-compiled-sync-closures/`, add the measured decision to the proposal, run the documentation renderer/tests, and commit the accepted experiment. Then write the next plan for expanding the winning closure representation across the proposal's full matrix before selecting it as the runtime.

- [ ] **Step 5B: Record a NO-GO**

If any criterion fails, remove the compiler, routing, and their prototype-only tests; retain only the proposal decision with exact measurements and the reason for rejection. Run all five gates again and commit the decision as documentation. Select the next bounded strategy from the proposal rather than weakening a budget or guarantee.
