# depin v2 — Design

**Status:** Draft · 2026-04-16
**Supersedes:** v1 (0.1.x). Breaking API changes are expected.

---

## 1. Goals & non-goals

### Goals

- **Type-first**: resolution driven by type hints. `Protocol` is a first-class abstraction. Inference gives the developer the correct return type everywhere — no `# type: ignore` needed at call sites.
- **Pythonic DX**: decorators where ergonomic (`@di.singleton()`), explicit builder where decoupling is desired (`Container().bind(...)`). No global container, no magic descriptors, no module scanning as default.
- **Full async/sync parity**: every provider shape supported — plain class, sync/async function, sync/async generator, `@contextmanager`/`@asynccontextmanager`, objects with `__enter__`/`__aenter__`.
- **Build-time validation**: `Container.freeze()` returns an immutable `FrozenContainer` after validating the entire dependency graph. Missing providers, cycles, and async-in-sync mismatches are caught at boot, not on the first request.
- **First-class FastAPI integration** as an optional extension — core has **zero runtime dependencies**.
- **Professional packaging**: strict `basedpyright`, `uv`-managed, high test coverage on the core, example applications.

### Non-goals (v2)

- Lazy proxies for breaking init-time cycles (`scoped` already covers most real cases).
- Multibind / plugin-list providers.
- User-named custom scopes beyond `singleton`/`scoped`/`transient`.
- Observability hooks (`on_resolve` / `on_teardown`).
- Thread-safety guarantees beyond asyncio task isolation (asyncio is single-threaded; if a user puts a container behind threads, singletons are `dict`-protected only).
- Module scanning as the recommended registration path (available as an opt-in utility).

---

## 2. Public API surface

Everything the user imports lives under `depin` (core) and `depin.ext.<framework>` (integrations).

```python
from depin import (
    Container,          # mutable builder
    FrozenContainer,    # the resolver (result of Container.freeze())
    Registry,           # decorator-populated provider collection
    Scope,              # enum: SINGLETON | SCOPED | TRANSIENT
    Token,              # Token[T] — typed nominal key for values
    Inject,             # Annotated marker: Annotated[T, Inject(factory)]
    Named,              # Annotated marker: Annotated[T, Named(token_or_key)]
    Tag,                # Annotated marker: Annotated[T, Tag("primary")]
    provides,           # decorator: attaches "provides=X" metadata to a factory
)
from depin.errors import (
    DepinError,
    MissingProviderError,
    CircularDependencyError,
    AsyncInSyncContextError,
    OutsideScopeError,
    AlreadyFrozenError,
    DuplicateProviderError,
)
```

### 2.1 Scopes

```python
class Scope(Enum):
    SINGLETON = "singleton"   # one per container lifetime
    SCOPED    = "scoped"      # one per active scope frame (e.g. per HTTP request)
    TRANSIENT = "transient"   # new on every resolution
```

### 2.2 Tokens (values / primitives)

```python
class Token[T]:
    def __init__(self, name: str) -> None: ...
    # __hash__/__eq__ identity-based — two tokens with same name are DIFFERENT keys.
```

`Token[T]` is the only way to bind primitives and configs. Eliminates `Named("string")` used against bare `str`.

### 2.3 `Container` (mutable builder)

```python
class Container:
    def bind[T](
        self,
        source: type[T] | Callable[..., T] | Callable[..., Awaitable[T]]
              | Callable[..., Iterator[T]] | Callable[..., AsyncIterator[T]],
        *,
        scope: Scope = Scope.SINGLETON,
        provides: type[T] | None = None,
        tag: str | None = None,
    ) -> Self: ...

    def value[T](self, token: Token[T], value: T) -> Self: ...

    # decorator shortcuts — equivalent to .bind(source, scope=...)
    def singleton[T](self, *, provides: type | None = None, tag: str | None = None) -> Callable[[T], T]: ...
    def scoped[T]   (self, *, provides: type | None = None, tag: str | None = None) -> Callable[[T], T]: ...
    def transient[T](self, *, provides: type | None = None, tag: str | None = None) -> Callable[[T], T]: ...

    @classmethod
    def from_(cls, *registries: Registry) -> Self: ...

    def merge(self, other: Container | Registry) -> Self: ...

    def freeze(self) -> FrozenContainer: ...  # validates graph, returns immutable resolver
```

