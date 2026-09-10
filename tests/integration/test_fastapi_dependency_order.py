"""Regression coverage for FastAPI direct dependency ordering."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from depin import Container, Scope
from depin.ext.fastapi import Inject, install


def _route(app: FastAPI, path: str) -> APIRoute:
    return next(route for route in app.routes if isinstance(route, APIRoute) and route.path == path)


@pytest.mark.asyncio
async def test_install_keeps_an_inject_before_depends_in_fastapi_order() -> None:
    """Direct injection must run before a later native dependency."""

    events: list[str] = []

    class Service:
        pass

    def provide() -> Service:
        events.append('provider')
        return Service()

    async def native() -> None:
        events.append('native')

    app = FastAPI()

    @app.get('/')
    async def endpoint(
        service: Inject[Service], native_value: Annotated[None, Depends(native)]
    ) -> dict[str, list[str]]:
        del service, native_value
        events.append('endpoint')
        return {'events': events}

    _ = endpoint
    install(app, Container().bind(provide).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/')

    assert response.json() == {'events': ['provider', 'native', 'endpoint']}


@pytest.mark.asyncio
async def test_install_keeps_an_inject_before_security_in_fastapi_order() -> None:
    """Direct injection must run before a later native security dependency."""

    events: list[str] = []

    class Service:
        pass

    def provide() -> Service:
        events.append('provider')
        return Service()

    async def native() -> None:
        events.append('security')

    app = FastAPI()

    @app.get('/')
    async def endpoint(
        service: Inject[Service], security_value: Annotated[None, Security(native)]
    ) -> dict[str, list[str]]:
        del service, security_value
        events.append('endpoint')
        return {'events': events}

    _ = endpoint
    install(app, Container().bind(provide).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/')

    assert response.json() == {'events': ['provider', 'security', 'endpoint']}


@pytest.mark.asyncio
async def test_install_preserves_provider_failure_precedence_before_a_native_dependency() -> None:
    """A later native dependency cannot hide an earlier provider failure."""

    events: list[str] = []

    class Service:
        pass

    def provide() -> Service:
        events.append('provider')
        raise HTTPException(status_code=418, detail='provider')

    async def native() -> None:
        events.append('native')
        raise HTTPException(status_code=409, detail='native')

    app = FastAPI()

    @app.get('/')
    async def endpoint(service: Inject[Service], native_value: Annotated[None, Depends(native)]) -> None:
        del service, native_value

    _ = endpoint
    install(app, Container().bind(provide).freeze())

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test'
    ) as client:
        response = await client.get('/')

    assert response.status_code == 418
    assert response.json() == {'detail': 'provider'}
    assert events == ['provider']


@pytest.mark.asyncio
async def test_install_preserves_native_failure_after_an_earlier_provider() -> None:
    """A failing native dependency still follows the earlier direct provider."""

    events: list[str] = []

    class Service:
        pass

    def provide() -> Service:
        events.append('provider')
        return Service()

    async def native() -> None:
        events.append('native')
        raise HTTPException(status_code=409, detail='native')

    app = FastAPI()

    @app.get('/')
    async def endpoint(service: Inject[Service], native_value: Annotated[None, Depends(native)]) -> None:
        del service, native_value

    _ = endpoint
    install(app, Container().bind(provide).freeze())

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test'
    ) as client:
        response = await client.get('/')

    assert response.status_code == 409
    assert response.json() == {'detail': 'native'}
    assert events == ['provider', 'native']


@pytest.mark.asyncio
async def test_install_compiles_when_native_dependencies_precede_inject() -> None:
    """Native dependencies before direct injection retain their order when compiled."""

    events: list[str] = []

    class Service:
        pass

    def provide() -> Service:
        events.append('provider')
        return Service()

    async def native() -> None:
        events.append('native')

    app = FastAPI()

    @app.get('/')
    async def endpoint(
        native_value: Annotated[None, Depends(native)], service: Inject[Service]
    ) -> dict[str, list[str]]:
        del native_value, service
        events.append('endpoint')
        return {'events': events}

    _ = endpoint
    route = _route(app, '/')
    original_call = route.dependant.call
    install(app, Container().bind(provide).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/')

    assert response.json() == {'events': ['native', 'provider', 'endpoint']}
    assert route.dependant.call is not original_call
    assert len(route.dependant.dependencies) == 1


@pytest.mark.asyncio
async def test_install_retains_mixed_direct_dependency_graph_and_openapi() -> None:
    """Interleaved direct dependencies use the unmodified FastAPI compatibility route."""

    class First:
        pass

    class Second:
        pass

    async def first_native() -> None:
        return None

    async def second_native() -> None:
        return None

    app = FastAPI()

    @app.get('/')
    async def endpoint(
        first: Inject[First],
        first_value: Annotated[None, Depends(first_native)],
        second: Inject[Second],
        second_value: Annotated[None, Depends(second_native)],
    ) -> dict[str, bool]:
        del first, first_value, second, second_value
        return {'ok': True}

    _ = endpoint
    route = _route(app, '/')
    original_call = route.dependant.call
    original_dependencies = route.dependant.dependencies
    original_openapi = app.openapi()
    container = Container().bind(First).bind(Second).freeze()
    install(app, container)
    install(app, container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/')

    assert response.json() == {'ok': True}
    assert route.dependant.call is original_call
    assert route.dependant.dependencies is original_dependencies
    assert app.openapi() == original_openapi


@pytest.mark.asyncio
async def test_install_compatibility_route_uses_the_actual_request_scope() -> None:
    """Fallback injection gets the request object FastAPI passes to native dependencies."""

    seen: list[Request] = []

    class Probe:
        def __init__(self, request: Request) -> None:
            self.request = request

    async def native(request: Request) -> None:
        seen.append(request)

    app = FastAPI()

    @app.get('/')
    async def endpoint(
        probe: Inject[Probe], native_value: Annotated[None, Depends(native)], request: Request
    ) -> dict[str, bool]:
        del native_value
        return {'same_request': probe.request is request and seen == [request]}

    _ = endpoint
    install(app, Container().scope_value(Request).bind(Probe, scope=Scope.SCOPED).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/')

    assert response.json() == {'same_request': True}


@pytest.mark.asyncio
async def test_order_guard_proves_the_compatibility_fallback_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing the scan-time fallback reverses an Inject-before-Depends route."""

    import depin.ext._fastapi as implementation

    events: list[str] = []

    class Service:
        pass

    def provide() -> Service:
        events.append('provider')
        return Service()

    async def native() -> None:
        events.append('native')

    app = FastAPI()

    @app.get('/')
    async def endpoint(
        service: Inject[Service], native_value: Annotated[None, Depends(native)]
    ) -> dict[str, list[str]]:
        del service, native_value
        events.append('endpoint')
        return {'events': events}

    _ = endpoint

    def always_equivalent(dependencies: list[Dependant]) -> bool:
        del dependencies
        return True

    monkeypatch.setattr(implementation, '_direct_dependency_order_is_equivalent', always_equivalent)
    install(app, Container().bind(provide).freeze())

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/')

    assert response.json() == {'events': ['native', 'provider', 'endpoint']}
