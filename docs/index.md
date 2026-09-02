# depin

Type-first dependency injection for Python 3.12+.

Declare bindings on a `Container`, call `freeze()` to validate the graph, then
resolve from the immutable `FrozenContainer` it returns. Resolution is driven by
type hints; `Protocol` and `Annotated` are first-class, and the core has zero
runtime dependencies.

## Install

```bash
uv add pydepin                # core
uv add 'pydepin[fastapi]'     # with the FastAPI integration
uv add 'pydepin[starlette]'   # with the Starlette integration
uv add 'pydepin[litestar]'    # with the Litestar integration
uv add 'pydepin[flask]'       # with the Flask integration
uv add 'pydepin[click]'       # with the Click integration
uv add 'pydepin[typer]'       # with the Typer integration
uv add 'pydepin[taskiq]'      # with the Taskiq integration
```

`depin.ext.asgi` and `depin.ext.wsgi` are the framework-free middlewares the
four web extras specialise, and `depin.ext.cli` is the framework-free command
seam Click and Typer specialise; all three import no third-party package and
need no extra. See
[the request and response integrations](guide/integrations.md#the-request-and-response-integrations)
and [the command and message hosts](guide/integrations.md#the-command-and-message-hosts).

The distribution is named `pydepin` on PyPI; the import package is `depin`.

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

## The mental model

| Stage | Object | What it does |
| --- | --- | --- |
| Declare | `Container` | Mutable builder. Collects bindings; validates nothing. |
| Validate | `Container.freeze()` | Runs every static check, then returns the runtime. |
| Resolve | `FrozenContainer` | Immutable. Builds and caches values, opens scopes, injects. |

`freeze()` is the gate. It rejects missing providers, dependency cycles,
duplicate bindings, a singleton that would capture a scoped provider, and
providers whose type information is too thin to infer a key — all before a
single value is constructed. See the [guide](guide/index.md) for the full
list.

## Lifetimes

| Scope | Built | Cached on | Torn down by |
| --- | --- | --- | --- |
| `Scope.SINGLETON` | Once, on first resolution | The container | `frozen.close()` / `aclose()` |
| `Scope.SCOPED` | Once per active scope | The scope frame | Exit of `scope()` / `ascope()` |
| `Scope.TRANSIENT` | Every resolution | Nothing | Not applicable |

## Where to go next

- [Guide](guide/index.md) — lifetimes and scopes, composing bindings,
  resolution semantics, testing, inspecting the graph, and the web, command,
  and message integrations.
- [API reference](reference/index.md) — the full public API, generated from the
  source docstrings.
- [Performance](performance/index.md) — what each operation costs against a
  direct-Python baseline, how it scales, the methodology, and the limits of what
  the numbers support.
- [Examples](https://github.com/andrelopes-code/depin/tree/main/examples) —
  seventeen runnable programs, each executed by the test suite.
- [Contributing](https://github.com/andrelopes-code/depin/blob/main/CONTRIBUTING.md)
  — development setup, the five gates, and the release process.
