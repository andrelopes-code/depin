import asyncio

import pytest

from depin._core.container import Container
from depin._core.scope import Scope


@pytest.mark.asyncio
async def test_concurrent_singleton_async_constructs_once() -> None:
    count = 0

    class Pool:
        def __init__(self) -> None:
            nonlocal count
            count += 1

    async def make_pool() -> Pool:
        await asyncio.sleep(0.01)
        return Pool()

    frozen = Container().bind(make_pool, scope=Scope.SINGLETON, provides=Pool).freeze()
    async with frozen.ascope():
        a, b = await asyncio.gather(frozen.aresolve(Pool), frozen.aresolve(Pool))

    assert a is b
    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_scoped_async_constructs_once_per_scope() -> None:
    count = 0

    class Conn:
        def __init__(self) -> None:
            nonlocal count
            count += 1

    async def make_conn() -> Conn:
        await asyncio.sleep(0.01)
        return Conn()

    frozen = Container().bind(make_conn, scope=Scope.SCOPED, provides=Conn).freeze()
    async with frozen.ascope():
        a, b = await asyncio.gather(frozen.aresolve(Conn), frozen.aresolve(Conn))

    assert a is b
    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_singleton_with_async_dep_constructs_once() -> None:
    dep_count = 0
    svc_count = 0

    class Dep:
        def __init__(self) -> None:
            nonlocal dep_count
            dep_count += 1

    class Service:
        def __init__(self, dep: Dep) -> None:
            nonlocal svc_count
            svc_count += 1
            self.dep = dep

    async def make_dep() -> Dep:
        await asyncio.sleep(0.01)
        return Dep()

    frozen = (
        Container().bind(make_dep, scope=Scope.SINGLETON, provides=Dep).bind(Service, scope=Scope.SINGLETON).freeze()
    )
    async with frozen.ascope():
        a, b = await asyncio.gather(frozen.aresolve(Service), frozen.aresolve(Service))

    assert a is b
    assert a.dep is b.dep
    assert dep_count == 1
    assert svc_count == 1
