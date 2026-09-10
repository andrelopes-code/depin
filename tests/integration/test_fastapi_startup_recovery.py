"""Regression coverage for FastAPI install without rebuilding route handlers."""

import asyncio
from collections.abc import AsyncGenerator
from threading import get_ident
from typing import Annotated

import pytest
from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, HTTPException, Header, Request, Response, Security
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from starlette.requests import HTTPConnection

from depin import Container, Scope, optional_hosted_container
from depin.errors import FastAPIIntegrationError
from depin.ext.fastapi import Inject, install


def _route(app: FastAPI, path: str) -> APIRoute:
    return next(route for route in app.routes if isinstance(route, APIRoute) and route.path == path)


def test_install_reserves_hidden_request_name_for_direct_dependency() -> None:
    """A direct FastAPI dependency keeps the preferred hidden request name."""

    class Service:
        pass

    async def native() -> str:
        return 'native'

    app = FastAPI()

    @app.get('/')
    async def endpoint(service: Inject[Service], __depin_request__: str = Depends(native)) -> dict[str, str]:
        del service
        return {'value': __depin_request__}

    _ = endpoint
    install(app, Container().bind(Service).freeze())

    assert _route(app, '/').dependant.request_param_name != '__depin_request__'


def test_install_reserves_hidden_request_name_for_root_parameter_fields() -> None:
    """Root endpoint fields cannot be overwritten by the synthesized request."""

    class Service:
        pass

    class Payload(BaseModel):
        value: str

    app = FastAPI()

    @app.get('/path/{__depin_request__}')
    async def path(service: Inject[Service], __depin_request__: str) -> dict[str, str]:
        del service
        return {'value': __depin_request__}

    @app.get('/query')
    async def query(service: Inject[Service], __depin_request__: str) -> dict[str, str]:
        del service
        return {'value': __depin_request__}

    @app.post('/body')
    async def body(service: Inject[Service], __depin_request__: Payload) -> dict[str, str]:
        del service
        return {'value': __depin_request__.value}

    _ = path, query, body
    install(app, Container().bind(Service).freeze())

    assert all(
        _route(app, path).dependant.request_param_name != '__depin_request__'
        for path in ('/path/{__depin_request__}', '/query', '/body')
    )


def test_install_reserves_hidden_request_name_for_root_special_parameters() -> None:
    """FastAPI root special parameters cannot be overwritten by the synthesized request."""

    class Service:
        pass

    app = FastAPI()

    @app.get('/response')
    async def response(service: Inject[Service], __depin_request__: Response) -> dict[str, bool]:
        del service, __depin_request__
        return {'ok': True}

    @app.get('/background')
    async def background(service: Inject[Service], __depin_request__: BackgroundTasks) -> dict[str, bool]:
        del service, __depin_request__
        return {'ok': True}

    @app.get('/connection')
    async def connection(service: Inject[Service], __depin_request__: HTTPConnection) -> dict[str, bool]:
        del service, __depin_request__
        return {'ok': True}

    @app.get('/scopes')
    async def scopes(service: Inject[Service], __depin_request__: SecurityScopes) -> dict[str, bool]:
        del service, __depin_request__
        return {'ok': True}

    _ = response, background, connection, scopes
    install(app, Container().bind(Service).freeze())

    assert all(
        _route(app, path).dependant.request_param_name != '__depin_request__'
        for path in ('/response', '/background', '/connection', '/scopes')
    )


def test_install_retains_inject_before_a_direct_native_dependency() -> None:
    """A later direct native dependency preserves the original FastAPI graph."""

    class Service:
        pass

    async def nested(__depin_request__: str = 'nested') -> str:
        return __depin_request__

    async def direct(value: str = Depends(nested)) -> str:
        return value

    app = FastAPI()

    @app.get('/')
    async def endpoint(service: Inject[Service], value: str = Depends(direct)) -> dict[str, str]:
        del service
        return {'value': value}

    _ = endpoint
    install(app, Container().bind(Service).freeze())

    assert _route(app, '/').dependant.request_param_name is None


