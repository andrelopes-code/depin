"""Lifetimes, scopes, overrides, and the four teardown entry points.

`Scope` members take a typed witness rather than `assert_type`: every checker
narrows a member access to its own literal member type, so
``assert_type(Scope.SINGLETON, Scope)`` would be a promise about the checker's
printer rather than about the library. `scope()`, `ascope()` and `override()`
are context managers, whose parameterisation differs between checkers — Pyrefly
prints `_GeneratorContextManager[ScopeFrame]` where the other four print
`_GeneratorContextManager[ScopeFrame, None, None]` — so the assertion is made on
the value the `with` statement binds, which is nominal.
"""

from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import assert_type

from depin import Container, FrozenContainer, Scope, ScopeFrame, Token


class Config:
    def __init__(self, dsn: str = 'sqlite://') -> None:
        self.dsn = dsn


class Session:
    def __init__(self) -> None:
        self.open = True


class Request:
    def __init__(self, path: str = '/') -> None:
        self.path = path


port = Token[int]('port')


def build() -> FrozenContainer:
    return Container().bind(Config).bind(Session, scope=Scope.SCOPED).value(port, 8080).freeze()


def every_lifetime_is_a_scope() -> None:
    _singleton: Scope = Scope.SINGLETON
    _scoped: Scope = Scope.SCOPED
    _transient: Scope = Scope.TRANSIENT


def a_lifetime_is_a_bind_keyword() -> None:
    assert_type(Container().bind(Config, scope=Scope.SINGLETON), Container)
    assert_type(Container().bind(Config, scope=Scope.SCOPED), Container)
    assert_type(Container().bind(Config, scope=Scope.TRANSIENT), Container)


def scope_is_a_context_manager_over_a_frame() -> None:
    di = build()
    _manager: AbstractContextManager[ScopeFrame] = di.scope()
    with di.scope() as frame:
        assert_type(frame, ScopeFrame)


def ascope_is_an_async_context_manager_over_a_frame() -> None:
    di = build()
    _manager: AbstractAsyncContextManager[ScopeFrame] = di.ascope()


async def an_async_scope_yields_a_frame() -> None:
    di = build()
    async with di.ascope() as frame:
        assert_type(frame, ScopeFrame)


def a_frame_stores_and_reports_what_was_seeded() -> None:
    di = Container().scope_value(Request).freeze()
    with di.scope() as frame:
        assert_type(frame.provide(Request, Request('/health')), None)
        assert_type(frame.get(Request), object)
        assert_type(frame.lookup(Request), object)
        assert_type(Request in frame, bool)
        assert_type(frame.parent, ScopeFrame | None)


def a_nested_scope_yields_a_frame_of_the_same_type() -> None:
    di = build()
    with di.scope() as outer, di.scope() as inner:
        assert_type(outer, ScopeFrame)
        assert_type(inner, ScopeFrame)


def override_yields_a_container_with_the_replacement_in_place() -> None:
    di = build()
    _manager: AbstractContextManager[FrozenContainer] = di.override(Config, Config('postgres://'))
    with di.override(Config, Config('postgres://')) as overridden:
        assert_type(overridden, FrozenContainer)
        assert_type(overridden.resolve(Config), Config)


def override_replaces_a_token_at_its_own_type() -> None:
    di = build()
    with di.override(port, 9090) as overridden:
        assert_type(overridden.resolve(port), int)


def override_carries_a_tag_without_changing_its_type() -> None:
    di = Container().bind(Config, tag='primary').freeze()
    with di.override(Config, Config('postgres://'), tag='primary') as overridden:
        assert_type(overridden, FrozenContainer)


def the_synchronous_teardown_entry_points_return_none() -> None:
    di = build()
    assert_type(di.reset(), None)
    assert_type(di.close(), None)


async def the_asynchronous_teardown_entry_points_return_none() -> None:
    di = build()
    assert_type(await di.areset(), None)
    assert_type(await di.aclose(), None)
