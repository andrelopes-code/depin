import contextlib
from collections.abc import AsyncGenerator
from typing import Annotated, Protocol

import pytest
from fastapi import BackgroundTasks, Depends, FastAPI, Response
from fastapi import Request as FastAPIRequest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.security import SecurityScopes
from httpx import ASGITransport, AsyncClient
from starlette.requests import HTTPConnection

from depin import Container, FrozenContainer, Host, Scope
from depin._core.scope import active_frame
from depin.errors import ContainerNotBoundError, OutsideScopeError
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
    async def ready() -> dict[str, object]:
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

    _ = ready

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


@pytest.mark.asyncio
async def test_inject_resolves_from_an_active_host_without_a_request_scope() -> None:
    class Config:
        value: int = 1

    frozen = Container().bind(Config).freeze()

    app = FastAPI()

    @app.get('/config')
    async def _config(config: Inject[Config]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {'value': config.value}

    transport = ASGITransport(app=app)
    with Host(frozen).activated():
        async with AsyncClient(transport=transport, base_url='http://t') as client:
            r = await client.get('/config')
    assert r.json() == {'value': 1}


@pytest.mark.asyncio
async def test_inject_raises_outside_any_hosted_container() -> None:
    class Config:
        value: int = 1

    app = FastAPI()

    @app.get('/config')
    async def _config(config: Inject[Config]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {'value': config.value}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        with pytest.raises(ContainerNotBoundError) as caught:
            await client.get('/config')

    assert str(caught.value) == (
        'Inject[...] resolved outside a hosted FastAPI request; call install(app, container) '
        'after route registration or install RequestScope compatibility middleware.'
    )


@pytest.mark.asyncio
async def test_install_resolves_multiple_injections_through_one_program() -> None:
    """A compiler regression would construct distinct scoped dependencies."""
    events: list[str] = []

    class Shared:
        def __init__(self) -> None:
            events.append('shared')

    class Left:
        def __init__(self, shared: Shared) -> None:
            self.shared = shared

    class Right:
        def __init__(self, shared: Shared) -> None:
            self.shared = shared

    container = (
        Container()
        .bind(Shared, scope=Scope.SCOPED)
        .bind(Left, scope=Scope.SCOPED)
        .bind(Right, scope=Scope.SCOPED)
        .freeze()
    )
    app = FastAPI()

    @app.get('/value')
    async def value(left: Inject[Left], right: Inject[Right]) -> dict[str, bool]:
        return {'shared': left.shared is right.shared}

    _ = value

    fastapi_ext.install(app, container)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        response = await client.get('/value')

    assert response.json() == {'shared': True}
    assert events == ['shared']
    route = _route(app, '/value')
    assert all(_dependency_call_name(node) != '_EndpointProgram' for node in route.dependant.dependencies)
    assert all(_dependency_call_name(node) != '_InjectResolver' for node in route.dependant.dependencies)


@pytest.mark.asyncio
async def test_install_compiles_singleton_injection_into_the_route_call() -> None:
    """The compiled wrapper receives FastAPI's request without a depin dependency node."""
    constructed: list[str] = []

    class Singleton:
        def __init__(self) -> None:
            constructed.append('singleton')

    container = Container().bind(Singleton).freeze()
    _ = await container.awarmup()
    app = FastAPI()

    async def native(request: FastAPIRequest) -> FastAPIRequest:
        return request

    @app.get('/value/{item_id}')
    async def value(
        request: FastAPIRequest,
        item_id: int,
        singleton: Inject[Singleton],
        native_request: Annotated[FastAPIRequest, Depends(native)],
    ) -> dict[str, object]:
        try:
            active_frame()
        except OutsideScopeError:
            frame_open = False
        else:
            frame_open = True
        return {
            'same_request': request is native_request,
            'singleton': singleton is container[Singleton],
            'frame_open': frame_open,
            'item_id': item_id,
        }

    _ = value
    fastapi_ext.install(app, container)

    route = _route(app, '/value/{item_id}')
    assert all(_dependency_call_name(node) != '_EndpointProgram' for node in route.dependant.dependencies)
    assert all(_dependency_call_name(node) != '_InjectResolver' for node in route.dependant.dependencies)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        response = await client.get('/value/7')
        invalid = await client.get('/value/not-an-int')

    assert response.json() == {'same_request': True, 'singleton': True, 'frame_open': False, 'item_id': 7}
    assert invalid.status_code == 422
    assert constructed == ['singleton']
    assert 'request' not in app.openapi()['paths']['/value/{item_id}']['get']['parameters']


@pytest.mark.asyncio
async def test_install_keeps_internal_request_argument_distinct_from_fastapi_values() -> None:
    """The hidden request value cannot overwrite any FastAPI-produced argument."""

    class Singleton:
        pass

    async def native() -> str:
        return 'native'

    app = FastAPI()

    @app.get('/query')
    async def query(singleton: Inject[Singleton], __depin_request__: int) -> dict[str, int]:
        del singleton
        return {'value': __depin_request__}

    @app.get('/path/{__depin_request__}')
    async def path(singleton: Inject[Singleton], __depin_request__: int) -> dict[str, int]:
        del singleton
        return {'value': __depin_request__}

    @app.get('/dependency')
    async def dependency(singleton: Inject[Singleton], __depin_request__: str = Depends(native)) -> dict[str, str]:
        del singleton
        return {'value': __depin_request__}

    _ = query, path, dependency
    fastapi_ext.install(app, Container().bind(Singleton).freeze())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        query_response = await client.get('/query?__depin_request__=7')
        path_response = await client.get('/path/8')
        dependency_response = await client.get('/dependency')
        invalid_response = await client.get('/query?__depin_request__=not-an-int')

    assert query_response.json() == {'value': 7}
    assert path_response.json() == {'value': 8}
    assert dependency_response.json() == {'value': 'native'}
    assert invalid_response.status_code == 422
    schema = app.openapi()
    assert schema['paths']['/query']['get']['parameters'][0]['name'] == '__depin_request__'
    assert schema['paths']['/path/{__depin_request__}']['get']['parameters'][0]['name'] == '__depin_request__'


@pytest.mark.asyncio
async def test_install_reserves_fastapi_special_value_names_in_direct_and_nested_dependants() -> None:
    """The synthetic request argument cannot shadow FastAPI's special values."""

    class Singleton:
        pass

    async def nested_connection(__depin_request__: HTTPConnection) -> str:
        return __depin_request__.url.path

    async def nested_response_dependency(__depin_request__: Response) -> str:
        __depin_request__.headers['x-nested-response'] = 'yes'
        return 'response'

    async def nested_background(__depin_request__: BackgroundTasks) -> str:
        __depin_request__.add_task(lambda: None)
        return 'background'

    async def nested_security(__depin_request__: SecurityScopes) -> str:
        return ','.join(__depin_request__.scopes)

    app = FastAPI()

    @app.get('/connection')
    async def connection(singleton: Inject[Singleton], __depin_request__: HTTPConnection) -> dict[str, str]:
        del singleton
        return {'value': __depin_request__.url.path}

    @app.get('/response')
    async def response(singleton: Inject[Singleton], __depin_request__: Response) -> dict[str, str]:
        del singleton
        __depin_request__.headers['x-response'] = 'yes'
        return {'value': 'response'}

    @app.get('/background')
    async def background(singleton: Inject[Singleton], __depin_request__: BackgroundTasks) -> dict[str, str]:
        del singleton
        __depin_request__.add_task(lambda: None)
        return {'value': 'background'}

    @app.get('/security')
    async def security(singleton: Inject[Singleton], __depin_request__: SecurityScopes) -> dict[str, str]:
        del singleton
        return {'value': ','.join(__depin_request__.scopes)}

    @app.get('/nested')
    async def nested(
        singleton: Inject[Singleton],
        connection_value: str = Depends(nested_connection),
        response_value: str = Depends(nested_response_dependency),
        background_value: str = Depends(nested_background),
        security_value: str = Depends(nested_security),
    ) -> dict[str, str]:
        del singleton
        return {
            'connection': connection_value,
            'response': response_value,
            'background': background_value,
            'security': security_value,
        }

    _ = connection, response, background, security, nested
    fastapi_ext.install(app, Container().bind(Singleton).freeze())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        connection_response = await client.get('/connection')
        response_response = await client.get('/response')
        background_response = await client.get('/background')
        security_response = await client.get('/security')
        nested_http_response = await client.get('/nested')

    assert connection_response.json() == {'value': '/connection'}
    assert response_response.json() == {'value': 'response'}
    assert response_response.headers['x-response'] == 'yes'
    assert background_response.json() == {'value': 'background'}
    assert security_response.json() == {'value': ''}
    assert nested_http_response.json() == {
        'connection': '/nested',
        'response': 'response',
        'background': 'background',
        'security': '',
    }
    assert nested_http_response.headers['x-nested-response'] == 'yes'
    schema = app.openapi()
    assert all(
        parameter['name'] != '__depin_request__'
        for parameter in schema['paths']['/connection']['get'].get('parameters', [])
    )
    assert all(
        parameter['name'] != '__depin_request__'
        for parameter in schema['paths']['/nested']['get'].get('parameters', [])
    )


@pytest.mark.asyncio
async def test_install_leaves_a_route_without_injection_unchanged() -> None:
    """A compiler regression would mutate native FastAPI routes."""
    app = FastAPI()

    @app.get('/plain')
    async def plain(value: int) -> dict[str, int]:
        return {'value': value}

    _ = plain

    route = _route(app, '/plain')
    original_endpoint: object = route.endpoint
    original_dependencies = route.dependant.dependencies

    fastapi_ext.install(app, Container().freeze())

    assert route.endpoint is original_endpoint
    assert route.dependant.dependencies is original_dependencies

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        response = await client.get('/plain?value=4')
    assert response.json() == {'value': 4}
