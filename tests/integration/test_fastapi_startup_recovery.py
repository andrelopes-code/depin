"""Regression coverage for FastAPI install without rebuilding route handlers."""

from threading import get_ident

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from depin import Container, Scope
from depin.errors import FastAPIIntegrationError
from depin.ext.fastapi import Inject, install


def _route(app: FastAPI, path: str) -> APIRoute:
    return next(route for route in app.routes if isinstance(route, APIRoute) and route.path == path)


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
