# FastAPI

The integration lives in `depin.ext.fastapi` and needs the extra:

```bash
uv add 'pydepin[fastapi]'
```

It is two pieces: middleware that opens a depin scope around every request, and
an annotation that resolves a dependency into a route handler.

## Wiring an app

```python
import contextlib
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request

from depin import Container, FrozenContainer
from depin.ext.fastapi import Inject, RequestScope

from .wiring import infra, services


def create_app(container: FrozenContainer | None = None) -> FastAPI:
    di = container if container is not None else Container(infra, services).scope_value(Request).freeze()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        yield
        await di.aclose()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(RequestScope, container=di)

    @app.get('/users/{uid}')
    async def get_user(uid: int, svc: Inject[UserService]) -> User:
        return await svc.get(uid)

    return app
```

Taking the container as an argument is what makes the app testable: a test
passes its own graph instead of patching module state. `aclose()` in the
lifespan drains the singletons that own resources.

## `Inject[T]`

`Inject[T]` is a type-level shortcut. To the type checker the parameter is
plain `T`; at runtime `Inject[T]` expands to `Annotated[T, Depends(...)]`, so
FastAPI resolves it through its normal dependency plumbing. There is no
default-value marker at the call site, and no `# noqa: B008` waiver.

Resolving it raises `ContainerNotBoundError` when no container is hosted in the
current context. A missing `RequestScope` is the usual cause, not the
definition: `Inject[T]` reads whichever container the current context carries,
so a container published elsewhere — by `Host.activated()` in a lifespan, for
instance — satisfies it just as well. Reached that way no scope is open, so a
*scoped* provider then fails with `OutsideScopeError` rather than
`ContainerNotBoundError`.

## One scope per request

`RequestScope` is implemented directly against the ASGI protocol rather than
Starlette's `BaseHTTPMiddleware`, so streaming responses, server-sent events and
WebSockets pass through unbuffered. A connection scope that is neither `http`
nor `websocket` — the lifespan scope above all — is forwarded untouched: no
depin scope is opened and nothing is published. A websocket is scoped and
hosted exactly like an HTTP request, but it is not seeded, because it has no
request-body semantics and `Request` is HTTP-shaped.

Every scoped provider is therefore built once per request and torn down when the
response finishes:

```python
@services.scoped()
async def open_session(db: Database) -> AsyncGenerator[Session]:
    session = await db.begin()
    yield session
    await session.close()
```

## Reading the request

For HTTP requests the middleware places a `Request` into the scope frame. A
scoped provider reads it back because the container declares the key with
`scope_value(Request)`, as the wiring above does; without that declaration the
graph fails at `freeze()`:

```python
@services.scoped()
def current_tenant(request: Request) -> Tenant:
    return Tenant(request.headers['x-tenant'])
```

!!! warning "The `Request` in a provider is metadata only"

    It carries no receive channel: headers, URL, cookies and state are readable,
    but reading the **body** through it raises rather than consuming the stream
    the route handler needs. The body belongs to the route's own typed
    parameters, where FastAPI parses it once.

## Testing an app

```python
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_get_user():
    di = Container(fake_infra, services).freeze()
    transport = ASGITransport(app=create_app(di))
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        response = await client.get('/users/1')
    assert response.status_code == 200
    await di.aclose()
```

Because the transport drives the real ASGI app, the middleware runs and the
per-request scope behaves exactly as in production.
