"""Flask integration: the shared WSGI middleware, seeded with a `flask.Request`.

Importing this module requires the ``flask`` extra (``pip install
'pydepin[flask]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract and the
framework-free middleware in `depin.ext.wsgi`: a seed and a partial
application, nothing more.

The seed binds `flask.Request`, the class, and not ``flask.request``, the
proxy. The proxy is bound to Flask's own application context, which depin
neither opens nor closes; providing it would tie a depin scope to a context
depin does not control, and it would resolve to whichever request that context
happens to hold rather than the one this scope was opened for.

Flask hosts a WSGI middleware as an instance on ``app.wsgi_app`` rather than
taking a class the way the ASGI frameworks do — see `RequestScope` for what
that means at the call site.

The environment and the response starter are named from `wsgiref.types`, the
standard library's own WSGI vocabulary, which is what Flask's signatures are
written against. A middleware both takes those two values from the server and
hands them to the application below, so its types have to be the framework's
exactly rather than merely wide enough to cover them; that is why
`depin.ext.wsgi.RequestScope` is generic over the pair, and why the aliases it
declares for a hand-written application are not the ones used here.
"""

from wsgiref.types import StartResponse, WSGIApplication, WSGIEnvironment

from flask import Request

from depin import FrozenContainer, ProviderKey
from depin.ext.wsgi import RequestScope as WSGIRequestScope


def seed_request(environ: WSGIEnvironment) -> tuple[ProviderKey, object]:
    """Build the `flask.Request` that `RequestScope` places into each request frame.

    Args:
        environ: The WSGI environment of the request being opened.

    Returns:
        The key to bind the request under, and the request itself.
    """
    return Request, Request(environ)


class RequestScope(WSGIRequestScope[WSGIEnvironment, StartResponse]):
    """WSGI middleware that opens a depin scope around every Flask request.

    Implemented directly against the WSGI protocol, so it wraps the whole
    application — including the error handling and the teardown callbacks
    Flask runs inside ``wsgi_app``.

    The container is published to the request's context for the duration of
    the scope, so `depin.hosted_container()` reaches it from anywhere inside
    the request. It places a `flask.Request` built from the environment into
    the active scope frame, so scoped providers can read headers, URL,
    cookies, and form data without touching Flask's own context locals.

    Unlike the ASGI integrations, which hand the framework the class and let it
    construct the middleware, Flask is given an instance: ``app.wsgi_app`` is
    the application, and wrapping it is an assignment. The wrapping is
    therefore explicit about order — install it once, after any other
    ``wsgi_app`` wrapper whose work should happen inside the depin scope.

    Flask declares ``wsgi_app`` as a method, so mypy reports ``method-assign``
    on the assignment below — for this middleware exactly as it does for every
    other WSGI middleware, ``ProxyFix`` included. Waive it at that one line, or
    keep the wrapper as the object the server is pointed at
    (``application = RequestScope(app.wsgi_app, di)``) and leave the Flask
    instance alone.

    The scope ends when the application returns, not when the response is
    finished, which is a limit of WSGI rather than of Flask: a streaming
    response's body is pulled by the server after `RequestScope` has drained,
    so nothing inside a streaming generator can resolve. Resolve what the
    generator needs before returning the response and close over the values.
    `depin.ext.wsgi.RequestScope` states the whole trade-off.

    Args:
        app: The downstream WSGI application this middleware wraps — normally
            ``app.wsgi_app``, read before it is reassigned.
        container: The frozen container to host for the duration of each
            request.

    Raises:
        TeardownError: An async provider left a teardown in the request's
            synchronous scope. A WSGI application cannot await, so an async
            provider has no place in one.
        ExceptionGroup: One or more teardowns failed when the request's scope
            closed. Every failure is included; one does not hide another.

    Example:
        Install the middleware once, by wrapping the application in place::

            app = Flask(__name__)
            app.wsgi_app = RequestScope(app.wsgi_app, di)
    """

    __slots__ = ()

    def __init__(self, app: WSGIApplication, container: FrozenContainer) -> None:
        super().__init__(app, container, seed=seed_request)
