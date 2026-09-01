"""Litestar integration: the shared ASGI middleware, seeded with a `litestar.Request`.

Importing this module requires the ``litestar`` extra (``pip install
'pydepin[litestar]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract and the
framework-free middleware in `depin.ext.asgi`: a seed and a partial
application, nothing more.

`litestar.Request` accepts the bare connection scope: its ``receive`` and
``send`` parameters default to Litestar's ``empty_receive`` and
``empty_send``, which raise when called. The seed therefore constructs the
request from the scope alone, exactly as the Starlette integration does, and
the request it seeds is metadata-only for the same reason — see `RequestScope`.

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

    A connection scope that is neither ``http`` nor ``websocket`` — the
    lifespan scope above all — is forwarded untouched: no scope is opened and
    nothing is published. A websocket is scoped and hosted exactly like an HTTP
    request, but it is not seeded, because it has no request-body semantics and
    `litestar.Request` is HTTP-shaped.

    For HTTP requests it places a metadata-only `litestar.Request` into the
    active scope frame, under the key ``Request[object, object, State]``, so
    scoped providers can read headers, URL, cookies, and state. That
    ``Request`` carries no receive channel: reading the body
    through it raises rather than consuming the stream the route handler needs
    (which would otherwise deadlock against the framework's own body parsing).
    Treat the body as a typed route parameter, not a provider input.

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
