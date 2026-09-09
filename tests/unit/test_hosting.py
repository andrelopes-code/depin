"""The integration contract: publishing a container, scoping a unit of work, reading it back."""

import asyncio
import dataclasses
import threading
from collections.abc import AsyncGenerator, AsyncIterator, Generator

import pytest

from depin import Container, FrozenContainer, Scope, Token
from depin._core.hosting import (
    CONTRACT_VERSION,
    ContractVersion,
    Host,
    hosted_container,
    optional_hosted_container,
)
from depin._core.lazy_scope import LazyScopeSeed, LazyScopeState
from depin._core.lazy_scope import lazy_host as _lazy_host
from depin._core.lazy_scope import provide_lazy_seed as _provide_lazy_seed
from depin._core.scope import ScopeFrame
from depin.errors import ContainerNotBoundError, OutsideScopeError

REQUEST = Token[str]('request')


@pytest.mark.asyncio
async def test_lazy_host_does_not_open_a_frame_for_a_singleton() -> None:
    class Service: ...

    container = Container().bind(Service, scope=Scope.SINGLETON).freeze()
    opened: list[ScopeFrame] = []

    async with _lazy_host(container, on_open=opened.append):
        assert await hosted_container().aresolve(Service) is await container.aresolve(Service)

    assert opened == []


@pytest.mark.asyncio
async def test_lazy_host_opens_one_frame_on_first_scoped_resolution() -> None:
    class Service: ...

    container = Container().bind(Service, scope=Scope.SCOPED).freeze()
    opened: list[ScopeFrame] = []

    async with _lazy_host(container, on_open=opened.append):
        first = await hosted_container().aresolve(Service)
        second = await hosted_container().aresolve(Service)

    assert first is second
    assert len(opened) == 1


@pytest.mark.asyncio
async def test_lazy_seed_is_applied_only_when_its_key_is_read() -> None:
    request = Token[str]('request')
    built: list[str] = []
    container = Container().scope_value(request).freeze()

    def build_request() -> str:
        built.append('r-1')
        return 'r-1'

    async with _lazy_host(container, seeds=(LazyScopeSeed(request, build_request),)):
        assert built == []
        assert await hosted_container().aresolve(request) == 'r-1'

    assert built == ['r-1']


@pytest.mark.asyncio
async def test_lazy_scope_retains_body_and_teardown_failures() -> None:
    events: list[str] = []

    async def resource() -> AsyncIterator[str]:
        try:
            yield 'value'
        finally:
            events.append('closed')
            raise LookupError('close failed')

    container = Container().bind(resource, scope=Scope.SCOPED).freeze()

    async def fail_after_construction() -> None:
        async with _lazy_host(container):
            assert await hosted_container().aresolve(str) == 'value'
            raise ValueError('body failed')

    with pytest.raises(ExceptionGroup) as raised:
        await fail_after_construction()

    assert events == ['closed']
    assert {type(error) for error in raised.value.exceptions} == {ValueError, LookupError}


@pytest.mark.asyncio
async def test_lazy_host_cancellation_drains_one_constructed_resource() -> None:
    events: list[str] = []
    constructed = asyncio.Event()
    never = asyncio.Event()

    async def resource() -> AsyncIterator[str]:
        try:
            yield 'value'
        finally:
            events.append('closed')

    container = Container().bind(resource, scope=Scope.SCOPED).freeze()

    async def resolve_then_wait() -> None:
        async with _lazy_host(container):
            assert await hosted_container().aresolve(str) == 'value'
            constructed.set()
            await never.wait()

    task = asyncio.create_task(resolve_then_wait())
    await constructed.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert events == ['closed']
    assert optional_hosted_container() is None


@pytest.mark.asyncio
async def test_concurrent_lazy_hosts_isolate_seeds_and_restore_enclosing_host() -> None:
    request = Token[str]('request')

    class Service: ...

    container = Container().scope_value(request).bind(Service, scope=Scope.SCOPED).freeze()
    outer = Container().freeze()
    entered_a = asyncio.Event()
    entered_b = asyncio.Event()
    release = asyncio.Event()

    async def request_scope(label: str, entered: asyncio.Event) -> tuple[str, bool]:
        async with _lazy_host(container, seeds=(LazyScopeSeed(request, lambda: label),)):
            first = await hosted_container().aresolve(Service)
            value = await hosted_container().aresolve(request)
            entered.set()
            await release.wait()
            second = await hosted_container().aresolve(Service)
            return value, first is second

    with Host(outer).activated():
        first_task = asyncio.create_task(request_scope('a', entered_a))
        second_task = asyncio.create_task(request_scope('b', entered_b))
        await entered_a.wait()
        await entered_b.wait()
        release.set()
        first, second = await asyncio.gather(first_task, second_task)
        assert hosted_container() is outer

    assert {first, second} == {('a', True), ('b', True)}


