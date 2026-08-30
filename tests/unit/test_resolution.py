"""Synchronous resolution: lookups, defaults, and the errors a bad key produces."""

import subprocess
import sys
from typing import Annotated, Protocol

import pytest

from depin._core.container import Container
from depin._core.frozen import FrozenContainer
from depin._core.markers import Tag, injected, provides
from depin._core.scope import Scope
from depin.errors import AsyncInSyncContextError, CircularDependencyError, MissingProviderError


def test_resolving_an_unregistered_key_names_the_key() -> None:
    class Unregistered: ...

    frozen = Container().freeze()
    with pytest.raises(MissingProviderError, match='Unregistered'):
        _ = frozen[Unregistered]


def test_resolving_a_value_that_is_not_a_provider_key_raises() -> None:
    frozen = Container().freeze()
    with pytest.raises(MissingProviderError, match='not a valid key type'):
        frozen.resolve(42)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType, reportUnusedCallResult]


def test_a_protocol_key_resolves_through_subscript() -> None:
    class Store(Protocol):
        def get(self) -> str: ...

    # `Store` is a Protocol; mypy treats any type[Protocol] argument as
    # non-instantiable, a separate known limitation from the one this test
    # guards against — provides() only stores the key, it never instantiates it.
    @provides(Store)  # type: ignore[type-abstract]
    class MemStore:
        def get(self) -> str:
            return 'v'

    frozen = Container().bind(MemStore).freeze()
    assert frozen[Store].get() == 'v'


def test_sync_resolution_of_an_async_provider_points_at_aresolve() -> None:
    class Service: ...

    async def make() -> Service:
        return Service()

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Service).freeze()
    with pytest.raises(
        AsyncInSyncContextError,
        match=r'Service requires async resolution; call aresolve\(\) instead$',
    ):
        _ = frozen[Service]


def test_sync_recursive_resolution_names_the_cyclic_provider() -> None:
    script = """
from depin import Container, Scope
from depin.errors import CircularDependencyError

frozen: object

def make() -> int:
    return frozen.resolve(int)

frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
try:
    frozen.resolve(int)
except CircularDependencyError as exc:
    print(exc)
else:
    raise AssertionError('recursive resolution did not raise CircularDependencyError')
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == (
        'int is already constructing in this context; '
        'resolve a different dependency or break the recursive provider call\n'
    )


def test_an_unbound_parameter_with_a_default_keeps_its_default() -> None:
    class Settings:
        def __init__(self, retries: int = 11) -> None:
            self.retries = retries

    frozen = Container().bind(Settings, scope=Scope.SINGLETON).freeze()
    assert frozen[Settings].retries == 11


def test_defaulted_dependency_does_not_skip_a_later_required_dependency() -> None:
    class OptionalDependency: ...

    default = OptionalDependency()

    class Result:
        def __init__(self, optional: OptionalDependency = default, *, number: int) -> None:
            self.optional = optional
            self.number = number

    frozen = Container().bind(lambda: 7, provides=int).bind(Result).freeze()
    assert frozen[Result].optional is default
    assert frozen[Result].number == 7


def test_a_tagged_provider_is_only_reachable_through_its_tag() -> None:
    class Store: ...

    frozen = Container().bind(Store, scope=Scope.SINGLETON, tag='primary').freeze()
    assert isinstance(frozen.resolve(Store, tag='primary'), Store)
    with pytest.raises(MissingProviderError):
        _ = frozen[Store]


@pytest.mark.asyncio
async def test_async_injection_preserves_a_dependency_tag() -> None:
    class Store:
        def __init__(self, label: str) -> None:
            self.label = label

    frozen = (
        Container()
        .bind(lambda: Store('default'), provides=Store)
        .bind(lambda: Store('primary'), provides=Store, tag='primary')
        .freeze()
    )

    @frozen.inject
    async def handler(store: Annotated[Store, Tag('primary')] = injected(Store, tag='primary')) -> str:
        return store.label

    assert await handler() == 'primary'


@pytest.mark.asyncio
async def test_async_recursive_resolution_has_the_full_actionable_message() -> None:
    frozen: FrozenContainer

    async def make() -> int:
        return await frozen.aresolve(int)

    frozen = Container().bind(make, provides=int).freeze()
    with pytest.raises(
        CircularDependencyError,
        match=(
            r'^int is already constructing in this context; '
            r'resolve a different dependency or break the recursive provider call$'
        ),
    ):
        await frozen.aresolve(int)


@pytest.mark.asyncio
async def test_async_defaulted_dependency_does_not_skip_a_later_required_dependency() -> None:
    class OptionalDependency: ...

    default = OptionalDependency()

    class Result:
        def __init__(self, optional: OptionalDependency = default, *, number: int) -> None:
            self.optional = optional
            self.number = number

    async def make_result(optional: OptionalDependency = default, *, number: int) -> Result:
        return Result(optional, number=number)

    frozen = Container().bind(lambda: 7, provides=int).bind(make_result).freeze()
    result = await frozen.aresolve(Result)
    assert result.optional is default
    assert result.number == 7
