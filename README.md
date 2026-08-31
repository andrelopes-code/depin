# depin

[![CI](https://github.com/andrelopes-code/depin/actions/workflows/ci.yml/badge.svg)](https://github.com/andrelopes-code/depin/actions/workflows/ci.yml)
[![Docs](https://github.com/andrelopes-code/depin/actions/workflows/docs.yml/badge.svg)](https://andrelopes-code.github.io/depin/)
[![PyPI](https://img.shields.io/pypi/v/pydepin.svg)](https://pypi.org/project/pydepin/)
[![Python versions](https://img.shields.io/pypi/pyversions/pydepin.svg)](https://pypi.org/project/pydepin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/andrelopes-code/depin/blob/main/LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/andrelopes-code/depin/badge)](https://scorecard.dev/viewer/?uri=github.com/andrelopes-code/depin)

Type-first dependency injection for Python 3.12+.

**Documentation:** <https://andrelopes-code.github.io/depin/> · **PyPI:** [`pydepin`](https://pypi.org/project/pydepin/)

- Resolution driven by type hints; `Protocol` and `Annotated` are first-class.
- Build-time validation: `Container.freeze()` catches missing providers, cycles,
  lifetime violations, and async/sync mismatches before anything runs.
- Full async/sync coverage: classes, sync/async factories, generators, async
  generators, `@(a)contextmanager`, instance context managers.
- Safe to share across threads and tasks: a singleton is built exactly once under
  contention, and scopes are isolated per `contextvars.Context`.
- Every failure is a `DepinError`. No stray `TypeError` from the middle of the
  library.
- **A public integration contract**: `Host`, `hosted_container`, and a version
  constant. `depin.ext.fastapi` is written on it, and so is any integration you
  write yourself — no `depin._core` import required.
  [Writing an integration](https://andrelopes-code.github.io/depin/guide/integrations/).
- Optional FastAPI integration in `depin.ext.fastapi`. **The core has zero
  runtime dependencies.**
- No `# type: ignore` at call sites: `resolve()`, `frozen[key]`, `injected()`,
  and `Inject[T]` are all precisely typed under `basedpyright --strict` and
  `mypy --strict`.

## Install

```bash
uv add pydepin                # core
uv add 'pydepin[fastapi]'     # with the FastAPI integration
uv add 'pydepin[pytest]'      # with the tested pytest floor enforced
```

The `depin.ext.pytest` fixtures are registered on the `pytest11` entry point
by the distribution, so plain `pydepin` already provides them; the `pytest`
extra only states the pytest version the plugin is tested against.

Requires Python 3.12+. The distribution is `pydepin`; the import package is
`depin`.

## Quickstart

```python
from typing import Annotated

from depin import Container, Token

db_url = Token[str]('db.url')


class Database:
    def __init__(self, url: str) -> None:
        self.url = url


def open_db(url: Annotated[str, db_url]) -> Database:
    return Database(url)


class UserRepo:
    def __init__(self, db: Database) -> None:
        self.db = db


di = Container().value(db_url, 'postgres://...').bind(open_db, provides=Database).bind(UserRepo).freeze()

repo = di[UserRepo]
```

`Scope.SINGLETON` is the default, so most bindings need nothing but `bind`.

## The three stages

| Stage | Object | What it does |
| --- | --- | --- |
| Declare | `Container` | Mutable builder. Collects bindings; validates nothing. |
| Validate | `Container.freeze()` | Runs every static check, then returns the runtime. |
| Resolve | `FrozenContainer` | Immutable. Builds and caches values, opens scopes, injects. |

## Lifetimes

| Scope | Built | Cached on | Torn down by |
| --- | --- | --- | --- |
| `Scope.SINGLETON` | Once, on first resolution | The container | `close()` / `aclose()` |
| `Scope.SCOPED` | Once per active scope | The scope frame | Exit of `scope()` / `ascope()` |
| `Scope.TRANSIENT` | Every resolution | Nothing | Nothing |

A provider that owns a resource is written as a generator — everything after the
`yield` is its teardown:

```python
def checkout(pool: Pool) -> Generator[Connection]:
    conn = pool.acquire()
    yield conn
    pool.release(conn)


di = Container().bind(checkout, scope=Scope.SCOPED).freeze()

with di.scope():
    conn = di[Connection]  # built here, released when the block ends
```

Read [Lifetimes and scopes](https://andrelopes-code.github.io/depin/guide/lifetimes/)
for nesting, captive dependencies, and shutdown.

## Cookbook

Runnable code lives in [`examples/`](examples/); each one is executed by the test
suite.

- **Tokens** for values: `Token[str]('db.url')`, resolved via `di[token]`.
- **Registries** for composition: `Container(infra, services).freeze()`.
- **Protocols**: `@provides(Store)` on the implementation, then `di.resolve(Store)`.
- **Aliases** for a second name on one binding:
  `di.alias(Store, to=PostgresStore)`, with no second instance.
- **Tags** when several implementations share a key:
  `di.resolve(Cache, tag='primary')`.
- **Optional dependencies** for a parameter that may go unbound:
  `def __init__(self, metrics: MetricsSink | None): ...`, resolved to `None`.
- **Collections** for plugin points: `di.collect(Handler, [EmailHandler, SmsHandler])`,
  injected as `def __init__(self, handlers: list[Handler]): ...`.
- **Scope-supplied values**: `di.scope_value(Request)`, filled by middleware with
  `frame.provide(Request, request)`.
- **Overrides** for tests: `with di.override(Database, FakeDB()): ...`.
- **Function injection** with `@di.inject`: parameters whose default is
  `injected(...)` are filled from the container, the rest are passed by the
  caller:

  ```python
  @di.inject
  def handler(uid: int, repo: UserRepo = injected(UserRepo)) -> User:
      return repo.get(uid)


  handler(uid=1)  # repo injected; call site stays type-clean
  ```

## FastAPI

```python
from fastapi import FastAPI

from depin import Container, Scope
from depin.ext.fastapi import Inject, RequestScope

di = Container().bind(UserService, scope=Scope.SCOPED).freeze()

app = FastAPI()
app.add_middleware(RequestScope, container=di)


@app.get('/users/{uid}')
async def get_user(uid: int, svc: Inject[UserService]) -> User:
    return await svc.get(uid)
```

`Inject[T]` is a type-level shortcut: the parameter's static type is `T`, while
at runtime `Inject[T]` resolves to `Annotated[T, Depends(...)]` so FastAPI picks
up the dependency from the annotation. No default-value calls, no `# noqa: B008`
waivers.

`RequestScope` runs as pure ASGI middleware, so streaming responses, SSE, and
WebSockets pass through unbuffered. Scoped providers may declare `Request` to
read headers, URL, cookies, and state — but it is metadata-only: the request body
belongs to the route's typed parameters, and reading it from a provider raises
rather than racing the handler's own parsing.

Full walkthrough: [FastAPI guide](https://andrelopes-code.github.io/depin/guide/fastapi/).

## Caveats

- **Nested scopes inherit.** A `SCOPED` instance resolved in an outer scope is
  reused inside a nested scope, not rebuilt. Open sibling scopes for independent
  instances.
- **A consumer built before the override keeps its old value.** `override()`
  replaces the key immediately, even for a singleton already built — but a
  consumer resolved earlier keeps the instance it was given. Call `reset()` to
  evict it, or use the `depin.ext.pytest` fixtures, which call `reset()` for you.
- **`@di.inject` uses default-position markers.** An injected parameter carries
  an `injected(...)` default, so it must follow non-default parameters or be
  keyword-only (a normal Python rule). Unlike provider constructors, which
  resolve from type hints and `Annotated[...]`, `@inject` fills *only* marked
  parameters and validates them at decoration time, raising
  `MissingProviderError` immediately if a marked key is unregistered.

## Project status

Beta, pre-1.0. CI enforces `ruff`, `basedpyright --strict`, `mypy --strict`, the
full test suite with its embedded doctests, and a 95% coverage floor, on Python
3.12–3.14 across Linux, macOS, and Windows, plus the free-threaded builds of 3.13
and 3.14. See the
[support policy](https://andrelopes-code.github.io/depin/support-policy/).
Releases are published from CI via PyPI Trusted Publishing. Minor releases may
still contain breaking changes until 1.0; those are marked in the
[changelog](CHANGELOG.md).

## Development

```bash
uv sync --all-extras
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

The five commands above are the gates every change must pass. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow and
[AGENTS.md](AGENTS.md) for the repository conventions that contributors — human
or agent — are expected to follow.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup, the five gates, and commit conventions; all participants are
expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). To report a
vulnerability, follow the [security policy](SECURITY.md).

## License

[MIT](LICENSE) © André Lopes
