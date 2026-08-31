"""`reset()` / `areset()`: dropping the singleton cache and draining what it held."""

from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope
from depin.errors import TeardownError


def test_reset_drops_a_built_singleton_so_the_next_resolution_rebuilds() -> None:
    class Widget: ...

    frozen = Container().bind(Widget, scope=Scope.SINGLETON).freeze()
    first = frozen[Widget]
    frozen.reset()
    assert frozen[Widget] is not first


def test_reset_runs_teardown_exactly_once_in_reverse_construction_order() -> None:
    events: list[str] = []

    def make_a() -> Generator[str]:
        yield 'a'
        events.append('a')

    def make_b() -> Generator[int]:
        yield 1
        events.append('b')

    frozen = (
        Container()
        .bind(make_a, scope=Scope.SINGLETON, provides=str)
        .bind(make_b, scope=Scope.SINGLETON, provides=int)
        .freeze()
    )
    _ = frozen[str]
    _ = frozen[int]
    frozen.reset()
    assert events == ['b', 'a']


def test_reset_on_a_container_with_nothing_built_runs_nothing_and_raises_nothing() -> None:
    class Widget: ...

    frozen = Container().bind(Widget, scope=Scope.SINGLETON).freeze()
    frozen.reset()


def test_reset_twice_in_a_row_is_idempotent() -> None:
    events: list[str] = []

    def make() -> Generator[str]:
        yield 'v'
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    _ = frozen[str]
    frozen.reset()
    frozen.reset()
    assert events == ['teardown']


def test_reset_collects_failing_teardowns_into_an_exception_group_and_still_drops_the_cache() -> None:
    class Widget: ...

    def make_int() -> Generator[int]:
        yield 1
        raise RuntimeError('int failed')

    def make_str() -> Generator[str]:
        yield 'x'
        raise RuntimeError('str failed')

    frozen = (
        Container()
        .bind(make_int, scope=Scope.SINGLETON, provides=int)
        .bind(make_str, scope=Scope.SINGLETON, provides=str)
        .bind(Widget, scope=Scope.SINGLETON)
        .freeze()
    )
    first = frozen[Widget]
    _ = frozen[int]
    _ = frozen[str]
    with pytest.raises(ExceptionGroup) as exc:
        frozen.reset()
    assert exc.value.message == 'depin teardown errors'
    assert [str(error) for error in exc.value.exceptions] == ['str failed', 'int failed']
    assert frozen[Widget] is not first


@pytest.mark.asyncio
async def test_reset_on_an_async_singleton_raises_teardown_error_and_areset_drains_it() -> None:
    events: list[str] = []

    async def make() -> AsyncGenerator[str]:
        yield 'v'
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert await frozen.aresolve(str) == 'v'
    with pytest.raises(ExceptionGroup) as exc:
        frozen.reset()
    assert [str(error) for error in exc.value.exceptions] == [
        'an async provider registered a teardown in a synchronous scope; '
        'open the scope with ascope() and drain it with aclose()/ascope() instead'
    ]
    assert [type(error) for error in exc.value.exceptions] == [TeardownError]

    assert await frozen.aresolve(str) == 'v'
    await frozen.areset()
    assert events == ['teardown']


def test_a_value_cached_in_an_active_scope_survives_reset() -> None:
    events: list[str] = []

    def make() -> Generator[str]:
        yield 'scoped-value'
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=str).freeze()
    with frozen.scope():
        value = frozen[str]
        frozen.reset()
        assert frozen[str] is value
        assert events == []


@pytest.mark.asyncio
async def test_areset_collects_failing_async_teardowns_into_an_exception_group() -> None:
    class Widget: ...

    async def make_int() -> AsyncGenerator[int]:
        yield 1
        raise RuntimeError('int failed')

    async def make_str() -> AsyncGenerator[str]:
        yield 'x'
        raise RuntimeError('str failed')

    frozen = (
        Container()
        .bind(make_int, scope=Scope.SINGLETON, provides=int)
        .bind(make_str, scope=Scope.SINGLETON, provides=str)
        .bind(Widget, scope=Scope.SINGLETON)
        .freeze()
    )
    first = await frozen.aresolve(Widget)
    _ = await frozen.aresolve(int)
    _ = await frozen.aresolve(str)
    with pytest.raises(ExceptionGroup) as exc:
        await frozen.areset()
    assert exc.value.message == 'depin teardown errors'
    assert [str(error) for error in exc.value.exceptions] == ['str failed', 'int failed']
    assert await frozen.aresolve(Widget) is not first


@pytest.mark.asyncio
async def test_areset_drains_an_async_generator_singleton_teardown_and_drops_it() -> None:
    events: list[str] = []

    class Widget: ...

    async def make() -> AsyncGenerator[Widget]:
        yield Widget()
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Widget).freeze()
    first = await frozen.aresolve(Widget)
    await frozen.areset()
    assert events == ['teardown']
    second = await frozen.aresolve(Widget)
    assert second is not first