@pytest.mark.asyncio
async def test_child_first_lazy_activation_drains_from_the_parent_context() -> None:
    events: list[str] = []

    async def resource() -> AsyncIterator[str]:
        try:
            yield 'value'
        finally:
            events.append('closed')

    container = Container().bind(resource, scope=Scope.SCOPED).freeze()
    outer = Container().freeze()

    async def resolve_in_child() -> None:
        assert await hosted_container().aresolve(str) == 'value'

    with Host(outer).activated():
        async with _lazy_host(container):
            await asyncio.create_task(resolve_in_child())
        assert hosted_container() is outer

    assert events == ['closed']
    assert container.scope_activity() == (0, 0)
    assert optional_hosted_container() is None


@pytest.mark.asyncio
async def test_child_first_lazy_activation_preserves_body_and_teardown_failures() -> None:
    events: list[str] = []

    async def resource() -> AsyncIterator[str]:
        try:
            yield 'value'
        finally:
            events.append('closed')
            raise LookupError('close failed')

    container = Container().bind(resource, scope=Scope.SCOPED).freeze()

    async def resolve_in_child() -> None:
        assert await hosted_container().aresolve(str) == 'value'

    async def fail_after_child_activation() -> None:
        async with _lazy_host(container):
            await asyncio.create_task(resolve_in_child())
            raise ValueError('body failed')

    with pytest.raises(ExceptionGroup) as raised:
        await fail_after_child_activation()

    assert events == ['closed']
    assert {type(error) for error in raised.value.exceptions} == {ValueError, LookupError}
    assert container.scope_activity() == (0, 0)


@pytest.mark.asyncio
async def test_inherited_child_cannot_open_a_drained_lazy_scope() -> None:
    class Service: ...

    container = Container().bind(Service, scope=Scope.SCOPED).freeze()
    parent_exited = asyncio.Event()

    async def resolve_after_parent_exit() -> None:
        await parent_exited.wait()
        await hosted_container().aresolve(Service)

    async with _lazy_host(container):
        child = asyncio.create_task(resolve_after_parent_exit())

    parent_exited.set()
    with pytest.raises(OutsideScopeError):
        await child


@pytest.mark.asyncio
async def test_providing_a_lazy_seed_registers_it_without_opening_or_building() -> None:
    request = Token[str]('request')
    built: list[str] = []
    opened: list[ScopeFrame] = []
    container = Container().scope_value(request).freeze()

    def build_request() -> str:
        built.append('request')
        return 'request'

    async with _lazy_host(container, on_open=opened.append):
        _provide_lazy_seed(LazyScopeSeed(request, build_request))
        assert built == []
        assert opened == []
        assert await hosted_container().aresolve(request) == 'request'

    assert built == ['request']
    assert len(opened) == 1


@pytest.mark.asyncio
async def test_lazy_state_activates_one_frame_across_threads() -> None:
    class Service: ...

    container = Container().bind(Service, scope=Scope.SCOPED).freeze()
    state = LazyScopeState(container, (), None)
    barrier = threading.Barrier(3)
    frames: list[ScopeFrame] = []
    lock = threading.Lock()

    def activate() -> None:
        barrier.wait()
        frame = state.frame()
        with lock:
            frames.append(frame)

    first = threading.Thread(target=activate)
    second = threading.Thread(target=activate)
    first.start()
    second.start()
    barrier.wait()
    first.join()
    second.join()

    await state.aclose(None)

    assert len(frames) == 2
    assert frames[0] is frames[1]
    assert container.scope_activity() == (0, 0)


def test_the_contract_version_is_one_zero() -> None:
    assert ContractVersion(1, 0) == CONTRACT_VERSION


def test_a_contract_version_renders_as_major_dot_minor() -> None:
    assert str(ContractVersion(2, 7)) == '2.7'