`Container` is **write-only**: no `.resolve`, no `__getitem__`. Resolution is a static type error until `freeze()` is called.

### 2.4 `Registry` (decorator target, decoupled from Container)

```python
class Registry:
    def __init__(self, name: str = "") -> None: ...

    def bind[T](self, source: ..., *, scope: Scope = ..., provides: ... = None, tag: ... = None) -> Self: ...
    def value[T](self, token: Token[T], value: T) -> Self: ...

    def singleton[T](self, *, provides=None, tag=None) -> Callable[[T], T]: ...
    def scoped[T]   (self, *, provides=None, tag=None) -> Callable[[T], T]: ...
    def transient[T](self, *, provides=None, tag=None) -> Callable[[T], T]: ...

    def __or__(self, other: Registry) -> Registry: ...  # merge (last-wins on conflict)
```

Registries are composable and mergeable. `Container.from_(a, b, c)` is sugar for `Container().merge(a).merge(b).merge(c)`.

### 2.5 `FrozenContainer` (the resolver)

```python
class FrozenContainer:
    @overload
    def __getitem__[T](self, key: type[T]) -> T: ...
    @overload
    def __getitem__[T](self, key: Token[T]) -> T: ...
    def __getitem__(self, key): ...

    def resolve[T] (self, key: type[T] | Token[T]) -> T: ...
    async def aresolve[T](self, key: type[T] | Token[T]) -> T: ...

    def inject[**P, R](self, fn: Callable[P, R]) -> Callable[P, R]: ...
    # works for both sync and async functions.

    def scope (self) -> AbstractContextManager[ScopeFrame]: ...
    def ascope(self) -> AbstractAsyncContextManager[ScopeFrame]: ...

    def override(self, key: type | Token, *, with_: Any) -> AbstractContextManager[Self]: ...

    async def aclose(self) -> None: ...
    # tears down all singleton context managers in LIFO order; aggregates errors in ExceptionGroup.
```

### 2.6 Markers

All markers live in `Annotated[T, ...]`. No more `Inject(...)` as a default value.

```python
# Annotated[T, Inject(factory)] — use this provider instead of the type binding.
class Inject:
    def __init__(self, factory: Callable[..., Any]) -> None: ...

# Annotated[T, Named(token)] — legacy/alternative form for Token lookup (prefer the Token itself as the key in Annotated).
class Named:
    def __init__(self, key: Token[Any] | str) -> None: ...

# Annotated[T, Tag("primary")] — disambiguates when multiple providers bind to the same type.
class Tag:
    def __init__(self, name: str) -> None: ...
```

**Preferred Token-in-Annotated form** (fewest concepts):

```python
db_url = Token[str]("db.url")

def make_pool(url: Annotated[str, db_url]) -> Pool: ...
```

The container treats `Token[T]` instances in `Annotated[...]` metadata as a direct key. `Named(token)` is redundant in this case and exists only for forwards-compatibility.

### 2.7 `provides` decorator

For decoupling the **domain** class from any container/registry instance:

```python
from depin import provides

@provides(Logger)
class StdLogger:
    def log(self, msg: str) -> None: print(msg)

# in bootstrap
DI = Container().bind(StdLogger, scope=Scope.SINGLETON).freeze()
# binding auto-registers `Logger -> StdLogger` because StdLogger carries the @provides metadata.
```

---

## 3. Cookbook — every supported shape

### 3.1 Classes

```python
@di.singleton()
class Config: ...

@di.scoped(provides=Logger)
class RequestLogger: ...

@di.transient()
class TempBuffer: ...
```

### 3.2 Factories

```python
@di.singleton()
def make_http(cfg: Config) -> HttpClient:
    return HttpClient(cfg.base_url)

@di.singleton()
async def make_db(cfg: Config) -> Database:
    return await Database.connect(cfg.url)
```

### 3.3 Generators (setup + teardown)

