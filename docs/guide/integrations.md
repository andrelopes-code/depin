# Writing an integration

`depin.ext.fastapi` is not special: it is written entirely against the same
seam any third-party integration uses — `Host`, `hosted_container`,
`optional_hosted_container`, `ContractVersion`, and `CONTRACT_VERSION`, all
re-exported from `depin`. This page states that contract, then builds one
integration — a job runner — against it end to end.

## What an integration does

Four operations cover every host depin has been fitted to: a web framework, a
CLI, a queue consumer.

| Operation | Call | When |
| --- | --- | --- |
| Publish the container | `Host.activated()` | Outside any unit of work — an ASGI lifespan, process-wide CLI setup. |
| Open a scope per unit of work | `Host.scope()` / `Host.ascope()` | Once per request, invocation, or message. |
| Seed the framework's objects | `ScopeFrame.provide()` on the yielded frame, against a key declared with `Container.scope_value()` | Right after the scope opens, before anything resolves. |
| Read the container back | `hosted_container()` / `optional_hosted_container()` | Anywhere downstream that carries no reference to the container. |

Pair every seeded key with `Container.scope_value()`. A key declared that way
gets a plan node: `resolve(key)` works, the value is cached in the frame on
first use, and an `override()` on the key is honoured. A bare
`frame.provide(key, value)` for a key with no such declaration wires nothing —
`resolve(key)` still raises `MissingProviderError` — and only reaches a
parameter that carries a default or admits `None`, as a fallback for the case
the plan has no route for at all; a required parameter with no default keeps
raising. Relying on that fallback skips the guarantees `scope_value()` buys,
so treat it as what happens when the pairing is missing, not as a second way
to seed.

## The integrations depin ships

Each shipped web integration is one of two middlewares — the ASGI one or the
WSGI one — with a single seed applied, so the module to import is chosen by the
framework and the extra is named after it:

| Framework | Module | Protocol | Install |
| --- | --- | --- | --- |
| FastAPI | `depin.ext.fastapi` | ASGI | `uv add 'pydepin[fastapi]'` |
| Starlette | `depin.ext.starlette` | ASGI | `uv add 'pydepin[starlette]'` |
| Litestar | `depin.ext.litestar` | ASGI | `uv add 'pydepin[litestar]'` |
| Flask | `depin.ext.flask` | WSGI | `uv add 'pydepin[flask]'` |
| Any other ASGI framework | `depin.ext.asgi` | ASGI | no extra |
| Any other WSGI framework | `depin.ext.wsgi` | WSGI | no extra |

`depin.ext.asgi` and `depin.ext.wsgi` import no third-party package, so a
framework outside that list installs `RequestScope` with a `seed` of its own
and needs nothing from depin beyond the contract above.

`examples/starlette_app/` is the whole shape in one runnable program —
registries, an app factory taking the container as an argument,
`scope_value(Request)` for the seeded request, and `aclose()` on shutdown. Run
it with `python -m examples.starlette_app.main`.

!!! warning "A WSGI scope ends when the application returns"

    The scope ends when the application returns, not when the response is
    finished. WSGI hands the server an iterable that the server consumes after
    the application has returned, and it offers no hook that outlives that
    return, so a streaming body cannot resolve: by the time the server pulls the
    first chunk the scope has drained and the container is no longer published.
    Resolve everything a streaming response needs before returning the iterable,
    and close over the values. ASGI has no such limit;
    `depin.ext.asgi.RequestScope` keeps the scope open for the whole response.

!!! warning "The Flask seed must not be used to read the body"

    The seeded `flask.Request` is built from the same environment Flask builds
    its own request from, and the two share one `environ['wsgi.input']` stream.
    Reading the body through the seed — `form`, `json`, `data`, `files` —
    consumes that stream, and Flask's own parse then finds it empty and returns
    400. The ASGI seeds differ here: `depin.ext.starlette` and
    `depin.ext.litestar` seed a request with no receive channel, so the same
    mistake raises instead of stealing the body. Treat the body as a route
    concern, not a provider input.

## A worked integration

The host is a job runner: `run()` is its unit of work, `Job` is the object it
has of its own to hand to providers.

```pycon
>>> from collections.abc import Generator
>>> from dataclasses import dataclass
>>> from depin import Container, Host, Scope, hosted_container
>>> @dataclass(frozen=True, slots=True)
... class Job:
...     name: str
>>> class Metrics:
...     def __init__(self) -> None:
...         self.completed = 0
>>> class Workspace:
...     def __init__(self, job: Job) -> None:
...         self.job = job
>>> def open_workspace(job: Job) -> Generator[Workspace]:
...     yield Workspace(job)

```

