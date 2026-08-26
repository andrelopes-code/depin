"""A FastAPI app wired by depin: one scope per request, one teardown on shutdown.

Run with ``uvicorn examples.fastapi_app.main:create_app --factory``.
"""

import contextlib
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from depin import Container, FrozenContainer
from depin.ext.fastapi import Inject, RequestScope

from .registries import Database, infra, services
from .services import UserService


def build_container() -> FrozenContainer:
    """Freeze the graph. Called once per application, never at import time."""
    return Container(infra, services).freeze()


def create_app(container: FrozenContainer | None = None) -> FastAPI:
    """Build the app around a container.

    Accepting the container as an argument is what makes the app testable: a test
    passes a container with its own bindings instead of patching module state.
    """
    di = container if container is not None else build_container()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        del app
        yield
        # Drains the singleton providers that own resources — here, the Database
        # async generator in `registries`.
        await di.aclose()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(RequestScope, container=di)

    @app.get('/users/{uid}')
    async def get_user(uid: int, svc: Inject[UserService]) -> dict[str, int | str]:  # pyright: ignore[reportUnusedFunction]
        return await svc.get(uid)

    @app.get('/health')
    async def health(db: Inject[Database]) -> dict[str, int | str]:  # pyright: ignore[reportUnusedFunction]
        return {'db': db.url, 'open_sessions': db.open_sessions}

    return app
