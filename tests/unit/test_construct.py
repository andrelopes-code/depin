"""Construction diagnostics exposed through a frozen container."""

import functools
from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope
from depin.errors import InvalidProviderError


class _Result: ...


def test_context_manager_contract_failure_names_the_bound_key() -> None:
    def declared_shape() -> Generator[_Result]:
        yield _Result()

    @functools.wraps(declared_shape)
    def provider() -> object:
        return 42

    frozen = Container().bind(provider, scope=Scope.SINGLETON, provides=_Result).freeze()

    with pytest.raises(InvalidProviderError) as exc:
        _ = frozen[_Result]

    assert str(exc.value) == 'context-manager provider for _Result returned 42, which is not a context manager'


@pytest.mark.asyncio
async def test_async_context_manager_contract_failure_names_the_bound_key() -> None:
    async def declared_shape() -> AsyncGenerator[_Result]:
        yield _Result()

    @functools.wraps(declared_shape)
    def provider() -> object:
        return 42

    frozen = Container().bind(provider, scope=Scope.SINGLETON, provides=_Result).freeze()

    with pytest.raises(InvalidProviderError) as exc:
        _ = await frozen.aresolve(_Result)

    assert (
        str(exc.value)
        == 'async context-manager provider for _Result returned 42, which is not an async context manager'
    )
