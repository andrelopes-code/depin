"""Starlette integration: the shared ASGI middleware, seeded with a `starlette.requests.Request`.

Importing this module requires the ``starlette`` extra (``pip install
'pydepin[starlette]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract and the
framework-free middleware in `depin.ext.asgi`: a seed and a partial
application, nothing more.
"""

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from depin import FrozenContainer, ProviderKey
from depin.ext.asgi import RequestScope as ASGIRequestScope


def seed_request(scope: Scope) -> tuple[ProviderKey, object]:
    """Build the `starlette.requests.Request` that `RequestScope` places into each HTTP frame.

    The request is constructed from the connection scope alone, which is what
    makes it metadata-only: see `RequestScope` for what that costs and why.

    Args:
        scope: The ASGI connection scope of the request being opened.

    Returns:
        The key to bind the request under, and the request itself.

    Example:
        >>> scope = {
        ...     'type': 'http',
        ...     'method': 'POST',
        ...     'path': '/orders',
        ...     'headers': [(b'x-tenant', b'acme')],
        ... }
        >>> key, request = seed_request(scope)
        >>> key is Request
        True
        >>> request.headers['x-tenant']
        'acme'
    """
    return Request, Request(scope)


class RequestScope(ASGIRequestScope[Scope, Receive, Send]):
    """ASGI middleware that opens a depin async scope around every Starlette request.

    Implemented directly against the ASGI protocol (not Starlette's
    ``BaseHTTPMiddleware``) so streaming responses, server-sent events, and
    WebSockets pass through without buffering.

    The container is published to the connection's context for the duration of
    the scope, so `depin.hosted_container()` reaches it from anywhere inside
    the request.

    A connection scope that is neither ``http`` nor ``websocket`` — the
    lifespan scope above all — is forwarded untouched: no scope is opened and
    nothing is published. A websocket is scoped and hosted exactly like an
    HTTP request, but it is not seeded, because it has no request-body
    semantics and `starlette.requests.Request` is HTTP-shaped.

    For HTTP requests it places a metadata-only `starlette.requests.Request`
    into the active scope frame so scoped providers can read headers, URL,
    cookies, and state. That ``Request`` carries no receive channel: reading
    the body through it raises rather than consuming the stream the route
    handler needs (which would otherwise deadlock against the framework's own
    body parsing). Treat the body as a typed route parameter, not a provider
    input.

    Args:
        app: The downstream ASGI application this middleware wraps.
        container: The frozen container to host for the duration of each
            request. Keyword-or-positional because the framework helpers that
            install middleware pass ``app`` positionally and ``container`` by
            keyword.

    Raises:
        ExceptionGroup: One or more teardowns failed when the request's scope
            closed. Every failure is included; one does not hide another.

    Example:
        Install the middleware once, then resolve scoped providers per request::

            app = Starlette(routes=routes)
            app.add_middleware(RequestScope, container=di)
    """

    __slots__ = ()

    def __init__(self, app: ASGIApp, container: FrozenContainer) -> None:
        super().__init__(app, container, seed=seed_request)
