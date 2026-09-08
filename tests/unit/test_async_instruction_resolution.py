import asyncio
import contextlib
from collections.abc import AsyncGenerator
from types import MappingProxyType

import pytest

from depin._core import async_instructions as async_instructions_module
from depin._core import frozen as frozen_module
from depin._core.async_instructions import AsyncInstructionProgram, compile_async_instructions
from depin._core.container import Container
from depin._core.instructions import InstructionReady, InstructionStart, Operation
from depin._core.markers import Token
from depin._core.scope import Scope
from depin._core.spec import Ident, ParamSpec, ProviderShape, ProviderSpec, ResolutionPlan
from depin._core.teardown import Teardown
from depin.errors import InvalidProviderError


class _ReadyAsyncRuntime:
    async def begin(self, scope: Scope, ident: Ident, claims: list[object | None]) -> InstructionStart:
        del scope, ident, claims
        return InstructionReady('cached')

    def publish(self, claim: object, value: object) -> None:
        del claim, value

    def abort(self, claim: object) -> None:
        del claim

    def read_frame(self, ident: Ident) -> object:
        del ident
        return object()

    def register_teardown(self, scope: Scope, record: Teardown) -> None:
        del scope, record


@pytest.mark.asyncio
async def test_async_program_rejects_a_missing_tagged_root() -> None:
    program = AsyncInstructionProgram((), MappingProxyType({}))

    with pytest.raises(InvalidProviderError, match=r"with tag 'missing'.*has no asynchronous instruction program"):
        await program.resolve((str, 'missing'))


@pytest.mark.asyncio
async def test_async_program_rejects_a_malformed_operation_slot() -> None:
    program = AsyncInstructionProgram((), MappingProxyType({(str, None): 1}))

    with pytest.raises(InvalidProviderError, match='invalid operation slot 1'):
        await program.resolve((str, None))


@pytest.mark.asyncio
async def test_async_program_rejects_a_malformed_dependency_slot_with_its_chain() -> None:
    operation = Operation(lambda: object(), (1,), (str, None))
    program = AsyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(
        InvalidProviderError, match='invalid dependency slot 1 in asynchronous instruction program while resolving str'
    ):
        await program.resolve((str, None))


@pytest.mark.asyncio
async def test_async_program_invokes_sync_operations_with_multiple_dependencies() -> None:
    def pair(first: object, second: object) -> tuple[object, object]:
        return first, second

    left = Operation(lambda: 'left', (), (str, 'left'))
    right = Operation(lambda: 'right', (), (str, 'right'))
    root = Operation(pair, (0, 1), (tuple[str, str], None))
    program = AsyncInstructionProgram((left, right, root), MappingProxyType({(tuple[str, str], None): 2}))

    assert await program.resolve((tuple[str, str], None)) == ('left', 'right')


@pytest.mark.asyncio
async def test_async_program_returns_a_ready_cached_instruction() -> None:
    def unexpected() -> object:
        raise AssertionError('cached async instruction called its factory')

    operation = Operation(unexpected, (), (str, None), Scope.SINGLETON)
    program = AsyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    assert await program.resolve((str, None), _ReadyAsyncRuntime()) == 'cached'


@pytest.mark.asyncio
async def test_cached_async_instruction_requires_a_runtime() -> None:
    operation = Operation(lambda: object(), (), (str, None), Scope.SINGLETON)
    program = AsyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(InvalidProviderError, match='requires a cache runtime'):
        await program.resolve((str, None))


@pytest.mark.asyncio
async def test_async_program_rejects_a_claim_that_completes_without_a_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def start_with_claim(
        _operation: object,
        _runtime: object,
        claims: list[object | None],
    ) -> None:
        claims.append(object())

    monkeypatch.setattr(async_instructions_module, '_start', start_with_claim)
    operation = Operation(lambda: object(), (), (str, None))
    program = AsyncInstructionProgram((operation,), MappingProxyType({(str, None): 0}))

    with pytest.raises(InvalidProviderError, match='cached instruction completed without a runtime'):
        await program.resolve((str, None))


def test_an_empty_async_operation_chain_has_no_diagnostic_suffix() -> None:
    program = AsyncInstructionProgram((), MappingProxyType({}))
    render_chain = object.__getattribute__(program, '_chain')
    if not callable(render_chain):
        raise AssertionError('async instruction program has no chain renderer')

    assert render_chain([]) == ''


def test_async_compiler_skips_a_root_whose_dependency_has_no_operation() -> None:
    async def make(value: int) -> str:
        return str(value)

    parameter = ParamSpec(name='value', key=int, tag=None, has_default=False, default=None)
    spec = ProviderSpec(
        key=str,
        tag=None,
        source=make,
        scope=Scope.TRANSIENT,
        shape=ProviderShape.ASYNC_FUNCTION,
        needs_async=True,
        params=(parameter,),
    )
    by_key: dict[Ident, ProviderSpec] = {(str, None): spec, (int, None): spec}
    plan = ResolutionPlan((spec,), MappingProxyType(by_key))

    assert not compile_async_instructions(plan).supports((str, None))


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
    assert frozen.resolve(Token[int]('shared-instruction-255')) == 255
    sync_program = object.__getattribute__(frozen, '_sync_instructions')
    async_program = object.__getattribute__(frozen, '_async_instructions')

    assert async_program.operations is sync_program.operations
    assert async_program.roots is sync_program.roots
    assert async_program.frame_sensitive is sync_program.frame_sensitive
