from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope


def test_scope_values() -> None:
    assert Scope.SINGLETON.value == 'singleton'
    assert Scope.SCOPED.value == 'scoped'
    assert Scope.TRANSIENT.value == 'transient'


def test_scope_distinct() -> None:
    assert {Scope.SINGLETON, Scope.SCOPED, Scope.TRANSIENT} == set(Scope)


def test_sync_scope_teardown_group_has_a_stable_message() -> None:
    def failing() -> Generator[int]:
        yield 1
        raise RuntimeError('failed')

    frozen = Container().bind(failing, scope=Scope.SCOPED, provides=int).freeze()
    with pytest.raises(ExceptionGroup) as exc, frozen.scope():
        assert frozen[int] == 1
    assert exc.value.message == 'depin teardown errors'


@pytest.mark.asyncio
async def test_async_scope_teardown_group_has_a_stable_message() -> None:
    async def failing() -> AsyncGenerator[int]:
        yield 1
        raise RuntimeError('failed')

    frozen = Container().bind(failing, scope=Scope.SCOPED, provides=int).freeze()
    with pytest.raises(ExceptionGroup) as exc:
        async with frozen.ascope():
            assert await frozen.aresolve(int) == 1
    assert exc.value.message == 'depin teardown errors'
