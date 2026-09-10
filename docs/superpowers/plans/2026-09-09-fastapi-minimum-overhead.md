# FastAPI Minimum-Overhead Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile direct FastAPI `Inject[...]` parameters into one endpoint program and open request scopes lazily, reducing paired DI-attributable CPU-light p50 overhead by at least 25% against the 2026-09-09 baseline without semantic or secondary-metric regressions.

**Architecture:** `install(app, container)` compiles existing `APIRoute` dependency nodes behind a contained FastAPI compatibility adapter and installs a pure-ASGI lazy host. The core lazy state publishes the existing `FrozenContainer`, activates one real `ScopeFrame` only when resolution needs it, applies framework seeds only on first read, and delegates cleanup to the same drain path used by `ascope()`.

**Tech Stack:** Python 3.12 PEP 695 typing, FastAPI 0.133+, Starlette 1.1+, `contextvars`, `pytest`, `pytest-asyncio`, `httpx`, Ruff, Basedpyright, mypy, MkDocs, and the repository benchmark harness.

**Spec:** `specs/2026-09-09-fastapi-minimum-overhead-design.md`

## Global Constraints

- Baseline revision is exactly `086adf98459773e3175f4723b2b64e3f47306e42`; comparison evidence is rooted at `benchmarks/results/2026-09-09-competitive-rebaseline/`.
- The upper 95% confidence bound of paired DI-attributable CPU-light p50 change must be at most `-25%`; the point estimate targets `-30%` or better.
- FastAPI p95 and p99 total latency may not regress by more than `5%`.
- No-injection latency, retained memory, peak memory, allocation count, startup, and contention must remain within their calibrated noise allowance or authored budget.
- Preserve lifecycle, reverse-order teardown, grouped failures, cancellation, concurrency isolation, typing, `Inject[T]` ergonomics, validation errors, and OpenAPI signatures.
- Preserve the eager `RequestScope` compatibility path; optimized setup is `install(app, container)` after route registration and before startup.
- Core modules keep zero third-party imports and zero runtime dependencies; FastAPI and Starlette imports stay under `depin/ext/`.
- Do not implement provider discovery, Rust/native acceleration, replacement FastAPI dependency injection, or unrelated core runtime optimization.
- Do not use `Any`, `typing.cast`, blanket or narrow type-ignore comments, swallowed exceptions, assertions for runtime validation, sleeps, or mutable module-level state.
- Every production behavior begins with a focused failing test against real `Container`/`FrozenContainer` and follows RED, GREEN, REFACTOR.
- Before every commit run, in order: `uv run ruff format`, `uv run ruff check`, `uv run basedpyright`, `uv run mypy`, `uv run pytest`; documentation commits additionally run `uv run --group docs mkdocs build --strict`.

---

### Task 1: Context-local lazy request scope

**Files:**
- Create: `depin/_core/lazy_scope.py`
- Modify: `depin/_core/scope.py`
- Modify: `depin/_core/hosting.py`
- Modify: `depin/_core/frozen.py`
- Test: `tests/unit/test_hosting.py`
- Test: `tests/unit/test_scope_frame.py`
- Test: `tests/unit/test_frozen_scoped.py`

**Interfaces:**
- Consumes: existing `Host.activated()`, `ScopeFrame`, `push_frame`, `FrozenContainer.ascope()` teardown semantics, `ScopeSeed`, and `active_frame()`.
- Produces: private `_lazy_host(container, seed_factory)` async context manager; private `_provide_lazy_seed(seed)`; a context-local frame activator used transparently by `active_frame()`; one shared eager/lazy scope-drain primitive.

- [ ] **Step 1: Add failing tests for the inactive and first-use transitions**

Add focused async tests whose observable break is eager frame allocation or more than one activation:

```python
@pytest.mark.asyncio
async def test_lazy_host_does_not_open_a_frame_for_a_singleton() -> None:
    class Service:
        pass

    container = Container().bind(Service, scope=Scope.SINGLETON).freeze()
    opened: list[ScopeFrame] = []

    async with _lazy_host(container, on_open=opened.append):
        assert await hosted_container().aresolve(Service) is await container.aresolve(Service)

    assert opened == []


@pytest.mark.asyncio
async def test_lazy_host_opens_one_frame_on_first_scoped_resolution() -> None:
    class Service:
        pass

    container = Container().bind(Service, scope=Scope.SCOPED).freeze()
    opened: list[ScopeFrame] = []

    async with _lazy_host(container, on_open=opened.append):
        first = await hosted_container().aresolve(Service)
        second = await hosted_container().aresolve(Service)

    assert first is second
    assert len(opened) == 1
```

