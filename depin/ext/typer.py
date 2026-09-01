"""Typer integration: the shared command scope, with nothing seeded into it.

Importing this module requires the ``typer`` extra (``pip install
'pydepin[typer]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract and the
framework-free seam in `depin.ext.cli`: a partial application, nothing more.

Alone among the framework scope integrations depin ships, this one seeds no
value, and the reason is measurable rather than a matter of taste. Typer 0.26 dropped its
dependency on Click and vendored a private copy of it, and from that release
the object handed to a callback annotated `typer.Context` is an instance of
the vendored private class, for which ``isinstance(value, typer.Context)`` is
false. Seeding under the key `typer.Context` would therefore bind a value that
is not an instance of its own key: depin keys on the annotation, so it would
resolve, and every provider declaring that parameter would be handed something
its own annotation denies. Seeding under the vendored class instead would make
depin import a third-party private name, which is the one thing depin asks
nobody to do to its own private package. The module ships neither.

The context is therefore the caller's to seed, under a key the caller owns.
Declare that key with `depin.Container.scope_value`, and place the context into
the frame `install` returns::

    COMMAND_CONTEXT = Token[typer.Context]('command-context')

    di = Container().scope_value(COMMAND_CONTEXT).bind(Report, scope=Scope.SCOPED).freeze()

    @app.callback()
    def main(ctx: typer.Context) -> None:
        frame = install(ctx, di)
        frame.provide(COMMAND_CONTEXT, ctx)

Providers then declare ``Annotated[typer.Context, COMMAND_CONTEXT]`` and read
the context through a key whose meaning the caller, not depin, defines.
"""

from typer import Context

from depin import FrozenContainer, ScopeFrame
from depin.ext.cli import install as install_command_scope


def install(ctx: Context, container: FrozenContainer) -> ScopeFrame:
    """Open one depin scope bound to a Typer invocation.

    Call it from the first function Typer runs for an invocation, taking the
    context as a parameter annotated `typer.Context`: the callback registered
    with ``@app.callback()``, or the command itself when the application
    declares no callback. `depin.ext.cli.install` states the lifetime the scope
    takes on, what the frame is for, and what nesting an install inside another
    one does.

    Nothing is placed into the fresh frame. The module docstring records the
    measurement behind that and shows how to seed the context under a key of
    your own.

    Args:
        ctx: The context of the callback or command being invoked. It ends the
            scope when it closes, so the scope lasts exactly as long as the
            invocation.
        container: The frozen container to host for that invocation.

    Returns:
        The scope's frame, for placing values into with
        `depin.ScopeFrame.provide` before anything resolves — the context
        itself, a tenant, a correlation id read off an option.

    Raises:
        TeardownError: An async provider left a teardown in the invocation's
            synchronous scope. Raised when the Typer context closes: a command
            callback cannot await, so an async provider has no place in one.
        ExceptionGroup: One or more teardowns failed when the invocation's
            scope closed. Every failure is included; one does not hide another.

    Example:
        Install once, in the callback, and every command of the application
        runs inside the one scope::

            @app.callback()
            def main(ctx: typer.Context) -> None:
                install(ctx, di)
    """
    return install_command_scope(ctx, container)
