"""Static conformance of the public API under both type checkers.

`assert_type` is a no-op at runtime; what this module buys is the diagnostic a
checker emits when an inferred type drifts. `pytest` collects the functions too,
so a change that breaks the import still fails the suite.
"""

from collections.abc import Awaitable
from typing import Protocol, assert_type

from depin import Container, FrozenContainer, Scope, ScopeFrame, Token, injected, provides


class Config:
    value: int = 1


class Service:
    def __init__(self, config: Config) -> None:
        self.config = config


port = Token[int]('port')


def test_resolve_returns_the_requested_type() -> None:
    di = Container().bind(Config).bind(Service).value(port, 8080).freeze()
    assert_type(di, FrozenContainer)
    assert_type(di.resolve(Service), Service)
    assert_type(di[Service], Service)
    assert_type(di.resolve(port), int)
    assert_type(di[port], int)


def test_tagged_resolution_keeps_the_requested_type() -> None:
    di = Container().bind(Config, tag='primary').freeze()
    assert_type(di.resolve(Config, tag='primary'), Config)


def test_inject_preserves_the_wrapped_signature() -> None:
    di = Container().bind(Config).freeze()

    @di.inject
    def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    assert_type(handler(label='n'), str)


def test_inject_preserves_an_async_signature() -> None:
    di = Container().bind(Config).freeze()

    @di.inject
    async def handler(label: str, config: Config = injected(Config)) -> str:
        return f'{label}={config.value}'

    # Nested and never called: `assert_type` is checked statically, and calling
    # the wrapper here would leave an un-awaited coroutine behind.
    def call_site() -> None:
        assert_type(handler(label='n'), Awaitable[str])

    _ = call_site


def test_injected_takes_the_type_of_its_key() -> None:
    assert_type(injected(Config), Config)
    assert_type(injected(port), int)


def test_scope_yields_a_frame() -> None:
    di = Container().bind(Config).freeze()
    with di.scope() as frame:
        assert_type(frame, ScopeFrame)


async def test_aresolve_returns_the_requested_type() -> None:
    di = Container().bind(Config).bind(Service).value(port, 8080).freeze()
    assert_type(await di.aresolve(Service), Service)
    assert_type(await di.aresolve(port), int)


async def test_ascope_yields_a_frame() -> None:
    di = Container().bind(Config).freeze()
    async with di.ascope() as frame:
        assert_type(frame, ScopeFrame)


def test_override_yields_the_container() -> None:
    di = Container().bind(Config).freeze()
    with di.override(Config, Config()) as overridden:
        assert_type(overridden, FrozenContainer)


def test_the_builder_stays_a_container_through_chaining() -> None:
    di = Container()
    assert_type(di.bind(Config), Container)
    assert_type(di.value(port, 8080), Container)
    assert_type(di.bind(Service, scope=Scope.SCOPED), Container)


def test_the_scope_decorator_preserves_a_class_target() -> None:
    di = Container()

    @di.singleton()
    class Pool:
        def __init__(self) -> None:
            self.size = 1

    assert_type(Pool(), Pool)


def test_the_scope_decorator_preserves_a_factory_target() -> None:
    di = Container()

    @di.singleton()
    def make_service(config: Config) -> Service:
        return Service(config)

    assert_type(make_service(Config()), Service)


def test_a_protocol_key_keeps_its_type_through_subscript() -> None:
    class Store(Protocol):
        def get(self) -> str: ...

    @provides(Store)  # type: ignore[type-abstract]  # mypy rejects type[Protocol] for a type[A] parameter
    class MemStore:
        def get(self) -> str:
            return 'v'

    di = Container().bind(MemStore).freeze()
    assert_type(di[Store], Store)
    assert_type(di.resolve(Store), Store)