The first test must fail because no lazy host exists. The second must fail for the same missing feature, not because of an import or fixture error.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/unit/test_hosting.py -k 'lazy_host' -vv
```

Expected: both new tests fail at the missing `_lazy_host` contract while existing hosting tests remain green.

- [ ] **Step 3: Implement minimal lazy activation without teardown duplication**

Create immutable/private seed state in `depin/_core/lazy_scope.py`. Keep the external shape private and type-safe:

```python
type SeedIdentity = tuple[object, str | None]


@dataclass(frozen=True, slots=True)
class LazyScopeSeed[T]:
    key: type[T] | Token[T]
    factory: Callable[[], T]
    tag: str | None = None
```

Implement `LazyScopeState.frame()`, `LazyScopeState.provide()`, `LazyScopeState.seed()`, and `LazyScopeState.aclose()` around that immutable seed descriptor. Use a `ContextVar[LazyScopeState | None]` alongside the existing frame context. `active_frame()` asks the state to activate only after the ordinary active-frame lookup is empty. A missing `scope_value` read asks the active lazy state for a matching seed before producing the existing missing-value error. Ordinary scopes and unhosted resolutions take their existing branches unchanged.

Factor the body/teardown exception handling currently used by `FrozenContainer.scope()` and `FrozenContainer.ascope()` into private helpers shared by eager and lazy entry. Do not duplicate drain order, exception grouping, pending-flight cleanup, or context restoration.

- [ ] **Step 4: Verify GREEN for first use**

Run:

```bash
uv run pytest tests/unit/test_hosting.py -k 'lazy_host' -vv
uv run pytest tests/unit/test_scope_frame.py tests/unit/test_frozen_scoped.py -q
```

Expected: the lazy tests pass; existing active-frame and scoped-resolution tests remain green with pristine output.

- [ ] **Step 5: Add failing tests for lazy seeds, failures, cancellation, and concurrency**

Add real-container tests with literal event logs:

```python
@pytest.mark.asyncio
async def test_lazy_seed_is_applied_only_when_its_key_is_read() -> None:
    request = Token[str]('request')
    built: list[str] = []
    container = Container().scope_value(request).freeze()

    def build_request() -> str:
        built.append('r-1')
        return 'r-1'

    async with _lazy_host(container, seeds=(LazyScopeSeed(request, build_request),)):
        assert built == []
        assert await hosted_container().aresolve(request) == 'r-1'

    assert built == ['r-1']


@pytest.mark.asyncio
async def test_lazy_scope_retains_body_and_teardown_failures() -> None:
    events: list[str] = []

    async def resource() -> AsyncIterator[str]:
        try:
            yield 'value'
        finally:
            events.append('closed')
            raise LookupError('close failed')

    container = Container().bind(resource, scope=Scope.SCOPED).freeze()
    with pytest.raises(ExceptionGroup) as raised:
        async with _lazy_host(container):
            assert await hosted_container().aresolve(str) == 'value'
            raise ValueError('body failed')

    assert events == ['closed']
    assert {type(error) for error in raised.value.exceptions} == {ValueError, LookupError}
