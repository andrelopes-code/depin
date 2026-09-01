"""The seven provider shapes, plus `value`, `scope_value` and `check=`.

`bind` is seven overloads over one name, and the overload chosen decides which
`T` the binding provides. Each shape is asserted twice: the builder stays a
`Container` through the call, and the frozen container resolves the shape's
value type rather than the generator, the context manager or the coroutine that
produced it.

`check=` is inferred from the same `T`, so a check written against the bound
type is accepted for every shape. The rejection of a check written against
another type is `negative/n02_check_parameter.py`.
"""

import contextlib
from collections.abc import AsyncGenerator, Generator
from typing import assert_type

from depin import Container, Scope, ScopeFrame, Token


class Config:
    def __init__(self) -> None:
        self.dsn = 'sqlite://'


class Pool:
    def __init__(self) -> None:
        self.size = 1


class Request:
    def __init__(self, path: str = '/') -> None:
        self.path = path


port = Token[int]('port')


def ping(pool: Pool) -> None:
    _ = pool.size


def a_class_is_a_provider() -> None:
    di = Container().bind(Config).freeze()
    assert_type(di.resolve(Config), Config)


def a_function_is_a_provider() -> None:
    def make_pool() -> Pool:
        return Pool()

    assert_type(Container().bind(make_pool), Container)
    assert_type(Container().bind(make_pool, check=ping), Container)
    assert_type(Container().bind(make_pool).freeze().resolve(Pool), Pool)


def an_async_function_is_a_provider() -> None:
    async def make_pool() -> Pool:
        return Pool()

    assert_type(Container().bind(make_pool), Container)
    assert_type(Container().bind(make_pool, check=ping), Container)


async def an_async_function_provider_resolves_through_aresolve() -> None:
    async def make_pool() -> Pool:
        return Pool()

    di = Container().bind(make_pool).freeze()
    assert_type(await di.aresolve(Pool), Pool)


def a_generator_is_a_provider() -> None:
    def make_pool() -> Generator[Pool]:
        yield Pool()

    assert_type(Container().bind(make_pool), Container)
    assert_type(Container().bind(make_pool, check=ping), Container)
    assert_type(Container().bind(make_pool).freeze().resolve(Pool), Pool)


def an_async_generator_is_a_provider() -> None:
    async def make_pool() -> AsyncGenerator[Pool]:
        yield Pool()

    assert_type(Container().bind(make_pool), Container)
    assert_type(Container().bind(make_pool, check=ping), Container)


async def an_async_generator_provider_resolves_through_aresolve() -> None:
    async def make_pool() -> AsyncGenerator[Pool]:
        yield Pool()

    di = Container().bind(make_pool).freeze()
    assert_type(await di.aresolve(Pool), Pool)


def a_context_manager_factory_is_a_provider() -> None:
    @contextlib.contextmanager
    def make_pool() -> Generator[Pool]:
        yield Pool()

    assert_type(Container().bind(make_pool), Container)
    assert_type(Container().bind(make_pool, check=ping), Container)
    assert_type(Container().bind(make_pool).freeze().resolve(Pool), Pool)


def an_async_context_manager_factory_is_a_provider() -> None:
    @contextlib.asynccontextmanager
    async def make_pool() -> AsyncGenerator[Pool]:
        yield Pool()

    assert_type(Container().bind(make_pool), Container)
    assert_type(Container().bind(make_pool, check=ping), Container)


async def an_async_context_manager_provider_resolves_through_aresolve() -> None:
    @contextlib.asynccontextmanager
    async def make_pool() -> AsyncGenerator[Pool]:
        yield Pool()

    di = Container().bind(make_pool).freeze()
    assert_type(await di.aresolve(Pool), Pool)


def a_value_binding_takes_the_token_parameter() -> None:
    def in_range(number: int) -> bool:
        return 0 < number < 65536

    assert_type(Container().value(port, 8080), Container)
    assert_type(Container().value(port, 8080, check=in_range), Container)
    assert_type(Container().value(port, 8080).freeze().resolve(port), int)


def a_scope_value_is_supplied_by_whoever_opens_the_scope() -> None:
    di = Container().scope_value(Request).freeze()
    with di.scope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(frame.provide(Request, Request('/health')), None)
        assert_type(di.resolve(Request), Request)


def a_scope_value_takes_a_token_key_too() -> None:
    correlation = Token[str]('correlation-id')
    di = Container().scope_value(correlation).freeze()
    with di.scope() as frame:
        frame.provide(correlation, 'abc')
        assert_type(di.resolve(correlation), str)


def every_shape_accepts_the_registration_keywords() -> None:
    def make_pool() -> Pool:
        return Pool()

    assert_type(Container().bind(make_pool, scope=Scope.TRANSIENT), Container)
    assert_type(Container().bind(make_pool, tag='primary'), Container)
    assert_type(Container().bind(make_pool, when=True), Container)
    assert_type(Container().bind(make_pool, provides=Pool), Container)
