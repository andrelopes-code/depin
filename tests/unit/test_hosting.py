"""The integration contract: publishing a container, scoping a unit of work, reading it back."""

import asyncio
import threading
from collections.abc import AsyncGenerator, Generator

import pytest

from depin import Container, Scope, Token
from depin._core.hosting import (
    CONTRACT_VERSION,
    ContractVersion,
    Host,
    hosted_container,
    optional_hosted_container,
)
from depin.errors import ContainerNotBoundError, OutsideScopeError

REQUEST = Token[str]('request')


def test_the_contract_version_is_one_zero() -> None:
    assert ContractVersion(1, 0) == CONTRACT_VERSION


def test_a_contract_version_renders_as_major_dot_minor() -> None:
    assert str(ContractVersion(2, 7)) == '2.7'


def test_contract_versions_order_by_major_then_minor() -> None:
    assert ContractVersion(1, 0) < ContractVersion(1, 1) < ContractVersion(2, 0)


def test_a_host_keeps_the_container_it_was_given() -> None:
    di = Container().freeze()

    assert Host(di).container is di


def test_nothing_is_hosted_by_default() -> None:
    assert optional_hosted_container() is None


def test_reading_an_unhosted_container_names_both_ways_to_publish_one() -> None:
    with pytest.raises(ContainerNotBoundError) as caught:
        hosted_container()

    assert str(caught.value) == (
        'no container is hosted in this context; open a scope with Host.scope() or Host.ascope(), '
        'or publish one with Host.activated()'
    )


def test_activated_publishes_the_container_and_undoes_it_on_exit() -> None:
    di = Container().freeze()

    with Host(di).activated():
        assert hosted_container() is di

    assert optional_hosted_container() is None


def test_activated_undoes_the_publication_when_the_block_raises() -> None:
    di = Container().freeze()

    with pytest.raises(RuntimeError), Host(di).activated():
        raise RuntimeError('boom')

    assert optional_hosted_container() is None


def test_a_nested_host_wins_and_restores_the_enclosing_one() -> None:
    outer = Container().freeze()
    inner = Container().freeze()

    with Host(outer).activated():
        with Host(inner).activated():
            assert hosted_container() is inner
        assert hosted_container() is outer


def test_activated_opens_no_scope() -> None:
    di = Container().scope_value(REQUEST).freeze()

    with Host(di).activated(), pytest.raises(OutsideScopeError):
        di.resolve(REQUEST)


def test_scope_publishes_seeds_and_resolves() -> None:
    di = Container().scope_value(REQUEST).freeze()
    host = Host(di)

    with host.scope() as frame:
        frame.provide(REQUEST, 'r-1')
        assert hosted_container().resolve(REQUEST) == 'r-1'

    assert optional_hosted_container() is None


def test_scope_drains_its_teardowns_before_unpublishing() -> None:
    seen: list[str | None] = []

    class Session: ...

    def open_session() -> Generator[Session]:
        yield Session()
        seen.append(None if optional_hosted_container() is None else 'hosted')

    di = Container().bind(open_session, scope=Scope.SCOPED).freeze()

    with Host(di).scope():
        _ = di.resolve(Session)

    assert seen == ['hosted']


def test_two_sibling_scopes_get_independent_seeds() -> None:
    di = Container().scope_value(REQUEST).freeze()
    host = Host(di)
    seen: list[str] = []

    for label in ('a', 'b'):
        with host.scope() as frame:
            frame.provide(REQUEST, label)
            seen.append(hosted_container().resolve(REQUEST))

    assert seen == ['a', 'b']


@pytest.mark.asyncio
async def test_ascope_publishes_seeds_and_resolves() -> None:
    class Session: ...

    async def open_session() -> AsyncGenerator[Session]:
        yield Session()

    di = Container().scope_value(REQUEST).bind(open_session, scope=Scope.SCOPED).freeze()
    host = Host(di)

    async with host.ascope() as frame:
        frame.provide(REQUEST, 'r-2')
        container = hosted_container()
        assert await container.aresolve(REQUEST) == 'r-2'
        assert isinstance(await container.aresolve(Session), Session)

    assert optional_hosted_container() is None


@pytest.mark.asyncio
async def test_ascope_undoes_the_publication_when_the_block_raises() -> None:
    di = Container().freeze()

    with pytest.raises(RuntimeError):
        async with Host(di).ascope():
            raise RuntimeError('boom')

    assert optional_hosted_container() is None


@pytest.mark.asyncio
async def test_concurrent_ascopes_do_not_see_each_others_seeds() -> None:
    di = Container().scope_value(REQUEST).freeze()
    host = Host(di)

    async def handle(label: str) -> str:
        entered = host.ascope()
        frame = await entered.__aenter__()
        try:
            frame.provide(REQUEST, label)
            return await hosted_container().aresolve(REQUEST)
        finally:
            await entered.__aexit__(None, None, None)

    assert sorted(await asyncio.gather(handle('a'), handle('b'))) == ['a', 'b']


def test_a_scope_entered_by_hand_publishes_and_unpublishes() -> None:
    di = Container().freeze()
    entered = Host(di).scope()
    _ = entered.__enter__()

    assert hosted_container() is di

    entered.__exit__(None, None, None)

    assert optional_hosted_container() is None


def test_a_host_in_another_thread_does_not_leak_into_this_one() -> None:
    di = Container().freeze()
    seen: list[object] = []

    def run() -> None:
        with Host(di).activated():
            seen.append(hosted_container())

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert seen == [di]
    assert optional_hosted_container() is None