def test_contract_versions_order_by_major_then_minor() -> None:
    assert ContractVersion(1, 0) < ContractVersion(1, 1) < ContractVersion(2, 0)


def test_a_contract_version_is_immutable() -> None:
    version = ContractVersion(1, 0)
    # Indirect attribute name: a direct `version.major = ...` is a static error on a
    # frozen dataclass, and setattr with a literal name trips ruff B010.
    field = 'major'
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(version, field, 9)


def test_a_contract_version_has_no_dict() -> None:
    assert not hasattr(ContractVersion(1, 0), '__dict__')


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

    def fail() -> None:
        raise RuntimeError('boom')

    with pytest.raises(RuntimeError), Host(di).activated():
        fail()

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


@pytest.mark.asyncio
async def test_ascope_drains_its_teardowns_before_unpublishing() -> None:
    seen: list[str | None] = []

    class Session: ...

    async def open_session() -> AsyncGenerator[Session]:
        yield Session()
        seen.append('hosted' if optional_hosted_container() is not None else None)

    di = Container().bind(open_session, scope=Scope.SCOPED).freeze()

    async with Host(di).ascope():
        _ = await di.aresolve(Session)

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

    def fail() -> None:
        raise RuntimeError('boom')

    with pytest.raises(RuntimeError):
        async with Host(di).ascope():
            fail()

    assert optional_hosted_container() is None


@pytest.mark.asyncio
async def test_concurrent_ascopes_do_not_see_each_others_seeds() -> None:
    di_a = Container().scope_value(REQUEST).freeze()
    di_b = Container().scope_value(REQUEST).freeze()
    a_published = asyncio.Event()
    b_published = asyncio.Event()
    a_checked = asyncio.Event()

    async def handle_a() -> tuple[bool, str]:
        async with Host(di_a).ascope() as frame:
            frame.provide(REQUEST, 'a')
            a_published.set()
            await b_published.wait()
            container = hosted_container()
            is_own = container is di_a
            value = await container.aresolve(REQUEST)
            a_checked.set()
        return is_own, value

    async def handle_b() -> tuple[bool, str]:
        async with Host(di_b).ascope() as frame:
            frame.provide(REQUEST, 'b')
            b_published.set()
            await a_checked.wait()
            container = hosted_container()
            is_own = container is di_b
            value = await container.aresolve(REQUEST)
        return is_own, value

    result_a, result_b = await asyncio.gather(handle_a(), handle_b())

    assert result_a == (True, 'a')
    assert result_b == (True, 'b')


def test_a_scope_entered_by_hand_publishes_and_unpublishes() -> None:
    di = Container().freeze()
    entered = Host(di).scope()
    _ = entered.__enter__()

    assert hosted_container() is di

    entered.__exit__(None, None, None)

    assert optional_hosted_container() is None


def test_a_host_in_another_thread_does_not_leak_into_this_one() -> None:
    di_a = Container().freeze()
    di_b = Container().freeze()
    barrier = threading.Barrier(2)
    results: list[bool] = []

    def run(di: FrozenContainer) -> None:
        with Host(di).activated():
            barrier.wait()
            results.append(hosted_container() is di)

    thread_a = threading.Thread(target=run, args=(di_a,))
    thread_b = threading.Thread(target=run, args=(di_b,))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    assert results == [True, True]
    assert optional_hosted_container() is None


def test_nested_scopes_from_different_containers_isolate_their_caches() -> None:
    """A hosted container can only observe scope frames that it owns."""

    class Label:
        def __init__(self, text: str) -> None:
            self.text = text

    def outer_label() -> Label:
        return Label('outer')

    def inner_label() -> Label:
        return Label('inner')

    di_outer = Container().bind(outer_label, provides=Label, scope=Scope.SCOPED).freeze()
    di_inner = Container().bind(inner_label, provides=Label, scope=Scope.SCOPED).freeze()

    with Host(di_outer).scope():
        assert hosted_container().resolve(Label).text == 'outer'
        with Host(di_inner).scope():
            assert hosted_container() is di_inner
            assert hosted_container().resolve(Label).text == 'inner'
        assert hosted_container().resolve(Label).text == 'outer'

    with Host(di_inner).scope():
        assert hosted_container().resolve(Label).text == 'inner'
