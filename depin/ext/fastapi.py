"""FastAPI integration: per-request scoping and type-level injection.

Importing this module requires the ``fastapi`` extra (``pip install
'pydepin[fastapi]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract — `depin.Host`
and `depin.optional_hosted_container` — so it is also the worked example the
"writing an integration" guide points at.
"""

from typing import TYPE_CHECKING, Annotated

from fastapi import Request
from fastapi.params import Depends
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as ASGIScope

from depin import FrozenContainer, Host, optional_hosted_container
from depin.errors import ContainerNotBoundError


class RequestScope:
    """ASGI middleware that opens a depin async scope around every HTTP request.

    Implemented directly against the ASGI protocol (not Starlette's
    ``BaseHTTPMiddleware``) so streaming responses, server-sent events, and
    WebSockets pass through without buffering. Lifespan and other non-HTTP
    scopes are forwarded untouched, with no depin scope opened.

    For HTTP requests it places a metadata-only `fastapi.Request` into the
    active scope frame so scoped providers can read headers, URL, cookies, and
    state. That ``Request`` carries no receive channel: reading the body through
    it raises rather than consuming the stream the route handler needs (which
    would otherwise deadlock against FastAPI's own body parsing). Treat the body
    as a typed route parameter, not a provider input.

    The container is published to the request's context for the duration of
    the scope, so `depin.hosted_container()` reaches it from anywhere inside
    the request.

    Example:
        Install the middleware once, then resolve scoped providers per request::

            app = FastAPI()
            app.add_middleware(RequestScope, container=di)
    """

    __slots__ = ('_app', '_host')

    def __init__(self, app: ASGIApp, container: FrozenContainer) -> None:
        self._app = app
        self._host = Host(container)

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self._app(scope, receive, send)
            return
        async with self._host.ascope() as frame:
            if scope['type'] == 'http':
                frame.provide(Request, Request(scope))
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
        """FastAPI parameter annotation that resolves a dependency from depin.

        Write ``svc: Inject[UserService]`` on a route handler: to the type checker
        the parameter is plain ``UserService``, while at runtime ``Inject[T]``
        expands to ``Annotated[T, Depends(...)]`` so FastAPI resolves it through the
        active `RequestScope`. No default-value markers and no
        ``# noqa: B008`` waivers at the call site.

        Raises:
            ContainerNotBoundError: ``Inject[T]`` was resolved outside a
                `RequestScope`. Install the middleware with
                ``app.add_middleware(RequestScope, container=...)``.
        """

        def __class_getitem__(cls, key: object) -> object:
            async def resolver() -> object:
                container = optional_hosted_container()
                if container is None:
                    raise ContainerNotBoundError(
                        'Inject[...] resolved outside a RequestScope; install the middleware with '
                        'app.add_middleware(RequestScope, container=...).'
                    )
                return await container.aresolve(key)

            return Annotated[key, Depends(dependency=resolver)]