```python
@di.scoped()
async def db_session(engine: Engine) -> AsyncIterator[Session]:
    async with engine.begin() as s:
        yield s
    # runs after the scope ends, reverse order

@di.scoped()
def temp_dir() -> Iterator[Path]:
    d = Path(tempfile.mkdtemp())
    try:
        yield d
    finally:
        shutil.rmtree(d)
```

Generators in `singleton` are also allowed; teardown runs during `await di.aclose()`.
Generators in `transient` raise `ValueError` at bind time (no teardown opportunity).

### 3.4 Context managers

```python
@asynccontextmanager
async def redis_pool(cfg: Config):
    pool = await Redis.from_url(cfg.url)
    try:
        yield pool
    finally:
        await pool.close()

container.bind(redis_pool, scope=Scope.SINGLETON, provides=Redis)
```

Classes implementing `__(a)enter__ / __(a)exit__`:

```python
@di.scoped()
class Transaction:
    async def __aenter__(self): self._tx = await begin_tx(); return self
    async def __aexit__(self, *exc): await self._tx.close()
```

The container calls `__enter__` / `__aenter__` after construction and stores the exit in the scope frame.

### 3.5 Tokens & overrides

```python
db_url = Token[str]("db.url")
max_conn = Token[int]("db.max_conn")

container.value(db_url, "postgres://...").value(max_conn, 50)

with frozen.override(db_url, with_="sqlite:///:memory:"):
    test_db = frozen[Database]
```

### 3.6 Tags for multiple implementations

```python
class Cache(Protocol): ...

@di.singleton(provides=Cache, tag="primary")
class Redis: ...

@di.singleton(provides=Cache, tag="fallback")
class InMem: ...

@di.scoped()
class Svc:
    def __init__(
        self,
        primary:  Annotated[Cache, Tag("primary")],
        fallback: Annotated[Cache, Tag("fallback")],
    ): ...
```

### 3.7 Handler wiring

```python
@frozen.inject
async def use_case(repo: UserRepo, log: Logger, uid: int) -> User: ...
```

`uid` has no provider → passed through as a regular argument.

---

## 4. Architecture

### 4.1 Module layout

```
depin/
  __init__.py               # public re-exports
  errors.py                 # exception hierarchy
  _core/
    __init__.py
    markers.py              # Inject, Named, Tag, Token, provides
    scope.py                # Scope enum, ScopeFrame, ContextVar management
    spec.py                 # ProviderSpec, ResolutionPlan dataclasses
    introspect.py           # cached signature/type-hint extraction, shape detection
    registry.py             # Registry
    container.py            # Container (mutable)
    resolver.py             # dependency-graph builder + validator
    frozen.py               # FrozenContainer (resolver runtime)
  ext/
    __init__.py
    fastapi.py              # RequestScope middleware, Inject wrapper
examples/
  minimal_sync/             # plain sync app with Container + freeze
  fastapi_app/              # registries, multiple modules, FastAPI wiring
tests/
  depin/
    unit/
      test_markers.py
      test_registry.py
      test_container.py
      test_resolver.py       # graph builder edges/cycles
      test_frozen_*.py       # one file per scope
      test_generators.py
      test_context_managers.py
      test_overrides.py
      test_aclose.py
      test_errors.py         # exception messages & paths
    integration/
      test_fastapi_ext.py
  conftest.py
```

> Internal design notes and implementation plans live under `docs/` in this repo. The shipped distribution contains code, tests, examples and the user-facing `README.md`.

### 4.2 Core data structures

```python
@dataclass(frozen=True, slots=True)
class ProviderSpec[T]:
    key: type[T] | Token[T]                  # primary lookup key
    tag: str | None
    source: Callable[..., Any] | type
    scope: Scope
    shape: ProviderShape                     # CLASS | FUNCTION | ASYNC_FN | GEN | ASYNC_GEN | CM | ACM | VALUE
    needs_async: bool                        # precomputed at freeze
    params: tuple[ParamSpec, ...]            # resolved dependencies

@dataclass(frozen=True, slots=True)
class ParamSpec:
    name: str
    key: type | Token                        # resolved lookup key
    tag: str | None
    has_default: bool
    default: Any

@dataclass(frozen=True, slots=True)
class ResolutionPlan:
    order: tuple[ProviderSpec, ...]          # topological
    by_key: Mapping[tuple[type | Token, str | None], ProviderSpec]
```

