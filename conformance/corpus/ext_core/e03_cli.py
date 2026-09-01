"""`depin.ext.cli` against a consumer's own command context.

`install` is generic over the context type because ``seed`` receives that
context, and a callable parameter is contravariant: a
``Callable[[CommandContext], ...]`` parameter would reject the
``Callable[[Invocation], ...]`` a caller actually writes. This file is the
caller. It declares its own context class — never Click's, never Typer's, never
depin's `CommandContext` itself — and passes a seed written against that class,
so what it proves is that `install` adopts the context it was handed and hands
the seed exactly that type back.

`depin.ext.cli` imports no third-party package, so this file is checked in both
install modes.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from typing import assert_type

from depin import Container, FrozenContainer, ProviderKey, ScopeFrame
from depin.ext.cli import CommandContext, install


class Invocation:
    """A command framework's own context, satisfying the protocol structurally."""

    def __init__(self, command: str) -> None:
        self.command = command
        self._stack = ExitStack()

    def with_resource[T](self, context_manager: AbstractContextManager[T], /) -> T:
        return self._stack.enter_context(context_manager)

    def close(self) -> None:
        self._stack.close()


class Tenant:
    def __init__(self, name: str) -> None:
        self.name = name


def seed(ctx: Invocation) -> tuple[ProviderKey, object] | None:
    return Tenant, Tenant(ctx.command)


def build() -> FrozenContainer:
    return Container().scope_value(Tenant).freeze()


def a_consumer_context_satisfies_the_protocol() -> None:
    _context: CommandContext = Invocation('report')


def install_returns_the_frame_it_opened() -> None:
    ctx = Invocation('report')
    assert_type(install(ctx, build()), ScopeFrame)


def install_hands_the_seed_the_context_it_was_given() -> None:
    ctx = Invocation('report')
    frame = install(ctx, build(), seed=seed)
    assert_type(frame, ScopeFrame)
    assert_type(frame.provide(Tenant, Tenant('acme')), None)


def a_seed_is_a_callable_from_the_consumer_context() -> None:
    _seed: Callable[[Invocation], tuple[ProviderKey, object] | None] = seed


def the_frame_resolves_what_the_seed_placed_in_it() -> None:
    di = build()
    ctx = Invocation('report')
    _ = install(ctx, di, seed=seed)
    assert_type(di.resolve(Tenant), Tenant)
    assert_type(di.resolve(Tenant).name, str)
    ctx.close()
