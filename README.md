# depin

[![CI](https://github.com/andrelopes-code/depin/actions/workflows/ci.yml/badge.svg)](https://github.com/andrelopes-code/depin/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pydepin.svg)](https://pypi.org/project/pydepin/)
[![Python versions](https://img.shields.io/pypi/pyversions/pydepin.svg)](https://pypi.org/project/pydepin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/andrelopes-code/depin/blob/main/LICENSE)

Type-first dependency-injection for Python 3.12+.

- Resolution driven by type hints; `Protocol` and `Annotated` are first-class.
- Build-time validation: `Container.freeze()` catches missing providers, cycles, lifetime violations (a singleton that would capture a scoped provider), and async/sync mismatches before anything runs.
- Full async/sync coverage: classes, sync/async factories, generators, async generators, `@(a)contextmanager`, instance context managers.
- Optional FastAPI integration in `depin.ext.fastapi`. **Core has zero runtime dependencies.**

## Install

```bash
uv add pydepin                # core
uv add 'pydepin[fastapi]'     # with FastAPI integration
```

Requires Python 3.12+.

## Quickstart

```python
from typing import Annotated

from depin import Container, Scope, Token

db_url = Token[str]('db.url')


class Database:
    def __init__(self, url: str) -> None:
        self.url = url


def make_db(url: Annotated[str, db_url]) -> Database:
    return Database(url)


class UserRepo:
    def __init__(self, db: Database) -> None:
        self.db = db


di = (
    Container()
    .value(db_url, 'postgres://...')
    .bind(make_db, scope=Scope.SINGLETON, provides=Database)
    .bind(UserRepo, scope=Scope.SINGLETON)
    .freeze()
)

repo = di[UserRepo]
```

## Cookbook

See `examples/` for runnable code. Highlights:

- **Tokens** for values: `Token[str]('db.url')`, resolved via `di[token]`.
- **Generator providers** for lifecycle: `def session() -> Generator[Session]: ...` with `yield`; teardown runs on scope exit.
- **Async generators** + `async with di.ascope(): ...` for per-request DB sessions.
- **Tag** + `provides` for multiple implementations of a `Protocol`.
- **Override** for tests: `with di.override(Database, with_=FakeDB()): ...`.
- **Frame-provided values** (`di.frame_provides(Request)`) for middleware-injected context.
- **Function injection** with `@frozen.inject`: parameters whose default is `injected(...)` are filled from the container, the rest are passed by the caller:

  ```python
  @di.inject
  def handler(uid: int, repo: UserRepo = injected(UserRepo)) -> User:
      return repo.get(uid)

  handler(uid=1)  # repo injected; call site stays type-clean
  ```

  Use `injected(Token[...])` for token values and `injected(Svc, tag='...')` for tagged providers.

## FastAPI

```python
from fastapi import FastAPI
from depin import Container, Scope
from depin.ext.fastapi import RequestScope, Inject

di = (
    Container()
    .bind(UserService, scope=Scope.SCOPED)
    .freeze()
)

app = FastAPI()
app.add_middleware(RequestScope, container=di)


@app.get('/users/{uid}')
async def get_user(uid: int, svc: Inject[UserService]):
    return await svc.get(uid)
```

`Inject[T]` is a type-level shortcut: the parameter's static type is `T`, while
at runtime `Inject[T]` resolves to `Annotated[T, Depends(...)]` so FastAPI picks
up the dependency from the parameter's annotation. No default-value calls, no
`# noqa: B008` waivers, no extra imports.

`RequestScope` runs as pure ASGI middleware, so streaming responses, SSE, and
WebSockets pass through unbuffered. Scoped providers may declare `Request` to
read headers, URL, cookies, and state — but it is metadata-only: the request
body belongs to the route's typed parameters, and reading it from a provider
raises rather than racing the handler's own parsing.

## Caveats

- **Lifecycle teardown.** Singleton providers that use `yield` / context managers
  are torn down by `await frozen.aclose()`. Call it on app shutdown; scope-local
  providers are drained automatically when their `scope()` / `ascope()` block exits.
- **Nested scopes inherit.** A `SCOPED` instance resolved in an outer scope is
  reused inside a nested scope, not rebuilt. Open sibling scopes for independent
  instances.
- **`@frozen.inject` uses default-position markers.** An injected parameter
  carries an `injected(...)` default, so it must follow non-default parameters or
  be keyword-only (a normal Python rule). The marker keeps call sites type-clean —
  no `# pyright: ignore` needed. Unlike provider constructors, which resolve from
  type hints and `Annotated[...]`, `@inject` fills *only* marked parameters and
  validates them at decoration time, raising `MissingProviderError` immediately if
  a marked key is unregistered.

## Status

v0.2.0 is a clean break from 0.1.x. The migration is breaking; older code will not run unchanged.

| 0.1.x | 0.2.0 |
| --- | --- |
| `Container()` resolves directly | `Container().freeze() -> FrozenContainer` |
| `Inject(fn)` default value | `svc: T = injected(T)` under `@frozen.inject`, or `Inject[T]` (fastapi ext) |
| `Container.Depends(X)` | `frozen[X]`, `frozen.resolve(X)`, or `Inject[T]` (fastapi ext) |
| `Scope.REQUEST` | `Scope.SCOPED` |
| `RequestScopeService.request_scope()` | `frozen.scope()` / `frozen.ascope()` |

## Development

```bash
uv sync --all-extras
uv run ruff format
uv run ruff check
uv run basedpyright
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow and
[CLAUDE.md](CLAUDE.md) for repository conventions.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup, the four gates, and commit conventions; all participants are
expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). To report a
vulnerability, follow the [security policy](SECURITY.md).

## License

[MIT](LICENSE) © André Lopes
