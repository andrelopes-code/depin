from depin._core.markers import Token
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin._core.spec import BindRecord


def test_registry_starts_empty() -> None:
    r = Registry()
    assert list(r.records()) == []


def test_bind_adds_record() -> None:
    class A: ...

    r = Registry()
    _ = r.bind(A, scope=Scope.SINGLETON)
    [rec] = list(r.records())
    assert rec.source is A
    assert rec.scope is Scope.SINGLETON
    assert rec.tag is None


def test_value_adds_record_with_token() -> None:
    tok = Token[str]('x')
    r = Registry()
    _ = r.value(tok, 'hello')
    [rec] = list(r.records())
    assert isinstance(rec, BindRecord)
    assert rec.scope is Scope.SINGLETON


def test_decorator_singleton_returns_same_class() -> None:
    r = Registry()

    @r.singleton()
    class A: ...

    [rec] = list(r.records())
    assert rec.source is A
    assert rec.scope is Scope.SINGLETON


def test_chained_calls_return_self() -> None:
    r = Registry()

    class A: ...

    result = r.bind(A, scope=Scope.SCOPED)
    assert result is r


def test_named_registry_carries_name() -> None:
    r = Registry('services')
    assert r.name == 'services'


def test_merge_concats_records_in_order() -> None:
    class A: ...

    class B: ...

    r1 = Registry().bind(A, scope=Scope.SINGLETON)
    r2 = Registry().bind(B, scope=Scope.SCOPED)

    merged = r1 | r2
    sources = [rec.source for rec in merged.records()]
    assert sources == [A, B]


def test_merge_does_not_mutate_originals() -> None:
    class A: ...

    class B: ...

    r1 = Registry().bind(A, scope=Scope.SINGLETON)
    r2 = Registry().bind(B, scope=Scope.SCOPED)
    _ = r1 | r2

    assert [rec.source for rec in r1.records()] == [A]
    assert [rec.source for rec in r2.records()] == [B]
