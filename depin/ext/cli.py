"""The command-line half of every CLI integration: one scope per invocation, and nothing else.

This module needs no installation extra and imports no third-party package,
not even under ``TYPE_CHECKING``. A command framework's context is a structural
seam, so the one type it needs is declared here instead of being borrowed from
Click or Typer: `CommandContext`, a `typing.Protocol` carrying the single
operation `install` uses. Two consequences follow, and both are the reason for
the rule: the module imports cleanly when no framework is installed, and a
command framework outside depin's curated set can use `install` without depin
having to know about it. That second consequence is not hypothetical here —
Typer stopped being Click, and vendored its own copy, so the two contexts depin
ships against are already two unrelated classes that satisfy the same protocol.

A command framework's context is a *block* seam rather than a hook pair: it
enters a context manager when asked and exits it when the command context
closes — after the command body, and after a group's result callback. So the
whole integration is `Host.scope()` handed to `CommandContext.with_resource`,
and there is nothing to pair by hand.

`install` is generic over the context type because ``seed`` receives that
context. A callable parameter is contravariant, so a
``Callable[[CommandContext], ...]`` parameter would reject the
``Callable[[click.Context], ...]`` a caller actually writes. Being generic,
`install` adopts whichever context type the caller passes and hands the seed
exactly that type.

Written against depin's public integration contract — `depin.Host` — so it
reaches nothing inside the private package.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from depin import FrozenContainer, Host, ProviderKey, ScopeFrame


class CommandContext(Protocol):
    """A command framework's context: anything that can own a resource for its own lifetime."""

    def with_resource[T](self, context_manager: AbstractContextManager[T], /) -> T: ...


def install[C: CommandContext](
    ctx: C,
    container: FrozenContainer,
    *,
    seed: Callable[[C], tuple[ProviderKey, object] | None] | None = None,
) -> ScopeFrame:
    """Open one depin scope bound to a command context's lifetime.

    Called from the callback of a command or a group. The container is
    published to the invocation's context for the duration of the scope, so
    `depin.hosted_container()` reaches it from anywhere the command calls into.
    The scope's teardowns run when the command context closes — after the
    command body, and after a group's result callback, including when the body
    ends by raising — and the publication is undone after them.

    Installing on a group and again on one of its commands is safe but
    redundant: the inner scope becomes a child of the outer frame, so a key
    already cached there is what the inner scope resolves.

    Args:
        ctx: The command context that will own the scope. It ends the scope
            when it closes, so the scope lasts exactly as long as the
            invocation the framework opened it for.
        container: The frozen container to host for that invocation.
        seed: Called once, before this function returns, to produce the key and
            value to place into the fresh scope frame. It receives ``ctx``.
            Returning ``None`` seeds nothing. Omitting it seeds nothing either.

    Returns:
        The scope's frame, so the caller can place its own values into it with
        `depin.ScopeFrame.provide` — a tenant, a correlation id read off an
        option — before anything resolves.

    Raises:
        TeardownError: An async provider left a teardown in the invocation's
            synchronous scope. Raised when the command context closes: a
            command callback cannot await, so an async provider has no place
            in one.
        ExceptionGroup: One or more teardowns failed when the invocation's
            scope closed. Every failure is included; one does not hide another.

    Example:
        Install once, in the callback the framework runs before the command
        body, and let the framework's own context own the scope::

            @app.callback()
            def main(ctx: typer.Context) -> None:
                install(ctx, di)
    """
    frame = ctx.with_resource(Host(container).scope())
    if seed is not None:
        seeded = seed(ctx)
        if seeded is not None:
            frame.provide(*seeded)
    return frame
