import pytest

from depin import Container, RequestScopeService, Scope
from depin._internal.exceptions import MissingProviderError


def test_resolve_same_class_different_scopes():
    """Não deve ser possível, mas testa o comportamento"""
    c = Container()

    class A:
        call_count = 0

        def __init__(self):
            A.call_count += 1

    c.bind(source=A, scope=Scope.SINGLETON)

    c.bind(source=A, scope=Scope.TRANSIENT)

    a1 = c.get(A)
    a2 = c.get(A)

    assert a1 is not a2
    assert A.call_count == 2


def test_complex_dependency_graph():
    c = Container()

    class Logger:
        def __init__(self):
            self.logs = []

    class Database:
        def __init__(self, logger: Logger):
            self.logger = logger

    class Cache:
        def __init__(self, logger: Logger):
            self.logger = logger

    class Repository:
        def __init__(self, db: Database, cache: Cache, logger: Logger):
            self.db = db
            self.cache = cache
            self.logger = logger

    class Service:
        def __init__(self, repo: Repository, logger: Logger):
            self.repo = repo
            self.logger = logger

    c.bind(source=Logger, scope=Scope.SINGLETON)
    c.bind(source=Database, scope=Scope.SINGLETON)
    c.bind(source=Cache, scope=Scope.SINGLETON)
    c.bind(source=Repository, scope=Scope.SINGLETON)
    c.bind(source=Service, scope=Scope.SINGLETON)

    service = c.get(Service)

    assert service.logger is service.repo.logger
    assert service.repo.db.logger is service.logger
    assert service.repo.cache.logger is service.logger


def test_varargs_and_kwargs_ignored():
    c = Container()

    class Service:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    c.bind(source=Service, scope=Scope.SINGLETON)

    s = c.get(Service)
    assert s.args == ()
    assert s.kwargs == {}


def test_request_scope_isolation():
    c = Container()

    class Counter:
        def __init__(self):
            self.value = 0

    c.bind(source=Counter, scope=Scope.REQUEST)

    with RequestScopeService.request_scope():
        c1 = c.get(Counter)
        c1.value = 10
        c1_again = c.get(Counter)

    with RequestScopeService.request_scope():
        c2 = c.get(Counter)

    assert c1 is c1_again
    assert c1.value == 10
    assert c2.value == 0


def test_mixed_scopes_in_dependency_tree():
    c = Container()

    class SingletonService:
        instances = []  # type: ignore[var-annotated]

        def __init__(self):
            SingletonService.instances.append(self)

    class TransientService:
        instances = []  # type: ignore[var-annotated]

        def __init__(self, singleton: SingletonService):
            TransientService.instances.append(self)
            self.singleton = singleton

    c.bind(source=SingletonService, scope=Scope.SINGLETON)
    c.bind(source=TransientService, scope=Scope.TRANSIENT)

    t1 = c.get(TransientService)
    t2 = c.get(TransientService)
    t3 = c.get(TransientService)

    assert len(TransientService.instances) == 3
    assert t1 is not t2

    assert len(SingletonService.instances) == 1
    assert t1.singleton is t2.singleton is t3.singleton


@pytest.mark.asyncio
async def test_generators_in_singleton_scope_raises():
    c = Container()

    async def async_gen():
        yield 23

    def sync_gen():
        yield 23

    with pytest.raises(RuntimeError, match='Async generators are not supported'):
        c.bind(source=async_gen, scope=Scope.SINGLETON)

    with pytest.raises(RuntimeError, match='Generators are not supported'):
        c.bind(source=sync_gen, scope=Scope.SINGLETON)


@pytest.mark.asyncio
async def test_generators_in_transient_scope_raises():
    c = Container()

    async def async_gen():
        yield 23

    def sync_gen():
        yield 23

    with pytest.raises(RuntimeError, match='Async generators are not supported'):
        c.bind(source=async_gen, scope=Scope.TRANSIENT)

    with pytest.raises(RuntimeError, match='Generators are not supported'):
        c.bind(source=sync_gen, scope=Scope.TRANSIENT)


@pytest.mark.asyncio
async def test_bind_raises_when_no_type_or_callabe_provided_as_source():
    c = Container()

    with pytest.raises(ValueError, match='failed to register'):
        c.bind(source=888, scope=Scope.TRANSIENT)  # type: ignore


def test_raises_when_no_provider_found():
    c = Container()

    class Logger:
        pass

    with pytest.raises(MissingProviderError, match=f'Provider for {Logger} not registered'):
        c.get(Logger)


def test_raises_when_usign_sync_get_to_resolve_async_providers():
    c = Container()

    async def async_dep_func():
        return 'async'

    c.bind(source=async_dep_func, scope=Scope.TRANSIENT)

    with pytest.raises(RuntimeError, match=f'Provider for {async_dep_func} is asynchronous'):
        c.get(async_dep_func)


def test_register_throws_exception_for_missing_sources():
    c = Container()

    with pytest.raises(ValueError, match='abstract, implementation or callable_source must be provided'):
        c._register(scope=Scope.TRANSIENT, abstract=None, implementation=None, callable_source=None)  # type: ignore

    with pytest.raises(ValueError, match='implementation and callable_source cannot both be None'):
        c._register(scope=Scope.TRANSIENT, abstract=Container, implementation=None, callable_source=None)  # type: ignore

    with pytest.raises(ValueError, match='callable_source and implementation cannot be both non-none'):
        c._register(scope=Scope.TRANSIENT, abstract=None, implementation=Container, callable_source=Container)  # type: ignore
