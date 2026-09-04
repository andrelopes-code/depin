"""`depin.ext.click` and `depin.ext.typer`: the two command specialisations.

Typer stopped being Click and vendored its own copy, so the two contexts depin
ships against are already two unrelated classes satisfying the same protocol.
Checking them side by side is what shows the structural seam carrying both:
each framework's own `Context` is assignable to `depin.ext.cli.CommandContext`,
and each `install` returns the frame the caller seeds.

Callbacks are registered by calling the framework's decorator rather than by
applying it. A decorated function whose name is never read afterwards is an
unused-function error under the strict Pyright engines, and this corpus carries
no suppressions.

Requires the `click` and `typer` extras, so this file is checked in all-extras
mode only.
"""

from collections.abc import Callable
from typing import assert_type

import click
import typer
from click import Context as ClickContext
from typer import Context as TyperContext

from depin import Container, FrozenContainer, ScopeFrame, ScopeSeed, Token
from depin.ext.cli import CommandContext
from depin.ext.click import install as click_install
from depin.ext.click import seed_context
from depin.ext.typer import install as typer_install


class Database:
    def __init__(self) -> None:
        self.url = 'sqlite://'


TENANT: Token[str] = Token[str]('tenant')


def build() -> FrozenContainer:
    return Container().bind(Database).scope_value(TENANT).freeze()


def a_click_context_satisfies_the_command_context_protocol(ctx: ClickContext) -> None:
    _context: CommandContext = ctx


def click_install_returns_the_frame_it_opened(ctx: ClickContext) -> None:
    assert_type(click_install(ctx, build()), ScopeFrame)


def the_click_seed_maps_a_context_to_a_key_and_a_value() -> None:
    _seed: Callable[[ClickContext], ScopeSeed] = seed_context


def a_click_group_opens_one_scope_for_the_whole_invocation() -> None:
    di = build()

    def cli(ctx: ClickContext, tenant: str) -> None:
        frame = click_install(ctx, di)
        assert_type(frame, ScopeFrame)
        frame.provide(TENANT, tenant)

    group = click.group()(click.option('--tenant', default='acme')(click.pass_context(cli)))
    assert_type(group, click.Group)


def a_typer_context_satisfies_the_command_context_protocol(ctx: TyperContext) -> None:
    _context: CommandContext = ctx


def typer_install_returns_the_frame_it_opened(ctx: TyperContext) -> None:
    assert_type(typer_install(ctx, build()), ScopeFrame)


def a_typer_callback_opens_one_scope_for_the_whole_invocation() -> None:
    di = build()
    app = typer.Typer()

    def main(ctx: TyperContext, tenant: str = 'acme') -> None:
        frame = typer_install(ctx, di)
        assert_type(frame, ScopeFrame)
        frame.provide(TENANT, tenant)

    _registered: Callable[[TyperContext, str], None] = app.callback()(main)