```

Use `asyncio.Event` or `threading.Barrier`; never sleep. Add a test with two concurrent requests and distinct seed values; each must resolve one stable scoped identity and restore the enclosing host. Add cancellation after resource construction and assert one close event.

- [ ] **Step 6: Verify RED, then implement seeds and complete cleanup**

Run each new test by node ID and confirm the expected missing-seed/failure-preservation behavior first. Implement only the state transitions needed by those tests, then run:

```bash
uv run pytest tests/unit/test_hosting.py tests/unit/test_scope_frame.py tests/unit/test_frozen_scoped.py -q
```

Expected: all focused tests pass; removing lazy activation from `active_frame()` makes the scoped/concurrency tests fail, and removing lazy seed lookup makes the seed test fail.

- [ ] **Step 7: Run commit gates and commit**

Run the five repository gates in the required order. Then:

```bash
git add depin/_core/lazy_scope.py depin/_core/scope.py depin/_core/hosting.py depin/_core/frozen.py tests/unit/test_hosting.py tests/unit/test_scope_frame.py tests/unit/test_frozen_scoped.py
git commit -m 'feat: add lazy hosted request scopes'
```

### Task 2: FastAPI endpoint compiler and installation

**Files:**
- Create: `depin/ext/_fastapi.py`
- Modify: `depin/ext/fastapi.py`
- Modify: `depin/errors.py`
- Modify: `depin/__init__.py`
- Test: `tests/integration/test_fastapi_ext.py`
- Test: `tests/integration/test_fastapi_robustness.py`

**Interfaces:**
- Consumes: Task 1 `_lazy_host` and `_provide_lazy_seed`; FastAPI `APIRoute` dependency graph; existing `Inject[T]` and eager `RequestScope`.
- Produces: `install(app: FastAPI, container: FrozenContainer) -> None`; `FastAPIIntegrationError`; private `_InjectResolver[T]`; private immutable `_EndpointProgram`; contained `compile_route(route, container)` compatibility adapter; private lazy ASGI middleware.

- [ ] **Step 1: Write failing installation and single-program tests**

Build real apps, call `install` after route registration, and send requests through `httpx.ASGITransport`:

```python
@pytest.mark.asyncio
async def test_install_resolves_multiple_injections_through_one_program() -> None:
    events: list[str] = []

    class Shared:
        def __init__(self) -> None:
            events.append('shared')

    class Left:
        def __init__(self, shared: Shared) -> None:
            self.shared = shared

    class Right:
        def __init__(self, shared: Shared) -> None:
            self.shared = shared

    container = Container().bind(Shared, scope=Scope.SCOPED).bind(Left).bind(Right).freeze()
    app = FastAPI()

    @app.get('/value')
    async def value(left: Inject[Left], right: Inject[Right]) -> dict[str, bool]:
        return {'shared': left.shared is right.shared}

    install(app, container)
    response = await request(app, '/value')

    assert response.json() == {'shared': True}
    assert events == ['shared']
    route = next(route for route in app.routes if getattr(route, 'path', None) == '/value')
    assert [type(node.call).__name__ for node in route.dependant.dependencies].count('_EndpointProgram') == 1
    assert all(type(node.call).__name__ != '_InjectResolver' for node in route.dependant.dependencies)
```

Add a no-injection route whose route call target and dependency list remain identical before and after `install`. Add a warm-singleton route that observes zero lazy-frame openings through the Task 1 test hook.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/integration/test_fastapi_ext.py -k 'install or program or singleton' -vv
```

Expected: failure because `install` and compiled program inspection do not exist. Existing eager `RequestScope` tests remain green.

- [ ] **Step 3: Implement resolver identity, compiler, and middleware**

Use an immutable resolver instead of a closure:

```python
@dataclass(frozen=True, slots=True)
class _InjectResolver[T]:
    key: type[T] | Token[T]

    async def __call__(self, request: Request) -> T:
        _provide_lazy_seed(ScopeSeed(Request, request))
        container = optional_hosted_container()
        if container is None:
            raise ContainerNotBoundError(
                'Inject[...] resolved outside a hosted FastAPI request; call install(app, container) '
                'after route registration or install RequestScope compatibility middleware.'
            )
        return await container.aresolve(self.key)
```

`Inject.__class_getitem__` returns `Annotated[key, Depends(dependency=_InjectResolver(key))]`. `compile_route` recognizes only direct dependency nodes whose callable is `_InjectResolver`, preserves their parameter order, replaces them with one `_EndpointProgram` node, replaces the route call target with a wrapper that merges the program mapping, and rebuilds the route ASGI callable only after all structural probes pass.

The private ASGI middleware enters `_lazy_host` only for `http` and `websocket`, forwards lifespan untouched, supplies a metadata-only HTTP `Request` fallback lazily, and awaits the downstream app inside the host so response streaming, background tasks, and WebSockets complete before drain.

- [ ] **Step 4: Verify GREEN and compatibility**

