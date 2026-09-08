"""Linear immutable instructions for asynchronous resolution."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from depin._core.instructions import (
    InstructionRuntime,
    InstructionStart,
    KeywordSlot,
    Operation,
    SyncOperation,
    compile_keyword_slots,
    compile_operation,
    invoke_structured,
    keyword_arguments,
    render_ident,
)
from depin._core.scope import Scope
from depin._core.spec import Ident, ProviderShape, ProviderSpec, ResolutionPlan, fmt_key
from depin._core.teardown import AsyncCMTeardown, AsyncGenTeardown
from depin._core.typeguards import as_async_context_manager, as_async_iterator, as_awaitable, as_factory
from depin.errors import InvalidProviderError


class AsyncInstructionRuntime(InstructionRuntime, Protocol):
    async def begin(self, scope: Scope, ident: Ident, claims: list[object | None]) -> InstructionStart: ...


@dataclass(frozen=True, slots=True)
class AsyncFunctionOperation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    keywords: tuple[KeywordSlot, ...]
    ident: Ident
    scope: Scope


@dataclass(frozen=True, slots=True)
class AsyncGeneratorOperation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    keywords: tuple[KeywordSlot, ...]
    ident: Ident
    scope: Scope


@dataclass(frozen=True, slots=True)
class AsyncContextManagerOperation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    keywords: tuple[KeywordSlot, ...]
    ident: Ident
    scope: Scope


type NativeAsyncOperation = AsyncFunctionOperation | AsyncGeneratorOperation | AsyncContextManagerOperation
type AsyncOperation = SyncOperation | NativeAsyncOperation


@dataclass(frozen=True, slots=True)
class AsyncInstructionProgram:
    operations: tuple[AsyncOperation, ...]
    roots: Mapping[Ident, int]
    frame_sensitive: frozenset[Ident] = frozenset()

    def supports(self, ident: Ident, *, frame_active: bool = False) -> bool:
        return ident in self.roots and (not frame_active or ident not in self.frame_sensitive)

    async def resolve(self, ident: Ident, runtime: AsyncInstructionRuntime | None = None) -> object:
        root = self.roots.get(ident)
        if root is None:
            tag = f' with tag {ident[1]!r}' if ident[1] is not None else ''
            raise InvalidProviderError(
                f'{fmt_key(ident[0])}{tag} has no asynchronous instruction program; use the interpreted path'
            )
        operation_count = len(self.operations)
        if root < 0 or root >= operation_count:
            raise InvalidProviderError(f'invalid operation slot {root} in asynchronous instruction program')

        claims: list[object | None] = []
        values: list[object] = []

        try:
            root_start = await _start(self.operations[root], runtime, claims)
            if root_start is not None and root_start.ready:
                return root_start.value

            operation_stack = [root]
            dependency_stack = [0]
            while operation_stack:
                operation_index = operation_stack[-1]
                operation = self.operations[operation_index]
                dependency_position = dependency_stack[-1]
                if dependency_position < len(operation.dependencies):
                    dependency_index = operation.dependencies[dependency_position]
                    if dependency_index < 0 or dependency_index >= operation_count:
                        raise InvalidProviderError(
                            f'invalid dependency slot {dependency_index} in asynchronous instruction program'
                            f'{self._chain(operation_stack)}'
                        )
                    dependency_stack[-1] = dependency_position + 1
                    started = await _start(self.operations[dependency_index], runtime, claims)
                    if started is not None and started.ready:
                        values.append(started.value)
                        continue
                    operation_stack.append(dependency_index)
                    dependency_stack.append(0)
                    continue

                operation_stack.pop()
                dependency_stack.pop()
                parameter_count = len(operation.dependencies)
                if isinstance(operation, Operation):
                    if parameter_count == 0:
                        resolved = operation.factory()
                    elif parameter_count == 1:
                        resolved = operation.factory(values.pop())
                    else:
                        first_parameter = len(values) - parameter_count
                        parameters = values[first_parameter:]
                        del values[first_parameter:]
                        resolved = operation.factory(*parameters)
                else:
                    first_parameter = len(values) - parameter_count
                    parameters = values[first_parameter:] if parameter_count else []
                    if parameter_count:
                        del values[first_parameter:]
                    if isinstance(
                        operation, AsyncFunctionOperation | AsyncGeneratorOperation | AsyncContextManagerOperation
                    ):
                        resolved = await _invoke_async(operation, parameters, runtime)
                    else:
                        resolved = invoke_structured(operation, parameters, runtime)

                claim = claims[-1]
                if claim is not None:
                    if runtime is None:
                        raise InvalidProviderError('cached instruction completed without a runtime')
                    runtime.publish(claim, resolved)
                claims.pop()
                values.append(resolved)
        except BaseException:
            if runtime is not None:
                for claim in reversed(claims):
                    if claim is not None:
                        runtime.abort(claim)
            raise

        return values[0]

    def _chain(self, operation_stack: list[int]) -> str:
        idents = [self.operations[index].ident for index in operation_stack if 0 <= index < len(self.operations)]
        if not idents:
            return ''
        rendered = ' -> '.join(render_ident(ident) for ident in idents)
        return f' while resolving {rendered}'


async def _start(
    operation: AsyncOperation,
    runtime: AsyncInstructionRuntime | None,
    claims: list[object | None],
) -> InstructionStart | None:
    if operation.scope is Scope.TRANSIENT:
        claims.append(None)
        return None
    if runtime is None:
        raise InvalidProviderError(
            f'{render_ident(operation.ident)} requires a cache runtime for asynchronous instructions'
        )
    return await runtime.begin(operation.scope, operation.ident, claims)


async def _invoke_async(
    operation: NativeAsyncOperation,
    parameters: list[object],
    runtime: AsyncInstructionRuntime | None,
) -> object:
    if isinstance(operation, AsyncFunctionOperation):
        return await as_awaitable(
            operation.factory(**keyword_arguments(operation.keywords, operation.ident, parameters)),
            operation.ident[0],
        )
    if isinstance(operation, AsyncGeneratorOperation):
        if runtime is None:
            raise InvalidProviderError(
                f'{render_ident(operation.ident)} requires a resource runtime for asynchronous instructions'
            )
        agen = as_async_iterator(
            operation.factory(**keyword_arguments(operation.keywords, operation.ident, parameters)),
            operation.ident[0],
        )
        value = await agen.__anext__()
        runtime.register_teardown(operation.scope, AsyncGenTeardown(agen))
        return value
    if runtime is None:
        raise InvalidProviderError(
            f'{render_ident(operation.ident)} requires a resource runtime for asynchronous instructions'
        )
    acm = as_async_context_manager(
        operation.factory(**keyword_arguments(operation.keywords, operation.ident, parameters)),
        operation.ident[0],
    )
    value = await acm.__aenter__()
    runtime.register_teardown(operation.scope, AsyncCMTeardown(acm))
    return value


def compile_async_instructions(plan: ResolutionPlan) -> AsyncInstructionProgram:
    operations: list[AsyncOperation] = []
    roots: dict[Ident, int] = {}
    frame_sensitive: set[Ident] = set()

    for spec in plan.order:
        compiled = _compile_async_operation(spec, plan, roots)
        if compiled is None:
            continue
        operation, reads_frame = compiled
        ident = (spec.key, spec.tag)
        roots[ident] = len(operations)
        operations.append(operation)
        if reads_frame or (
            frame_sensitive and any(operations[index].ident in frame_sensitive for index in operation.dependencies)
        ):
            frame_sensitive.add(ident)

    return AsyncInstructionProgram(tuple(operations), MappingProxyType(roots), frozenset(frame_sensitive))


def _compile_async_operation(
    spec: ProviderSpec,
    plan: ResolutionPlan,
    roots: dict[Ident, int],
) -> tuple[AsyncOperation, bool] | None:
    if spec.shape not in (
        ProviderShape.ASYNC_FUNCTION,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
    ):
        return compile_operation(spec, plan, roots)

    compiled_arguments = compile_keyword_slots(spec, plan, roots)
    if compiled_arguments is None:
        return None
    dependencies, keywords, reads_frame = compiled_arguments
    ident = (spec.key, spec.tag)
    factory = as_factory(spec.source, spec.key)
    if spec.shape is ProviderShape.ASYNC_FUNCTION:
        return AsyncFunctionOperation(factory, dependencies, keywords, ident, spec.scope), reads_frame
    if spec.shape is ProviderShape.ASYNC_GENERATOR:
        return AsyncGeneratorOperation(factory, dependencies, keywords, ident, spec.scope), reads_frame
    return AsyncContextManagerOperation(factory, dependencies, keywords, ident, spec.scope), reads_frame


def from_sync(
    operations: tuple[SyncOperation, ...],
    roots: Mapping[Ident, int],
    frame_sensitive: frozenset[Ident],
) -> AsyncInstructionProgram:
    return AsyncInstructionProgram(operations, roots, frame_sensitive)


EMPTY_ASYNC_INSTRUCTION_PROGRAM = AsyncInstructionProgram((), MappingProxyType({}))