`scope_value(Job)` is what makes `Job` fillable per scope rather than bound to
one factory; `Metrics` is an ordinary singleton, one per process:

```pycon
>>> di = Container().scope_value(Job).bind(Metrics).bind(open_workspace, scope=Scope.SCOPED).freeze()
>>> host = Host(di)

```

A handler carries no reference to `di` or `host` — only `hosted_container()`:

```pycon
>>> def handle() -> str:
...     container = hosted_container()
...     workspace = container.resolve(Workspace)
...     metrics = container.resolve(Metrics)
...     metrics.completed += 1
...     return f'{workspace.job.name} (completed={metrics.completed})'

```

`run()` opens the scope, seeds `Job`, and calls the handler:

```pycon
>>> with host.scope() as frame:
...     frame.provide(Job, Job('reindex'))
...     handle()
'reindex (completed=1)'

```

`Workspace` is scoped and rebuilt for the next job; `Metrics` is a singleton
and keeps counting across both scopes, which is why the count reads `2`, not
`1`:

```pycon
>>> with host.scope() as frame:
...     frame.provide(Job, Job('vacuum'))
...     handle()
'vacuum (completed=2)'

```

The full picture — one container, run twice from a `JobRunner` that owns the
`Host` — is `examples/integration/main.py`, run with
`python -m examples.integration.main` and pinned by
`tests/integration/test_examples.py`.

Two guarantees `scope()` makes are worth calling out by name, because both are
things an integration author relies on without necessarily testing for them.
The container is published before the scope opens and stays published until
the scope's own teardowns have finished draining — only then is the
publication undone — so a generator provider that reaches
`hosted_container()` from its teardown half still finds the container there.
And the publication is scoped to the current `contextvars.Context`: two
concurrent requests, or two concurrent tasks, never see each other's
container, and two `Host`s active in the same process nest rather than
collide — the innermost `hosted_container()` wins, and exiting its scope
restores whichever container the enclosing one had published.

That nesting is a property of the publication alone. Scopes do not nest the
same way: the scope frame stack is process-wide and shared by every container,
so a second `Host`'s scope opened inside a first one's becomes a child of the
first frame, and the frame cache is keyed on the key and its tag alone. A key
already resolved in the enclosing scope is therefore what the inner scope
resolves, from the enclosing container's cache, and the inner container's own
binding never runs. Do not nest two different containers' scopes — open the
second one after the first has closed, or host one container per context.

## Hosts whose lifecycle is a pair of hooks

`Host.scope()` returns an ordinary context-manager object; a `with` statement
is only the usual way to drive it. A framework that gives a host a `before`
hook and an `after` hook instead of a block — Flask's `before_request` /
`teardown_request` is the canonical shape — stores the context manager between
the two and calls `__enter__` / `__exit__` itself. Hold it per unit of work,
keyed by whatever identifier the framework already hands the hooks — a task id,
a message id — never on the integration object: one attribute is one slot for
the whole process, and a second unit of work arriving before the first finishes
overwrites it.

```pycon
>>> from contextlib import AbstractContextManager
>>> from types import TracebackType
>>> from depin import FrozenContainer, ScopeFrame
>>> class JobHost:
...     def __init__(self, container: FrozenContainer) -> None:
...         self._host = Host(container)
...         self._open: dict[str, AbstractContextManager[ScopeFrame]] = {}
...
...     def before(self, job_id: str, name: str) -> None:
...         opened = self._host.scope()
...         frame = opened.__enter__()
...         frame.provide(Job, Job(name))
...         self._open[job_id] = opened
...
...     def after(
...         self,
...         job_id: str,
...         exc_type: type[BaseException] | None = None,
...         exc: BaseException | None = None,
...         tb: TracebackType | None = None,
...     ) -> None:
...         opened = self._open.pop(job_id, None)
...         if opened is not None:
...             opened.__exit__(exc_type, exc, tb)
>>> jh = JobHost(di)
>>> jh.before('j-1', 'reindex')
>>> hosted_container() is di
True
>>> handle()
'reindex (completed=3)'
>>> jh.after('j-1')

```

