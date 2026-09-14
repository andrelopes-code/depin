"""Declarative provider values, ownership, and immutable composition."""

import inspect
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from dataclasses import FrozenInstanceError
from typing import Protocol, assert_type, runtime_checkable

import pytest

from depin._core import discovery as discovery_module
from depin._core.discovery import Provider, provider
from depin._core.markers import provides
from depin._core.scope import Scope
from depin.errors import InvalidProviderError

_DATA_ATTRIBUTE = '_data'
_TOKEN_ATTRIBUTE = '_ProviderToken'


class Service: ...


class _LocationView(Protocol):
    module: str
    filename: str
    line: int


@runtime_checkable
class _ProviderDataView(Protocol):
    target: object
    scope: Scope
    provides: object | None
    tag: str | None
    condition: object | None
    check: object | None
    owner: str
    location: _LocationView


def make_service(name: str) -> Service:
    del name
    return Service()


async def make_service_async(name: str) -> Service:
    del name
    return Service()


def generate_service(name: str) -> Generator[Service, None, None]:
    del name
    yield Service()


async def generate_service_async(name: str) -> AsyncGenerator[Service, None]:
    del name
    yield Service()


@contextmanager
def manage_service(name: str) -> Generator[Service, None, None]:
    del name
    yield Service()


@asynccontextmanager
async def manage_service_async(name: str) -> AsyncGenerator[Service, None]:
    del name
    yield Service()


def declared_provider_types() -> None:
    assert_type(provider(Service), Provider[Service])
    assert_type(provider(make_service), Provider[Service])
    assert_type(provider(make_service_async), Provider[Service])
    assert_type(provider(generate_service), Provider[Service])
    assert_type(provider(generate_service_async), Provider[Service])
    assert_type(provider(manage_service), Provider[Service])
    assert_type(provider(manage_service_async), Provider[Service])

    sync_manager: Callable[[str], AbstractContextManager[Service]] = manage_service
    async_manager: Callable[[str], AbstractAsyncContextManager[Service]] = manage_service_async
    assert_type(provider(sync_manager), Provider[Service])
    assert_type(provider(async_manager), Provider[Service])


def _call(callable_: Callable[..., object], arguments: tuple[object, ...]) -> object:
    return callable_(*arguments)


def _call_with_keywords(callable_: Callable[..., object], keywords: dict[str, object]) -> object:
    return callable_(**keywords)


def _provider_data(declaration: object) -> _ProviderDataView:
    snapshot: object = getattr(declaration, _DATA_ATTRIBUTE)
    if not isinstance(snapshot, _ProviderDataView):
        pytest.fail('Provider does not expose its private immutable snapshot')
    return snapshot


def _private_provider_token() -> object:
    token_type: object = getattr(discovery_module, _TOKEN_ATTRIBUTE)
    if not callable(token_type):
        pytest.fail('_ProviderToken is not callable')
    return token_type()


def test_provider_stores_the_exact_target_and_location() -> None:
    frame = inspect.currentframe()
    if frame is None:
        pytest.fail('inspect.currentframe() did not expose the test frame')
    declaration_line = frame.f_lineno + 1
    declaration = provider(Service)
    data = _provider_data(declaration)

    assert data.target is Service
    assert data.owner == __name__
    assert data.location.module == __name__
    assert data.location.filename == __file__
    assert data.location.line == declaration_line


def test_provider_is_frozen_and_slotted() -> None:
    declaration = provider(Service)

    with pytest.raises(FrozenInstanceError):
        setattr(declaration, _DATA_ATTRIBUTE, _provider_data(declaration))
    assert not hasattr(declaration, '__dict__')


@pytest.mark.parametrize('target', [None, 42, object()], ids=['none', 'integer', 'instance'])
def test_provider_rejects_unsupported_targets(target: object) -> None:
    with pytest.raises(InvalidProviderError, match='pass a class or callable'):
        _call(provider, (target,))


@pytest.mark.parametrize(
    'arguments',
    [(), (object(),), (_private_provider_token(),)],
    ids=['no-arguments', 'foreign-token', 'private-token'],
)
def test_provider_rejects_direct_construction(arguments: tuple[object, ...]) -> None:
    with pytest.raises(InvalidProviderError, match=r'use provider\(target\)'):
        _call(Provider, arguments)


def configured_provider_types() -> None:
    declaration = provider(Service)

    def check_service(service: Service) -> bool:
        del service
        return True

    assert_type(declaration.configure(check=check_service), Provider[Service])


def test_provider_configure_replaces_all_metadata_without_mutating_the_original() -> None:
    class Contract: ...

    condition_calls = 0
    check_calls = 0

    def condition() -> bool:
        nonlocal condition_calls
        condition_calls += 1
        return True

    def check(service: Service) -> bool:
        nonlocal check_calls
        check_calls += 1
        del service
        return True

    declaration = provider(Service)
    original = _provider_data(declaration)

    configured = declaration.configure(
        scope=Scope.SCOPED,
        provides=Contract,
        tag='primary',
        when=condition,
        check=check,
    )
    configured_data = _provider_data(configured)

    assert configured is not declaration
    assert configured_data.target is Service
    assert configured_data.scope is Scope.SCOPED
    assert configured_data.provides is Contract
    assert configured_data.tag == 'primary'
    assert configured_data.condition is condition
    assert configured_data.check is check
    assert configured_data.owner == original.owner
    assert configured_data.location is original.location
    assert original.scope is Scope.SINGLETON
    assert original.provides is None
    assert original.tag is None
    assert original.condition is None
    assert original.check is None
    assert condition_calls == 0
    assert check_calls == 0


def test_provider_configure_resets_omitted_metadata_on_a_later_call() -> None:
    class Contract: ...

    def condition() -> bool:
        return True

    def check(service: Service) -> bool:
        del service
        return True

    first = provider(Service).configure(
        scope=Scope.TRANSIENT,
        provides=Contract,
        tag='temporary',
        when=condition,
        check=check,
    )

    second = first.configure()
    data = _provider_data(second)

    assert data.scope is Scope.SINGLETON
    assert data.provides is None
    assert data.tag is None
    assert data.condition is None
    assert data.check is None


def test_provider_configure_from_another_module_retains_declaration_ownership() -> None:
    declaration = provider(Service)
    original = _provider_data(declaration)
    namespace: dict[str, object] = {'__name__': 'foreign_configuration', 'declaration': declaration}

    exec("configured = declaration.configure(tag='foreign')", namespace)
    configured = namespace['configured']
    data = _provider_data(configured)

    assert data.owner == __name__
    assert data.location is original.location


def test_provider_configure_preserves_provides_marker_applied_before_declaration() -> None:
    class Contract: ...

    @provides(Contract)
    class Implementation: ...

    declaration = provider(Implementation).configure(tag='before')

    assert _provider_data(declaration).target is Implementation


def test_provider_configure_preserves_provides_marker_applied_after_declaration() -> None:
    class Contract: ...

    class Implementation: ...

    declaration = provider(Implementation).configure(tag='after')
    marked = provides(Contract)(Implementation)

    assert marked is Implementation
    assert _provider_data(declaration).target is Implementation


@pytest.mark.parametrize(
    ('keyword', 'value'),
    [
        ('scope', 'singleton'),
        ('provides', object()),
        ('tag', 1),
        ('when', object()),
        ('check', object()),
    ],
)
def test_provider_configure_rejects_invalid_runtime_metadata(keyword: str, value: object) -> None:
    declaration = provider(Service)

    with pytest.raises(InvalidProviderError, match=keyword):
        _call_with_keywords(declaration.configure, {keyword: value})