Run:

```bash
uv run pytest tests/integration/test_fastapi_ext.py -q
uv run pytest tests/integration/test_fastapi_robustness.py -q
```

Expected: compiled tests pass and all existing eager-middleware tests remain green.

- [ ] **Step 5: Add failing idempotence and compatibility-boundary tests**

Cover same-container reinstall after adding a route, different-container reinstall, install after middleware stack creation, and a deliberately malformed route double. Assert `FastAPIIntegrationError` includes route/application state, installed FastAPI version, and `RequestScope` recovery. The malformed route must remain unchanged after the failed install.

- [ ] **Step 6: Verify RED, implement atomic setup, and re-run focused tests**

Run the new node IDs, implement atomic preflight followed by mutation, and re-run both FastAPI integration files. Confirm that removing the preflight causes the no-partial-mutation test to fail.

- [ ] **Step 7: Run commit gates and commit**

Run the five gates in order and the strict docs build because public docstrings and errors changed. Then:

```bash
git add depin/ext/_fastapi.py depin/ext/fastapi.py depin/errors.py depin/__init__.py tests/integration/test_fastapi_ext.py tests/integration/test_fastapi_robustness.py
git commit -m 'perf: compile FastAPI endpoint injection'
```

### Task 3: Lifecycle equivalence, typing, and user documentation

**Files:**
- Modify: `tests/integration/test_fastapi_ext.py`
- Modify: `tests/integration/test_fastapi_robustness.py`
- Modify: `tests/typing/test_conformance_fastapi.py`
- Modify: `tests/integration/test_conformance_coverage.py`
- Modify: `docs/guide/fastapi.md`
- Modify: `depin/ext/fastapi.py`

**Interfaces:**
- Consumes: Task 2 `install`, compiled endpoint program, eager `RequestScope`, and public error.
- Produces: behavior matrix proving optimized/compatibility equivalence; source-typing examples for `install`; migration and compatibility documentation.

- [ ] **Step 1: Add a failing optimized/compatibility equivalence matrix**

Parameterize a real-app builder over eager and optimized setup. Compare literal results for mixed native dependencies and request validation:

```python
@pytest.mark.parametrize('setup', [setup_compatibility, setup_optimized])
@pytest.mark.asyncio
async def test_mixed_fastapi_inputs_remain_equivalent(setup: Setup) -> None:
    app, events = mixed_application(setup)
    response = await post(app, '/users/7?active=true', json={'name': 'Ada'})

    assert response.status_code == 200
    assert response.json() == {'id': 7, 'active': True, 'name': 'Ada', 'tenant': 'acme'}
    assert events == ['dependency', 'provider', 'handler', 'close']


@pytest.mark.asyncio
async def test_optimized_openapi_and_validation_match_compatibility() -> None:
    compatibility = mixed_application(setup_compatibility)[0]
    optimized = mixed_application(setup_optimized)[0]

    assert optimized.openapi() == compatibility.openapi()
    assert await invalid_response(optimized) == await invalid_response(compatibility)
```

The expected dictionaries and event order are literals, not values computed by the application under test.

- [ ] **Step 2: Verify RED and close semantic gaps**

Run the new node IDs. Fix only optimized-path differences exposed by the tests, then run both FastAPI integration files.

- [ ] **Step 3: Add failure, stream, background, WebSocket, and concurrency cases**

Use real response streaming and WebSocket ASGI events. Cover handler error, provider error, response-stream error, cancellation, teardown error, body plus teardown `ExceptionGroup`, background task ordering, request identity, override isolation, and two concurrent scoped requests synchronized with `asyncio.Event`. Each case compares construction/closure logs with the eager path and asserts cleanup occurs after the last response/WebSocket event.

- [ ] **Step 4: Prove the lifecycle tests guard the implementation**

Run focused tests green. Temporarily bypass lazy drain or frame isolation and run the relevant focused test to observe failure; restore production code immediately and run it green again. Record both commands and outputs in the task report without committing the mutation.

- [ ] **Step 5: Extend typing and documentation**

Add source conformance that type-checks:

```python
app = FastAPI()
container = Container().bind(Service).freeze()


@app.get('/')
async def endpoint(service: Inject[Service]) -> str:
    return service.value


install(app, container)
```

