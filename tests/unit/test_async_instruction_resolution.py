import asyncio
import contextlib
from collections.abc import AsyncGenerator

import pytest

from depin._core import frozen as frozen_module
from depin._core.container import Container
from depin._core.markers import Token
from depin._core.scope import Scope
from depin._core.spec import ProviderSpec


@pytest.mark.asyncio
async def test_deep_sync_consumer_of_async_dependency_uses_async_instructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = Container()
    for index in range(254):
        container.value(Token[int](f'async-function-padding-{index}'), index)

    async def count() -> int:
        return 7

    def render(value: int) -> str:
        return f'count={value}'

    frozen = container.bind(count, scope=Scope.SINGLETON).bind(render, scope=Scope.TRANSIENT).freeze()

    async def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('deep async function root used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_async_iterative', unexpected_iterative)

    assert await frozen.aresolve(str) == 'count=7'
    assert await frozen.aresolve(str) == 'count=7'


@pytest.mark.asyncio
async def test_shallow_async_singleton_uses_instructions(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result: ...

    async def result() -> Result:
        return Result()

    frozen = Container().bind(result, scope=Scope.SINGLETON).freeze()

    async def unexpected_construct(*_args: object, **_kwargs: object) -> object:
        raise AssertionError('shallow async singleton used construct.asynchronous')

    monkeypatch.setattr('depin._core.frozen.construct.asynchronous', unexpected_construct)

    first = await frozen.aresolve(Result)
    assert await frozen.aresolve(Result) is first


@pytest.mark.asyncio
async def test_deep_async_resources_use_instructions_and_close_in_lifo_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Dependency: ...

    class Resource:
        def __init__(self, dependency: Dependency) -> None:
            self.dependency = dependency

    events: list[str] = []
    dependency_value = Dependency()
    container = Container()
    for index in range(254):
        container.value(Token[int](f'async-resource-padding-{index}'), index)

    async def dependency() -> AsyncGenerator[Dependency]:
        events.append('dependency setup')
        yield dependency_value
        events.append('dependency teardown')

    @contextlib.asynccontextmanager
    async def resource(dependency: Dependency) -> AsyncGenerator[Resource]:
        events.append('resource setup')
        yield Resource(dependency)
        events.append('resource teardown')

    frozen = (
        container.bind(dependency, scope=Scope.SCOPED).bind(resource, provides=Resource, scope=Scope.SCOPED).freeze()
    )

    async def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('deep async resource root used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_async_iterative', unexpected_iterative)

    async with frozen.ascope():
        first = await frozen.aresolve(Resource)
        assert await frozen.aresolve(Resource) is first
        assert first.dependency is dependency_value
        assert events == ['dependency setup', 'resource setup']
    assert events == [
        'dependency setup',
        'resource setup',
        'resource teardown',
        'dependency teardown',
    ]


@pytest.mark.asyncio
async def test_concurrent_async_instruction_claim_builds_a_singleton_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result: ...

    entered = asyncio.Event()
    released = asyncio.Event()
    calls = 0
    container = Container()
    for index in range(255):
        container.value(Token[int](f'async-contention-padding-{index}'), index)

    async def result() -> Result:
        nonlocal calls
        calls += 1
        entered.set()
        await released.wait()
        return Result()

    frozen = container.bind(result, scope=Scope.SINGLETON).freeze()

    async def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('contended async singleton used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_async_iterative', unexpected_iterative)

    first = asyncio.create_task(frozen.aresolve(Result))
    await entered.wait()
    second = asyncio.create_task(frozen.aresolve(Result))
    checkpoint = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(checkpoint.set_result, None)
    await checkpoint
    released.set()

    first_value, second_value = await asyncio.gather(first, second)
    assert first_value is second_value
    assert calls == 1


@pytest.mark.asyncio
async def test_cancelled_async_instruction_owner_releases_its_waiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result: ...

    entered = asyncio.Event()
    attempts = 0
    container = Container()
    for index in range(255):
        container.value(Token[int](f'async-cancellation-padding-{index}'), index)

    async def result() -> Result:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            entered.set()
            await asyncio.Event().wait()
        return Result()

    frozen = container.bind(result, scope=Scope.SINGLETON).freeze()

    async def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('cancelled async singleton used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_async_iterative', unexpected_iterative)

    owner = asyncio.create_task(frozen.aresolve(Result))
    await entered.wait()
    waiter = asyncio.create_task(frozen.aresolve(Result))
    checkpoint = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(checkpoint.set_result, None)
    await checkpoint
    owner.cancel()

    with pytest.raises(asyncio.CancelledError):
        await owner
    recovered = await waiter
    assert await frozen.aresolve(Result) is recovered
    assert attempts == 2


@pytest.mark.asyncio
async def test_active_override_bypasses_async_instructions() -> None:
    tokens = [Token[object](f'async-override-{index}') for index in range(256)]
    original = object()
    replacement = object()
    container = Container()

    async def leaf() -> object:
        return original

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):

        def pass_through(value: object) -> object:
            return value

        pass_through.__annotations__['value'] = tokens[index - 1]
        container.bind(pass_through, provides=token, scope=Scope.TRANSIENT)

    frozen = container.freeze()

    assert await frozen.aresolve(tokens[-1]) is original
    with frozen.override(tokens[0]).using(replacement):
        assert await frozen.aresolve(tokens[-1]) is replacement


@pytest.mark.asyncio
async def test_async_instructions_compose_decorators_aliases_and_collections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Service:
        def __init__(self, labels: tuple[str, ...]) -> None:
            self.labels = labels

    class Alias: ...

    class Element: ...

    class Second: ...

    element_value = Element()
    second_value = Second()
    container = Container()
    for index in range(250):
        container.value(Token[int](f'async-shape-padding-{index}'), index)

    async def service() -> Service:
        return Service(('inner',))

    def decorate(inner: Service, *, suffix: str = 'outer') -> Service:
        return Service((*inner.labels, suffix))

    async def element() -> Element:
        return element_value

    def second() -> Second:
        return second_value

    frozen = (
        container.bind(service, scope=Scope.TRANSIENT)
        .decorate(Service, decorate)
        .bind(element, scope=Scope.TRANSIENT)
        .bind(second, scope=Scope.TRANSIENT)
        .alias(Alias, to=Element)
        .collect(Element, [Alias, Second])
        .freeze()
    )

    async def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('composed async shapes used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_async_iterative', unexpected_iterative)

    decorated = await frozen.aresolve(Service)
    collected = await frozen.aresolve(list[Element])
    assert decorated.labels == ('inner', 'outer')
    assert collected == [element_value, second_value]


def test_sync_only_deep_plan_shares_its_immutable_instructions_with_async_resolution() -> None:
    container = Container()
    for index in range(256):
        container.value(Token[int](f'shared-instruction-{index}'), index)

    frozen = container.freeze()
    sync_program = object.__getattribute__(frozen, '_sync_instructions')
    async_program = object.__getattribute__(frozen, '_async_instructions')

    assert async_program.operations is sync_program.operations
    assert async_program.roots is sync_program.roots
    assert async_program.frame_sensitive is sync_program.frame_sensitive
