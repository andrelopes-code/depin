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


def test_sync_close_preserves_independent_failures_in_lifo_order() -> None:
    events: list[str] = []

    def make_int() -> Generator[int]:
        yield 1
        events.append('int')
        raise RuntimeError('int failed')

    def make_str() -> Generator[str]:
        yield 'x'
        events.append('str')
        raise RuntimeError('str failed')

    def make_bytes() -> Generator[bytes]:
        yield b'x'
        events.append('bytes')
        raise RuntimeError('bytes failed')

    frozen = (
        Container()
        .bind(make_int, scope=Scope.SINGLETON, provides=int)
        .bind(make_str, scope=Scope.SINGLETON, provides=str)
        .bind(make_bytes, scope=Scope.SINGLETON, provides=bytes)
        .freeze()
    )
    _ = frozen[int]
    _ = frozen[str]
    _ = frozen[bytes]
    with pytest.raises(ExceptionGroup) as exc:
        frozen.close()
    assert events == ['bytes', 'str', 'int']
    assert [str(error) for error in exc.value.exceptions] == ['bytes failed', 'str failed', 'int failed']


@pytest.mark.asyncio
async def test_sync_close_refuses_an_async_singleton_teardown() -> None:
    async def make() -> AsyncGenerator[str]:
        yield 'v'

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert await frozen.aresolve(str) == 'v'
    with pytest.raises(ExceptionGroup) as exc:
        frozen.close()
    assert any(isinstance(e, TeardownError) for e in exc.value.exceptions)


def test_sync_scoped_teardown_preserves_failures_in_lifo_order() -> None:
    events: list[str] = []

    def failing() -> Generator[int]:
        yield 1
        events.append('int')
        raise RuntimeError('provider failed')

    def yielding_twice() -> Generator[str]:
        yield 'x'
        events.append('str')
        yield 'y'

    frozen = (
        Container()
        .bind(failing, scope=Scope.SCOPED, provides=int)
        .bind(yielding_twice, scope=Scope.SCOPED, provides=str)
        .freeze()
    )

    def resolve_in_scope() -> None:
        with frozen.scope():
            assert frozen[int] == 1
            assert frozen[str] == 'x'

    with pytest.raises(ExceptionGroup) as exc:
        resolve_in_scope()
    assert events == ['str', 'int']
    assert [str(error) for error in exc.value.exceptions] == [
        'generator provider yielded more than once; it must yield exactly once',
        'provider failed',
    ]


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


@pytest.mark.asyncio
async def test_async_scope_preserves_sync_async_and_generator_failures_in_lifo_order() -> None:
    events: list[str] = []

    def sync_failing() -> Generator[int]:
        yield 1
        events.append('sync')
        raise RuntimeError('sync failed')

    async def async_failing() -> AsyncGenerator[str]:
        yield 'x'
        events.append('async')
        raise RuntimeError('async failed')

    async def async_yielding_twice() -> AsyncGenerator[bytes]:
        yield b'x'
        events.append('twice')
        yield b'y'

    frozen = (
        Container()
        .bind(sync_failing, scope=Scope.SCOPED, provides=int, tag='sync')
        .bind(async_failing, scope=Scope.SCOPED, provides=str, tag='async')
        .bind(async_yielding_twice, scope=Scope.SCOPED, provides=bytes, tag='twice')
        .freeze()
    )

    async def resolve_in_scope() -> None:
        async with frozen.ascope():
            assert await frozen.aresolve(int, tag='sync') == 1
            assert await frozen.aresolve(str, tag='async') == 'x'
            assert await frozen.aresolve(bytes, tag='twice') == b'x'

    with pytest.raises(ExceptionGroup) as exc:
        await resolve_in_scope()
    assert events == ['twice', 'async', 'sync']
    assert [str(error) for error in exc.value.exceptions] == [
        'async generator provider yielded more than once; it must yield exactly once',
        'async failed',
        'sync failed',
    ]
    assert isinstance(exc.value.exceptions[0], TeardownError)


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
