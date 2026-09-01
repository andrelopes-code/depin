"""The Typer integration, driven by real Typer applications over `typer.testing.CliRunner`.

`depin.ext.typer.install` is the framework-free command seam of `depin.ext.cli`
with no seed at all, so what these tests exercise is the wiring: one scope per
invocation, drained after the command body returned, with the container
reachable from anywhere the command calls into.

The last test pins the documented answer to the missing seed — the caller
places the context into the frame `install` returns, under a `depin.Token` the
caller owns — so the module's advice is executed rather than only stated.

Callbacks and command bodies are registered by calling Typer's decorators
rather than by applying them, because a decorated function whose name is never
read afterwards is an unused-function error under the strict checkers, and this
suite carries no suppressions.
"""

from collections.abc import Callable, Generator
from typing import Annotated

import typer
from typer import Context
from typer.testing import CliRunner

from depin import Container, FrozenContainer, Scope, Token, hosted_container, optional_hosted_container
from depin.ext.typer import install

COMMAND_CONTEXT: Token[Context] = Token[Context]('command-context')


class Counter:
    """A scoped dependency whose identity distinguishes one invocation from the next."""

    def __init__(self) -> None:
        self.value = 0

    def tick(self) -> int:
        self.value += 1
        return self.value


class Resource:
    """A scoped dependency whose teardown the tests count."""


class ContextProbe:
    """A provider whose only input is the context the caller seeded under its own key."""

    def __init__(self, ctx: Context) -> None:
        self.context = ctx
        self.tenant = ctx.params.get('tenant')


class CommandFailure(Exception):
    """Raised by a command body to prove the scope still drains."""


def command_container(torn: list[Resource]) -> FrozenContainer:
    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(item)

    return Container().bind(Counter, scope=Scope.SCOPED).bind(make, scope=Scope.SCOPED, provides=Resource).freeze()


def probing_container() -> FrozenContainer:
    def make_probe(ctx: Annotated[Context, COMMAND_CONTEXT]) -> ContextProbe:
        return ContextProbe(ctx)

    return Container().scope_value(COMMAND_CONTEXT).bind(make_probe, scope=Scope.SCOPED).freeze()


def scoped_application(di: FrozenContainer, body: Callable[[], None]) -> typer.Typer:
    """A one-command Typer application whose callback installs the scope, and nothing else.

    The command is named after ``body``, so every invocation below passes the
    body's own name as the subcommand.
    """

    def main(ctx: Context) -> None:
        _ = install(ctx, di)

    app = typer.Typer()
    _ = app.callback()(main)
    _ = app.command()(body)
    return app


def test_a_scoped_provider_is_resolved_once_per_invocation() -> None:
    di = command_container([])
    ticks: list[int] = []

    def report() -> None:
        ticks.append(hosted_container().resolve(Counter).tick())
        ticks.append(hosted_container().resolve(Counter).tick())

    result = CliRunner().invoke(scoped_application(di, report), ['report'])

    assert result.exit_code == 0
    assert ticks == [1, 2]


def test_two_invocations_get_independent_scoped_instances() -> None:
    di = command_container([])
    seen: list[Counter] = []
    ticks: list[int] = []

    def report() -> None:
        counter = hosted_container().resolve(Counter)
        seen.append(counter)
        ticks.append(counter.tick())

    app = scoped_application(di, report)
    runner = CliRunner()

    assert runner.invoke(app, ['report']).exit_code == 0
    assert runner.invoke(app, ['report']).exit_code == 0
    assert ticks == [1, 1]
    assert seen[0] is not seen[1]


def test_the_scope_drains_its_teardowns_after_the_command_body_returned() -> None:
    torn: list[Resource] = []
    torn_while_running: list[int] = []
    di = command_container(torn)

    def report() -> None:
        _ = hosted_container().resolve(Resource)
        torn_while_running.append(len(torn))

    result = CliRunner().invoke(scoped_application(di, report), ['report'])

    assert result.exit_code == 0
    assert torn_while_running == [0]
    assert len(torn) == 1


def test_the_hosted_container_is_reachable_from_the_command_body() -> None:
    di = Container().freeze()
    found: list[FrozenContainer] = []

    def report() -> None:
        found.append(hosted_container())

    result = CliRunner().invoke(scoped_application(di, report), ['report'])

    assert result.exit_code == 0
    assert found[0] is di


def test_a_command_that_raises_still_drains_its_scope() -> None:
    torn: list[Resource] = []
    di = command_container(torn)

    def report() -> None:
        _ = hosted_container().resolve(Resource)
        raise CommandFailure('the body failed')

    result = CliRunner().invoke(scoped_application(di, report), ['report'])

    assert isinstance(result.exception, CommandFailure)
    assert len(torn) == 1
    assert optional_hosted_container() is None


def test_asking_for_help_opens_no_scope() -> None:
    torn: list[Resource] = []
    di = command_container(torn)
    bodies: list[Resource] = []

    def report() -> None:
        bodies.append(hosted_container().resolve(Resource))

    result = CliRunner().invoke(scoped_application(di, report), ['--help'])

    assert result.exit_code == 0
    assert bodies == []
    assert torn == []
    assert optional_hosted_container() is None


def test_the_caller_seeds_the_context_into_the_returned_frame() -> None:
    """The documented answer to the seed `depin.ext.typer` deliberately omits.

    The key is a `depin.Token` the caller declares, so nothing is bound under a
    class the value is not an instance of, and the provider reads the context
    through a name whose meaning the caller defines. The context seeded is the
    callback's, which is why the subcommand's own argument is absent from the
    parameters the probe reads.
    """
    di = probing_container()
    callback_contexts: list[Context] = []
    probes: list[ContextProbe] = []

    def main(ctx: Context) -> None:
        frame = install(ctx, di)
        frame.provide(COMMAND_CONTEXT, ctx)
        callback_contexts.append(ctx)

    def report(tenant: str) -> None:
        probes.append(hosted_container().resolve(ContextProbe))

    app = typer.Typer()
    _ = app.callback()(main)
    _ = app.command()(report)

    result = CliRunner().invoke(app, ['report', 'acme'])

    assert result.exit_code == 0
    assert probes[0].context is callback_contexts[0]
    assert probes[0].tenant is None