The fixture must keep `service` inferred as `Service` across Basedpyright, mypy, Pyright, ty, and Pyrefly expectations. Update the FastAPI guide to show route registration followed by `install`, explain `RequestScope` compatibility, late route registration, the tested floor/latest policy, lazy request behavior, and unchanged streaming/WebSocket lifetime. Keep every `pycon` block executable.

- [ ] **Step 6: Run focused and full gates, then commit**

Run the typing-source checks named by the repository, the five commit gates in order, and strict MkDocs. Then:

```bash
git add tests/integration/test_fastapi_ext.py tests/integration/test_fastapi_robustness.py tests/typing/test_conformance_fastapi.py tests/integration/test_conformance_coverage.py docs/guide/fastapi.md depin/ext/fastapi.py
git commit -m 'docs: document optimized FastAPI setup'
```

### Task 4: Performance workloads and regression guards

**Files:**
- Create: `benchmarks/workloads/component/fastapi.py`
- Create: `tests/integration/test_fastapi_performance_contracts.py`
- Modify: `benchmarks/workloads/application/sync.py`
- Modify: `benchmarks/workloads/application/async_.py`
- Modify: `benchmarks/workloads/application/inventory.py`
- Modify: `benchmarks/workloads/application/measurement.py`
- Modify: `benchmarks/workloads/component/__init__.py`
- Modify: `benchmarks/leadership-targets.toml`
- Modify: `tests/integration/test_comparison_contracts.py`
- Modify: `tests/integration/test_comparison_collection.py`

**Interfaces:**
- Consumes: optimized `install`, existing six FastAPI application workloads, comparison protocol, deterministic observers, and authored leadership targets.
- Produces: optimized application deployment, `fastapi_no_injection` pair, component decomposition, semantic counters, and contract tests that reject benchmark drift.

- [ ] **Step 1: Write failing workload inventory and semantic tests**

Assert the exact application names include the new pair and that the depin builders use optimized setup while the direct builders remain hand-wired. Exercise every workload once and validate literal status/body/event counts before timing. Add component tests that observe zero frame opens for no-injection and singleton cases, one frame for scoped/resource cases, one endpoint program call, and exact teardown counts.

- [ ] **Step 2: Verify RED**

Run:

```bash
uv run pytest tests/integration/test_fastapi_performance_contracts.py tests/integration/test_comparison_contracts.py tests/integration/test_comparison_collection.py -vv
```

Expected: failures name the missing no-injection and component workloads.

- [ ] **Step 3: Implement the minimum benchmark changes**

Move every depin FastAPI deployment to route-registration-then-`install`. Add a no-injection deployment whose route response is identical on both sides. Add component claims for lazy publication, first activation/drain, one-key and multi-key endpoint programs, request seed read, and async resource close. Reuse the existing measurement functions and deterministic observer; do not create a parallel harness.

Author a leadership target for `fastapi_no_injection` using the repository target model and a calibrated fraction/fixed floor justified by the null run. Do not edit `benchmarks/budgets.toml` by hand.

- [ ] **Step 4: Verify GREEN and run a quick diagnostic**

Run the focused tests, then collect a short local diagnostic for the CPU-light, no-injection, request-scoped, resource, and startup cases. The diagnostic is not acceptance evidence; it only decides whether implementation work should continue before the full five-repetition run.

Expected: CPU-light DI-attributable p50 point estimate improves by at least 25%, no-injection stays inside noise, and semantic counters match. If not, invoke systematic debugging, attribute the remaining time to endpoint traversal, host publication, activation, resolution, or teardown, and make a new failing performance-contract test before changing production code.

- [ ] **Step 5: Run commit gates and commit**

Run the five gates in order. Then:

```bash
git add benchmarks/workloads/component/fastapi.py benchmarks/workloads/application/sync.py benchmarks/workloads/application/async_.py benchmarks/workloads/application/inventory.py benchmarks/workloads/application/measurement.py benchmarks/workloads/component/__init__.py benchmarks/leadership-targets.toml tests/integration/test_fastapi_performance_contracts.py tests/integration/test_comparison_contracts.py tests/integration/test_comparison_collection.py
git commit -m 'perf: measure optimized FastAPI integration'
```

