from typing import Annotated, Protocol

import pytest

from depin._core.container import Container
from depin._core.markers import Tag, Token
from depin._core.scope import Scope


def test_singleton_class_returns_same_instance() -> None:
    class A:
        def __init__(self) -> None: ...

    frozen = Container().bind(A, scope=Scope.SINGLETON).freeze()
    assert frozen[A] is frozen[A]


def test_singleton_function_called_once() -> None:
    calls = {'n': 0}

    def make() -> int:
        calls['n'] += 1
        return 42

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
    assert frozen[int] == 42
    assert frozen[int] == 42
    assert calls['n'] == 1


def test_value_token_resolves() -> None:
    db_url = Token[str]('db.url')
    frozen = Container().value(db_url, 'postgres://x').freeze()
    assert frozen[db_url] == 'postgres://x'


def test_unhashable_value_binding_resolves_and_caches() -> None:
    origins = Token[list[str]]('cors.origins')
    settings = Token[dict[str, int]]('settings')
    frozen = Container().value(origins, ['a', 'b']).value(settings, {'k': 1}).freeze()
    assert frozen[origins] == ['a', 'b']
    assert frozen[settings] == {'k': 1}
    assert frozen[origins] is frozen[origins]


def test_class_with_dep() -> None:
    class A: ...

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    frozen = Container().bind(A, scope=Scope.SINGLETON).bind(B, scope=Scope.SINGLETON).freeze()
    b = frozen[B]
    assert isinstance(b.a, A)


def test_tag_disambiguates_two_impls() -> None:
    class Cache(Protocol):
        name: str

    class RedisCache:
        name = 'redis'

    class InMemCache:
        name = 'inmem'

    def use(
        primary: Annotated[Cache, Tag('primary')],
        fallback: Annotated[Cache, Tag('fallback')],
    ) -> tuple[str, str]:
        return primary.name, fallback.name

    frozen = (
        Container()
        .bind(RedisCache, provides=Cache, tag='primary', scope=Scope.SINGLETON)
        .bind(InMemCache, provides=Cache, tag='fallback', scope=Scope.SINGLETON)
        .bind(use, scope=Scope.SINGLETON, provides=tuple)
        .freeze()
    )
    assert frozen[tuple] == ('redis', 'inmem')


@pytest.mark.asyncio
async def test_async_singleton_is_cached_after_its_first_resolution() -> None:
    class Service: ...

    async def make() -> Service:
        return Service()

    frozen = Container().bind(make, provides=Service).freeze()
    assert await frozen.aresolve(Service) is await frozen.aresolve(Service)
