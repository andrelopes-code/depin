import pytest

from depin._core.markers import Token
from depin._core.registry import Registry
from depin._core.resolver import build_plan
from depin._core.scope import Scope
from depin.errors import (
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