### Task 5: Accepted before/after evidence and closure

**Files:**
- Create: `benchmarks/results/2026-09-09-fastapi-minimum-overhead/environment.json`
- Create: `benchmarks/results/2026-09-09-fastapi-minimum-overhead/base/`
- Create: `benchmarks/results/2026-09-09-fastapi-minimum-overhead/head/`
- Create: `benchmarks/results/2026-09-09-fastapi-minimum-overhead/report.md`
- Create: `benchmarks/results/2026-09-09-fastapi-minimum-overhead/gate.txt`
- Create: `benchmarks/results/2026-09-09-fastapi-minimum-overhead/analysis.md`
- Modify: `docs/performance/comparison-baseline.md`
- Modify: `specs/proposals/2026-09-02-fastapi-minimum-overhead-proposal.md`
- Modify: `specs/roadmap.md`

**Interfaces:**
- Consumes: baseline SHA `086adf98459773e3175f4723b2b64e3f47306e42`, Task 4 workloads, paired harness, gate, accepted 2026-09-09 evidence.
- Produces: five-repetition counterbalanced raw evidence, generated report, explicit gate output, concise before/after analysis, and updated active-decision documents.

- [ ] **Step 1: Materialize an isolated baseline checkout and locked environments**

Create a detached benchmark-only worktree outside the feature worktree at the exact baseline SHA. Synchronize baseline and head with:

```bash
uv sync --locked --no-default-groups --group bench
```

Record both full SHAs, package pins, interpreter, CPU, kernel, governor, affinity, harness revision, and collection command in the result environment. Do not reuse the feature `.venv` for the baseline.

- [ ] **Step 2: Collect five counterbalanced repetitions**

Use `benchmarks.harness.pairs` with base/head directories, baseline revision `086adf9`, identical workload filters, and five alternating independent processes. Include the six existing FastAPI workloads and all common core guards. Collect the new no-injection and component workloads separately on head with their direct/null baselines because they do not exist at the baseline revision.

Expected: every repetition validates payloads, event counts, teardown, and deterministic invariants before retaining timing samples.

- [ ] **Step 3: Generate and run the gates**

Generate `report.md` from the raw pair directories and run `benchmarks.harness.gate` against the accepted baseline and current authored targets. Capture stdout in `gate.txt`. Run the comparison leadership report for current FastAPI competitors without changing semantic classifications.

Acceptance requires the paired CPU-light DI-attributable p50 confidence bound, tail totals, no-injection noise, memory, allocations, startup, contention, and all existing core budgets to satisfy the Global Constraints. A failed performance gate returns to the smallest owning task with a falsifiable attribution; do not weaken a target or edit generated budgets to make it pass.

- [ ] **Step 4: Write the before/after analysis**

`analysis.md` must contain:

- the exact base/head revisions and environment;
- baseline and head p50/p95/p99 totals for every FastAPI workload;
- paired direct-baseline increments and 95% confidence intervals;
- CPU, throughput, allocation, peak/retained memory, startup, and contention deltas;
- decomposition of endpoint traversal, host publication, lazy activation, core resolution, and teardown;
- semantic-equivalence checks and unsupported comparisons;
- the 25% gate verdict and 30% stretch verdict; and
- any measured trade-off, even when inside budget.

Update the published comparison page from generated evidence. Mark the proposal implemented only after the gate passes and route the roadmap to the next already-accepted item without activating provider discovery or native acceleration in this change.

- [ ] **Step 5: Remove benchmark-only workspace and run final gates**

Remove only the detached baseline worktree created in Step 1 after all raw evidence is safely inside the feature branch. Run:

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Also run the benchmark gate directly from the committed result directory and both lowest-direct and latest supported FastAPI/Starlette integration matrices.

- [ ] **Step 6: Commit evidence and decision updates**

```bash
git add benchmarks/results/2026-09-09-fastapi-minimum-overhead docs/performance/comparison-baseline.md specs/proposals/2026-09-02-fastapi-minimum-overhead-proposal.md specs/roadmap.md
git commit -m 'perf: reduce FastAPI integration overhead'
```

The branch is ready for final whole-branch review only after this commit's fresh verification evidence and benchmark gate are recorded.
