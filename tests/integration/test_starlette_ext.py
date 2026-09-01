"""The Starlette integration, driven by a real `Starlette` app over a real HTTP client.

`depin.ext.starlette.RequestScope` is the shared ASGI middleware with one seed
applied, so what these tests exercise is the seed and the wiring: the request
object reaches providers, the scope is per request, and it drains when the
request ends.

The app is reached through `httpx.ASGITransport` rather than Starlette's own
``TestClient``, which types its request methods against httpx's private
``_types`` module and so resolves to `Unknown` under both checkers.
"""

from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from depin import Container, FrozenContainer, Scope, hosted_container
from depin.ext.starlette import RequestScope

BODY = b'{"a":1}'
JSON_HEADERS = {'content-type': 'application/json'}


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

    def __init__(self, request: Request) -> None:
        self.probe = request.headers.get('x-probe', 'none')
        self.path = request.url.path


class BodyReader:
    """A provider that reads the body off the seeded request, which is the mistake."""

    def __init__(self, request: Request) -> None:
        self.request = request

    async def read(self) -> bytes:
        return await self.request.body()


def hosted(container: FrozenContainer, *routes: Route) -> AsyncClient:
    app = Starlette(routes=list(routes))
    app.add_middleware(RequestScope, container=container)
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://t')


async def test_a_scoped_provider_is_resolved_once_per_request() -> None:
    async def endpoint(request: Request) -> JSONResponse:
        counter = await hosted_container().aresolve(Counter)
        again = await hosted_container().aresolve(Counter)
        return JSONResponse({'n': counter.tick(), 'again': again.tick()})

    di = Container().bind(Counter, scope=Scope.SCOPED).freeze()
    async with hosted(di, Route('/tick', endpoint)) as client:
        assert (await client.get('/tick')).json() == {'n': 1, 'again': 2}


async def test_two_requests_get_independent_scoped_instances() -> None:
    seen: list[Counter] = []

    async def endpoint(request: Request) -> JSONResponse:
        counter = await hosted_container().aresolve(Counter)
        seen.append(counter)
        return JSONResponse({'n': counter.tick()})

    di = Container().bind(Counter, scope=Scope.SCOPED).freeze()
    async with hosted(di, Route('/tick', endpoint)) as client:
        first = (await client.get('/tick')).json()
        second = (await client.get('/tick')).json()

    assert (first, second) == ({'n': 1}, {'n': 1})
    assert seen[0] is not seen[1]


async def test_the_request_scope_drains_its_teardowns_when_the_request_ends() -> None:
    torn: list[Resource] = []
    torn_while_serving: list[int] = []

    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(item)

    async def endpoint(request: Request) -> JSONResponse:
        _ = await hosted_container().aresolve(Resource)
        torn_while_serving.append(len(torn))
        return JSONResponse({'ok': True})

    di = Container().bind(make, scope=Scope.SCOPED, provides=Resource).freeze()
    async with hosted(di, Route('/res', endpoint)) as client:
        assert (await client.get('/res')).json() == {'ok': True}
        assert len(torn) == 1
        _ = await client.get('/res')
        assert len(torn) == 2

    assert torn_while_serving == [0, 1]


async def test_the_hosted_container_is_reachable_from_a_handler() -> None:
    async def endpoint(request: Request) -> JSONResponse:
        return JSONResponse({'same': hosted_container() is di})

    di = Container().freeze()
    async with hosted(di, Route('/host', endpoint)) as client:
        assert (await client.get('/host')).json() == {'same': True}


async def test_a_provider_reads_headers_off_the_seeded_request() -> None:
    async def endpoint(request: Request) -> JSONResponse:
        found = await hosted_container().aresolve(HeaderProbe)
        return JSONResponse({'probe': found.probe, 'path': found.path})

    di = Container().scope_value(Request).bind(HeaderProbe, scope=Scope.SCOPED).freeze()
    async with hosted(di, Route('/probe/{x}', endpoint)) as client:
        payload = (await client.get('/probe/abc', headers={'x-probe': 'yes'})).json()

    assert payload == {'probe': 'yes', 'path': '/probe/abc'}


@pytest.mark.parametrize(
    'handler_reads_first',
    [
        pytest.param(False, id='the provider reads before the handler'),
        pytest.param(True, id='the handler reads before the provider'),
    ],
)
async def test_the_seeded_request_raises_on_a_body_read(handler_reads_first: bool) -> None:
    """The seed has no receive channel, and `starlette.requests.Request` caches per instance.

    Neither order makes the read succeed, and neither order costs the handler
    its own body: the request Starlette builds for the route is a different
    object with its own ``_body`` and the live receive channel.
    """

    async def endpoint(request: Request) -> JSONResponse:
        read_first = (await request.body()).decode() if handler_reads_first else None
        reader = await hosted_container().aresolve(BodyReader)
        with pytest.raises(RuntimeError, match='Receive channel has not been made available'):
            _ = await reader.read()
        return JSONResponse({'read_first': read_first, 'handler_body': (await request.body()).decode()})

    di = Container().scope_value(Request).bind(BodyReader, scope=Scope.SCOPED).freeze()
    async with hosted(di, Route('/body', endpoint, methods=['POST'])) as client:
        payload = (await client.post('/body', content=BODY, headers=JSON_HEADERS)).json()

    assert payload == {
        'read_first': BODY.decode() if handler_reads_first else None,
        'handler_body': BODY.decode(),
    }
