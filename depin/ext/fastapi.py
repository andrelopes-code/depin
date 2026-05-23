from typing import cast

from fastapi import Depends, Request
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as ASGIScope

from depin._core.frozen import FrozenContainer
from depin._core.markers import Token


class RequestScope:
    """ASGI middleware that opens a depin async scope around every HTTP request.

    Implemented directly against the ASGI protocol (not Starlette's
    ``BaseHTTPMiddleware``) so streaming responses, server-sent events, and
    WebSockets pass through without buffering.

    The middleware exposes the container at ``app.state.depin_container`` so
    :func:`Inject` can retrieve it via the FastAPI dependency-injection plumbing,
    and places the current :class:`fastapi.Request` (for HTTP) into the active
    scope frame so scoped providers can declare it as a constructor parameter.
    """

    __slots__ = ('_app', '_container')

    def __init__(self, app: ASGIApp, container: FrozenContainer) -> None:
        self._app = app
        self._container = container

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self._app(scope, receive, send)
            return
        scope.setdefault('app', None)
        app = scope.get('app')
        if app is not None and hasattr(app, 'state'):
            app.state.depin_container = self._container
        async with self._container.ascope() as frame:
            if scope['type'] == 'http':
                frame.put(Request, Request(scope, receive=receive, send=send))
            await self._app(scope, receive, send)


def Inject[T](key: type[T] | Token[T], *, tag: str | None = None) -> T:
    """Mark a FastAPI route parameter for resolution from the depin container.

    The return value at runtime is a :class:`fastapi.Depends` instance — FastAPI
    consumes it via the dependency-injection machinery — but the call site needs
    the parameter to be typed as ``T`` so the handler body sees the right type.
    Python's type system has no way to express "this object is also T", so
    ``typing.cast`` at this boundary is a documented exception: the unsafety is
    confined to one return statement and the runtime contract is honoured by
    FastAPI's own resolver.
    """

    async def resolver(request: Request) -> T:
        container: FrozenContainer = request.app.state.depin_container
        return await container.aresolve(key, tag=tag)

    # See docstring: FastAPI requires a Depends sentinel at the call site while
    # the static type must remain T.
    return cast(T, Depends(resolver))
