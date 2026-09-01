"""A Click CLI wired by depin: one scope per invocation, one teardown at exit.

Run with ``python -m examples.click_app.main`` to drive three invocations in one
process and print what each one saw.
"""

import click
from click import Context

from depin import Container, FrozenContainer, hosted_container
from depin.ext.click import install

from .registries import TENANT, Database, infra, services
from .services import ReportService


def build_container() -> FrozenContainer:
    """Freeze the graph. Called once per process, never at import time.

    The two ``scope_value`` declarations are what give the invocation's values a
    plan node: the `click.Context` `depin.ext.click.install` seeds, and the
    tenant the callback reads off an option.
    """
    return Container(infra, services).scope_value(Context).scope_value(TENANT).freeze()


def build_cli(container: FrozenContainer | None = None) -> click.Group:
    """Build the command group around a container.

    Accepting the container as an argument is what makes the CLI testable: a
    test passes a container with its own bindings instead of patching module
    state.
    """
    di = container if container is not None else build_container()

    @click.group()
    @click.option('--tenant', default='acme', help='The tenant every command in this invocation runs for.')
    @click.pass_context
    def cli(ctx: Context, tenant: str) -> None:
        """Open one scope for the whole invocation, before any subcommand runs."""
        frame = install(ctx, di)
        frame.provide(TENANT, tenant)

    @cli.command()
    def report() -> None:  # pyright: ignore[reportUnusedFunction]
        """A command that holds no container: `hosted_container()` reaches the hosted one."""
        click.echo(hosted_container().resolve(ReportService).summary())

    @cli.command()
    def health() -> None:  # pyright: ignore[reportUnusedFunction]
        db = hosted_container().resolve(Database)
        click.echo(f'db={db.url} open_sessions={db.open_sessions}')

    return cli


def main() -> None:
    """Drive the CLI three times in one process, then drain the singletons.

    A console script hands `build_cli()` straight to Click and lets the process
    exit. Three invocations here are what make the scope boundary visible: each
    one gets its own session, and ``health`` reports none left open once the two
    before it have closed. ``standalone_mode=False`` keeps Click from calling
    `sys.exit` between them.
    """
    di = build_container()
    cli = build_cli(di)
    try:
        _ = cli.main(args=['--tenant', 'acme', 'report'], standalone_mode=False)
        _ = cli.main(args=['--tenant', 'globex', 'report'], standalone_mode=False)
        _ = cli.main(args=['health'], standalone_mode=False)
    finally:
        # Drains the singleton providers that own resources — here, the Database
        # generator in `registries`.
        di.close()


if __name__ == '__main__':
    main()
