import pytest

from depin._core.registry import Registry
from depin._core.resolver import build_plan
from depin._core.scope import Scope
from depin.errors import (
    CircularDependencyError,
    MissingProviderError,
)


def test_missing_provider_raises() -> None:
    class A: ...

    class B:
        def __init__(self, a: A) -> None: ...

    r = Registry().bind(B, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError, match='A'):
        _ = build_plan(r.records())


def test_default_value_satisfies_missing() -> None:
    class B:
        def __init__(self, x: int = 5) -> None:
            self.x = x

    r = Registry().bind(B, scope=Scope.SINGLETON)
    plan = build_plan(r.records())
    assert len(plan.order) == 1


def test_cycle_detected() -> None:
    class A:
        def __init__(self, b: 'B') -> None: ...

    class B:
        def __init__(self, a: A) -> None: ...

    r = Registry().bind(A, scope=Scope.SINGLETON).bind(B, scope=Scope.SINGLETON)
    with pytest.raises(CircularDependencyError) as exc:
        _ = build_plan(r.records())
    assert 'A' in str(exc.value)
    assert 'B' in str(exc.value)


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
