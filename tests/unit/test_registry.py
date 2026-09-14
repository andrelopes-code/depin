from collections.abc import Callable, Iterable
from typing import override

import pytest

from depin._core.discovery import Catalog, Manifest, provider
from depin._core.markers import Token
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin._core.spec import BindRecord
from depin.errors import InvalidProviderError


class _SourceFailure(Exception): ...


class _FailingBindings:
    def __init__(self, record: BindRecord, failure: Exception) -> None:
        self._record = record
        self._failure = failure

    def records(self) -> Iterable[BindRecord]:
        yield self._record
        raise self._failure


class _CountingBindings:
    def __init__(self, record: BindRecord) -> None:
        self._record = record
        self.calls = 0

    def records(self) -> Iterable[BindRecord]:
        self.calls += 1
        return (self._record,)


class _TrackingRecords(list[BindRecord]):
    def __init__(self) -> None:
        super().__init__()
        self.extend_calls = 0

    @override
    def extend(self, values: Iterable[BindRecord]) -> None:
        self.extend_calls += 1
        super().extend(values)


def _call(callable_: Callable[..., object], arguments: tuple[object, ...]) -> object:
    return callable_(*arguments)


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


def test_registry_default_name_is_empty() -> None:
    assert Registry().name == ''


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


@pytest.mark.parametrize(
    ('left_name', 'right_name', 'expected_name'),
    [('left', 'right', 'left'), ('', 'right', 'right'), ('left', '', 'left')],
)
def test_merge_keeps_the_first_non_empty_name(left_name: str, right_name: str, expected_name: str) -> None:
    assert (Registry(left_name) | Registry(right_name)).name == expected_name


def test_registry_manifest_ingestion_calls_records_once_and_extends_once() -> None:
    class A: ...

    manifest = Manifest(__name__, Catalog(__name__, provider(A)))
    source = _CountingBindings(BindRecord(ValueError, Scope.SINGLETON, None, None))
    registry = Registry()
    tracking = _TrackingRecords()
    object.__setattr__(registry, '_records', tracking)

    registry.include(manifest, source)

    assert tracking.extend_calls == 2
    assert source.calls == 1
    assert tuple(tracking) == (
        BindRecord(A, Scope.SINGLETON, None, None),
        BindRecord(ValueError, Scope.SINGLETON, None, None),
    )


def test_registry_include_is_atomic_when_source_iteration_fails() -> None:
    class Existing: ...

    failure = _SourceFailure('source iteration failed')
    source = _FailingBindings(BindRecord(RuntimeError, Scope.SINGLETON, None, None), failure)
    registry = Registry()
    tracking = _TrackingRecords()
    object.__setattr__(registry, '_records', tracking)
    registry.bind(Existing)
    before = tuple(registry.records())
    prior_extend_calls = tracking.extend_calls

    with pytest.raises(InvalidProviderError) as exc:
        registry.include(source)

    assert exc.value.__cause__ is failure
    assert repr(source) in str(exc.value)
    assert 'records()' in str(exc.value)
    assert tuple(registry.records()) == before
    assert tracking.extend_calls == prior_extend_calls


def test_registry_include_keeps_earlier_source_when_a_later_source_fails() -> None:
    class Existing: ...

    class Added: ...

    failure = _SourceFailure('later source failed')
    failing = _FailingBindings(BindRecord(RuntimeError, Scope.SINGLETON, None, None), failure)
    registry = Registry().bind(Existing)
    successful = Registry().bind(Added)

    with pytest.raises(InvalidProviderError) as exc:
        registry.include(successful, failing)

    assert exc.value.__cause__ is failure
    assert tuple(record.source for record in registry.records()) == (Existing, Added)


def test_registry_rejects_a_catalog_until_it_is_composed_through_a_manifest() -> None:
    catalog = Catalog(__name__, provider(ValueError))

    with pytest.raises(InvalidProviderError) as exc:
        _call(Registry().include, (catalog,))

    message = str(exc.value)
    assert repr(catalog) in message
    assert 'Manifest' in message
    assert 'Catalog' in message
