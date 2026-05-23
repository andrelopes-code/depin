from fastapi import Request
from fastapi.params import Depends
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


def Inject[T](key: type[T] | Token[T], *, tag: str | None = None) -> Depends:
    """Resolve ``key`` from the depin container for a FastAPI route parameter.

    Use inside :class:`typing.Annotated` so the parameter keeps its static type::

        async def handler(svc: Annotated[UserService, Inject(UserService)]) -> ...:
            ...

    The return value is a :class:`fastapi.params.Depends` instance; FastAPI picks
    it up from the ``Annotated`` metadata and the parameter's runtime type comes
    from the first ``Annotated`` argument. The legacy default-value form
    (``svc: UserService = Inject(UserService)``) is not supported: it triggers
    ruff's B008 (function call in default) and forces every call site to silence
    a lint warning.
    """

    async def resolver(request: Request) -> T:
        container: FrozenContainer = request.app.state.depin_container
        return await container.aresolve(key, tag=tag)

    return Depends(dependency=resolver)
