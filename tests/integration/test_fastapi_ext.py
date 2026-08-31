from typing import Protocol

import pytest
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from httpx import ASGITransport, AsyncClient

from depin import Container, Scope
from depin.ext.fastapi import Inject, RequestScope


@pytest.mark.asyncio
async def test_request_scope_middleware_opens_scope_per_request() -> None:
    class Counter:
        def __init__(self) -> None:
            self.value = 0

        def tick(self) -> int:
            self.value += 1
            return self.value

    frozen = Container().bind(Counter, scope=Scope.SCOPED).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/tick')
    async def _tick(c: Inject[Counter]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {'n': c.tick(), 'again': c.tick()}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r1 = await client.get('/tick')
        r2 = await client.get('/tick')
    assert r1.json() == {'n': 1, 'again': 2}
    assert r2.json() == {'n': 1, 'again': 2}


@pytest.mark.asyncio
async def test_request_is_available_as_scoped_dependency() -> None:
    class Probe:
        def __init__(self, request: FastAPIRequest) -> None:
            self.path = request.url.path

    frozen = Container().scope_value(FastAPIRequest).bind(Probe, scope=Scope.SCOPED).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/probe/{x}')
    async def _probe(p: Inject[Probe]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {'p': p.path}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/probe/abc')
    assert r.json() == {'p': '/probe/abc'}


@pytest.mark.asyncio
async def test_the_graph_describes_a_request_scoped_binding() -> None:
    class Session:
        pass

    frozen = Container().bind(Session, scope=Scope.SCOPED).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/explain')
    async def _explain(session: Inject[Session]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        del session
        return {'tree': frozen.explain(Session), 'dot': frozen.graph().dot()}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        body = (await client.get('/explain')).json()

    assert body['tree'] == ('test_the_graph_describes_a_request_scoped_binding.<locals>.Session  [scoped, class]')
    assert 'digraph depin {' in body['dot']
    assert frozen.graph().node(Session).scope is Scope.SCOPED


@pytest.mark.asyncio
async def test_a_route_resolves_a_request_scoped_binding_through_an_alias() -> None:
    class Session:
        def __init__(self) -> None:
            self.label = 'session'

    class Unit(Protocol):
        label: str

    frozen = Container().bind(Session, scope=Scope.SCOPED).alias(Unit, to=Session).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/unit')
    async def _unit(unit: Inject[Unit], session: Inject[Session]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {'same': unit is session}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        assert (await client.get('/unit')).json() == {'same': True}


@pytest.mark.asyncio
async def test_a_route_resolves_a_collection_of_handlers() -> None:
    class Handler(Protocol):
        def name(self) -> str: ...

    class EmailHandler:
        def name(self) -> str:
            return 'email'

    class SmsHandler:
        def name(self) -> str:
            return 'sms'

    class Dispatcher:
        def __init__(self, handlers: list[Handler]) -> None:
            self.handlers = handlers

    frozen = (
        Container()
        .bind(EmailHandler)
        .bind(SmsHandler)
        .collect(Handler, [EmailHandler, SmsHandler])
        .bind(Dispatcher)
        .freeze()
    )

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/handlers')
    async def _handlers(dispatcher: Inject[Dispatcher]) -> dict[str, list[str]]:  # pyright: ignore[reportUnusedFunction]
        return {'names': [handler.name() for handler in dispatcher.handlers]}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/handlers')
    assert r.json() == {'names': ['email', 'sms']}


@pytest.mark.asyncio
async def test_a_request_scoped_route_resolves_an_unbound_optional_to_none() -> None:
    class Cache:
        def get(self) -> str:
            return 'cached'

    class Session:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    frozen = Container().bind(Session, scope=Scope.SCOPED).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/session')
    async def _session(session: Inject[Session]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {'has_cache': session.cache is not None}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/session')
    assert r.json() == {'has_cache': False}