`FrozenContainer` holds a `ResolutionPlan` plus a singleton cache `dict[ProviderSpec, Any]` and a registry of cleanup callbacks.

### 4.3 Resolution algorithm

**At freeze():**

1. Merge all registrations into a flat `list[ProviderSpec]`.
2. For each class/function provider: introspect `__init__`/signature, walk parameter annotations, produce `ParamSpec` for each. `Annotated[T, ...]` metadata is scanned for `Token`, `Inject`, `Named`, `Tag`; the first present wins in that order.
3. Build the dependency graph (nodes = keys, edges = deps). Toposort. Cycles in **singleton/transient** → `CircularDependencyError` with the full path. Cycles in `scoped` chains are still errors (v2 has no lazy-proxy escape hatch).
4. Compute `needs_async` bottom-up: a spec is async if it itself is async OR any transitive dep is async.
5. Validate: for every spec, confirm each `ParamSpec.key` is registered OR `has_default` is true. Missing → `MissingProviderError` with the call chain.
6. Reject: sync provider chain that transitively needs async → `AsyncInSyncContextError` at freeze (not at first resolution).
7. Reject: generator/CM in `TRANSIENT` scope → `ValueError` at bind time (not freeze).
8. Emit `FrozenContainer(plan)`.

**At resolve(key):**

1. Look up `ProviderSpec` by `(key, tag)` (tag defaults to `None`).
2. By scope:
   - `SINGLETON`: check `self._singletons`; if miss, construct, cache, register any teardown in the root cleanup stack.
   - `SCOPED`: fetch current `ScopeFrame` via `ContextVar`; check its cache; if miss, construct and register teardown in the frame.
   - `TRANSIENT`: construct and return.
3. Construction = resolve each dep recursively → call source with kwargs → enter CM / awaiten coroutine as needed.
4. Sync `resolve` raises if any dep is async (`AsyncInSyncContextError`).

### 4.4 Scopes

- `ScopeFrame` holds: `instances: dict[ProviderSpec, Any]` and `teardowns: list[AsyncExitStack | ExitStack entry]`.
- A `ContextVar[ScopeFrame | None]` tracks the active frame. `scope()` / `ascope()` push and pop.
- Nested scopes: inner frame is a child of outer; lookup searches child first, then parent. Scoped bindings from outer still use outer's cache; this lets nested request-like scopes share a session if desired.
- `FrozenContainer` itself also acts as the **root** ScopeFrame for singletons.

### 4.5 Async/sync handling

- `iscoroutinefunction`, `isasyncgenfunction`, `isgeneratorfunction`, `hasattr(obj, '__aenter__')` detect shape at bind time.
- `needs_async` is a graph property, memoized per spec at freeze time.
- `FrozenContainer[X]` (sync subscript) raises `AsyncInSyncContextError` *at freeze* if the graph is async — users find out before writing any runtime code.
- `aresolve` works for sync and async graphs uniformly.

### 4.6 Overrides

```python
def override[T](self, key: type[T] | Token[T], *, with_: T | Callable[..., T]) -> AbstractContextManager[Self]: ...
```

- Pushes a per-task `ContextVar` frame of `dict[key, override]`.
- `resolve()` checks overrides before the regular plan.
- Nests cleanly (task-safe). No mutation of the `FrozenContainer`.
- `with_` may be a value, an instance, or a callable (a replacement provider).

### 4.7 Teardown (`aclose`)

- Singletons that are generators / context managers are unwound LIFO.
- Each teardown is awaited (or called sync if plain CM) in its own `try` block.
- Exceptions are collected. After all teardowns run, if any failed, raise `ExceptionGroup("depin teardown errors", [...])`.
- This is the **opposite** of v1's silent `except Exception: pass` — exceptions during teardown are surfaced, never swallowed.

---

