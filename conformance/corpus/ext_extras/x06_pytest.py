"""`depin.ext.pytest`: the plugin's fixtures, as a consumer's own suite sees them.

The two factory protocols are checked from both sides, and the second side is
the one the existing repository corpus was missing. Declaring a parameter
`OverrideFactory` and calling it proves what the protocol promises; it proves
nothing about the value the plugin actually hands over. That value is
`FrozenContainer.override` wrapped in a pair of resets, so its result is a
`contextlib._GeneratorContextManager` and the protocol advertises a
`contextlib.AbstractContextManager[FrozenContainer]`. Binding the real method
to the protocol is what makes that widening a checked promise rather than a
docstring.

The fixture objects themselves carry no type argument to bind: under pytest 9
``@pytest.fixture`` returns a `FixtureFunctionDefinition`, which is neither
generic nor exported from `pytest`. So what this file checks of them is that
the installed wheel exports all five names, and their value types are checked
through the protocols.

Requires the `pytest` extra, so this file is checked in all-extras mode only.
"""

import contextlib
from collections.abc import AsyncGenerator
from typing import assert_type

import pytest

from depin import Container, FrozenContainer, ProviderKey, ScopeFrame, Token
from depin.ext.pytest import AsyncOverrideFactory, AsyncOverrideHandle, OverrideFactory, OverrideHandle
from depin.ext.pytest import depin_aoverride as real_aoverride_fixture
from depin.ext.pytest import depin_ascope as real_ascope_fixture
from depin.ext.pytest import depin_container as real_container_fixture
from depin.ext.pytest import depin_override as real_override_fixture
from depin.ext.pytest import depin_scope as real_scope_fixture


class Clock:
    def now(self) -> str:
        return 'real'


class FakeClock:
    def now(self) -> str:
        return 'fake'


class Report:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock


class Request:
    def __init__(self, path: str = '/') -> None:
        self.path = path


tenant = Token[str]('tenant')


@pytest.fixture
def depin_container() -> FrozenContainer:
    """The fixture a consumer's own conftest defines; every other one builds on it."""
    return Container().bind(Clock).bind(Report).scope_value(Request).value(tenant, 'acme').freeze()


def the_plugin_exports_all_five_fixtures() -> None:
    _exported: tuple[object, ...] = (
        real_container_fixture,
        real_override_fixture,
        real_aoverride_fixture,
        real_scope_fixture,
        real_ascope_fixture,
    )


def the_container_method_behind_the_fixture_satisfies_the_protocol(di: FrozenContainer) -> None:
    _factory: OverrideFactory = di.override
    _handle: OverrideHandle = di.override(Clock)


def an_async_context_manager_factory_satisfies_the_async_protocol(di: FrozenContainer) -> None:
    class Handle:
        @contextlib.asynccontextmanager
        async def using(self, replacement: object, /) -> AsyncGenerator[FrozenContainer]:
            yield di

    def factory(key: ProviderKey, /, *, tag: str | None = None) -> AsyncOverrideHandle:
        return Handle()

    _factory: AsyncOverrideFactory = factory


def a_test_overrides_a_class_key(depin_override: OverrideFactory) -> None:
    with depin_override(Clock).using(FakeClock()) as di:
        assert_type(di, FrozenContainer)
        assert_type(di.resolve(Report), Report)
        assert_type(di.resolve(Report).clock.now(), str)


def a_test_overrides_a_token_key(depin_override: OverrideFactory) -> None:
    with depin_override(tenant).using('globex') as di:
        assert_type(di.resolve(tenant), str)


def a_test_overrides_a_tagged_binding(depin_override: OverrideFactory) -> None:
    with depin_override(Clock, tag='primary').using(FakeClock()) as di:
        assert_type(di, FrozenContainer)


async def an_async_test_overrides_a_class_key(depin_aoverride: AsyncOverrideFactory) -> None:
    async with depin_aoverride(Clock).using(FakeClock()) as di:
        assert_type(di, FrozenContainer)
        assert_type(await di.aresolve(Report), Report)


def a_test_seeds_the_scope_the_plugin_opened(depin_scope: ScopeFrame) -> None:
    assert_type(depin_scope, ScopeFrame)
    assert_type(depin_scope.provide(Request, Request('/health')), None)


async def an_async_test_seeds_the_scope_the_plugin_opened(depin_ascope: ScopeFrame) -> None:
    assert_type(depin_ascope, ScopeFrame)
    depin_ascope.provide(Request, Request('/health'))
