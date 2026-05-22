import contextlib
from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope


def test_contextmanager_factory() -> None:
    cleaned: list[str] = []

    @contextlib.contextmanager
    def make() -> Generator[str]:
        cleaned.append('setup')
        yield 'cm'
        cleaned.append('teardown')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=str).freeze()
    with frozen.scope():
        assert frozen[str] == 'cm'
    assert cleaned == ['setup', 'teardown']


@pytest.mark.asyncio
async def test_asynccontextmanager_factory() -> None:
    cleaned: list[str] = []

    @contextlib.asynccontextmanager
    async def make() -> AsyncGenerator[str]:
        cleaned.append('setup')
        yield 'acm'
        cleaned.append('teardown')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=str).freeze()
    async with frozen.ascope():
        assert await frozen.aresolve(str) == 'acm'
    assert cleaned == ['setup', 'teardown']