## 5. Error ergonomics

All errors inherit `DepinError(Exception)`. Every message includes:

- The **key** that failed to resolve.
- The **chain** leading to that key (caller → callee → ...).
- A concrete **suggestion** when possible.

Example:

```
MissingProviderError: No provider for Database.

Resolution chain:
  UserService         (scoped)      — myapp/services/user.py:12
  └─ UserRepo         (scoped)      — myapp/repos/user.py:8
     └─ Database      (missing!)

Suggestion: did you forget to register Database? Candidates in this codebase:
  - myapp.infra.db.PgDatabase   (has @provides(Database))
Import myapp.infra.db or add it to your Registry.
```

Candidates are discovered by scanning already-imported modules at `freeze()` time for classes carrying `@provides(Database)` metadata.

---

## 6. Type-system usage

- **PEP 695** generics (`class X[T]: ...`, `def f[T](x: T) -> T: ...`) are used throughout (requires Python 3.12+).
- `Annotated[T, ...]` metadata is the extension point; marker types are plain classes with `__class_getitem__` when useful.
- `FrozenContainer.__getitem__` uses `@overload` pair to preserve precise return types for both `type[T]` and `Token[T]`.
- Decorators return the class/function **unchanged** (never a wrapper that would lose typing) — they only register side effects.
- `@frozen.inject` uses `ParamSpec`/`Concatenate` pattern to preserve the decorated function's signature.
- `basedpyright` strict mode is enforced with minimal waivers (the few `cast`s live in `_core/introspect.py` where runtime introspection fundamentally cannot be typed).

### 6.1 Developer-facing signatures (illustrative)

```python
class FrozenContainer:
    @overload
    def __getitem__[T](self, key: type[T]) -> T: ...
    @overload
    def __getitem__[T](self, key: Token[T]) -> T: ...

    def resolve[T]  (self, key: type[T] | Token[T]) -> T: ...
    async def aresolve[T](self, key: type[T] | Token[T]) -> T: ...

    def inject[**P, R](self, fn: Callable[P, R]) -> Callable[P, R]: ...
```

### 6.2 Registration signatures (illustrative)

```python
class Container:
    @overload
    def bind[T](self, source: type[T], *,
                scope: Scope = ..., provides: type[T] | None = None, tag: str | None = None) -> Self: ...
    @overload
    def bind[T](self, source: Callable[..., T] | Callable[..., Awaitable[T]]
                    | Callable[..., Iterator[T]] | Callable[..., AsyncIterator[T]],
                *, scope: Scope = ..., provides: type[T] | None = None, tag: str | None = None) -> Self: ...
```

---

## 7. FastAPI extension

`depin.ext.fastapi` is the only place that imports `fastapi`. Core has **zero** runtime deps.

### 7.1 Public surface

```python
from depin.ext.fastapi import RequestScope, Inject

app.add_middleware(RequestScope, container=frozen)

@app.get("/users/{uid}")
async def get_user(uid: int, svc: UserService = Inject(UserService)) -> User:
    return await svc.get(uid)
```

- `RequestScope` middleware opens `frozen.ascope()` per request and places the current `fastapi.Request` into the scope frame (so scoped providers may accept a `Request` parameter).
- `Inject(T)` returns a real `fastapi.Depends` bound to an async resolver that calls `frozen.aresolve(T)`. Its return type is typed as `T` so the parameter annotation stays precise.
- `Inject` accepts `type[T]`, `Token[T]`, or `(type[T], tag)`.

### 7.2 Why default-value instead of pure `Annotated[T, Inject]`

FastAPI recognises `Depends` as a default value or as metadata. Making `Annotated[T, Inject]` work without repeating the type would require scanning/rewriting every route signature, which is fragile. The `svc: UserService = Inject(UserService)` form is:

- One line, unambiguous, FastAPI-native (no framework magic).
- Fully typed — `Inject(T)` at type-level is `T` (exactly the parameter type), so there is no `# type: ignore` at any call site.
- Symmetric with FastAPI's own `svc: UserService = Depends(UserService)`.

