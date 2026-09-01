"""The Litestar integration, driven by a real `Litestar` app over a real HTTP client.

`depin.ext.litestar.RequestScope` is the shared ASGI middleware with one seed
applied, so what these tests exercise is the seed and the wiring: the request
object reaches providers, the scope is per request, and it drains when the
request ends.

The app is reached through Litestar's own ``AsyncTestClient``, which — unlike
Starlette's ``TestClient``, the reason that suite falls back to
`httpx.ASGITransport` — types cleanly under both checkers.
`httpx.ASGITransport` is not an option here: it declares its application as
taking ``MutableMapping[str, Any]``, and Litestar's ``__call__`` takes
``TypedDict``s, so a `Litestar` instance is not assignable to it.
"""

from collections.abc import Generator

import pytest
from litestar import Litestar, Request, get, post
from litestar.datastructures import State
from litestar.handlers import HTTPRouteHandler
from litestar.middleware import DefineMiddleware
from litestar.testing import AsyncTestClient

from depin import Container, FrozenContainer, Scope, hosted_container
from depin.ext.litestar import RequestScope


class Counter:
    """A scoped dependency whose identity distinguishes one request from the next."""

    def __init__(self) -> None:
        self.value = 0

    def tick(self) -> int:
        self.value += 1
        return self.value


class Resource:
    """A scoped dependency whose teardown the tests count."""


class HeaderProbe:
    """A provider whose only input is the seeded request."""

    def __init__(self, request: Request[object, object, State]) -> None:
        self.probe = request.headers.get('x-probe', 'none')
        self.path = request.url.path


class BodyReader:
    """A provider that reads the body off the seeded request, which is the mistake."""

    def __init__(self, request: Request[object, object, State]) -> None:
        self.request = request

    async def read(self) -> bytes:
        return await self.request.body()


def hosting_a_body_reader() -> FrozenContainer:
    return Container().scope_value(Request[object, object, State]).bind(BodyReader, scope=Scope.SCOPED).freeze()


def hosted(container: FrozenContainer, *handlers: HTTPRouteHandler) -> AsyncTestClient[Litestar]:
    app = Litestar(
        route_handlers=list(handlers),
        middleware=[DefineMiddleware(RequestScope, container=container)],
    )
    return AsyncTestClient(app=app)


async def test_a_scoped_provider_is_resolved_once_per_request() -> None:
    @get('/tick')
    async def endpoint() -> dict[str, int]:
        counter = await hosted_container().aresolve(Counter)
        again = await hosted_container().aresolve(Counter)
        return {'n': counter.tick(), 'again': again.tick()}

    di = Container().bind(Counter, scope=Scope.SCOPED).freeze()
    async with hosted(di, endpoint) as client:
        assert (await client.get('/tick')).json() == {'n': 1, 'again': 2}


async def test_two_requests_get_independent_scoped_instances() -> None:
    seen: list[int] = []

    @get('/tick')
    async def endpoint() -> dict[str, int]:
        counter = await hosted_container().aresolve(Counter)
        seen.append(id(counter))
        return {'n': counter.tick()}

    di = Container().bind(Counter, scope=Scope.SCOPED).freeze()
    async with hosted(di, endpoint) as client:
        first = (await client.get('/tick')).json()
        second = (await client.get('/tick')).json()

    assert (first, second) == ({'n': 1}, {'n': 1})
    assert seen[0] != seen[1]


async def test_the_request_scope_drains_its_teardowns_when_the_request_ends() -> None:
    torn: list[Resource] = []
    torn_while_serving: list[int] = []

    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(item)

    @get('/res')
    async def endpoint() -> dict[str, bool]:
        _ = await hosted_container().aresolve(Resource)
        torn_while_serving.append(len(torn))
        return {'ok': True}

    di = Container().bind(make, scope=Scope.SCOPED, provides=Resource).freeze()
    async with hosted(di, endpoint) as client:
        assert (await client.get('/res')).json() == {'ok': True}
        assert len(torn) == 1
        _ = await client.get('/res')
        assert len(torn) == 2

    assert torn_while_serving == [0, 1]


async def test_the_hosted_container_is_reachable_from_a_handler() -> None:
    @get('/host')
    async def endpoint() -> dict[str, bool]:
        return {'same': hosted_container() is di}

    di = Container().freeze()
    async with hosted(di, endpoint) as client:
        assert (await client.get('/host')).json() == {'same': True}


async def test_a_provider_reads_headers_off_the_seeded_request() -> None:
    @get('/probe/{x:str}')
    async def endpoint() -> dict[str, str]:
        found = await hosted_container().aresolve(HeaderProbe)
        return {'probe': found.probe, 'path': found.path}

    di = Container().scope_value(Request[object, object, State]).bind(HeaderProbe, scope=Scope.SCOPED).freeze()
    async with hosted(di, endpoint) as client:
        payload = (await client.get('/probe/abc', headers={'x-probe': 'yes'})).json()

    assert payload == {'probe': 'yes', 'path': '/probe/abc'}


async def test_the_seeded_request_raises_when_nothing_has_parsed_the_body_yet() -> None:
    """With no ``data`` parameter to trigger Litestar's own parse, the seed hits ``empty_receive``.

    The `RuntimeError` carries no message, so only its type is asserted. The
    handler's own request still yields the body: the seed reaches no receive
    channel and so can take nothing from it.
    """

    @post('/body')
    async def endpoint(request: Request[object, object, State]) -> dict[str, str]:
        reader = await hosted_container().aresolve(BodyReader)
        with pytest.raises(RuntimeError):
            _ = await reader.read()
        return {'handler_body': (await request.body()).decode()}

    async with hosted(hosting_a_body_reader(), endpoint) as client:
        assert (await client.post('/body', json={'a': 1})).json() == {'handler_body': '{"a":1}'}


async def test_the_seeded_request_replays_the_body_the_handler_declared() -> None:
    """`litestar.Request` caches the body on ``ScopeState``, which is scope-level, not per instance.

    Litestar parses ``data`` before the handler runs, so by the time the
    provider resolves, the cache the seed reads is already filled and the read
    returns rather than raising. The handler's ``data`` is unaffected — the
    seed replays the cache, it does not consume a stream — which is why the
    guarantee this pins is safety, not a raise.
    """

    @post('/body')
    async def endpoint(data: dict[str, int]) -> dict[str, object]:
        reader = await hosted_container().aresolve(BodyReader)
        return {'data': data, 'seen': (await reader.read()).decode()}

    async with hosted(hosting_a_body_reader(), endpoint) as client:
        payload = (await client.post('/body', json={'a': 1})).json()

    assert payload == {'data': {'a': 1}, 'seen': '{"a":1}'}
