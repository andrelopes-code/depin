# depin

Type-first dependency-injection for Python 3.12+.

- Resolution driven by type hints; `Protocol` and `Annotated` are first-class.
- Build-time validation: `Container.freeze()` catches missing providers, cycles, and async/sync mismatches before anything runs.
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

## FastAPI

```python
from typing import Annotated

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
async def get_user(uid: int, svc: Annotated[UserService, Inject(UserService)]):
    return await svc.get(uid)
```

`Inject(T)` is used inside :class:`typing.Annotated`, which is FastAPI's modern
dependency-injection style. The call sits in an annotation, so ruff's B008
(function call in default value) never fires and no per-line waivers are needed.

## Status

v0.2.0 is a clean break from 0.1.x. The migration is breaking; older code will not run unchanged.

| 0.1.x | 0.2.0 |
| --- | --- |
| `Container()` resolves directly | `Container().freeze() -> FrozenContainer` |
| `Inject(fn)` default value | `@frozen.inject` decorator or `Annotated[T, Inject(T)]` (fastapi ext) |
| `Container.Depends(X)` | `frozen[X]`, `frozen.resolve(X)`, or `Annotated[T, Inject(T)]` (fastapi ext) |
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

See `CLAUDE.md` for repository conventions.
