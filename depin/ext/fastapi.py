from typing import TYPE_CHECKING, Annotated

from fastapi import Request
from fastapi.params import Depends
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as ASGIScope

from depin._core.frozen import FrozenContainer


class RequestScope:
    """ASGI middleware that opens a depin async scope around every HTTP request.

    Implemented directly against the ASGI protocol (not Starlette's
    ``BaseHTTPMiddleware``) so streaming responses, server-sent events, and
    WebSockets pass through without buffering.

    The middleware exposes the container at ``app.state.depin_container`` so
    ``Inject[T]`` can retrieve it via the FastAPI dependency-injection plumbing,
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


if TYPE_CHECKING:
    # `Inject[T]` is a PEP 695 type alias so the parameter's static type is `T` —
    # `svc: Inject[UserService]` is read by basedpyright as `svc: UserService`.
    # At runtime (else-branch) `Inject[T]` is a class whose `__class_getitem__`
    # returns `Annotated[T, Depends(resolver)]`, which FastAPI picks up via the
    # usual dependency-injection plumbing. The two views must stay in sync.
    type Inject[T] = T
else:

    class Inject:
        def __class_getitem__(cls, key: object) -> object:
            async def resolver(request: Request) -> object:
                container: FrozenContainer = request.app.state.depin_container
                return await container.aresolve(key)

            return Annotated[key, Depends(dependency=resolver)]
