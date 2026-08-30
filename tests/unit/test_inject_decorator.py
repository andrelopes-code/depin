"""The @inject decorator: which parameters it fills and when it validates them."""

import pytest

from depin._core.container import Container
from depin._core.markers import Token, injected
from depin._core.scope import Scope
from depin.errors import MissingProviderError


def test_inject_fills_marked_param() -> None:
    class Service:
        def __init__(self) -> None:
            self.value = 7

    frozen = Container().bind(Service, scope=Scope.SINGLETON).freeze()

    @frozen.inject
    def handler(multiplier: int, svc: Service = injected(Service)) -> int:
        return svc.value * multiplier

    assert handler(multiplier=2) == 14


def test_inject_does_not_override_explicit_args() -> None:
    class Service:
        def __init__(self) -> None:
            self.v = 1

    frozen = Container().bind(Service, scope=Scope.SINGLETON).freeze()

    @frozen.inject
    def handler(svc: Service = injected(Service)) -> int:
        return svc.v

    other = Service()
    other.v = 99
    assert handler(svc=other) == 99


def test_inject_resolves_tagged_provider() -> None:
    class Cache:
        def __init__(self, kind: str) -> None:
            self.kind = kind

    def redis() -> Cache:
        return Cache('redis')

    def memory() -> Cache:
        return Cache('memory')

    frozen = (
        Container()
        .bind(redis, scope=Scope.SINGLETON, provides=Cache, tag='dist')
        .bind(memory, scope=Scope.SINGLETON, provides=Cache, tag='local')
        .freeze()
    )

    @frozen.inject
    def handler(cache: Cache = injected(Cache, tag='dist')) -> str:
        return cache.kind

    assert handler() == 'redis'


def test_inject_resolves_token_key() -> None:
    db_url = Token[str]('db.url')
    frozen = Container().value(db_url, 'postgres://x').freeze()

    @frozen.inject
    def handler(url: str = injected(db_url)) -> str:
        return url

    assert handler() == 'postgres://x'


def test_inject_unregistered_key_raises_at_decoration() -> None:
    class NotBound: ...

    frozen = Container().freeze()

    def handler(x: NotBound = injected(NotBound)) -> None: ...

    with pytest.raises(MissingProviderError) as exc:
        frozen.inject(handler)

    assert str(exc.value) == (
        f"@inject: parameter 'x' requests injected({NotBound.__qualname__}) "
        'but no provider is registered for that key. '
        'Bind it on the Container before calling .freeze(), or remove the injected() default.'
    )


def test_inject_unregistered_tagged_key_names_tag() -> None:
    class Cache: ...

    frozen = Container().freeze()

    def handler(c: Cache = injected(Cache, tag='dist')) -> None: ...

    with pytest.raises(MissingProviderError, match="tag='dist'"):
        frozen.inject(handler)


def test_inject_leaves_non_marker_defaults_alone() -> None:
    class Service:
        def __init__(self) -> None:
            self.value = 10

    frozen = Container().bind(Service, scope=Scope.SINGLETON).freeze()

    @frozen.inject
    def handler(svc: Service = injected(Service), n: int = 5) -> int:
        return svc.value + n

    assert handler() == 15
    assert handler(n=2) == 12


@pytest.mark.asyncio
async def test_inject_async() -> None:
    async def dep() -> int:
        return 21

    frozen = Container().bind(dep, scope=Scope.TRANSIENT, provides=int).freeze()

    @frozen.inject
    async def handler(n: int = injected(int)) -> int:
        return n * 2

    assert await handler() == 42


def test_inject_fills_a_token_keyed_parameter() -> None:
    answer: Token[int] = Token[int]('answer')
    frozen = Container().value(answer, 42).freeze()

    @frozen.inject
    def handler(n: int = injected(answer)) -> int:
        return n + 1

    assert handler() == 43


def test_inject_fills_a_keyword_only_parameter_between_varargs() -> None:
    class Service: ...

    frozen = Container().bind(Service, scope=Scope.SINGLETON).freeze()

    @frozen.inject
    def handler(*args: object, svc: Service = injected(Service), **kwargs: object) -> Service:
        del args, kwargs
        return svc

    assert isinstance(handler(), Service)


def test_inject_on_a_method_leaves_self_to_the_caller() -> None:
    class Service: ...

    frozen = Container().bind(Service, scope=Scope.SINGLETON).freeze()

    class Handler:
        @frozen.inject
        def handle(self, svc: Service = injected(Service)) -> Service:
            del self
            return svc

    assert isinstance(Handler().handle(), Service)


def test_inject_distinguishes_tagged_providers() -> None:
    class Cache: ...

    primary = Cache()
    fallback = Cache()
    frozen = (
        Container()
        .bind(lambda: primary, scope=Scope.SINGLETON, provides=Cache, tag='primary')
        .bind(lambda: fallback, scope=Scope.SINGLETON, provides=Cache, tag='fallback')
        .freeze()
    )

    @frozen.inject
    def handler(
        p: Cache = injected(Cache, tag='primary'),
        f: Cache = injected(Cache, tag='fallback'),
    ) -> tuple[Cache, Cache]:
        return p, f

    assert handler() == (primary, fallback)
