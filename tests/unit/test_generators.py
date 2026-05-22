from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope


def test_sync_generator_teardown_on_scope_exit() -> None:
    cleaned: list[str] = []

    def make() -> Generator[str]:
        cleaned.append('setup')
        yield 'value'
        cleaned.append('teardown')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=str).freeze()
    with frozen.scope():
        assert frozen[str] == 'value'
        assert cleaned == ['setup']
    assert cleaned == ['setup', 'teardown']


def test_sync_generator_teardown_runs_in_reverse() -> None:
    order: list[str] = []

    def make_first() -> Generator[int]:
        order.append('first-setup')
        yield 1
        order.append('first-teardown')

    def make_second(first: int) -> Generator[str]:
        order.append('second-setup')
        yield f'b{first}'
        order.append('second-teardown')

    frozen = (
        Container()
        .bind(make_first, scope=Scope.SCOPED, provides=int)
        .bind(make_second, scope=Scope.SCOPED, provides=str)
        .freeze()
    )
    with frozen.scope():
        assert frozen[str] == 'b1'
    assert order == ['first-setup', 'second-setup', 'second-teardown', 'first-teardown']


@pytest.mark.asyncio
async def test_async_generator_teardown_on_ascope_exit() -> None:
    cleaned: list[str] = []

    async def make() -> AsyncGenerator[str]:
        cleaned.append('setup')
        yield 'value'
        cleaned.append('teardown')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=str).freeze()
    async with frozen.ascope():
        assert await frozen.aresolve(str) == 'value'
    assert cleaned == ['setup', 'teardown']
