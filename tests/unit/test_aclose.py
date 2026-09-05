import asyncio
from collections.abc import AsyncGenerator

import pytest

from depin._core.container import Container
from depin._core.scope import Scope
from depin.errors import ContainerClosedError, ContainerLifecycleError


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


@pytest.mark.asyncio
async def test_operations_reject_shutdown_in_progress_and_closed_container() -> None:
    class Service: ...

    started = asyncio.Event()
    release = asyncio.Event()

    async def build() -> Service:
        started.set()
        await release.wait()
        return Service()

    frozen = Container().bind(build, scope=Scope.SINGLETON).freeze()
    resolving = asyncio.create_task(frozen.aresolve(Service))
    await started.wait()
    closing = asyncio.create_task(frozen.aclose())
    checkpoint = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(checkpoint.set_result, None)
    await checkpoint

    with pytest.raises(ContainerLifecycleError):
        _ = frozen.resolve(Service)
    with pytest.raises(ContainerLifecycleError):
        _ = await frozen.aresolve(Service)
    with pytest.raises(ContainerLifecycleError), frozen.scope():
        pass
    with pytest.raises(ContainerLifecycleError):
        async with frozen.ascope():
            pass
    with pytest.raises(ContainerLifecycleError):
        frozen.reset()
    with pytest.raises(ContainerLifecycleError):
        await frozen.areset()
    with pytest.raises(ContainerLifecycleError):
        _ = frozen.warmup()
    with pytest.raises(ContainerLifecycleError):
        _ = await frozen.awarmup()

    release.set()
    assert isinstance(await resolving, Service)
    await closing

    with pytest.raises(ContainerClosedError):
        _ = frozen.resolve(Service)
    with pytest.raises(ContainerClosedError):
        _ = await frozen.aresolve(Service)
    with pytest.raises(ContainerClosedError), frozen.scope():
        pass
    with pytest.raises(ContainerClosedError):
        async with frozen.ascope():
            pass
    with pytest.raises(ContainerClosedError):
        frozen.reset()
    with pytest.raises(ContainerClosedError):
        await frozen.areset()
    with pytest.raises(ContainerClosedError):
        _ = frozen.warmup()
    with pytest.raises(ContainerClosedError):
        _ = await frozen.awarmup()
