"""The framework-free command seam, driven by a hand-written context and no framework.

These tests install no command framework and import none. `depin.ext.cli`
speaks the command-context protocol structurally, so an object that enters a
context manager and exits it when it closes — which is all a Click or Typer
context does for `install` — is a legitimate peer. Supplying one is not mocking
depin, whose real `FrozenContainer` performs every resolution asserted here.
"""

from collections.abc import Generator
from contextlib import AbstractContextManager, ExitStack
from typing import Self

import pytest

from depin import Container, FrozenContainer, Scope, ScopeSeed, Token, optional_hosted_container
from depin.errors import MissingProviderError
from depin.ext.cli import install

TENANT = Token[str]('tenant')


class Resource:
    """A scoped dependency whose teardown the tests count."""


class CommandFailure(Exception):
    """Raised by a command body to prove the scope still drains."""


class CommandContextStandIn:
    """A command framework's context, reduced to the one operation `install` uses.

    Backed by `contextlib.ExitStack`, which is what a real Click context holds:
    `with_resource` enters the manager now and exits it when the context
    closes, not when the command body returns.
    """

    def __init__(self) -> None:
        self._resources = ExitStack()

    def with_resource[T](self, context_manager: AbstractContextManager[T], /) -> T:
        return self._resources.enter_context(context_manager)

    def close(self) -> None:
        self._resources.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def seeded_container() -> FrozenContainer:
    return Container().scope_value(TENANT).freeze()


def torn_down_container(torn: list[Resource]) -> FrozenContainer:
    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(item)

    return Container().bind(make, scope=Scope.SCOPED, provides=Resource).freeze()


def seed_tenant(value: str) -> ScopeSeed:
    return ScopeSeed(TENANT, value)


def test_install_returns_the_frame_the_caller_seeds_its_own_values_into() -> None:
    di = seeded_container()

    with CommandContextStandIn() as ctx:
        frame = install(ctx, di)
        frame.provide(TENANT, 'acme')

        assert di.resolve(TENANT) == 'acme'


def test_the_container_is_published_for_the_life_of_the_context() -> None:
    di = seeded_container()

    with CommandContextStandIn() as ctx:
        install(ctx, di)

        assert optional_hosted_container() is di


def test_the_seed_is_applied_before_anything_resolves() -> None:
    di = seeded_container()

    with CommandContextStandIn() as ctx:
        install(ctx, di, seed=lambda _: seed_tenant('acme'))

        assert di.resolve(TENANT) == 'acme'


def test_a_seed_returning_none_seeds_nothing_and_still_opens_the_scope() -> None:
    di = seeded_container()

    with CommandContextStandIn() as ctx:
        install(ctx, di, seed=lambda _: None)

        assert optional_hosted_container() is di
        with pytest.raises(MissingProviderError):
            di.resolve(TENANT)


def test_no_seed_at_all_behaves_like_a_seed_returning_none() -> None:
    di = seeded_container()

    with CommandContextStandIn() as ctx:
        install(ctx, di)

        assert optional_hosted_container() is di
        with pytest.raises(MissingProviderError):
            di.resolve(TENANT)


def test_the_seed_receives_the_context_it_was_installed_on() -> None:
    di = seeded_container()
    seen: list[object] = []

    def seed(ctx: CommandContextStandIn) -> ScopeSeed:
        seen.append(ctx)
        return seed_tenant('acme')

    with CommandContextStandIn() as ctx:
        install(ctx, di, seed=seed)

        assert seen == [ctx]


def test_the_scope_drains_when_the_context_closes_not_when_install_returns() -> None:
    torn: list[Resource] = []
    di = torn_down_container(torn)

    ctx = CommandContextStandIn()
    install(ctx, di)
    resolved = di.resolve(Resource)

    assert torn == []

    ctx.close()

    assert torn == [resolved]


def test_the_publication_is_undone_when_the_context_closes() -> None:
    di = seeded_container()

    with CommandContextStandIn() as ctx:
        install(ctx, di)

    assert optional_hosted_container() is None


def test_a_body_that_raises_still_drains_the_scope_and_the_exception_propagates() -> None:
    torn: list[Resource] = []
    di = torn_down_container(torn)

    def command() -> None:
        with CommandContextStandIn() as ctx:
            install(ctx, di)
            di.resolve(Resource)
            raise CommandFailure

    with pytest.raises(CommandFailure):
        command()

    assert len(torn) == 1
    assert optional_hosted_container() is None


def test_two_sequential_commands_get_independent_instances() -> None:
    torn: list[Resource] = []
    di = torn_down_container(torn)
    built: list[Resource] = []

    for _ in range(2):
        with CommandContextStandIn() as ctx:
            install(ctx, di)
            built.append(di.resolve(Resource))

    assert torn == built
    assert built[0] is not built[1]
