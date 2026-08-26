"""Teardown records: what runs, what refuses to run, and how failures surface."""

from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope
from depin._core.teardown import (
    AsyncCMTeardown,
    AsyncGenTeardown,
    SyncCMTeardown,
    SyncGenTeardown,
    run_async,
    run_sync,
)
from depin.errors import TeardownError


class _FakeAsyncGen:
    async def __anext__(self) -> object:
        raise StopAsyncIteration

    def __aiter__(self) -> '_FakeAsyncGen':
        return self


class _FakeAsyncCM:
    def __init__(self) -> None:
        self.exited = False

    async def __aenter__(self) -> object:
        return None

    async def __aexit__(self, *args: object) -> None:
        self.exited = True


class _FakeSyncCM:
    def __init__(self) -> None:
        self.exited = False

    def __enter__(self) -> object:
        return None

    def __exit__(self, *args: object) -> None:
        self.exited = True


def test_sync_close_drains_singleton_generators() -> None:
    events: list[str] = []

    def make() -> Generator[str]:
        events.append('setup')
        yield 'v'
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert frozen[str] == 'v'
    frozen.close()
    assert events == ['setup', 'teardown']


def test_sync_close_is_idempotent() -> None:
    events: list[str] = []

    def make() -> Generator[str]:
        yield 'v'
        events.append('teardown')

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    _ = frozen[str]
    frozen.close()
    frozen.close()
    assert events == ['teardown']


def test_sync_close_aggregates_failures() -> None:
    def boom() -> Generator[int]:
        yield 1
        raise RuntimeError('a')

    def bang() -> Generator[str]:
        yield 'x'
        raise RuntimeError('b')

    frozen = (
        Container()
        .bind(boom, scope=Scope.SINGLETON, provides=int)
        .bind(bang, scope=Scope.SINGLETON, provides=str)
        .freeze()
    )
    _ = frozen[int]
    _ = frozen[str]
    with pytest.raises(ExceptionGroup) as exc:
        frozen.close()
    assert len(exc.value.exceptions) == 2


@pytest.mark.asyncio
async def test_sync_close_refuses_an_async_singleton_teardown() -> None:
    async def make() -> AsyncGenerator[str]:
        yield 'v'

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert await frozen.aresolve(str) == 'v'
    with pytest.raises(ExceptionGroup) as exc:
        frozen.close()
    assert any(isinstance(e, TeardownError) for e in exc.value.exceptions)


def test_sync_generator_yielding_twice_is_reported_on_drain() -> None:
    def make() -> Generator[int]:
        yield 1
        yield 2

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    with pytest.raises(ExceptionGroup) as exc, frozen.scope():
        assert frozen[int] == 1
    assert any(isinstance(e, TeardownError) for e in exc.value.exceptions)


@pytest.mark.asyncio
async def test_async_generator_yielding_twice_is_reported_on_drain() -> None:
    async def make() -> AsyncGenerator[int]:
        yield 1
        yield 2

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    with pytest.raises(ExceptionGroup) as exc:
        async with frozen.ascope():
            assert await frozen.aresolve(int) == 1
    assert any(isinstance(e, TeardownError) for e in exc.value.exceptions)


@pytest.mark.parametrize(
    'record',
    [
        AsyncGenTeardown(_FakeAsyncGen()),
        AsyncCMTeardown(_FakeAsyncCM()),
    ],
    ids=['async-generator', 'async-context-manager'],
)
def test_run_sync_refuses_async_records(record: AsyncGenTeardown | AsyncCMTeardown) -> None:
    with pytest.raises(TeardownError, match='synchronous scope'):
        run_sync(record)


def test_run_sync_exits_a_sync_context_manager() -> None:
    cm = _FakeSyncCM()
    run_sync(SyncCMTeardown(cm))
    assert cm.exited


@pytest.mark.asyncio
async def test_run_async_handles_every_record_kind() -> None:
    sync_cm = _FakeSyncCM()
    async_cm = _FakeAsyncCM()
    drained: list[int] = []

    def gen() -> Generator[int]:
        yield 1
        drained.append(1)

    started = gen()
    _ = next(started)

    await run_async(SyncGenTeardown(started))
    await run_async(AsyncGenTeardown(_FakeAsyncGen()))
    await run_async(SyncCMTeardown(sync_cm))
    await run_async(AsyncCMTeardown(async_cm))

    assert drained == [1]
    assert sync_cm.exited
    assert async_cm.exited