def test_install_does_not_recurse_when_selecting_hidden_request_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hidden request selection uses the direct dependency scan from preflight."""

    import depin.ext._fastapi as fastapi_implementation

    class Service:
        pass

    app = FastAPI()

    @app.get('/')
    async def endpoint(service: Inject[Service]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = endpoint

    def recursive_collection() -> set[str]:
        raise AssertionError('recursive hidden-name collection ran')

    monkeypatch.setitem(fastapi_implementation.__dict__, '_dependency_value_names', recursive_collection)

    install(app, Container().bind(Service).freeze())


@pytest.mark.asyncio
async def test_install_routes_header_and_cookie_values_named_like_hidden_request() -> None:
    """Root header and cookie values remain distinct from the synthesized request."""

    class Service:
        pass

    app = FastAPI()

    @app.get('/header')
    async def header(
        service: Inject[Service], __depin_request__: Annotated[str, Header(convert_underscores=False)]
    ) -> dict[str, str]:
        del service
        return {'value': __depin_request__}

    @app.get('/cookie')
    async def cookie(service: Inject[Service], __depin_request__: Annotated[str, Cookie()]) -> dict[str, str]:
        del service
        return {'value': __depin_request__}

    _ = header, cookie
    install(app, Container().bind(Service).freeze())

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test', cookies={'__depin_request__': 'cookie'}
    ) as client:
        header_response = await client.get('/header', headers={'__depin_request__': 'header'})
        cookie_response = await client.get('/cookie')

    assert header_response.json() == {'value': 'header'}
    assert cookie_response.json() == {'value': 'cookie'}
    assert _route(app, '/header').dependant.request_param_name != '__depin_request__'
    assert _route(app, '/cookie').dependant.request_param_name != '__depin_request__'


@pytest.mark.asyncio
async def test_install_preserves_root_request_named_like_hidden_request() -> None:
    """An explicit root Request remains the instance seeded for direct injection."""

    class Probe:
        def __init__(self, request: Request) -> None:
            self.request = request

    app = FastAPI()

    @app.get('/')
    async def endpoint(probe: Inject[Probe], __depin_request__: Request) -> dict[str, bool]:
        return {'same_request': probe.request is __depin_request__}

    _ = endpoint
    install(app, Container().scope_value(Request).bind(Probe, scope=Scope.SCOPED).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/')

    assert response.json() == {'same_request': True}
    assert _route(app, '/').dependant.request_param_name == '__depin_request__'


@pytest.mark.asyncio
async def test_install_routes_direct_security_result_named_like_hidden_request() -> None:
    """A direct Security result keeps its root dependency name during compilation."""

    class Service:
        pass

    bearer = HTTPBearer()
    app = FastAPI()

    @app.get('/')
    async def endpoint(
        service: Inject[Service], __depin_request__: Annotated[HTTPAuthorizationCredentials, Security(bearer)]
    ) -> dict[str, str]:
        del service
        return {'token': __depin_request__.credentials}

    _ = endpoint
    install(app, Container().bind(Service).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/', headers={'Authorization': 'Bearer protected'})

    assert response.json() == {'token': 'protected'}
    assert _route(app, '/').dependant.request_param_name != '__depin_request__'


@pytest.mark.asyncio
async def test_install_uses_captured_dependant_when_route_handler_rebuild_is_unavailable() -> None:
    """FastAPI's original route app must observe the in-place dependant mutation."""

    class AsyncService:
        value = 'async'

    class SyncService:
        value = 'sync'

    app = FastAPI()

    @app.get('/async')
    async def async_endpoint(service: Inject[AsyncService]) -> dict[str, str]:
        return {'value': service.value}

    @app.get('/sync')
    def sync_endpoint(service: Inject[SyncService]) -> dict[str, str]:
        return {'value': service.value}

    _ = async_endpoint, sync_endpoint

    async_route = _route(app, '/async')
    sync_route = _route(app, '/sync')
    original_async_app = async_route.app
    original_sync_app = sync_route.app

    def fail_rebuild() -> object:
        raise RuntimeError('route handler rebuild is unavailable')

    object.__setattr__(async_route, 'get_route_handler', fail_rebuild)
    object.__setattr__(sync_route, 'get_route_handler', fail_rebuild)

    install(app, Container().bind(AsyncService).bind(SyncService).freeze())

    assert async_route.app is original_async_app
    assert sync_route.app is original_sync_app

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/async')).json() == {'value': 'async'}
        assert (await client.get('/sync')).json() == {'value': 'sync'}


