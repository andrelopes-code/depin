"""Context-local overrides: the testing seam that replaces a provider in place."""

from typing import Annotated

import pytest

from depin._core.container import Container
from depin._core.markers import Tag, Token, injected
from depin._core.scope import Scope
from depin.errors import MissingProviderError


def test_override_with_value() -> None:
    class A:
        def __init__(self) -> None:
            self.v = 1

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    fake = A()
    fake.v = 99
    with frozen.override(A, fake):
        assert frozen[A].v == 99
    assert frozen[A].v == 1


def test_override_token() -> None:
    db_url = Token[str]('db.url')
    frozen = Container().value(db_url, 'prod').freeze()
    with frozen.override(db_url, 'test'):
        assert frozen[db_url] == 'test'
    assert frozen[db_url] == 'prod'


def test_override_with_factory_callable() -> None:
    class A: ...

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    with frozen.override(A, lambda: A()):
        a1 = frozen[A]
        a2 = frozen[A]
    assert a1 is not a2


class _Db:
    name = 'real'


class _FakeDb(_Db):
    name = 'fake'


class _Repo:
    def __init__(self, db: _Db) -> None:
        self.db = db


def test_override_applies_to_nested_dependency() -> None:
    frozen = Container().bind(_Db, scope=Scope.SINGLETON).bind(_Repo, scope=Scope.TRANSIENT).freeze()
    with frozen.override(_Db, _FakeDb()):
        assert frozen[_Repo].db.name == 'fake'
    assert frozen[_Repo].db.name == 'real'


@pytest.mark.asyncio
async def test_override_applies_to_nested_dependency_async() -> None:
    frozen = Container().bind(_Db, scope=Scope.SINGLETON).bind(_Repo, scope=Scope.TRANSIENT).freeze()
    with frozen.override(_Db, _FakeDb()):
        repo = await frozen.aresolve(_Repo)
        assert repo.db.name == 'fake'


def test_override_applies_through_inject_decorator() -> None:
    frozen = Container().bind(_Db, scope=Scope.SINGLETON).bind(_Repo, scope=Scope.TRANSIENT).freeze()

    @frozen.inject
    def handler(repo: _Repo = injected(_Repo)) -> str:
        return repo.db.name

    with frozen.override(_Db, _FakeDb()):
        assert handler() == 'fake'
    assert handler() == 'real'


def test_override_of_nested_dependency_respects_tag() -> None:
    class Engine:
        def __init__(self, kind: str) -> None:
            self.kind = kind

    class Consumer:
        def __init__(self, engine: Annotated[Engine, Tag('fast')]) -> None:
            self.engine = engine

    frozen = (
        Container()
        .bind(lambda: Engine('fast'), provides=Engine, tag='fast')
        .bind(Consumer, scope=Scope.TRANSIENT)
        .freeze()
    )
    with frozen.override(Engine, Engine('override'), tag='fast'):
        assert frozen[Consumer].engine.kind == 'override'
    assert frozen[Consumer].engine.kind == 'fast'


def test_override_rejects_a_key_that_is_not_a_provider_key() -> None:
    frozen = Container().freeze()
    with pytest.raises(MissingProviderError, match='not a valid key type'), frozen.override(42, 'x'):  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        pass


def test_override_selects_the_tagged_provider() -> None:
    class Cache:
        def __init__(self, label: str = 'real') -> None:
            self.label = label

    frozen = Container().bind(Cache, scope=Scope.SINGLETON, tag='primary').freeze()
    with frozen.override(Cache, Cache('fake'), tag='primary'):
        assert frozen.resolve(Cache, tag='primary').label == 'fake'
    assert frozen.resolve(Cache, tag='primary').label == 'real'


def test_override_resolves_a_key_that_was_never_bound() -> None:
    class Marker: ...

    frozen = Container().freeze()
    sentinel = Marker()
    with frozen.override(Marker, sentinel):
        assert frozen[Marker] is sentinel
    with pytest.raises(MissingProviderError):
        _ = frozen[Marker]


def test_reset_makes_an_override_reach_a_consumer_built_before_the_block() -> None:
    class Clock:
        def now(self) -> str:
            return 'real'

    class FakeClock:
        def now(self) -> str:
            return 'fake'

    class Report:
        def __init__(self, clock: Clock) -> None:
            self.clock = clock

    frozen = Container().bind(Clock, scope=Scope.SINGLETON).bind(Report, scope=Scope.SINGLETON).freeze()
    report = frozen[Report]
    assert report.clock.now() == 'real'
    with frozen.override(Clock, FakeClock()):
        assert report.clock.now() == 'real'

    frozen.reset()
    with frozen.override(Clock, FakeClock()):
        assert frozen[Report].clock.now() == 'fake'
