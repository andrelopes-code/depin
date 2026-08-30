"""Graph ordering and async reachability validation."""

from collections.abc import AsyncGenerator

import pytest

from depin._core.container import Container
from depin._core.graph import build_plan
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin.errors import AsyncInSyncContextError


def test_toposort_keeps_independent_roots_after_a_visited_dependency() -> None:
    class Dependency: ...

    class Consumer:
        def __init__(self, dependency: Dependency) -> None: ...

    class Independent: ...

    plan = build_plan(Registry().bind(Consumer).bind(Dependency).bind(Independent).records())
    assert {spec.key for spec in plan.order} == {Consumer, Dependency, Independent}


def test_toposort_visits_every_parameter_dependency_before_its_consumer() -> None:
    class First: ...

    class Second: ...

    class Consumer:
        def __init__(self, first: First, second: Second) -> None: ...

    plan = build_plan(Registry().bind(Consumer).bind(First).bind(Second).records())
    order = plan.order
    positions = {spec.key: index for index, spec in enumerate(order)}
    assert positions[First] < positions[Consumer]
    assert positions[Second] < positions[Consumer]


def test_sync_chain_with_async_dep_rejected() -> None:
    class A: ...

    async def make_a() -> A:
        return A()

    class B:
        def __init__(self, a: A) -> None: ...

    def sync_use(b: B) -> int:
        return 0

    r = (
        Registry()
        .bind(make_a, scope=Scope.SINGLETON, provides=A)
        .bind(B, scope=Scope.SINGLETON)
        .bind(sync_use, scope=Scope.SINGLETON)
    )
    plan = build_plan(r.records())
    sync_spec = next(s for s in plan.order if s.source is sync_use)
    assert sync_spec.needs_async is True


def test_async_dependency_propagates_through_a_sync_chain() -> None:
    async def make_a() -> int:
        return 1

    def make_b(a: int) -> str:
        return str(a)

    def make_c(b: str) -> bytes:
        return b.encode()

    frozen = (
        Container()
        .bind(make_a, scope=Scope.SINGLETON, provides=int)
        .bind(make_b, scope=Scope.SINGLETON, provides=str)
        .bind(make_c, scope=Scope.SINGLETON, provides=bytes)
        .freeze()
    )
    with pytest.raises(AsyncInSyncContextError):
        _ = frozen[bytes]


def test_async_generator_dependency_propagates_to_its_consumer() -> None:
    async def make_a() -> AsyncGenerator[int]:
        yield 1

    def use(a: int) -> str:
        return str(a)

    frozen = (
        Container()
        .bind(make_a, scope=Scope.SINGLETON, provides=int)
        .bind(use, scope=Scope.SINGLETON, provides=str)
        .freeze()
    )
    with pytest.raises(AsyncInSyncContextError):
        _ = frozen[str]
