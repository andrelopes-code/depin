"""Graph validation performed by freeze(): duplicates, cycles, captives, async reach."""

from collections.abc import AsyncGenerator
from typing import Annotated

import pytest

from depin._core.container import Container
from depin._core.graph import build_plan
from depin._core.markers import Named, Token
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin.errors import (
    AsyncInSyncContextError,
    CaptiveDependencyError,
    CircularDependencyError,
    DuplicateProviderError,
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


def test_reports_all_missing_providers_at_once() -> None:
    class A: ...

    class B: ...

    class Service:
        def __init__(self, a: A, b: B) -> None: ...

    r = Registry().bind(Service, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'A' in msg
    assert 'B' in msg
    assert '2 missing providers' in msg


def test_single_missing_provider_keeps_concise_message() -> None:
    class A: ...

    class B:
        def __init__(self, a: A) -> None: ...

    r = Registry().bind(B, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'missing providers' not in msg
    assert msg.startswith('no provider for ')


def test_missing_provider_message_includes_chain() -> None:
    class A: ...

    class B:
        def __init__(self, a: A) -> None: ...

    class C:
        def __init__(self, b: B) -> None: ...

    r = Registry().bind(B, scope=Scope.SINGLETON).bind(C, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'A' in msg
    assert 'B' in msg
    assert 'C' in msg


def test_missing_provider_suggests_candidates_with_provides() -> None:
    from depin._core.markers import provides

    class Database: ...

    @provides(Database)
    class PgDatabase(Database): ...

    class Repo:
        def __init__(self, db: Database) -> None: ...

    # PgDatabase is referenced via @provides — keep it live so the gc-scan sees it.
    assert PgDatabase is not None
    r = Registry().bind(Repo, scope=Scope.SINGLETON)
    with pytest.raises(MissingProviderError) as exc:
        _ = build_plan(r.records())
    assert 'PgDatabase' in str(exc.value)


def test_duplicate_class_binding_raises() -> None:
    class Foo: ...

    r = Registry().bind(Foo, scope=Scope.SINGLETON).bind(Foo, scope=Scope.SINGLETON)
    with pytest.raises(DuplicateProviderError, match='Foo'):
        _ = build_plan(r.records())


def test_duplicate_provides_without_tag_raises() -> None:
    class Iface: ...

    class A(Iface): ...

    class B(Iface): ...

    r = Registry().bind(A, provides=Iface).bind(B, provides=Iface)
    with pytest.raises(DuplicateProviderError, match='Iface'):
        _ = build_plan(r.records())


def test_duplicate_value_binding_raises() -> None:
    tok = Token[int]('x')
    r = Registry().value(tok, 100).value(tok, 200)
    with pytest.raises(DuplicateProviderError):
        _ = build_plan(r.records())


def test_same_key_distinct_tags_allowed() -> None:
    class Iface: ...

    class A(Iface): ...

    class B(Iface): ...

    r = Registry().bind(A, provides=Iface, tag='a').bind(B, provides=Iface, tag='b')
    plan = build_plan(r.records())
    assert len(plan.order) == 2


def test_duplicate_message_names_key_and_tag() -> None:
    class Iface: ...

    class A(Iface): ...

    class B(Iface): ...

    r = Registry().bind(A, provides=Iface, tag='primary').bind(B, provides=Iface, tag='primary')
    with pytest.raises(DuplicateProviderError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'Iface' in msg
    assert 'primary' in msg


def test_singleton_depending_on_scoped_is_rejected() -> None:
    class Session: ...

    class Service:
        def __init__(self, session: Session) -> None: ...

    r = Registry().bind(Session, scope=Scope.SCOPED).bind(Service, scope=Scope.SINGLETON)
    with pytest.raises(CaptiveDependencyError) as exc:
        _ = build_plan(r.records())
    msg = str(exc.value)
    assert 'Service' in msg
    assert 'Session' in msg


def test_singleton_capturing_scoped_through_transient_is_rejected() -> None:
    class Session: ...

    class Work:
        def __init__(self, session: Session) -> None: ...

    class Service:
        def __init__(self, work: Work) -> None: ...

    r = (
        Registry()
        .bind(Session, scope=Scope.SCOPED)
        .bind(Work, scope=Scope.TRANSIENT)
        .bind(Service, scope=Scope.SINGLETON)
    )
    with pytest.raises(CaptiveDependencyError) as exc:
        _ = build_plan(r.records())
    chain = str(exc.value).split('chain: ', 1)[1]
    assert chain.index('Service') < chain.index('Work') < chain.index('Session')


def test_scoped_depending_on_scoped_is_allowed() -> None:
    class Session: ...

    class Repo:
        def __init__(self, session: Session) -> None: ...

    r = Registry().bind(Session, scope=Scope.SCOPED).bind(Repo, scope=Scope.SCOPED)
    plan = build_plan(r.records())
    assert len(plan.order) == 2


def test_singleton_depending_on_transient_is_allowed() -> None:
    class Clock: ...

    class Service:
        def __init__(self, clock: Clock) -> None: ...

    r = Registry().bind(Clock, scope=Scope.TRANSIENT).bind(Service, scope=Scope.SINGLETON)
    plan = build_plan(r.records())
    assert len(plan.order) == 2


def test_singleton_transient_diamond_is_allowed() -> None:
    class Leaf: ...

    class Left:
        def __init__(self, leaf: Leaf) -> None: ...

    class Right:
        def __init__(self, leaf: Leaf) -> None: ...

    class Service:
        def __init__(self, left: Left, right: Right) -> None: ...

    r = (
        Registry()
        .bind(Leaf, scope=Scope.TRANSIENT)
        .bind(Left, scope=Scope.TRANSIENT)
        .bind(Right, scope=Scope.TRANSIENT)
        .bind(Service, scope=Scope.SINGLETON)
    )
    plan = build_plan(r.records())
    assert len(plan.order) == 4


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


def test_a_string_key_referenced_by_named_must_still_be_bound() -> None:
    def provider() -> int:
        return 99

    def consumer(x: Annotated[int, Named('legacy_key')]) -> str:
        return str(x)

    builder = (
        Container()
        .bind(provider, scope=Scope.SINGLETON, provides=int)
        .bind(consumer, scope=Scope.SINGLETON, provides=str)
    )
    with pytest.raises(MissingProviderError, match='legacy_key'):
        _ = builder.freeze()
