from typing import Annotated

import pytest

from depin._core.container import Container
from depin._core.markers import Tag, Token, injected
from depin._core.scope import Scope


def test_override_with_value() -> None:
    class A:
        def __init__(self) -> None:
            self.v = 1

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    fake = A()
    fake.v = 99
    with frozen.override(A, with_=fake):
        assert frozen[A].v == 99
    assert frozen[A].v == 1


def test_override_token() -> None:
    db_url = Token[str]('db.url')
    frozen = Container().value(db_url, 'prod').freeze()
    with frozen.override(db_url, with_='test'):
        assert frozen[db_url] == 'test'
    assert frozen[db_url] == 'prod'


def test_override_with_factory_callable() -> None:
    class A: ...

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    with frozen.override(A, with_=lambda: A()):
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
    with frozen.override(_Db, with_=_FakeDb()):
        assert frozen[_Repo].db.name == 'fake'
    assert frozen[_Repo].db.name == 'real'


@pytest.mark.asyncio
async def test_override_applies_to_nested_dependency_async() -> None:
    frozen = Container().bind(_Db, scope=Scope.SINGLETON).bind(_Repo, scope=Scope.TRANSIENT).freeze()
    with frozen.override(_Db, with_=_FakeDb()):
        repo = await frozen.aresolve(_Repo)
        assert repo.db.name == 'fake'


def test_override_applies_through_inject_decorator() -> None:
    frozen = Container().bind(_Db, scope=Scope.SINGLETON).bind(_Repo, scope=Scope.TRANSIENT).freeze()

    @frozen.inject
    def handler(repo: _Repo = injected(_Repo)) -> str:
        return repo.db.name

    with frozen.override(_Db, with_=_FakeDb()):
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
    with frozen.override(Engine, with_=Engine('override'), tag='fast'):
        assert frozen[Consumer].engine.kind == 'override'
    assert frozen[Consumer].engine.kind == 'fast'
