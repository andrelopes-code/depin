"""The WSGI half of every web integration: one scope per request, and nothing else.

This module needs no installation extra and imports no third-party package,
not even under ``TYPE_CHECKING``. WSGI is a structural protocol, so the three
types it needs — application, environment, response starter — are declared here
with `typing.Protocol` instead of being borrowed from a framework. Two
consequences follow, and both are the reason for the rule: the module imports
cleanly when no framework is installed, and a framework outside depin's curated
set can install `RequestScope` without depin having to know about it.

Written against depin's public integration contract — `depin.Host` — so it
reaches nothing inside the private package.
"""

from collections.abc import Callable, Iterable, MutableMapping
from typing import Protocol

from depin import FrozenContainer, Host, ProviderKey

type Environ = MutableMapping[str, object]
"""The per-request environment: CGI variables plus the ``wsgi.*`` server keys."""


class StartResponse(Protocol):
    """The callable a WSGI application invokes to begin the response."""

    def __call__(self, status: str, headers: list[tuple[str, str]], /) -> object: ...


class WSGIApp(Protocol):
    """Any WSGI application or middleware: the downstream peer `RequestScope` wraps."""

    def __call__(self, environ: Environ, start_response: StartResponse, /) -> Iterable[bytes]: ...


class RequestScope:
    """WSGI middleware that opens one depin scope around every request.

    Implemented directly against the WSGI protocol rather than a framework's
    own middleware base class, so every WSGI integration depin ships
    specialises this class, supplying only the ``seed`` that places its own
    framework's request object into the frame.

    The container is published to the request's context for the duration of
    the scope, so `depin.hosted_container()` reaches it from anywhere inside
    the request. The scope's teardowns run when the downstream application
    returns — including when it returns by raising — and the publication is
    undone after them.

    The scope ends when the application returns, not when the response is
    finished. WSGI hands the server an iterable that the server consumes after
    the application has returned, and it offers no hook that outlives that
    return, so a streaming body cannot resolve: by the time the server pulls
    the first chunk the scope has drained and the container is no longer
    published. Resolve everything a streaming response needs before returning
    the iterable, and close over the values. The alternative — materialising
    the body into a list before returning it — would buy streaming safety by
    buffering every response in memory, which is a worse default than the
    boundary being stated, and it would defeat the one thing WSGI streaming is
    for. ASGI has no such limit; `depin.ext.asgi.RequestScope` keeps the scope
    open for the whole response.

    Args:
        app: The downstream WSGI application this middleware wraps.
        container: The frozen container to host for the duration of each
            request. Keyword-or-positional because the framework helpers that
            install middleware pass ``app`` positionally and ``container`` by
            keyword.
        seed: Called once per request, before the downstream application runs,
            to produce the key and value to place into the fresh scope frame.
            Returning ``None`` seeds nothing. Omitting it seeds nothing either.

    Raises:
        TeardownError: An async provider left a teardown in the request's
            synchronous scope. A WSGI application cannot await, so an async
            provider has no place in one.
        ExceptionGroup: One or more teardowns failed when the request's scope
            closed. Every failure is included; one does not hide another.

    Example:
        Install the middleware once, per the wrapping framework's own idiom::

            app.wsgi_app = RequestScope(app.wsgi_app, di, seed=lambda environ: (Request, Request(environ)))
    """

    __slots__ = ('_app', '_host', '_seed')

    def __init__(
        self,
        app: WSGIApp,
        container: FrozenContainer,
        *,
        seed: Callable[[Environ], tuple[ProviderKey, object] | None] | None = None,
    ) -> None:
        self._app = app
        self._host = Host(container)
        self._seed = seed

    def __call__(self, environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
        with self._host.scope() as frame:
            if self._seed is not None:
                seeded = self._seed(environ)
                if seeded is not None:
                    frame.provide(*seeded)
            return self._app(environ, start_response)
