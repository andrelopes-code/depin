"""The Click integration, driven by real Click commands over `click.testing.CliRunner`.

`depin.ext.click.install` is the framework-free command seam of
`depin.ext.cli` with one seed applied, so what these tests exercise is the seed
and the wiring: one scope per invocation, drained after the body returned and
after a group's result callback, with the container reachable from anywhere the
command calls into.

`click.testing.CliRunner` drives the same entry point the console script does —
``Command.main`` — so the context whose closing ends the scope is a real one,
opened and closed by Click.

The two group tests register the result callback and the subcommand by calling
Click's decorators rather than by applying them. A decorated function whose
name is never read afterwards is an unused-function error under the strict
checkers, and this suite carries no suppressions.
"""

from collections.abc import Generator

import click
from click import Context
from click.testing import CliRunner

from depin import Container, FrozenContainer, Scope, hosted_container, optional_hosted_container
from depin.ext.click import install


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
    """A provider whose only input is the seeded `click.Context`."""

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
    return Container().scope_value(Context).bind(ContextProbe, scope=Scope.SCOPED).freeze()


def test_a_scoped_provider_is_resolved_once_per_invocation() -> None:
    di = command_container([])
    ticks: list[int] = []

    @click.command()
    @click.pass_context
    def report(ctx: Context) -> None:
        _ = install(ctx, di)
        ticks.append(hosted_container().resolve(Counter).tick())
        ticks.append(hosted_container().resolve(Counter).tick())

    result = CliRunner().invoke(report, [])

    assert result.exit_code == 0
    assert ticks == [1, 2]


def test_two_invocations_get_independent_scoped_instances() -> None:
    di = command_container([])
    seen: list[Counter] = []
    ticks: list[int] = []

    @click.command()
    @click.pass_context
    def report(ctx: Context) -> None:
        _ = install(ctx, di)
        counter = hosted_container().resolve(Counter)
        seen.append(counter)
        ticks.append(counter.tick())

    runner = CliRunner()

    assert runner.invoke(report, []).exit_code == 0
    assert runner.invoke(report, []).exit_code == 0
    assert ticks == [1, 1]
    assert seen[0] is not seen[1]


def test_the_scope_drains_its_teardowns_after_the_command_body_returned() -> None:
    torn: list[Resource] = []
    torn_while_running: list[int] = []
    di = command_container(torn)

    @click.command()
    @click.pass_context
    def report(ctx: Context) -> None:
        _ = install(ctx, di)
        _ = hosted_container().resolve(Resource)
        torn_while_running.append(len(torn))

    result = CliRunner().invoke(report, [])

    assert result.exit_code == 0
    assert torn_while_running == [0]
    assert len(torn) == 1


def test_the_hosted_container_is_reachable_from_the_command_body() -> None:
    di = Container().freeze()
    found: list[FrozenContainer] = []

    @click.command()
    @click.pass_context
    def report(ctx: Context) -> None:
        _ = install(ctx, di)
        found.append(hosted_container())

    result = CliRunner().invoke(report, [])

    assert result.exit_code == 0
    assert found[0] is di


def test_a_command_that_raises_still_drains_its_scope() -> None:
    torn: list[Resource] = []
    di = command_container(torn)

    @click.command()
    @click.pass_context
    def report(ctx: Context) -> None:
        _ = install(ctx, di)
        _ = hosted_container().resolve(Resource)
        raise CommandFailure('the body failed')

    result = CliRunner().invoke(report, [])

    assert isinstance(result.exception, CommandFailure)
    assert len(torn) == 1
    assert optional_hosted_container() is None


def test_asking_for_help_opens_no_scope() -> None:
    torn: list[Resource] = []
    di = command_container(torn)
    bodies: list[Resource] = []

    @click.command()
    @click.pass_context
    def report(ctx: Context) -> None:
        _ = install(ctx, di)
        bodies.append(hosted_container().resolve(Resource))

    result = CliRunner().invoke(report, ['--help'])

    assert result.exit_code == 0
    assert bodies == []
    assert torn == []
    assert optional_hosted_container() is None


