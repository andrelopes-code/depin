from collections.abc import AsyncGenerator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope


@pytest.mark.asyncio
async def test_aclose_unwinds_singleton_generators() -> None:
    cleaned: list[str] = []

    async def make() -> AsyncGenerator[str]:
        cleaned.append('setup')
        yield 'v'
        cleaned.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert await frozen.aresolve(str) == 'v'
    await frozen.aclose()
    assert cleaned == ['setup', 'teardown']


@pytest.mark.asyncio
async def test_aclose_aggregates_errors() -> None:
    async def boom() -> AsyncGenerator[int]:
        yield 1
        raise RuntimeError('a')

    async def bang() -> AsyncGenerator[str]:
        yield 'x'
        raise RuntimeError('b')

    frozen = (
        Container()
        .bind(boom, scope=Scope.SINGLETON, provides=int)
        .bind(bang, scope=Scope.SINGLETON, provides=str)
        .freeze()
    )
    _ = await frozen.aresolve(int)
    _ = await frozen.aresolve(str)
    with pytest.raises(ExceptionGroup) as exc:
        await frozen.aclose()
    assert len(exc.value.exceptions) == 2
