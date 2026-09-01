"""`depin.ext.asgi` against a consumer's own structural connection triple.

`RequestScope` is generic over scope, receive and send precisely so a framework
outside depin's curated set can install it. This file is that framework: it
declares its own three types and never borrows depin's, so what it proves is
that the bound `ScopeT: ASGIScope` admits a consumer's own mapping and that the
middleware still satisfies `ASGIApp` at the triple it was built with.

`depin.ext.asgi` imports no third-party package, so this file is checked in
both install modes.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from depin import Container, FrozenContainer, ProviderKey
from depin.ext.asgi import ASGIApp, RequestScope

type Scope = Mapping[str, object]
type Event = Mapping[str, object]


class Receive(Protocol):
    def __call__(self) -> Awaitable[Event]: ...


class Send(Protocol):
    def __call__(self, event: Event, /) -> Awaitable[None]: ...


class Request:
    def __init__(self, scope: Scope) -> None:
        self.scope = scope


class Application:
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({'type': 'http.response.start', 'status': 200})


def seed(scope: Scope) -> tuple[ProviderKey, object] | None:
    return Request, Request(scope)


def build() -> FrozenContainer:
    return Container().freeze()


def install(container: FrozenContainer) -> RequestScope[Scope, Receive, Send]:
    return RequestScope(Application(), container, seed=seed)


def the_middleware_is_itself_an_asgi_app(container: FrozenContainer) -> None:
    _app: ASGIApp[Scope, Receive, Send] = install(container)


def a_seed_is_a_callable_from_scope_to_a_key_and_a_value() -> None:
    _seed: Callable[[Scope], tuple[ProviderKey, object] | None] = seed
