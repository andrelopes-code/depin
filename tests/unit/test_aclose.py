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
async def test_built_deps_torn_down_when_later_resolution_fails() -> None:
    log: list[str] = []

    async def good() -> AsyncGenerator[str]:
        log.append('good-setup')
        yield 'g'
        log.append('good-teardown')

    class Boom(Exception): ...

    async def bad() -> AsyncGenerator[int]:
        raise Boom
        yield 0  # type: ignore[unreachable]  # the yield makes `bad` an async generator function; it is dead by design

    frozen = (
        Container().bind(good, scope=Scope.SCOPED, provides=str).bind(bad, scope=Scope.SCOPED, provides=int).freeze()
    )

    async def use_scope() -> None:
        async with frozen.ascope():
            _ = await frozen.aresolve(str)
            _ = await frozen.aresolve(int)

    with pytest.raises(Boom):
        await use_scope()

    assert log == ['good-setup', 'good-teardown']


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
