"""The ASGI half of every web integration: one scope per request, and nothing else.

This module needs no installation extra and imports no third-party package,
not even under ``TYPE_CHECKING``. ASGI is a structural protocol, so the four
types it needs — application, connection scope, receive channel, send
channel — are declared here with `typing.Protocol` instead of being borrowed
from Starlette. Two consequences follow, and both are the reason for the rule:
the module imports cleanly when no framework is installed, and a framework
outside depin's curated set can install `RequestScope` without depin having to
know about it.

The three awaitable members return `collections.abc.Awaitable` rather than
being declared ``async def``. An ``async def`` member narrows the return to a
coroutine, which would reject the servers and frameworks that hand over a
plain awaitable — Starlette types its own channels that way — even though the
ASGI specification asks only for something awaitable.

Written against depin's public integration contract — `depin.Host` — so it
reaches nothing inside the private package.
"""

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Protocol

from depin import FrozenContainer, Host, ProviderKey

type Message = MutableMapping[str, object]
"""One ASGI event, in either direction."""

type ASGIScope = MutableMapping[str, object]
"""The connection scope: ``scope['type']`` is ``'http'``, ``'websocket'`` or ``'lifespan'``."""


class Receive(Protocol):
    """The channel an ASGI application awaits to read the next inbound event."""

    def __call__(self) -> Awaitable[Message]: ...


class Send(Protocol):
    """The channel an ASGI application awaits to write one outbound event."""

    def __call__(self, message: Message, /) -> Awaitable[None]: ...


class ASGIApp(Protocol):
    """Any ASGI application or middleware: the downstream peer `RequestScope` wraps."""

    def __call__(self, scope: ASGIScope, receive: Receive, send: Send, /) -> Awaitable[None]: ...


class RequestScope:
    """ASGI middleware that opens one depin async scope around every request.

    Implemented directly against the ASGI protocol rather than a framework's
    HTTP-middleware base class, so streaming responses, server-sent events and
    WebSockets pass through without buffering. Every ASGI integration depin
    ships specialises this class, supplying only the ``seed`` that places its
    own framework's request object into the frame.

    Connection scopes other than ``http`` and ``websocket`` are forwarded
    untouched, with no depin scope opened. The lifespan scope in particular is
    opened once at startup and lives for the whole process: wrapping it would
    leak a frame for the application's lifetime and put startup and shutdown
    inside a scope that never drains.

    For the scopes it does wrap, the container is published to the request's
    context for the duration of the scope, so `depin.hosted_container()`
    reaches it from anywhere inside the request. The scope's teardowns run when
    the request ends — including when it ends by raising — and the publication
    is undone after them.

    ``seed`` is applied to ``http`` connections only. A websocket connection
    has no request-body semantics, and the framework request classes the seeds
    construct are HTTP-shaped; a websocket therefore gets the scope and the
    published container, but no seeded request.

    Args:
        app: The downstream ASGI application this middleware wraps.
        container: The frozen container to host for the duration of each
            request. Keyword-or-positional because the framework helpers that
            install middleware pass ``app`` positionally and ``container`` by
            keyword.
        seed: Called once per ``http`` connection, before the downstream
            application runs, to produce the key and value to place into the
            fresh scope frame. Returning ``None`` seeds nothing. Omitting it
            seeds nothing either.

    Raises:
        ExceptionGroup: One or more teardowns failed when the request's scope
            closed. Every failure is included; one does not hide another.

    Example:
        Install the middleware once, per the wrapping framework's own idiom::

            middleware = RequestScope(app, di, seed=lambda scope: (Request, Request(scope)))
    """

    __slots__ = ('_app', '_host', '_seed')

    def __init__(
        self,
        app: ASGIApp,
        container: FrozenContainer,
        *,
        seed: Callable[[ASGIScope], tuple[ProviderKey, object] | None] | None = None,
    ) -> None:
        self._app = app
        self._host = Host(container)
        self._seed = seed

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self._app(scope, receive, send)
            return
        async with self._host.ascope() as frame:
            if self._seed is not None and scope['type'] == 'http':
                seeded = self._seed(scope)
                if seeded is not None:
                    frame.provide(*seeded)
            await self._app(scope, receive, send)
