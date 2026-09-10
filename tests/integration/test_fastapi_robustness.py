import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager

import fastapi.dependencies.models as fastapi_models
import pytest
from fastapi import BackgroundTasks, Depends, FastAPI, Security, WebSocket
from fastapi import Request as FastAPIRequest
from fastapi.dependencies.models import Dependant
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPBearer
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from starlette.types import Message, Receive, Send
from starlette.types import Scope as ASGIScope

from depin import Container, FrozenContainer, Host, Scope, hosted_container, optional_hosted_container
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
    async def _stream() -> StreamingResponse:
        return StreamingResponse(gen(), media_type='text/plain')

    _ = _stream

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
    async def _m(payload: _Payload, probe: Inject[HeaderProbe]) -> dict[str, str]:
        return {'name': payload.name, 'probe': probe.probe}

    _ = _m

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.post('/m', json={'name': 'zoe'}, headers={'x-probe': 'yes'})
    assert r.status_code == 200
    assert r.json() == {'name': 'zoe', 'probe': 'yes'}


@pytest.mark.asyncio
async def test_inject_outside_request_scope_raises_actionable_error() -> None:
    app = FastAPI()  # no RequestScope middleware installed

    @app.get('/x')
    async def _x(svc: Inject[_Service]) -> dict[str, int]:
        return {'v': svc.value}

    _ = _x

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
    async def value(service: Inject[Service]) -> dict[str, int]:
        return {'value': service.value}

    _ = value

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
    async def plain() -> dict[str, bool]:
        return {'ok': True}

    _ = plain

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
    async def first(service: Inject[First]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = first

    @app.get('/second')
    async def second(service: Inject[Second]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = second

    first_route = _route(app, '/first')
    second_route = _route(app, '/second')
    original_call: object = first_route.dependant.call
    object.__setattr__(second_route.dependant, 'dependencies', ())

    with pytest.raises(FastAPIIntegrationError, match='mutable list'):
        fastapi_ext.install(app, container)

    assert first_route.dependant.call is original_call
    assert _dependency_call_name(first_route.dependant.dependencies[0]) == '_InjectResolver'


def test_install_does_not_rebuild_when_a_later_route_handler_is_unavailable() -> None:
    """Installed routes keep FastAPI's original route applications."""

    class First:
        pass

    class Second:
        pass

    app = FastAPI()

    @app.get('/first')
    async def first(service: Inject[First]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = first

    @app.get('/second')
    async def second(service: Inject[Second]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = second

    first_route = _route(app, '/first')
    second_route = _route(app, '/second')

    def fail_rebuild() -> object:
        raise RuntimeError('rebuild failed')

    object.__setattr__(second_route, 'get_route_handler', fail_rebuild)
    original_app: object = first_route.app
    second_app: object = second_route.app

    fastapi_ext.install(app, Container().bind(First).bind(Second).freeze())

    assert first_route.app is original_app
    assert second_route.app is second_app


def test_install_does_not_call_a_route_handler_rebuild_with_an_arbitrary_failure() -> None:
    """A stale rebuild seam does not affect installation."""

    class First:
        pass

    class Second:
        pass

    app = FastAPI()

    @app.get('/first')
    async def first(service: Inject[First]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = first

    @app.get('/second')
    async def second(service: Inject[Second]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = second

    first_route = _route(app, '/first')
    second_route = _route(app, '/second')

    def fail_rebuild() -> object:
        raise ValueError('unexpected rebuild failure')

    object.__setattr__(second_route, 'get_route_handler', fail_rebuild)
    original_app: object = first_route.app

    fastapi_ext.install(app, Container().bind(First).bind(Second).freeze())

    assert first_route.app is original_app


def test_install_rejects_an_invalid_application_shape_without_mutating_routes() -> None:
    """Application preflight must translate internal shape failures."""

    class Service:
        pass

    app = FastAPI()

    @app.get('/value')
    async def value(service: Inject[Service]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = value

    route = _route(app, '/value')
    original_call: object = route.dependant.call
    object.__setattr__(app, 'user_middleware', None)

    with pytest.raises(FastAPIIntegrationError, match='application'):
        fastapi_ext.install(app, Container().bind(Service).freeze())

    assert route.dependant.call is original_call


def _request_identity_compatibility_setup(app: FastAPI, container: FrozenContainer) -> None:
    app.add_middleware(RequestScope, container=container)


@pytest.mark.parametrize('setup', [_request_identity_compatibility_setup, fastapi_ext.install])
@pytest.mark.asyncio
async def test_setup_uses_the_actual_request_after_an_earlier_native_dependency_reads_its_body(
    setup: Callable[[FastAPI, FrozenContainer], None],
) -> None:
    """A synthetic middleware request would lose identity and receive semantics."""
    seen: list[FastAPIRequest] = []

    class Probe:
        def __init__(self, request: FastAPIRequest) -> None:
            self.request = request

    async def native(request: FastAPIRequest) -> None:
        assert await request.json() == {'name': 'zoe'}
        seen.append(request)

    app = FastAPI()

    @app.post('/body', dependencies=[Depends(native)])
    async def body(probe: Inject[Probe], request: FastAPIRequest) -> dict[str, bool]:
        return {'same': probe.request is request and seen == [request]}

    _ = body
    setup(app, Container().scope_value(FastAPIRequest).bind(Probe, scope=Scope.SCOPED).freeze())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        response = await client.post('/body', json={'name': 'zoe'})
    assert response.json() == {'same': True}


class _Service:
    def __init__(self) -> None:
        self.value = 7


async def _noop_send(message: object) -> None:
    return None


type _Setup = Callable[[FastAPI, FrozenContainer], None]


def _compatibility_setup(app: FastAPI, container: FrozenContainer) -> None:
    app.add_middleware(RequestScope, container=container)


def _optimized_setup(app: FastAPI, container: FrozenContainer) -> None:
    fastapi_ext.install(app, container)


class _MixedPayload(BaseModel):
    name: str


def _mixed_application(setup: _Setup) -> tuple[FastAPI, list[str]]:
    events: list[str] = []

    class Singleton:
        def __init__(self) -> None:
            events.append('singleton')

    class Transient:
        def __init__(self) -> None:
            events.append('transient')

    class Tenant:
        def __init__(self, request: FastAPIRequest) -> None:
            self.name = request.headers['x-tenant']
            events.append('scoped')

    class Resource:
        pass

    async def resource() -> AsyncIterator[Resource]:
        events.append('resource')
        yield Resource()
        events.append('close')

    async def native() -> None:
        events.append('dependency')

    security = HTTPBearer(auto_error=False)
    container = (
        Container()
        .scope_value(FastAPIRequest)
        .bind(Singleton)
        .bind(Transient, scope=Scope.TRANSIENT)
        .bind(Tenant, scope=Scope.SCOPED)
        .bind(resource, scope=Scope.SCOPED)
        .freeze()
    )
    app = FastAPI()

    @app.post('/users/{user_id}', dependencies=[Depends(native)])
    async def user(
        user_id: int,
        active: bool,
        payload: _MixedPayload,
        singleton: Inject[Singleton],
        transient: Inject[Transient],
        tenant: Inject[Tenant],
        resource_value: Inject[Resource],
        token: str | None = Security(security),
    ) -> dict[str, object]:
        del singleton, transient, resource_value
        events.append('handler')
        return {'id': user_id, 'active': active, 'name': payload.name, 'tenant': tenant.name, 'token': token}

    _ = user
    setup(app, container)
    return app, events


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_mixed_fastapi_inputs_remain_equivalent(setup: _Setup) -> None:
    app, events = _mixed_application(setup)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        response = await client.post('/users/7?active=true', json={'name': 'Ada'}, headers={'x-tenant': 'acme'})

    assert response.status_code == 200
    assert response.json() == {'id': 7, 'active': True, 'name': 'Ada', 'tenant': 'acme', 'token': None}
    assert events == ['dependency', 'singleton', 'transient', 'scoped', 'resource', 'handler', 'close']


@pytest.mark.asyncio
async def test_optimized_openapi_and_validation_match_compatibility() -> None:
    compatibility = _mixed_application(_compatibility_setup)[0]
    optimized = _mixed_application(_optimized_setup)[0]
    compatibility_transport = ASGITransport(app=compatibility)
    optimized_transport = ASGITransport(app=optimized)
    async with (
        AsyncClient(transport=compatibility_transport, base_url='http://t') as compatibility_client,
        AsyncClient(transport=optimized_transport, base_url='http://t') as optimized_client,
    ):
        compatibility_response = await compatibility_client.post(
            '/users/not-an-int?active=true', json={'name': 1}, headers={'x-tenant': 'acme'}
        )
        optimized_response = await optimized_client.post(
            '/users/not-an-int?active=true', json={'name': 1}, headers={'x-tenant': 'acme'}
        )

    assert optimized.openapi() == compatibility.openapi()
    assert optimized_response.status_code == compatibility_response.status_code == 422
    assert optimized_response.json() == compatibility_response.json()


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_sync_handler_and_background_task_drain_before_scope_closes(setup: _Setup) -> None:
    events: list[str] = []

    class Resource:
        pass

    async def resource() -> AsyncIterator[Resource]:
        events.append('construct')
        yield Resource()
        events.append('close')

    container = Container().bind(resource, scope=Scope.SCOPED).freeze()
    app = FastAPI()

    @app.get('/background')
    def background(tasks: BackgroundTasks, resource_value: Inject[Resource]) -> dict[str, bool]:
        del resource_value
        tasks.add_task(events.append, 'background')
        events.append('handler')
        return {'ok': True}

    _ = background
    setup(app, container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        response = await client.get('/background')

    assert response.json() == {'ok': True}
    assert events == ['construct', 'handler', 'background', 'close']


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_streaming_response_drains_resource_after_final_body_event(setup: _Setup) -> None:
    events: list[str] = []

    class Resource:
        pass

    async def resource() -> AsyncIterator[Resource]:
        events.append('construct')
        yield Resource()
        events.append('close')

    async def chunks() -> AsyncIterator[bytes]:
        events.append('first-body')
        yield b'first;'
        events.append('last-body')
        yield b'last;'

    container = Container().bind(resource, scope=Scope.SCOPED).freeze()
    app = FastAPI()

    @app.get('/stream')
    async def stream(resource_value: Inject[Resource]) -> StreamingResponse:
        del resource_value
        return StreamingResponse(chunks(), media_type='text/plain')

    _ = stream
    _ = stream
    setup(app, container)
    received = False
    disconnected = asyncio.Event()

    async def receive() -> Message:
        nonlocal received
        if not received:
            received = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await disconnected.wait()
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        if message['type'] == 'http.response.body' and message.get('more_body') is False:
            events.append('terminal-body')

    await app(_http_scope('GET', '/stream'), receive, send)

    assert events == ['construct', 'first-body', 'last-body', 'terminal-body', 'close']


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_two_concurrent_scoped_requests_do_not_share_a_frame(setup: _Setup) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    arrived = 0
    identifiers: list[int] = []

    class Scoped:
        pass

    container = Container().bind(Scoped, scope=Scope.SCOPED).freeze()
    app = FastAPI()

    @app.get('/concurrent')
    async def concurrent(scoped: Inject[Scoped]) -> dict[str, int]:
        nonlocal arrived
        identifiers.append(id(scoped))
        arrived += 1
        if arrived == 2:
            entered.set()
        await release.wait()
        return {'id': id(scoped)}

    _ = concurrent
    setup(app, container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        first = asyncio.create_task(client.get('/concurrent'))
        second = asyncio.create_task(client.get('/concurrent'))
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        assert len(set(identifiers)) == 2
        release.set()
        first_response, second_response = await asyncio.gather(first, second)

    assert first_response.json()['id'] != second_response.json()['id']


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_websocket_closes_scoped_resource_after_close_event(setup: _Setup) -> None:
    events: list[str] = []

    class Connection:
        pass

    async def connection() -> AsyncIterator[Connection]:
        events.append('construct')
        yield Connection()
        events.append('close')

    app = FastAPI()

    @app.websocket('/ws')
    async def websocket(socket: WebSocket) -> None:
        _ = await hosted_container().aresolve(Connection)
        await socket.accept()
        await socket.send_text('ready')
        await socket.close()

    _ = websocket
    _ = websocket
    setup(app, Container().bind(connection, scope=Scope.SCOPED).freeze())
    receive_events = iter(({'type': 'websocket.connect'},))

    async def receive() -> Message:
        return next(receive_events)

    async def send(message: Message) -> None:
        if message['type'] == 'websocket.close':
            events.append('terminal-close')

    await app(
        {'type': 'websocket', 'path': '/ws', 'raw_path': b'/ws', 'headers': [], 'query_string': b''}, receive, send
    )

    assert events == ['construct', 'terminal-close', 'close']


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.parametrize('failure', ['handler', 'provider'])
@pytest.mark.asyncio
async def test_handler_and_provider_failures_preserve_lifecycle(setup: _Setup, failure: str) -> None:
    events: list[str] = []

    class Resource:
        pass

    def provider() -> Resource:
        events.append('provider')
        raise RuntimeError('provider failure')

    async def resource() -> AsyncIterator[Resource]:
        events.append('construct')
        yield Resource()
        events.append('close')

    container = (
        Container().bind(provider, provides=Resource, scope=Scope.SCOPED).freeze()
        if failure == 'provider'
        else Container().bind(resource, scope=Scope.SCOPED).freeze()
    )
    app = FastAPI()

    @app.get('/failure')
    async def endpoint(value: Inject[Resource]) -> dict[str, bool]:
        del value
        events.append('handler')
        raise RuntimeError('handler failure')

    _ = endpoint
    setup(app, container)
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        with pytest.raises(RuntimeError, match=f'{failure} failure'):
            await client.get('/failure')

    assert events == (['provider'] if failure == 'provider' else ['construct', 'handler', 'close'])


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_body_and_teardown_failures_keep_both_errors_in_order(setup: _Setup) -> None:
    events: list[str] = []

    class Resource:
        pass

    async def resource() -> AsyncIterator[Resource]:
        events.append('construct')
        yield Resource()
        events.append('teardown')
        raise RuntimeError('teardown failure')

    app = FastAPI()

    async def body() -> AsyncIterator[bytes]:
        events.append('response-body')
        yield b'partial'
        raise RuntimeError('body failure')

    @app.get('/failure')
    async def endpoint(value: Inject[Resource]) -> StreamingResponse:
        del value
        return StreamingResponse(body())

    _ = endpoint
    setup(app, Container().bind(resource, scope=Scope.SCOPED).freeze())
    request_sent = False
    disconnected = asyncio.Event()

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await disconnected.wait()
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        if message['type'] == 'http.response.body' and message.get('more_body') is True:
            events.append('sent-body')

    with pytest.raises(ExceptionGroup) as caught:
        await app(_http_scope('GET', '/failure'), receive, send)

    assert [type(error) for error in caught.value.exceptions] == [RuntimeError, RuntimeError]
    assert [str(error) for error in caught.value.exceptions] == ['body failure', 'teardown failure']
    assert events == ['construct', 'response-body', 'sent-body', 'teardown']


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_multiple_resources_close_in_reverse_construction_order(setup: _Setup) -> None:
    events: list[str] = []

    class First:
        pass

    class Second:
        pass

    async def first() -> AsyncIterator[First]:
        events.append('first-open')
        yield First()
        events.append('first-close')

    async def second(value: First) -> AsyncIterator[Second]:
        del value
        events.append('second-open')
        yield Second()
        events.append('second-close')

    app = FastAPI()

    @app.get('/resources')
    async def endpoint(value: Inject[Second]) -> dict[str, bool]:
        del value
        events.append('handler')
        return {'ok': True}

    _ = endpoint
    setup(app, Container().bind(first, scope=Scope.SCOPED).bind(second, scope=Scope.SCOPED).freeze())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        assert (await client.get('/resources')).json() == {'ok': True}

    assert events == ['first-open', 'second-open', 'handler', 'second-close', 'first-close']


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_request_override_does_not_escape_its_context(setup: _Setup) -> None:
    class Service:
        value = 'real'

    class FakeService(Service):
        value = 'fake'

    container = Container().bind(Service).freeze()
    app = FastAPI()

    @app.get('/value')
    async def endpoint(service: Inject[Service]) -> dict[str, str]:
        return {'value': service.value}

    _ = endpoint
    setup(app, container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        with container.override(Service).using(FakeService()):
            assert (await client.get('/value')).json() == {'value': 'fake'}
        assert (await client.get('/value')).json() == {'value': 'real'}


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_stream_failure_keeps_resource_cleanup(setup: _Setup) -> None:
    events: list[str] = []

    class Resource:
        pass

    async def resource() -> AsyncIterator[Resource]:
        events.append('construct')
        yield Resource()
        events.append('close')

    async def chunks() -> AsyncIterator[bytes]:
        events.append('first-body')
        yield b'first'
        raise RuntimeError('stream failure')

    app = FastAPI()

    @app.get('/stream')
    async def endpoint(value: Inject[Resource]) -> StreamingResponse:
        del value
        return StreamingResponse(chunks())

    _ = endpoint
    setup(app, Container().bind(resource, scope=Scope.SCOPED).freeze())
    sent_request = False
    disconnected = asyncio.Event()

    async def receive() -> Message:
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await disconnected.wait()
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        return None

    with pytest.raises(RuntimeError, match='stream failure'):
        await app(_http_scope('GET', '/stream'), receive, send)

    assert events == ['construct', 'first-body', 'close']


@pytest.mark.parametrize('setup', [_compatibility_setup, _optimized_setup])
@pytest.mark.asyncio
async def test_stream_cancellation_drains_resource_without_terminal_body(setup: _Setup) -> None:
    events: list[str] = []
    second_body = asyncio.Event()

    class Resource:
        pass

    async def resource() -> AsyncIterator[Resource]:
        events.append('construct')
        yield Resource()
        events.append('close')

    async def chunks() -> AsyncIterator[bytes]:
        events.append('first-body')
        yield b'first'
        await second_body.wait()
        events.append('unexpected-second-body')
        yield b'second'

    app = FastAPI()

    @app.get('/stream')
    async def endpoint(value: Inject[Resource]) -> StreamingResponse:
        del value
        return StreamingResponse(chunks())

    _ = endpoint
    setup(app, Container().bind(resource, scope=Scope.SCOPED).freeze())
    sent_request = False
    disconnect = asyncio.Event()

    async def receive() -> Message:
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await disconnect.wait()
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        if message['type'] == 'http.response.body' and message.get('more_body') is True:
            disconnect.set()

    await app(_http_scope('GET', '/stream'), receive, send)

    assert events == ['construct', 'first-body', 'close']


@pytest.mark.asyncio
async def test_installed_lazy_scope_passes_non_http_work_through_unhosted() -> None:
    observed: list[bool] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        del app
        observed.append(optional_hosted_container() is None)
        try:
            active_frame()
        except OutsideScopeError:
            observed.append(True)
        yield

    app = FastAPI(lifespan=lifespan)
    fastapi_ext.install(app, Container().freeze())
    events = iter(({'type': 'lifespan.startup'}, {'type': 'lifespan.shutdown'}))

    async def receive() -> Message:
        return next(events)

    await app({'type': 'lifespan'}, receive, _noop_send)

    assert observed == [True, True]


@pytest.mark.asyncio
async def test_installed_no_inject_route_hosts_container_without_opening_a_frame() -> None:
    container = Container().freeze()
    app = FastAPI()

    @app.get('/')
    async def endpoint() -> dict[str, bool]:
        try:
            active_frame()
        except OutsideScopeError:
            return {'hosted': hosted_container() is container, 'frame': False}
        return {'hosted': hosted_container() is container, 'frame': True}

    _ = endpoint
    fastapi_ext.install(app, container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        assert (await client.get('/')).json() == {'hosted': True, 'frame': False}


@pytest.mark.asyncio
async def test_installed_no_inject_failure_re_raises_and_restores_outer_host() -> None:
    container = Container().freeze()
    outer = Container().freeze()
    failure = RuntimeError('sentinel handler failure')
    frames: list[bool] = []
    app = FastAPI()

    @app.get('/')
    async def endpoint() -> None:
        try:
            active_frame()
        except OutsideScopeError:
            frames.append(False)
        else:
            frames.append(True)
        assert hosted_container() is container
        raise failure

    _ = endpoint
    fastapi_ext.install(app, container)

    with Host(outer).activated():
        with pytest.raises(RuntimeError) as raised:
            await app(_http_scope('GET', '/'), _json_body_receive, _noop_send)
        assert raised.value is failure
        assert hosted_container() is outer

    assert frames == [False]
    assert container.scope_activity() == (0, 0)
    assert optional_hosted_container() is None


def test_install_accepts_fastapi_without_models_coroutine_detector(monkeypatch: pytest.MonkeyPatch) -> None:
    class Service:
        pass

    app = FastAPI()

    @app.get('/')
    async def endpoint(service: Inject[Service]) -> dict[str, bool]:
        del service
        return {'injected': True}

    _ = endpoint
    monkeypatch.delattr(fastapi_models, '_is_coroutine_callable')

    fastapi_ext.install(app, Container().bind(Service).freeze())
