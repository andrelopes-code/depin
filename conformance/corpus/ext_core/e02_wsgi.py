"""`depin.ext.wsgi` against a consumer's own structural environment pair.

`RequestScope` is generic over the environment and the response starter
precisely so a framework outside depin's curated set can install it. This file
is that framework: it declares its own pair and never borrows depin's, so what
it proves is that the middleware adopts whichever pair the application beneath
it declares and still satisfies `WSGIApp` at that pair.

The response starter is the case that makes the genericity load-bearing. The one
declared here takes a third ``exc_info`` argument and returns a writer, which
`depin.ext.wsgi.StartResponse` does not state; a middleware pinned to depin's
own alias would reject this application.

`depin.ext.wsgi` imports no third-party package, so this file is checked in both
install modes.
"""

from collections.abc import Callable, Iterable, MutableMapping
from types import TracebackType
from typing import Protocol

from depin import Container, FrozenContainer, ProviderKey
from depin.ext.wsgi import Environ as WSGIEnviron
from depin.ext.wsgi import RequestScope, WSGIApp
from depin.ext.wsgi import StartResponse as WSGIStartResponse

type Environ = MutableMapping[str, object]
type ExcInfo = tuple[type[BaseException], BaseException, TracebackType]


class StartResponse(Protocol):
    def __call__(
        self, status: str, headers: list[tuple[str, str]], exc_info: ExcInfo | None = None, /
    ) -> Callable[[bytes], object]: ...


class Request:
    def __init__(self, environ: Environ) -> None:
        self.environ = environ


class Application:
    def __call__(self, environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
        _ = start_response('200 OK', [('content-type', 'text/plain')])
        return [b'ok']


def seed(environ: Environ) -> tuple[ProviderKey, object] | None:
    return Request, Request(environ)


def build() -> FrozenContainer:
    return Container().scope_value(Request).freeze()


def install(container: FrozenContainer) -> RequestScope[Environ, StartResponse]:
    return RequestScope(Application(), container, seed=seed)


def the_middleware_is_itself_a_wsgi_app(container: FrozenContainer) -> None:
    _app: WSGIApp[Environ, StartResponse] = install(container)


def the_middleware_is_callable_at_the_pair_it_was_built_with(container: FrozenContainer) -> None:
    _call: Callable[[Environ, StartResponse], Iterable[bytes]] = install(container)


def a_seed_is_a_callable_from_the_environment_to_a_key_and_a_value() -> None:
    _seed: Callable[[Environ], tuple[ProviderKey, object] | None] = seed


def the_middleware_installs_without_a_seed(container: FrozenContainer) -> None:
    _app: WSGIApp[Environ, StartResponse] = RequestScope(Application(), container)


def the_declared_pair_serves_an_application_with_no_framework(container: FrozenContainer) -> None:
    """The other half of the same promise: depin's own pair is a usable one.

    `Environ` and `StartResponse` are what a hand-written application uses when
    no framework is involved, so the middleware must install over them as
    readily as over the consumer's own types above.
    """

    def plain(environ: WSGIEnviron, start_response: WSGIStartResponse) -> Iterable[bytes]:
        _ = environ
        _ = start_response('200 OK', [('content-type', 'text/plain')])
        return [b'ok']

    _app: WSGIApp[WSGIEnviron, WSGIStartResponse] = RequestScope(plain, container)
