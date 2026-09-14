"""Declarative provider values, ownership, and immutable composition."""

import inspect
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from dataclasses import FrozenInstanceError
from typing import Protocol, assert_type, runtime_checkable

import pytest

from depin._core import discovery as discovery_module
from depin._core.discovery import Provider, provider
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
