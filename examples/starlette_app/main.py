"""A Starlette app wired by depin: one scope per request, one teardown on shutdown.

Run with ``uvicorn examples.starlette_app.main:create_app --factory`` to serve
it, or with ``python -m examples.starlette_app.main`` to drive the same app
over an in-process transport and print the two responses.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from depin import Container, FrozenContainer, hosted_container
from depin.ext.starlette import RequestScope

from .registries import Database, infra, services
from .services import UserService


def build_container() -> FrozenContainer:
    """Freeze the graph. Called once per application, never at import time.

    ``scope_value(Request)`` is what gives the request the middleware seeds a
    plan node, so a provider can take it as a parameter.
    """
    return Container(infra, services).scope_value(Request).freeze()


async def get_user(request: Request) -> JSONResponse:
    """A route that holds no container: `hosted_container()` reaches the hosted one."""
    service = await hosted_container().aresolve(UserService)
    return JSONResponse(await service.get(int(request.query_params['uid'])))


async def health(request: Request) -> JSONResponse:
    del request
    db = await hosted_container().aresolve(Database)
    return JSONResponse({'db': db.url, 'open_sessions': db.open_sessions})


def create_app(container: FrozenContainer | None = None) -> Starlette:
    """Build the app around a container.

    Accepting the container as an argument is what makes the app testable: a test
    passes a container with its own bindings instead of patching module state.
    """
    di = container if container is not None else build_container()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None]:
        del app
        yield
        # Drains the singleton providers that own resources — here, the Database
        # async generator in `registries`.
        await di.aclose()

    routes = [Route('/users', get_user), Route('/health', health)]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(RequestScope, container=di)
    return app


async def main() -> None:
    # Imported here rather than at module level so serving the app needs only
    # Starlette; the in-process client is a convenience of this entry point.
    from httpx import ASGITransport, AsyncClient

    di = build_container()
    app = create_app(di)

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://t') as client:
        print('user:', (await client.get('/users', params={'uid': 1}, headers={'user-agent': 'demo/1.0'})).json())
        print('health:', (await client.get('/health')).json())

    # The transport speaks no lifespan, so the shutdown drain is run by hand.
    await di.aclose()


if __name__ == '__main__':
    asyncio.run(main())
