import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from depin import Container, Scope
from depin._core.scope import active_frame
from depin.errors import OutsideScopeError
from depin.ext.fastapi import Inject, RequestScope


def _http_scope(method: str = 'POST', path: str = '/') -> dict[str, object]:
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


async def _json_body_receive() -> dict[str, object]:
    return {'type': 'http.request', 'body': b'{"name": "x"}', 'more_body': False}


@pytest.mark.asyncio
async def test_lifespan_scope_passes_through_without_opening_frame() -> None:
    seen: list[str] = []
    frame_open: list[bool] = []

    async def inner(scope: dict[str, object], receive: object, send: object) -> None:
        seen.append(str(scope['type']))
        try:
            active_frame()
            frame_open.append(True)
        except OutsideScopeError:
            frame_open.append(False)

    mw = RequestScope(inner, Container().freeze())  # pyright: ignore[reportArgumentType]
    await mw({'type': 'lifespan'}, _json_body_receive, _noop_send)  # pyright: ignore[reportArgumentType]
    assert seen == ['lifespan']
    assert frame_open == [False]


@pytest.mark.asyncio
async def test_websocket_scope_opens_frame_and_delegates() -> None:
    seen: list[tuple[str, bool]] = []

    async def inner(scope: dict[str, object], receive: object, send: object) -> None:
        in_scope = True
        try:
            active_frame()
        except OutsideScopeError:
            in_scope = False
        seen.append((str(scope['type']), in_scope))

    mw = RequestScope(inner, Container().freeze())  # pyright: ignore[reportArgumentType]
    ws_scope: dict[str, object] = {'type': 'websocket', 'path': '/ws', 'headers': []}
    await mw(ws_scope, _json_body_receive, _noop_send)  # pyright: ignore[reportArgumentType]
    assert seen == [('websocket', True)]


@pytest.mark.asyncio
async def test_http_request_in_frame_is_metadata_only() -> None:
    captured: dict[str, object] = {}

    async def inner(scope: dict[str, object], receive: object, send: object) -> None:
        req = active_frame().get(FastAPIRequest)
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

    mw = RequestScope(inner, Container().freeze())  # pyright: ignore[reportArgumentType]
    await mw(_http_scope(), _json_body_receive, _noop_send)  # pyright: ignore[reportArgumentType]
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

    frozen = Container().frame_provides(FastAPIRequest).bind(HeaderProbe, scope=Scope.SCOPED).freeze()
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


class _Service:
    def __init__(self) -> None:
        self.value = 7


async def _noop_send(message: object) -> None:
    return None
