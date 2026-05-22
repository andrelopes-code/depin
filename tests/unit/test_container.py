from depin._core.container import Container
from depin._core.markers import Token
from depin._core.registry import Registry
from depin._core.scope import Scope


def test_container_bind_returns_self() -> None:
    class A: ...

    c = Container()
    assert c.bind(A, scope=Scope.SINGLETON) is c


def test_container_value_with_token() -> None:
    tok = Token[int]('x')
    c = Container().value(tok, 42)
    [rec] = list(c.records())
    assert rec.scope is Scope.SINGLETON


def test_container_from_collects_registries() -> None:
    class A: ...

    class B: ...

    r1 = Registry().bind(A, scope=Scope.SINGLETON)
    r2 = Registry().bind(B, scope=Scope.SCOPED)

    c = Container.from_(r1, r2)
    sources = [rec.source for rec in c.records()]
    assert sources == [A, B]


def test_container_merge_appends_records() -> None:
    class A: ...

    r = Registry().bind(A, scope=Scope.SINGLETON)
    c = Container().merge(r)
    assert [rec.source for rec in c.records()] == [A]


def test_container_singleton_decorator() -> None:
    c = Container()

    @c.singleton()
    class A: ...

    assert [rec.source for rec in c.records()] == [A]