@pytest.mark.asyncio
async def test_install_preserves_sync_fastapi_contracts_while_resolving_in_worker_thread() -> None:
    """The synchronous wrapper keeps FastAPI's dependency, response, and request semantics."""

    native_calls: list[int] = []
    endpoint_threads: list[int] = []
    main_thread = get_ident()

    class Payload(BaseModel):
        value: str

    class Probe:
        def __init__(self, request: Request) -> None:
            self.request = request

    def native() -> object:
        native_calls.append(get_ident())
        return object()

    app = FastAPI()

    @app.get('/value/{value}', response_model=Payload)
    def endpoint(
        value: int,
        request: Request,
        probe: Inject[Probe],
        first: object = Depends(native),
        second: object = Depends(native),
        fail: bool = False,
    ) -> dict[str, str]:
        del first, second
        endpoint_threads.append(get_ident())
        if fail:
            raise HTTPException(status_code=409, detail='expected')
        return {'value': str(value) if probe.request is request else 'wrong-request'}

    _ = endpoint

    install(app, Container().scope_value(Request).bind(Probe, scope=Scope.SCOPED).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        valid = await client.get('/value/7')
        invalid = await client.get('/value/not-an-int')
        failure = await client.get('/value/8?fail=true')

    assert valid.status_code == 200
    assert valid.json() == {'value': '7'}
    assert invalid.status_code == 422
    assert failure.status_code == 409
    assert failure.json() == {'detail': 'expected'}
    assert len(native_calls) == 3
    assert all(thread != main_thread for thread in endpoint_threads)
    assert app.openapi()['paths']['/value/{value}']['get']['responses']['200']['content']['application/json'][
        'schema'
    ] == {'$ref': '#/components/schemas/Payload'}


@pytest.mark.asyncio
async def test_install_reuses_existing_route_apps_for_reinstall_and_new_routes() -> None:
    """Reinstalling compiles only later routes without replacing existing ASGI apps."""

    class First:
        value = 'first'

    class Second:
        value = 'second'

    app = FastAPI()

    @app.get('/first')
    async def first(value: Inject[First]) -> dict[str, str]:
        return {'value': value.value}

    _ = first

    container = Container().bind(First).bind(Second).freeze()
    first_route = _route(app, '/first')
    first_app = first_route.app
    first_dependant = first_route.dependant
    install(app, container)

    @app.get('/second')
    async def second(value: Inject[Second]) -> dict[str, str]:
        return {'value': value.value}

    _ = second

    second_route = _route(app, '/second')
    second_app = second_route.app
    install(app, container)

    assert first_route.app is first_app
    assert second_route.app is second_app
    assert first_route.dependant is first_dependant

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/first')).json() == {'value': 'first'}
        assert (await client.get('/second')).json() == {'value': 'second'}


def test_install_restores_root_fields_after_middleware_failure_and_allows_retry() -> None:
    """Middleware failures leave the captured FastAPI dependant exactly retryable."""

    class Service:
        pass

    app = FastAPI()

    @app.get('/')
    async def endpoint(service: Inject[Service]) -> dict[str, bool]:
        del service
        return {'ok': True}

    _ = endpoint

    route = _route(app, '/')
    root = route.dependant
    original_call = root.call
    original_dependencies = root.dependencies
    original_request_name = root.request_param_name
    original_app = route.app
    add_middleware = app.add_middleware

    def fail_middleware(*arguments: object, **keywords: object) -> None:
        del arguments, keywords
        raise RuntimeError('middleware failure')

    object.__setattr__(app, 'add_middleware', fail_middleware)
    with pytest.raises(FastAPIIntegrationError, match='middleware failure'):
        install(app, Container().bind(Service).freeze())

    assert route.dependant is root
    assert root.call is original_call
    assert root.dependencies is original_dependencies
    assert root.request_param_name is original_request_name
    assert route.app is original_app

    object.__setattr__(app, 'add_middleware', add_middleware)
    install(app, Container().bind(Service).freeze())


@pytest.mark.asyncio
async def test_sync_endpoint_resolves_async_resource_on_request_task_and_drains_after_one_call() -> None:
    """The worker bridge keeps async resource lifetime on the hosted request task."""

    events: list[str] = []
    provider_tasks: list[asyncio.Task[object] | None] = []
    endpoint_calls = 0
    worker_threads: list[int] = []
    main_thread = get_ident()

    class Resource:
        def __init__(self, request: Request) -> None:
            self.request = request

    async def provide(request: Request) -> AsyncGenerator[Resource]:
        provider_tasks.append(asyncio.current_task())
        events.append('open')
        assert optional_hosted_container() is not None
        try:
            yield Resource(request)
        finally:
            events.append('close')

    app = FastAPI()

    @app.get('/')
    def endpoint(resource: Inject[Resource], request: Request) -> dict[str, bool]:
        nonlocal endpoint_calls
        endpoint_calls += 1
        worker_threads.append(get_ident())
        events.append('endpoint')
        return {'request': resource.request is request}

    _ = endpoint
    install(app, Container().scope_value(Request).bind(provide, scope=Scope.SCOPED).freeze())

    request_task = asyncio.current_task()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/')

    assert response.json() == {'request': True}
    assert endpoint_calls == 1
    assert provider_tasks == [request_task]
    assert all(thread != main_thread for thread in worker_threads)
    assert events == ['open', 'endpoint', 'close']


@pytest.mark.asyncio
async def test_sync_endpoint_preserves_async_provider_error_and_drains_open_resource() -> None:
    """Errors crossing the worker bridge retain their original exception and cleanup."""

    events: list[str] = []
    endpoint_calls = 0
    expected = RuntimeError('provider failed')

    class Resource:
        pass

    class Result:
        pass

    async def provide_resource() -> AsyncGenerator[Resource]:
        events.append('open')
        try:
            yield Resource()
        finally:
            events.append('close')

    async def fail(resource: Resource) -> Result:
        del resource
        raise expected

    app = FastAPI()

    @app.get('/')
    def endpoint(result: Inject[Result]) -> dict[str, bool]:
        nonlocal endpoint_calls
        endpoint_calls += 1
        del result
        return {'ok': True}

    _ = endpoint
    install(app, Container().bind(provide_resource, scope=Scope.SCOPED).bind(fail, scope=Scope.SCOPED).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        with pytest.raises(RuntimeError) as caught:
            await client.get('/')

    assert caught.value is expected
    assert endpoint_calls == 0
    assert events == ['open', 'close']


@pytest.mark.asyncio
async def test_sync_endpoint_cancellation_cleans_up_a_blocked_async_provider() -> None:
    """Cancellation reaches a blocked provider and leaves no request resource open."""

    started = asyncio.Event()
    closed = asyncio.Event()
    events: list[str] = []

    class Resource:
        pass

    async def provide() -> AsyncGenerator[Resource]:
        events.append('open')
        started.set()
        try:
            await asyncio.Event().wait()
            yield Resource()
        finally:
            events.append('close')
            closed.set()

    app = FastAPI()

    @app.get('/')
    def endpoint(resource: Inject[Resource]) -> dict[str, bool]:
        del resource
        return {'ok': True}

    _ = endpoint
    install(app, Container().bind(provide, scope=Scope.SCOPED).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        request = asyncio.create_task(client.get('/'))
        await started.wait()
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        await closed.wait()

    assert events == ['open', 'close']


@pytest.mark.asyncio
async def test_sync_program_dependency_is_last_after_native_security_and_avoids_value_collisions() -> None:
    """Native security runs first and the program mapping cannot replace a user value."""

    events: list[str] = []

    class Service:
        value = 'ready'

    security = HTTPBearer()

    async def provide() -> Service:
        events.append('program')
        return Service()

    app = FastAPI()

    @app.get('/')
    def endpoint(
        credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
        service: Inject[Service],
        __depin_request__: int,
    ) -> dict[str, object]:
        return {'token': credentials.credentials, 'service': service.value, 'value': __depin_request__}

    _ = endpoint
    route = _route(app, '/')
    security_dependency = route.dependant.dependencies[0]
    install(app, Container().bind(provide).freeze())

    assert route.dependant.dependencies[0] is security_dependency
    assert route.dependant.dependencies[-1].name == '__depin_request___'

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        unauthorized = await client.get('/?__depin_request__=3')
        authorized = await client.get('/?__depin_request__=3', headers={'Authorization': 'Bearer token'})

    assert unauthorized.status_code == 401
    assert events == ['program']
    assert authorized.json() == {'token': 'token', 'service': 'ready', 'value': 3}


@pytest.mark.asyncio
async def test_sync_handler_and_async_resource_teardown_preserve_exception_group_order() -> None:
    """A sync handler failure remains before its async resource cleanup failure."""

    class HandlerFailure(Exception):
        pass

    class CleanupFailure(Exception):
        pass

    class Resource:
        pass

    async def provide() -> AsyncGenerator[Resource]:
        try:
            yield Resource()
        finally:
            raise CleanupFailure('cleanup')

    app = FastAPI()

    @app.get('/')
    def endpoint(resource: Inject[Resource]) -> dict[str, bool]:
        del resource
        raise HandlerFailure('handler')

    _ = endpoint
    install(app, Container().bind(provide, scope=Scope.SCOPED).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        with pytest.raises(ExceptionGroup) as caught:
            await client.get('/')

    assert [type(error) for error in caught.value.exceptions] == [HandlerFailure, CleanupFailure]