def test_the_group_scope_spans_the_subcommand_and_the_result_callback() -> None:
    torn: list[Resource] = []
    di = command_container(torn)
    seen: list[int] = []
    torn_at_the_result_callback: list[int] = []

    @click.group()
    @click.pass_context
    def cli(ctx: Context) -> None:
        _ = install(ctx, di)
        seen.append(id(hosted_container().resolve(Counter)))

    def finished(subcommand_result: object) -> None:
        seen.append(id(hosted_container().resolve(Counter)))
        torn_at_the_result_callback.append(len(torn))

    def run() -> None:
        seen.append(id(hosted_container().resolve(Counter)))
        _ = hosted_container().resolve(Resource)

    _ = cli.result_callback()(finished)
    _ = cli.command()(run)

    result = CliRunner().invoke(cli, ['run'])

    assert result.exit_code == 0
    assert len(seen) == 3
    assert len(set(seen)) == 1
    assert torn_at_the_result_callback == [0]
    assert len(torn) == 1


def test_installing_on_a_group_and_again_on_its_subcommand_is_redundant() -> None:
    """The nesting `depin.ext.cli.install` documents as safe but redundant, pinned.

    The subcommand's scope becomes a child of the group's frame, so a key the
    group already resolved is served from that frame's cache: one instance
    across both scopes, and one teardown, run when the group's context closes.
    """
    torn: list[Resource] = []
    di = command_container(torn)
    counters: list[Counter] = []
    resources: list[Resource] = []
    torn_when_the_subcommand_returned: list[int] = []

    @click.group()
    @click.pass_context
    def cli(ctx: Context) -> None:
        _ = install(ctx, di)
        counters.append(hosted_container().resolve(Counter))
        resources.append(hosted_container().resolve(Resource))

    def run(ctx: Context) -> None:
        _ = install(ctx, di)
        counters.append(hosted_container().resolve(Counter))
        resources.append(hosted_container().resolve(Resource))

    def finished(subcommand_result: object) -> None:
        torn_when_the_subcommand_returned.append(len(torn))

    _ = cli.result_callback()(finished)
    _ = cli.command()(click.pass_context(run))

    result = CliRunner().invoke(cli, ['run'])

    assert result.exit_code == 0
    assert counters[0] is counters[1]
    assert resources[0] is resources[1]
    assert torn_when_the_subcommand_returned == [0]
    assert torn == [resources[0]]


def test_a_provider_reads_an_option_off_the_seeded_context() -> None:
    di = probing_container()
    contexts: list[Context] = []
    probes: list[ContextProbe] = []

    @click.command()
    @click.option('--tenant')
    @click.pass_context
    def report(ctx: Context, tenant: str | None) -> None:
        _ = install(ctx, di)
        contexts.append(ctx)
        probes.append(hosted_container().resolve(ContextProbe))

    result = CliRunner().invoke(report, ['--tenant', 'acme'])

    assert result.exit_code == 0
    assert probes[0].context is contexts[0]
    assert probes[0].tenant == 'acme'


def test_the_seeded_context_is_the_one_the_scope_was_opened_with() -> None:
    """Inside a group, the seed stays the group's context, not the subcommand's child.

    Click pushes a fresh context per subcommand. The scope belongs to the
    callback that opened it, so that is the context a provider resolves — the
    behaviour `depin.ext.click` documents.
    """
    di = probing_container()
    group_contexts: list[Context] = []
    subcommand_contexts: list[Context] = []
    probes: list[ContextProbe] = []

    @click.group()
    @click.pass_context
    def cli(ctx: Context) -> None:
        _ = install(ctx, di)
        group_contexts.append(ctx)

    def run(ctx: Context) -> None:
        subcommand_contexts.append(ctx)
        probes.append(hosted_container().resolve(ContextProbe))

    _ = cli.command()(click.pass_context(run))

    result = CliRunner().invoke(cli, ['run'])

    assert result.exit_code == 0
    assert subcommand_contexts[0] is not group_contexts[0]
    assert probes[0].context is group_contexts[0]
