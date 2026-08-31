import contextlib
from collections.abc import AsyncGenerator
from typing import Protocol

import pytest
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from httpx import ASGITransport, AsyncClient

from depin import Container, FrozenContainer, Scope
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
async def test_a_route_resolves_a_generic_key() -> None:
    class User:
        def __init__(self, name: str) -> None:
            self.name = name

    class Repo[T]:
        def __init__(self, rows: list[T]) -> None:
            self.rows = rows

    def user_repo() -> Repo[User]:
        return Repo([User('ana'), User('bia')])

    frozen = Container().bind(user_repo).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/users')
    async def _users(repo: Inject[Repo[User]]) -> dict[str, list[str]]:  # pyright: ignore[reportUnusedFunction]
        return {'names': [user.name for user in repo.rows]}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/users')
    assert r.json() == {'names': ['ana', 'bia']}


@pytest.mark.asyncio
async def test_a_route_resolves_a_decorated_scoped_provider() -> None:
    class Counter:
        def __init__(self) -> None:
            self.value = 0

        def tick(self) -> int:
            self.value += 1
            return self.value

    class Doubled:
        def __init__(self, inner: Counter) -> None:
            self.inner = inner

        def tick(self) -> int:
            return self.inner.tick() * 2

    frozen = Container().bind(Counter, scope=Scope.SCOPED).decorate(Counter, Doubled).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/tick')
    async def _tick(c: Inject[Counter]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {'n': c.tick(), 'again': c.tick()}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/tick')
    # A plain Counter would answer {'n': 1, 'again': 2}; the wrapper is what
    # doubles every tick before the route sees it.
    assert r.json() == {'n': 2, 'again': 4}


@pytest.mark.asyncio
async def test_a_route_resolves_the_binding_selected_by_condition() -> None:
    class Store(Protocol):
        def label(self) -> str: ...

    class Postgres:
        def label(self) -> str:
            return 'postgres'

    class Memory:
        def label(self) -> str:
            return 'memory'

    production = False
    frozen = (
        Container()
        .bind(Postgres, provides=Store, when=production)
        .bind(Memory, provides=Store, when=not production)
        .freeze()
    )

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/store')
    async def _store(store: Inject[Store]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {'label': store.label()}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/store')
    assert r.json() == {'label': 'memory'}


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


@pytest.mark.asyncio
async def test_a_lifespan_warmup_constructs_singletons_before_the_first_request() -> None:
    built: list[str] = []

    class Pool:
        def __init__(self) -> None:
            built.append('Pool')

    frozen = Container().bind(Pool).freeze()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        del app
        _ = await frozen.awarmup()
        yield

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/ping')
    async def _ping(pool: Inject[Pool]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {'is_the_warmed_pool': pool is frozen[Pool]}

    transport = ASGITransport(app=app)
    # ASGITransport does not run the lifespan on its own; drive it explicitly so
    # the assertion below can tell warmup ran before the request did.
    async with lifespan(app), AsyncClient(transport=transport, base_url='http://t') as client:
        assert built == ['Pool']
        r = await client.get('/ping')

    assert r.json() == {'is_the_warmed_pool': True}


@pytest.mark.asyncio
async def test_a_readiness_route_reports_a_failing_check() -> None:
    class Database:
        def __init__(self) -> None:
            self.connected = True

    class Cache:
        def __init__(self) -> None:
            self.connected = False

    def check_database(db: Database) -> bool:
        return db.connected

    def check_cache(cache: Cache) -> bool:
        return cache.connected

    frozen: FrozenContainer = Container().bind(Database, check=check_database).bind(Cache, check=check_cache).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/ready')
    async def _ready() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        report = await frozen.ahealth()
        return {
            'healthy': report.healthy,
            'results': [
                {
                    'key': result.key.__qualname__ if isinstance(result.key, type) else str(result.key),
                    'healthy': result.healthy,
                }
                for result in report.results
            ],
        }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/ready')

    assert r.json() == {
        'healthy': False,
        'results': [
            {'key': Database.__qualname__, 'healthy': True},
            {'key': Cache.__qualname__, 'healthy': False},
        ],
    }
