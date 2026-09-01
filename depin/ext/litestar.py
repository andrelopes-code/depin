"""Litestar integration: the shared ASGI middleware, seeded with a `litestar.Request`.

Importing this module requires the ``litestar`` extra (``pip install
'pydepin[litestar]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract and the
framework-free middleware in `depin.ext.asgi`: a seed and a partial
application, nothing more.

`litestar.Request` accepts the bare connection scope: its ``receive`` and
``send`` parameters default to Litestar's ``empty_receive`` and
``empty_send``, which raise when called. The seed therefore constructs the
request from the scope alone, exactly as the Starlette integration does. What
that costs is not the same on the two frameworks — see `RequestScope`.

Litestar types its scope and its two channels as ``TypedDict``s rather than as
mappings of `typing.Any`, so the triple this module hands the shared
middleware is Litestar's own; `depin.ext.asgi.RequestScope` is generic over it
for that reason.

`litestar.Request` is generic in its user, auth, and state types, and both
type checkers reject the unparameterised form. depin keys a binding on the
annotation as written, so the seed binds the widest parameterisation a
provider can be annotated with — ``Request[object, object, State]`` — and that
is the annotation a provider taking the request declares.
"""

from litestar import Request
from litestar.datastructures import State
from litestar.types import ASGIApp, Receive, Scope, Send

from depin import FrozenContainer, ProviderKey
from depin.ext.asgi import RequestScope as ASGIRequestScope


def seed_request(scope: Scope) -> tuple[ProviderKey, object]:
    """Build the `litestar.Request` that `RequestScope` places into each HTTP frame.

    The request is constructed from the connection scope alone, which is what
    makes it metadata-only: see `RequestScope` for what that costs and why.

    Args:
        scope: The ASGI connection scope of the request being opened.

    Returns:
        The key to bind the request under, and the request itself.
    """
    request: Request[object, object, State] = Request(scope)
    return Request[object, object, State], request


class RequestScope(ASGIRequestScope[Scope, Receive, Send]):
    """ASGI middleware that opens a depin async scope around every Litestar request.

    Implemented directly against the ASGI protocol (not a Litestar middleware
    base class) so streaming responses, server-sent events, and WebSockets pass
    through without buffering.

    The container is published to the connection's context for the duration of
    the scope, so `depin.hosted_container()` reaches it from anywhere inside
    the request.

    Only ``http`` and ``websocket`` connections reach it. Litestar answers the
    lifespan scope inside ``Litestar.__call__``, above its middleware stack, so
    unlike the Starlette integration this one is never handed one — which is
    why the connection triple it is typed against is ``Scope``, Litestar's
    union of the two connection scopes, and a lifespan scope would not
    type-check as an argument to it. A websocket is scoped and hosted exactly
    like an HTTP request, but it is not seeded, because it has no request-body
    semantics and `litestar.Request` is HTTP-shaped.

    For HTTP requests it places a `litestar.Request` into the active scope
    frame, under the key ``Request[object, object, State]``, so scoped
    providers can read headers, URL, cookies, and state.

    Do not read the body through that request. It carries no receive channel,
    so it can never take the body from the route handler — but unlike the
    Starlette seed it does not reliably raise either, because
    `litestar.Request` caches the body on ``ScopeState``, which belongs to the
    connection scope and is therefore shared with the request Litestar builds
    for the handler. A read before anything has parsed the body raises
    `RuntimeError` from ``empty_receive``; a read from a handler that declares
    a ``data`` parameter returns the body Litestar has already parsed, with no
    error at all. Treat the body as a typed route parameter, not a provider
    input.

    Args:
        app: The downstream ASGI application this middleware wraps. Litestar
            supplies it by keyword, so the parameter must stay keyword-usable.
        container: The frozen container to host for the duration of each
            request.

    Raises:
        ExceptionGroup: One or more teardowns failed when the request's scope
            closed. Every failure is included; one does not hide another.

    Example:
        Install the middleware once, wrapped so the container reaches the
        constructor Litestar calls with ``app=``::

            app = Litestar(
                route_handlers=[handler],
                middleware=[DefineMiddleware(RequestScope, container=di)],
            )
    """

    __slots__ = ()

    def __init__(self, app: ASGIApp, container: FrozenContainer) -> None:
        super().__init__(app, container, seed=seed_request)
