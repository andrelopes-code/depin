# Lifetimes and scopes

A binding's scope answers two questions: how often is the value built, and who
tears it down.

| Scope | Built | Cached on | Torn down by |
| --- | --- | --- | --- |
| `Scope.SINGLETON` | Once, on first resolution | The container | `close()` / `aclose()` |
| `Scope.SCOPED` | Once per active scope | The scope frame | Exit of `scope()` / `ascope()` |
| `Scope.TRANSIENT` | Every resolution | Nothing | Nothing |

`SINGLETON` is the default, because most of a dependency graph — configuration,
clients, connection pools, stateless services — is built once and shared.

## Providers that own a resource

A provider that has cleanup to do is written as a generator. Everything before
the `yield` is setup, everything after is teardown:

```python
from collections.abc import Generator

from depin import Container, Scope


class Connection:
    def close(self) -> None: ...


def checkout() -> Generator[Connection]:
    conn = Connection()
    yield conn
    conn.close()


di = Container().bind(checkout, scope=Scope.SCOPED).freeze()
```

`@contextmanager` and `@asynccontextmanager` factories work the same way, as do
async generators. What they have in common is a teardown, and that is why they
cannot be `TRANSIENT`: a transient value is never cached, so nothing would ever
hold a reference to run the teardown from. `freeze()` rejects that combination
with `InvalidScopeError`.

## Scopes

A scope is a unit of work — an HTTP request, a job, a CLI invocation. Scoped
values are built once inside it and drained when it ends, in reverse order of
construction:

```python
with di.scope():
    conn = di[Connection]  # built here
    ...
# conn.close() has run
```

Use `ascope()` instead when any provider in the scope is async. Both forms yield
the scope's `ScopeFrame`, which is also how you hand values *into* the scope —
see [`scope_value`](#values-supplied-by-the-scope) below.

If several teardowns fail, every failure is reported: the errors are collected
into an `ExceptionGroup` rather than the first one hiding the rest.

### Nesting

Scopes nest, and a nested scope inherits the outer scope's instances rather than
rebuilding them:

```python
with di.scope():
    outer = di[Connection]
    with di.scope():
        assert di[Connection] is outer
```

When you want independent instances, open sibling scopes, not nested ones.

## Why a singleton cannot depend on a scoped provider

A singleton is built once and lives for the life of the container. A scoped
value lives for one unit of work. If a singleton took a scoped dependency it
would capture the first scope's instance and quietly reuse it in every scope
afterwards — a connection from a closed request, reused for the next thousand.

`freeze()` refuses:

```pycon
>>> from depin import Container, Scope
>>> from depin.errors import CaptiveDependencyError
>>> class Session: ...
>>> class Repo:
...     def __init__(self, session: Session) -> None: ...
>>> try:
...     Container().bind(Session, scope=Scope.SCOPED).bind(Repo).freeze()
... except CaptiveDependencyError as exc:
...     print(type(exc).__name__)
CaptiveDependencyError

```

The check looks through chains of transients, because a transient is inlined
into whoever asked for it and carries the capture along with it.

## Shutdown

Singletons that own resources are drained by `close()`, or `aclose()` when any
of them is async:

```python
di = build()
try:
    run(di)
finally:
    di.close()
```

Calling it twice is harmless: the second call finds nothing left to drain.
Calling `close()` on a graph with an async singleton teardown raises
`TeardownError` — that teardown needs an event loop, so use `aclose()`.

## Values supplied by the scope

Some values are not built by the graph at all; they arrive with the unit of work.
An HTTP request, an authenticated principal, a job payload. Declare them with
`scope_value()` and hand them in when you open the scope:

```pycon
>>> from depin import Container, Scope
>>> class Principal:
...     def __init__(self, name: str) -> None:
...         self.name = name
>>> class Audit:
...     def __init__(self, who: Principal) -> None:
...         self.who = who
>>> di = Container().scope_value(Principal).bind(Audit, scope=Scope.SCOPED).freeze()
>>> with di.scope() as frame:
...     frame.provide(Principal, Principal('ana'))
...     di[Audit].who.name
'ana'

```

Resolving such a key outside a scope raises `OutsideScopeError`; resolving it
inside a scope that never received the value raises `MissingProviderError`. This
is how [the FastAPI integration](fastapi.md) exposes the per-request `Request`.

## Concurrency

A frozen container is safe to share across threads and tasks. Scopes are tracked
per `contextvars.Context`, so two concurrent requests never see each other's
scoped instances, and construction of a cached provider is single-flighted:
a singleton is built exactly once no matter how many threads or tasks race for
it, under a thread lock on the synchronous path and an asyncio lock on the
asynchronous one.
