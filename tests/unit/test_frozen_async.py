import pytest

from depin._core.container import Container
from depin._core.scope import Scope
from depin.errors import AsyncInSyncContextError


@pytest.mark.asyncio
async def test_aresolve_async_function() -> None:
    async def make() -> int:
        return 5

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    assert await frozen.aresolve(int) == 5


@pytest.mark.asyncio
async def test_aresolve_works_for_sync_graph_too() -> None:
    class A: ...

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    a = await frozen.aresolve(A)
    assert isinstance(a, A)


@pytest.mark.asyncio
async def test_class_with_async_dep_resolves_async() -> None:
    class A: ...

    async def make_a() -> A:
        return A()

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    frozen = (
        Container()
        .bind(make_a, scope=Scope.SINGLETON, provides=A)
        .bind(B, scope=Scope.SINGLETON)
        .freeze()
    )
    b = await frozen.aresolve(B)
    assert isinstance(b.a, A)


def test_sync_resolve_async_chain_raises_at_call() -> None:
    class A: ...

    async def make_a() -> A:
        return A()

    frozen = Container().bind(make_a, scope=Scope.SINGLETON, provides=A).freeze()
    with pytest.raises(AsyncInSyncContextError):
        _ = frozen[A]
