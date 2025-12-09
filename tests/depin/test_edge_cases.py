from depin import Container, RequestScopeService, Scope


def test_resolve_same_class_different_scopes():
    """Não deve ser possível, mas testa o comportamento"""
    c = Container()

    class A:
        call_count = 0

        def __init__(self):
            A.call_count += 1

    c.bind(source=A, scope=Scope.SINGLETON)

    # Segunda tentativa de registro sobrescreve
    c.bind(source=A, scope=Scope.TRANSIENT)

    a1 = c.get(A)
    a2 = c.get(A)

    # Deve usar o último registro (TRANSIENT)
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

    # Todos devem compartilhar a mesma instância de Logger
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

    # Request 1
    with RequestScopeService.request_scope():
        c1 = c.get(Counter)
        c1.value = 10
        c1_again = c.get(Counter)

    # Request 2
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

    # TransientService deve ter 3 instâncias
    assert len(TransientService.instances) == 3
    assert t1 is not t2

    # SingletonService deve ter apenas 1 instância
    assert len(SingletonService.instances) == 1
    assert t1.singleton is t2.singleton is t3.singleton
