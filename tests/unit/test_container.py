"""Container construction and composition of binding sources."""

from collections.abc import Callable, Iterable
from typing import Annotated, override

import pytest

from depin._core.container import Container
from depin._core.discovery import Catalog, Manifest, provider
from depin._core.markers import Named, Token
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin._core.spec import BindRecord
from depin.errors import InvalidProviderError


class _MissingRecords: ...


class _NonCallableRecords:
    records = 42


class _NonIterableRecords:
    def records(self) -> object:
        return object()


class _InvalidMemberRecords:
    def records(self) -> Iterable[object]:
        return (object(),)


class _RecordsFailure(Exception): ...


class _UnreadableRecords:
    @override
    def __getattribute__(self, name: str) -> object:
        if name == 'records':
            raise _RecordsFailure('records cannot be read')
        return object.__getattribute__(self, name)

    def records(self) -> Iterable[BindRecord]:
        return ()


class _DynamicRecords:
    @override
    def __getattribute__(self, name: str) -> object:
        if name == 'records':

            def records() -> Iterable[BindRecord]:
                return ()

            return records
        return object.__getattribute__(self, name)


class _RaisingRecords:
    def records(self) -> Iterable[BindRecord]:
        raise _RecordsFailure('records cannot be called')


def _call(callable_: Callable[..., object], arguments: tuple[object, ...]) -> object:
    return callable_(*arguments)


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


def test_container_constructor_and_include_accept_a_complete_manifest() -> None:
    class A: ...

    class B: ...

    manifest = Manifest(__name__, Catalog(__name__, provider(A), provider(B)))
    expected = (
        BindRecord(A, Scope.SINGLETON, None, None),
        BindRecord(B, Scope.SINGLETON, None, None),
    )

    constructed = Container(manifest)
    included = Container().include(manifest)

    assert constructed.records() == expected
    assert included.records() == expected


def test_container_rejects_a_catalog_until_it_is_composed_through_a_manifest() -> None:
    catalog = Catalog(__name__, provider(ValueError))

    with pytest.raises(InvalidProviderError) as exc:
        _call(Container, (catalog,))

    message = str(exc.value)
    assert repr(catalog) in message
    assert 'Manifest' in message
    assert 'Catalog' in message


@pytest.mark.parametrize(
    ('source_type', 'expected_context', 'failure_cause'),
    [
        (_MissingRecords, 'records', False),
        (_NonCallableRecords, 'callable', False),
        (_NonIterableRecords, 'iterable', False),
        (_InvalidMemberRecords, 'BindRecord', False),
        (_UnreadableRecords, 'reading its records', True),
        (_DynamicRecords, 'does not satisfy Bindings', False),
        (_RaisingRecords, 'records() raised', True),
    ],
)
def test_container_include_rejects_malformed_structural_sources_atomically(
    source_type: type[object],
    expected_context: str,
    failure_cause: bool,
) -> None:
    class Existing: ...

    container = Container().bind(Existing)
    before = tuple(container.records())
    source = source_type()

    with pytest.raises(InvalidProviderError) as exc:
        _call(container.include, (source,))

    message = str(exc.value)
    assert repr(source) in message
    assert expected_context in message
    assert 'Bindings' in message or 'return' in message
    assert container.records() == before
    if failure_cause:
        assert isinstance(exc.value.__cause__, _RecordsFailure)


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


def test_scope_decorators_preserve_provides_and_tag() -> None:
    class Contract: ...

    container = Container()

    @container.singleton(provides=Contract, tag='singleton')
    class SingletonImplementation(Contract): ...

    @container.scoped(provides=Contract, tag='scoped')
    class ScopedImplementation(Contract): ...

    @container.transient(provides=Contract, tag='transient')
    class TransientImplementation(Contract): ...

    assert [(record.source, record.scope, record.provides, record.tag) for record in container.records()] == [
        (SingletonImplementation, Scope.SINGLETON, Contract, 'singleton'),
        (ScopedImplementation, Scope.SCOPED, Contract, 'scoped'),
        (TransientImplementation, Scope.TRANSIENT, Contract, 'transient'),
    ]


def test_scope_value_preserves_its_tag_and_scope() -> None:
    token = Token[int]('request.id')
    [record] = Container().scope_value(token, tag='request').records()
    assert record.scope is Scope.SCOPED
    assert record.tag == 'request'


def test_the_scope_decorators_reject_a_non_callable_target() -> None:
    with pytest.raises(InvalidProviderError, match='expected a class or a callable'):
        Container().singleton()(42)  # type: ignore[call-overload]  # pyright: ignore[reportArgumentType, reportCallIssue, reportUnusedCallResult]


def test_bind_registers_a_factory_under_a_token_given_as_provides() -> None:
    port = Token[int]('port')

    def make() -> int:
        return 8080

    di = Container().bind(make, provides=port).freeze()
    assert di.resolve(port) == 8080


def test_a_scope_decorator_registers_under_a_token_given_as_provides() -> None:
    port = Token[int]('port')
    container = Container()

    @container.singleton(provides=port)
    def make() -> int:
        return 8080

    di = container.freeze()
    assert di.resolve(port) == 8080
    assert make() == 8080


def test_freeze_rejects_a_provides_value_that_is_no_key() -> None:
    def make() -> int:
        return 1

    with pytest.raises(InvalidProviderError, match='as a provider key'):
        _ = Container().bind(make, provides=42).freeze()  # type: ignore[call-overload]  # pyright: ignore[reportArgumentType]


def test_bind_registers_a_factory_under_a_name_given_as_provides() -> None:
    def make() -> int:
        return 8080

    def consumer(port: Annotated[int, Named('http.port')]) -> str:
        return f'port {port}'

    di = Container().bind(make, provides='http.port').bind(consumer, provides=str).freeze()
    assert di.resolve(str) == 'port 8080'
