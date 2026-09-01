"""Click integration: the shared command scope, seeded with a `click.Context`.

Importing this module requires the ``click`` extra (``pip install
'pydepin[click]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract and the
framework-free seam in `depin.ext.cli`: a seed and a partial application,
nothing more.

The seed binds `click.Context` — the class Click annotates its callbacks with
and the class Click instantiates — so the value placed into the scope is an
instance of the key it is placed under. `depin.ext.typer` records why the same
seed is not offered there.

What is seeded is the context `install` was handed, not the context that
happens to be current when a provider resolves. The two differ inside a group:
Click pushes a child context for each subcommand, while the scope, and so the
seeded value, belongs to the callback that opened it. A provider that needs a
subcommand's own context takes it there with ``@click.pass_context`` and places
it into the frame under a key of its own.
"""

from click import Context

from depin import FrozenContainer, ProviderKey, ScopeFrame
from depin.ext.cli import install as install_command_scope


def seed_context(ctx: Context) -> tuple[ProviderKey, object]:
    """Build the `click.Context` binding that `install` places into the invocation's frame.

    Args:
        ctx: The context of the command or group the scope is opened for.

    Returns:
        The key to bind the context under, and the context itself.

    Example:
        >>> from click import Command, Context
        >>> ctx = Context(Command('report'))
        >>> key, value = seed_context(ctx)
        >>> key is Context
        True
        >>> value is ctx
        True
    """
    return Context, ctx


def install(ctx: Context, container: FrozenContainer) -> ScopeFrame:
    """Open one depin scope bound to a Click invocation, seeded with its context.

    Call it from the callback of a command or a group, which is the first code
    Click runs for an invocation. `depin.ext.cli.install` states the lifetime
    the scope takes on, what the frame is for, and what nesting an install
    inside another one does; this adds the seed, so a scoped provider can
    declare a `click.Context` parameter and be handed the context of the
    callback that opened the scope.

    Args:
        ctx: The context of the command or group being invoked, taken with
            ``@click.pass_context``.
        container: The frozen container to host for that invocation.

    Returns:
        The scope's frame, for placing further values into with
        `depin.ScopeFrame.provide` before anything resolves — a tenant, a
        correlation id read off an option.

    Raises:
        TeardownError: An async provider left a teardown in the invocation's
            synchronous scope. Raised when the Click context closes: a command
            callback cannot await, so an async provider has no place in one.
        ExceptionGroup: One or more teardowns failed when the invocation's
            scope closed. Every failure is included; one does not hide another.

    Example:
        Install once, in the group callback, and every subcommand of that group
        runs inside the one scope::

            @click.group()
            @click.pass_context
            def cli(ctx: click.Context) -> None:
                install(ctx, di)
    """
    return install_command_scope(ctx, container, seed=seed_context)
