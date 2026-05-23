from contextvars import ContextVar
from typing import TYPE_CHECKING, Annotated

from fastapi import Request
from fastapi.params import Depends
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as ASGIScope

from depin._core.frozen import FrozenContainer

_active_container: ContextVar[FrozenContainer | None] = ContextVar('depin_fastapi_container', default=None)


class RequestScope:
    """ASGI middleware that opens a depin async scope around every HTTP request.

    Implemented directly against the ASGI protocol (not Starlette's
    ``BaseHTTPMiddleware``) so streaming responses, server-sent events, and
    WebSockets pass through without buffering. Lifespan and other non-HTTP
    scopes are forwarded untouched, with no depin scope opened.

    For HTTP requests it places a metadata-only :class:`fastapi.Request` into the
    active scope frame so scoped providers can read headers, URL, cookies, and
    state. That ``Request`` carries no receive channel: reading the body through
    it raises rather than consuming the stream the route handler needs (which
    would otherwise deadlock against FastAPI's own body parsing). Treat the body
    as a typed route parameter, not a provider input.
    """

    __slots__ = ('_app', '_container')

    def __init__(self, app: ASGIApp, container: FrozenContainer) -> None:
        self._app = app
        self._container = container

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self._app(scope, receive, send)
            return
        token = _active_container.set(self._container)
        try:
            async with self._container.ascope() as frame:
                if scope['type'] == 'http':
                    frame.put(Request, Request(scope))
                await self._app(scope, receive, send)
        finally:
            _active_container.reset(token)


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
            async def resolver() -> object:
                container = _active_container.get()
                if container is None:
                    raise RuntimeError(
                        'Inject[...] resolved outside a RequestScope; install the middleware with '
                        'app.add_middleware(RequestScope, container=...).'
                    )
                return await container.aresolve(key)

            return Annotated[key, Depends(dependency=resolver)]
