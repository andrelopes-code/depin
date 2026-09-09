import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.dependencies.models import Dependant
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from starlette.types import Message, Receive, Send
from starlette.types import Scope as ASGIScope

from depin import Container, Scope, hosted_container
from depin._core.scope import active_frame
from depin.errors import FastAPIIntegrationError, OutsideScopeError
from depin.ext import fastapi as fastapi_ext
from depin.ext.fastapi import Inject, RequestScope


def _route(app: FastAPI, path: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path:
            return route
    raise AssertionError(f'no route registered at {path!r}')


def _dependency_call_name(dependency: Dependant) -> str:
    call: object = dependency.call
    return type(call).__name__


def _http_scope(method: str = 'POST', path: str = '/') -> ASGIScope:
    return {
        'type': 'http',
        'method': method,
        'path': path,
        'raw_path': path.encode(),
        'query_string': b'',
        'headers': [(b'content-type', b'application/json'), (b'x-probe', b'meta')],
        'scheme': 'http',
        'server': ('test', 80),
        'client': ('test', 12345),
    }


async def _json_body_receive() -> Message:
    return {'type': 'http.request', 'body': b'{"name": "x"}', 'more_body': False}


@pytest.mark.asyncio
async def test_lifespan_scope_passes_through_without_opening_frame() -> None:
    seen: list[str] = []
    frame_open: list[bool] = []

    async def inner(scope: ASGIScope, receive: Receive, send: Send) -> None:
        seen.append(str(scope['type']))
        try:
            active_frame()
            frame_open.append(True)
        except OutsideScopeError:
            frame_open.append(False)

    mw = RequestScope(inner, Container().freeze())
    await mw({'type': 'lifespan'}, _json_body_receive, _noop_send)
    assert seen == ['lifespan']
    assert frame_open == [False]


@pytest.mark.asyncio
async def test_websocket_scope_opens_frame_and_delegates() -> None:
    seen: list[tuple[str, bool]] = []

    class Connection:
        pass

    async def inner(scope: ASGIScope, receive: Receive, send: Send) -> None:
        in_scope = True
        try:
            hosted_container().resolve(Connection)
        except OutsideScopeError:
            in_scope = False
        seen.append((str(scope['type']), in_scope))

    mw = RequestScope(inner, Container().bind(Connection, scope=Scope.SCOPED).freeze())
    ws_scope: ASGIScope = {'type': 'websocket', 'path': '/ws', 'headers': []}
    await mw(ws_scope, _json_body_receive, _noop_send)
    assert seen == [('websocket', True)]


@pytest.mark.asyncio
async def test_http_request_in_frame_is_metadata_only() -> None:
    captured: dict[str, object] = {}

    async def inner(scope: ASGIScope, receive: Receive, send: Send) -> None:
        req = hosted_container().resolve(FastAPIRequest)
        assert isinstance(req, FastAPIRequest)
        captured['header'] = req.headers.get('x-probe')
        captured['path'] = req.url.path
        try:
            await req.body()
            captured['body'] = 'read'
        except Exception as exc:
            # The metadata-only Request has no receive channel; reading the body
            # must raise here rather than consume the route's stream.
            captured['body_error'] = type(exc).__name__

    mw = RequestScope(inner, Container().scope_value(FastAPIRequest).freeze())
    await mw(_http_scope(), _json_body_receive, _noop_send)
    assert captured['header'] == 'meta'
    assert captured['path'] == '/'
    assert 'body_error' in captured
    assert 'body' not in captured


@pytest.mark.asyncio
async def test_streaming_response_round_trips() -> None:
    async def gen() -> AsyncIterator[bytes]:
        for i in range(3):
            yield f'chunk{i};'.encode()

    app = FastAPI()
    app.add_middleware(RequestScope, container=Container().freeze())

    @app.get('/stream')
    async def _stream() -> StreamingResponse:  # pyright: ignore[reportUnusedFunction]
        return StreamingResponse(gen(), media_type='text/plain')

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/stream')
    assert r.text == 'chunk0;chunk1;chunk2;'


class _Payload(BaseModel):
    name: str


@pytest.mark.asyncio
async def test_route_body_parsing_unaffected_by_metadata_provider() -> None:
    class HeaderProbe:
        def __init__(self, request: FastAPIRequest) -> None:
            self.probe = request.headers.get('x-probe', 'none')

    frozen = Container().scope_value(FastAPIRequest).bind(HeaderProbe, scope=Scope.SCOPED).freeze()
    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.post('/m')
    async def _m(payload: _Payload, probe: Inject[HeaderProbe]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {'name': payload.name, 'probe': probe.probe}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.post('/m', json={'name': 'zoe'}, headers={'x-probe': 'yes'})
    assert r.status_code == 200
    assert r.json() == {'name': 'zoe', 'probe': 'yes'}


@pytest.mark.asyncio
async def test_inject_outside_request_scope_raises_actionable_error() -> None:
    app = FastAPI()  # no RequestScope middleware installed

    @app.get('/x')
    async def _x(svc: Inject[_Service]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {'v': svc.value}

    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        with pytest.raises(Exception, match='RequestScope'):
            _ = await asyncio.wait_for(client.get('/x'), timeout=5.0)


@pytest.mark.asyncio
async def test_install_recompiles_routes_added_with_the_same_container() -> None:
    """A stale installation would leave later direct injections unhosted."""

    class Service:
        value = 3

    container = Container().bind(Service).freeze()
    app = FastAPI()
    fastapi_ext.install(app, container)

    @app.get('/value')
    async def value(service: Inject[Service]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {'value': service.value}

    fastapi_ext.install(app, container)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        response = await client.get('/value')
    assert response.json() == {'value': 3}
    assert len(app.user_middleware) == 1


@pytest.mark.asyncio
async def test_install_rejects_a_different_container() -> None:
    """A second container would make request resolution nondeterministic."""
    app = FastAPI()
    fastapi_ext.install(app, Container().freeze())

    with pytest.raises(FastAPIIntegrationError) as caught:
        fastapi_ext.install(app, Container().freeze())

    message = str(caught.value)
    assert 'different FrozenContainer' in message
    assert 'FastAPI' in message
    assert 'RequestScope' in message


@pytest.mark.asyncio
async def test_install_rejects_an_application_after_its_middleware_stack_is_built() -> None:
    """A late installation cannot reliably wrap an already running application."""
    app = FastAPI()

    @app.get('/plain')
    async def plain() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {'ok': True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        assert (await client.get('/plain')).json() == {'ok': True}

    with pytest.raises(FastAPIIntegrationError, match='before startup'):
        fastapi_ext.install(app, Container().freeze())


def test_install_does_not_mutate_earlier_routes_when_a_later_route_is_malformed() -> None:
    """Missing preflight would leave a partially compiled application behind."""

    class First:
        pass

    class Second:
        pass

    container = Container().bind(First).bind(Second).freeze()
    app = FastAPI()

    @app.get('/first')
    async def first(service: Inject[First]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        del service
        return {'ok': True}

    @app.get('/second')
    async def second(service: Inject[Second]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        del service
        return {'ok': True}

    first_route = _route(app, '/first')
    second_route = _route(app, '/second')
    original_call: object = first_route.dependant.call
    object.__setattr__(second_route.dependant, 'dependencies', ())

    with pytest.raises(FastAPIIntegrationError, match='mutable list'):
        fastapi_ext.install(app, container)

    assert first_route.dependant.call is original_call
    assert _dependency_call_name(first_route.dependant.dependencies[0]) == '_InjectResolver'


class _Service:
    def __init__(self) -> None:
        self.value = 7


async def _noop_send(message: object) -> None:
    return None
