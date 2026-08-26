"""Asynchronous resolution: every provider shape reached through aresolve()."""

import contextlib
from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.container import Container
from depin._core.markers import Token
from depin._core.scope import Scope
from depin.errors import AsyncInSyncContextError


@pytest.mark.asyncio
async def test_aresolve_unhashable_value_binding() -> None:
    origins = Token[list[str]]('origins')
    frozen = Container().value(origins, ['x']).freeze()
    assert await frozen.aresolve(origins) == ['x']


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

    frozen = Container().bind(make_a, scope=Scope.SINGLETON, provides=A).bind(B, scope=Scope.SINGLETON).freeze()
    b = await frozen.aresolve(B)
    assert isinstance(b.a, A)


def test_sync_resolve_async_chain_raises_at_call() -> None:
    class A: ...

    async def make_a() -> A:
        return A()

    frozen = Container().bind(make_a, scope=Scope.SINGLETON, provides=A).freeze()
    with pytest.raises(AsyncInSyncContextError):
        _ = frozen[A]


@pytest.mark.asyncio
async def test_aresolve_builds_a_transient_provider_every_time() -> None:
    class Ticket: ...

    async def make() -> Ticket:
        return Ticket()

    frozen = Container().bind(make, scope=Scope.TRANSIENT, provides=Ticket).freeze()
    assert await frozen.aresolve(Ticket) is not await frozen.aresolve(Ticket)


@pytest.mark.asyncio
async def test_aresolve_caches_a_singleton_across_calls() -> None:
    class Pool: ...

    frozen = Container().bind(Pool, scope=Scope.SINGLETON).freeze()
    assert await frozen.aresolve(Pool) is await frozen.aresolve(Pool)


@pytest.mark.asyncio
async def test_aresolve_caches_a_scoped_provider_within_one_scope() -> None:
    class Session: ...

    frozen = Container().bind(Session, scope=Scope.SCOPED).freeze()
    async with frozen.ascope():
        first = await frozen.aresolve(Session)
        assert first is await frozen.aresolve(Session)
    async with frozen.ascope():
        assert await frozen.aresolve(Session) is not first


@pytest.mark.asyncio
async def test_aresolve_wires_an_async_dependency_into_a_class_constructor() -> None:
    class Repo:
        def __init__(self, size: int) -> None:
            self.size = size

    async def make_size() -> int:
        return 5

    frozen = Container().bind(make_size, scope=Scope.SINGLETON, provides=int).bind(Repo, scope=Scope.SINGLETON).freeze()
    assert (await frozen.aresolve(Repo)).size == 5


@pytest.mark.asyncio
async def test_aresolve_handles_sync_providers_too() -> None:
    token: Token[int] = Token[int]('x')

    def make() -> str:
        return 'sync'

    frozen = Container().value(token, 5).bind(make, scope=Scope.SINGLETON, provides=str).freeze()
    assert await frozen.aresolve(token) == 5
    assert await frozen.aresolve(str) == 'sync'


@pytest.mark.asyncio
async def test_aresolve_drains_a_sync_generator_on_scope_exit() -> None:
    events: list[str] = []

    def make() -> Generator[int]:
        yield 5
        events.append('done')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    async with frozen.ascope():
        assert await frozen.aresolve(int) == 5
    assert events == ['done']


@pytest.mark.asyncio
async def test_aresolve_drains_a_sync_context_manager_on_scope_exit() -> None:
    events: list[str] = []

    @contextlib.contextmanager
    def make() -> Generator[int]:
        yield 7
        events.append('done')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    async with frozen.ascope():
        assert await frozen.aresolve(int) == 7
    assert events == ['done']


@pytest.mark.asyncio
async def test_aresolve_reads_a_scope_value_and_injects_it() -> None:
    class Principal: ...

    class Audit:
        def __init__(self, who: Principal) -> None:
            self.who = who

    frozen = Container().scope_value(Principal).bind(Audit, scope=Scope.SCOPED).freeze()
    principal = Principal()
    async with frozen.ascope() as frame:
        frame.provide(Principal, principal)
        assert await frozen.aresolve(Principal) is principal
        assert (await frozen.aresolve(Audit)).who is principal


@pytest.mark.asyncio
async def test_aresolve_of_an_async_generator_yields_the_first_value() -> None:
    async def make() -> AsyncGenerator[int]:
        yield 3

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    async with frozen.ascope():
        assert await frozen.aresolve(int) == 3