Both hooks must run in the same `contextvars.Context`. The publication is a
`contextvars.ContextVar`, and resetting it from a different context raises a
bare `ValueError` — `Token ... was created in a different Context` — which is
not a `DepinError` and escapes `__exit__` untranslated. A framework that runs
`before` and `after` on the same thread or the same task satisfies this; one
that copies a fresh context for the `after` hook does not, and needs the whole
unit of work driven from a single callable with a `with` statement instead.

`Host.ascope()` is an async context manager, driven the same way through
`__aenter__` / `__aexit__` for a framework whose hooks are themselves
coroutines.

## Sync or async

`scope()` suits a WSGI host, a CLI, or anything that never awaits inside the
unit of work. `ascope()` is required the moment any provider in that scope is
async — the same rule that already separates `resolve()` from `aresolve()`:

```pycon
>>> import asyncio
>>> async def run_job(name: str) -> str:
...     async with host.ascope() as frame:
...         frame.provide(Job, Job(name))
...         return handle()
>>> asyncio.run(run_job('compact'))
'compact (completed=4)'

```

Mixing them the wrong way fails the way the rest of depin does: resolving an
async provider inside a sync `scope()` raises `AsyncInSyncContextError`, the
same error `resolve()` raises anywhere else; and a sync `scope()` that closes
over an async provider's teardown raises `TeardownError`, naming `ascope()` as
the fix.

## Startup and shutdown

`Host.container` is the `FrozenContainer` the host was built around, so
startup and shutdown are reached through it rather than through `Host`
itself — a lifespan hook, or its CLI or worker equivalent, is where they
belong:

```pycon
>>> host.container is di
True
>>> [node.key.__qualname__ for node in host.container.warmup().cached]
['Metrics']
>>> host.container.close()

```

`warmup()` builds every singleton up front so a broken one fails at startup
instead of on the first unit of work; here `Metrics` is already built from the
scopes opened above, so it reports `cached` rather than `constructed`.
`awarmup()` and `aclose()` are the async counterparts, called the same way
from an async lifespan:

```pycon
>>> async def make_pool() -> object:
...     return object()
>>> di2 = Container().bind(make_pool, provides=object).freeze()
>>> host2 = Host(di2)
>>> async def startup_and_shutdown() -> None:
...     report = await host2.container.awarmup()
...     print([node.key.__qualname__ for node in report.constructed])
...     await host2.container.aclose()
>>> asyncio.run(startup_and_shutdown())
['object']

```

## Raising your own error

`hosted_container()` raises `ContainerNotBoundError` with a contract-level
message. An integration that knows which of *its own* setup steps a caller
skipped gives a more specific error instead, by reading
`optional_hosted_container()` and raising when it comes back `None` —
the way `depin.ext.fastapi` names the missing `RequestScope` middleware
rather than repeating the contract's generic wording:

```pycon
>>> from depin import optional_hosted_container
>>> from depin.errors import ContainerNotBoundError
>>> def resolve_job() -> Workspace:
...     container = optional_hosted_container()
...     if container is None:
...         raise ContainerNotBoundError('resolve_job() called outside JobRunner.run(); call it from run().')
...     return container.resolve(Workspace)
>>> resolve_job()
Traceback (most recent call last):
    ...
depin.errors.ContainerNotBoundError: resolve_job() called outside JobRunner.run(); call it from run().

```

## The version

`CONTRACT_VERSION` names the shape of the contract this release of depin
implements:

```pycon
>>> from depin import CONTRACT_VERSION, ContractVersion
>>> CONTRACT_VERSION >= ContractVersion(1, 0)
True

```

It covers the four operations above and nothing else: an ordinary
`FrozenContainer` method is versioned by the depin release that introduced it,
not by this number.

The minor number rises when an operation is added and every existing one
keeps its meaning; the major number rises when an operation changes meaning
or is removed. An integration that needs an operation added in `1.2` guards
with `depin.CONTRACT_VERSION >= ContractVersion(1, 2)` rather than pinning a
depin release directly.

## What not to import

An integration imports from `depin` only — never from `depin._core`, which
carries no compatibility promise across releases. `depin.ext.fastapi` is held
to that rule by `tests/unit/test_integration_contract.py`, which fails on the
literal substring `_core` appearing anywhere in a module under `depin/ext/`,
prose included. A third-party integration gets the same guarantee `depin`
gives its own: everything a host needs — `Host`, `hosted_container`,
`optional_hosted_container`, `ContractVersion`, `CONTRACT_VERSION` — is
re-exported from `depin` itself.