This side-steps v1's main issue: there, `Inject(fn)` returned an opaque sentinel typed as the parameter type via `# type: ignore[return-value]`. In v2, `Inject(T)` is honest: it genuinely returns a `Depends`-like object typed to behave as `T` in the handler signature.

### 7.3 Request as a scoped dependency

```python
registry.bind(
    source=lambda req: req,
    provides=fastapi.Request,
    scope=Scope.SCOPED,
)
```

The `RequestScope` middleware places the current `Request` into the scope frame keyed by `fastapi.Request`, so any provider with a `request: Request` parameter receives it automatically.

---

## 8. Packaging & tooling

### 8.1 `pyproject.toml`

- `requires-python = ">=3.12"` (PEP 695 generics).
- **Core dependencies: none.**
- `[project.optional-dependencies]`:
  - `fastapi = ["fastapi>=0.110"]`
  - `dev = ["pytest", "pytest-asyncio", "pytest-cov", "basedpyright", "ruff", "uv"]`
- Build backend: `hatchling` (simpler than setuptools for pure-Python).
- `basedpyright` configured under `[tool.basedpyright]`; the separate `pyrightconfig.json` is removed — single source of truth.

### 8.2 `basedpyright`

- `typeCheckingMode = "strict"`.
- Waivers confined to `_core/introspect.py` (runtime reflection).
- `reportAny`, `reportExplicitAny`, `reportUnknown*` re-enabled where possible (v1 disabled many).

### 8.3 `uv`

- `uv` as the canonical package manager. `uv.lock` committed.
- `Makefile`/`justfile` with `test`, `type`, `lint`, `fmt`, `cov` targets.

### 8.4 `ruff`

- Line length 120, single quotes, import sorting.
- Lint set: `E`, `F`, `W`, `I`, `B`, `UP`, `SIM`, `RUF`, `PT`.

### 8.5 Documentation

- `README.md` is the user-facing doc: installation, quickstart, cookbook, FastAPI section, migration table.
- Internal design documents and implementation plans live under `docs/` (this file, `docs/v2-implementation-plan.md`, future ADRs). They are versioned with the source but excluded from sdist/wheel via Hatch's default packaging — only the `depin` package and `README.md` ship.

---

## 9. Testing strategy

- **Core coverage target: ≥ 95%.**
- One test file per public surface (`test_container.py`, `test_frozen_singleton.py`, etc.).
- Property tests for the graph validator (`hypothesis` optional dev dep): random DAGs, ensure no false cycle/missing errors.
- Integration test suite under `tests/depin/integration/` exercises the FastAPI extension end-to-end with a real `httpx.AsyncClient`.
- **No** mocks for the container — every test uses real `Container`/`FrozenContainer`.

---

## 10. Examples

Two examples ship with the repo:

1. `examples/minimal_sync/` — 40 lines, single file, no async, no FastAPI. Demonstrates `Container`, `bind`, `freeze`, `FrozenContainer[T]`.
2. `examples/fastapi_app/` — multi-module app using `Registry` per layer (`infra`, `services`, `handlers`), async DB sessions with generator teardown, overrides in a test, full `RequestScope` wiring.

---

## 11. Migration notes (v1 → v2)

Breaking changes are embraced; a short migration table ships in `README.md`:

| v1 | v2 |
| --- | --- |
| `Container()` (resolvable) | `Container().freeze()` |
| `Container.inject` as method | `FrozenContainer.inject` |
| `Inject(fn)` as default value | `Annotated[T, Inject(fn)]` |
| `Container.Depends(X)` | `Annotated[X, Depends]` + `RequestScope` middleware |
| `Scope.SINGLETON/TRANSIENT/REQUEST` | `Scope.SINGLETON/TRANSIENT/SCOPED` |
| `RequestScopeService.request_scope()` | `frozen.scope()` / `frozen.ascope()` |

No compatibility shims.

---

## 12. Rollout

This document is the single source of truth for the v2 design. The implementation is tracked in `docs/v2-implementation-plan.md`, broken into reviewable stages (core scaffold → markers & registry → container & resolver → frozen runtime → scopes & teardown → fastapi ext → examples → docs).
