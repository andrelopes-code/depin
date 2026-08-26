"""Container construction and composition of binding sources."""

import pytest

from depin._core.container import Container
from depin._core.markers import Token
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin.errors import InvalidProviderError


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

    c = Container(r1, r2)
    sources = [rec.source for rec in c.records()]
    assert sources == [A, B]


def test_container_merge_appends_records() -> None:
    class A: ...

    r = Registry().bind(A, scope=Scope.SINGLETON)
    c = Container().include(r)
    assert [rec.source for rec in c.records()] == [A]


def test_container_singleton_decorator() -> None:
    c = Container()

    @c.singleton()
    class A: ...

    assert [rec.source for rec in c.records()] == [A]


def test_a_new_container_has_no_bindings() -> None:
    assert list(Container().records()) == []


def test_a_container_can_include_another_container() -> None:
    class A: ...

    source = Container().bind(A, scope=Scope.SINGLETON)
    assert len(list(Container().include(source).records())) == 1


def test_a_container_accepts_sources_at_construction() -> None:
    class A: ...

    class B: ...

    di = Container(Registry().bind(A), Registry().bind(B)).freeze()
    assert isinstance(di[A], A)
    assert isinstance(di[B], B)


def test_the_scope_decorators_register_a_factory_and_return_it_unchanged() -> None:
    container = Container()

    @container.scoped(provides=int)
    def make_scoped() -> int:
        return 1

    @container.transient(provides=str)
    def make_transient() -> str:
        return 'x'

    scopes = {rec.scope for rec in container.records()}
    assert scopes == {Scope.SCOPED, Scope.TRANSIENT}
    assert make_scoped() == 1
    assert make_transient() == 'x'


def test_the_scope_decorators_reject_a_non_callable_target() -> None:
    with pytest.raises(InvalidProviderError, match='expected a class or a callable'):
        Container().singleton()(42)  # pyright: ignore[reportArgumentType, reportCallIssue, reportUnusedCallResult]
