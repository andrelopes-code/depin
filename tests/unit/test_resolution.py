"""Synchronous resolution: lookups, defaults, and the errors a bad key produces."""

import pytest

from depin._core.container import Container
from depin._core.scope import Scope
from depin.errors import AsyncInSyncContextError, MissingProviderError


def test_resolving_an_unregistered_key_names_the_key() -> None:
    class Unregistered: ...

    frozen = Container().freeze()
    with pytest.raises(MissingProviderError, match='Unregistered'):
        _ = frozen[Unregistered]


def test_resolving_a_value_that_is_not_a_provider_key_raises() -> None:
    frozen = Container().freeze()
    with pytest.raises(MissingProviderError, match='not a valid key type'):
        frozen.resolve(42)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType, reportUnusedCallResult]


def test_sync_resolution_of_an_async_provider_points_at_aresolve() -> None:
    class Service: ...

    async def make() -> Service:
        return Service()

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Service).freeze()
    with pytest.raises(AsyncInSyncContextError, match='aresolve'):
        _ = frozen[Service]


def test_an_unbound_parameter_with_a_default_keeps_its_default() -> None:
    class Settings:
        def __init__(self, retries: int = 11) -> None:
            self.retries = retries

    frozen = Container().bind(Settings, scope=Scope.SINGLETON).freeze()
    assert frozen[Settings].retries == 11


def test_a_tagged_provider_is_only_reachable_through_its_tag() -> None:
    class Store: ...

    frozen = Container().bind(Store, scope=Scope.SINGLETON, tag='primary').freeze()
    assert isinstance(frozen.resolve(Store, tag='primary'), Store)
    with pytest.raises(MissingProviderError):
        _ = frozen[Store]
