from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from depin._core.frozen import FrozenContainer
from depin._core.markers import Token


class RequestScope(BaseHTTPMiddleware):
    """Open a depin async scope around every HTTP request.

    The middleware exposes the container at ``request.app.state.depin_container``
    so :func:`Inject` can retrieve it via the FastAPI dependency-injection plumbing.
    The current ``Request`` is also placed into the scope frame keyed by ``Request``
    so that scoped providers can declare it as a constructor parameter.
    """

    def __init__(self, app: ASGIApp, container: FrozenContainer) -> None:
        super().__init__(app)
        self._container = container

    async def dispatch(  # pyright: ignore[reportImplicitOverride]
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.app.state.depin_container = self._container
        async with self._container.ascope() as frame:
            frame.put(Request, request)
            return await call_next(request)


def Inject[T](key: type[T] | Token[T], *, tag: str | None = None) -> T:  # noqa: N802
    """Mark a FastAPI route parameter for resolution from the depin container.

    The return value at runtime is a :class:`fastapi.Depends` instance — FastAPI
    consumes it via the dependency-injection machinery — but the call site needs
    the parameter to be typed as ``T`` so the handler body sees the right type.
    Python's type system has no way to express "this object is also T", so the
    cast at the boundary is the documented single approved exception.
    """

    async def resolver(request: Request) -> T:
        container: FrozenContainer = request.app.state.depin_container
        return await container.aresolve(key, tag=tag)

    return cast(T, Depends(resolver))
