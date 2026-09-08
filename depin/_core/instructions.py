"""Linear immutable instructions for synchronous resolution."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from depin._core.call_contracts import sync_positional_factory
from depin._core.scope import Scope
from depin._core.spec import Ident, ProviderShape, ProviderSpec, ResolutionPlan, fmt_key
from depin._core.teardown import SyncCMTeardown, SyncGenTeardown, Teardown
from depin._core.typeguards import as_class, as_factory, as_sync_context_manager, as_sync_iterator
from depin.errors import InvalidProviderError


@dataclass(frozen=True, slots=True)
class ResolvedKeyword:
    name: str
    position: int


@dataclass(frozen=True, slots=True)
class DefaultKeyword:
    name: str


@dataclass(frozen=True, slots=True)
class OptionalKeyword:
    name: str


type KeywordSlot = ResolvedKeyword | DefaultKeyword | OptionalKeyword


class InstructionStart(Protocol):
    @property
    def ready(self) -> bool: ...

    @property
    def value(self) -> object: ...


@dataclass(frozen=True, slots=True)
class InstructionReady:
    value: object

    @property
    def ready(self) -> bool:
        return True


class InstructionRuntime(Protocol):
    def publish(self, claim: object, value: object) -> None: ...

    def abort(self, claim: object) -> None: ...

    def read_frame(self, ident: Ident) -> object: ...

    def register_teardown(self, scope: Scope, record: Teardown) -> None: ...


class SyncInstructionRuntime(InstructionRuntime, Protocol):
    def begin(self, scope: Scope, ident: Ident, claims: list[object | None]) -> InstructionStart: ...


@dataclass(frozen=True, slots=True)
class Operation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    ident: Ident
    scope: Scope = Scope.TRANSIENT


@dataclass(frozen=True, slots=True)
class KeywordOperation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    keywords: tuple[KeywordSlot, ...]
    ident: Ident
    scope: Scope = Scope.TRANSIENT


@dataclass(frozen=True, slots=True)
class AliasOperation:
    dependencies: tuple[int, ...]
    ident: Ident
    scope: Scope = Scope.TRANSIENT


@dataclass(frozen=True, slots=True)
class CollectionOperation:
    dependencies: tuple[int, ...]
    ident: Ident
    scope: Scope = Scope.TRANSIENT


@dataclass(frozen=True, slots=True)
class ValueOperation:
    value: object
    dependencies: tuple[int, ...]
    ident: Ident
    scope: Scope


@dataclass(frozen=True, slots=True)
class FrameOperation:
    dependencies: tuple[int, ...]
    ident: Ident
    scope: Scope


@dataclass(frozen=True, slots=True)
class GeneratorOperation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    keywords: tuple[KeywordSlot, ...]
    ident: Ident
    scope: Scope


@dataclass(frozen=True, slots=True)
class ContextManagerOperation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    keywords: tuple[KeywordSlot, ...]
    ident: Ident
    scope: Scope


type SyncOperation = (
    Operation
    | KeywordOperation
    | AliasOperation
    | CollectionOperation
    | ValueOperation
    | FrameOperation
    | GeneratorOperation
    | ContextManagerOperation
)
type StructuredOperation = (
    KeywordOperation
    | AliasOperation
    | CollectionOperation
    | ValueOperation
    | FrameOperation
    | GeneratorOperation
    | ContextManagerOperation
)


@dataclass(frozen=True, slots=True)
class SyncInstructionProgram:
    operations: tuple[SyncOperation, ...]
    roots: Mapping[Ident, int]
    frame_sensitive: frozenset[Ident] = frozenset()

    def supports(self, ident: Ident, *, frame_active: bool = False) -> bool:
        return ident in self.roots and (not frame_active or ident not in self.frame_sensitive)

    def resolve(self, ident: Ident, runtime: SyncInstructionRuntime | None = None) -> object:
        root = self.roots.get(ident)
        if root is None:
            tag = f' with tag {ident[1]!r}' if ident[1] is not None else ''
            raise InvalidProviderError(
                f'{fmt_key(ident[0])}{tag} has no synchronous instruction program; use the interpreted path'
            )
        operation_count = len(self.operations)
        if root < 0 or root >= operation_count:
            raise InvalidProviderError(f'invalid operation slot {root} in synchronous instruction program')

        claims: list[object | None] = []
        values: list[object] = []

        try:
            root_start = _start(self.operations[root], runtime, claims)
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
                            f'invalid dependency slot {dependency_index} in synchronous instruction program'
                            f'{self._chain(operation_stack)}'
                        )
                    dependency_stack[-1] = dependency_position + 1
                    started = _start(self.operations[dependency_index], runtime, claims)
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


def _start(
    operation: SyncOperation, runtime: SyncInstructionRuntime | None, claims: list[object | None]
) -> InstructionStart | None:
    if operation.scope is Scope.TRANSIENT:
        claims.append(None)
        return None
    if runtime is None:
        raise InvalidProviderError(
            f'{render_ident(operation.ident)} requires a cache runtime for synchronous instructions'
        )
    return runtime.begin(operation.scope, operation.ident, claims)


def invoke_structured(
    operation: StructuredOperation, parameters: list[object], runtime: InstructionRuntime | None
) -> object:
    match operation:
        case KeywordOperation(factory=factory, keywords=keywords, ident=ident):
            return factory(**keyword_arguments(keywords, ident, parameters))
        case AliasOperation(ident=ident):
            if len(parameters) != 1:
                raise InvalidProviderError(
                    f'alias instruction for {render_ident(ident)} requires exactly one dependency'
                )
            return parameters[0]
        case CollectionOperation():
            return list(parameters)
        case ValueOperation(value=value):
            return value
        case FrameOperation(ident=ident):
            if runtime is None:
                raise InvalidProviderError(
                    f'{render_ident(ident)} requires a frame runtime for synchronous instructions'
                )
            return runtime.read_frame(ident)
        case GeneratorOperation(factory=factory, keywords=keywords, ident=ident, scope=scope):
            if runtime is None:
                raise InvalidProviderError(
                    f'{render_ident(ident)} requires a resource runtime for synchronous instructions'
                )
            gen = as_sync_iterator(factory(**keyword_arguments(keywords, ident, parameters)), ident[0])
            value = next(gen)
            runtime.register_teardown(scope, SyncGenTeardown(gen))
            return value
        case ContextManagerOperation(factory=factory, keywords=keywords, ident=ident, scope=scope):
            if runtime is None:
                raise InvalidProviderError(
                    f'{render_ident(ident)} requires a resource runtime for synchronous instructions'
                )
            cm = as_sync_context_manager(factory(**keyword_arguments(keywords, ident, parameters)), ident[0])
            value = cm.__enter__()
            runtime.register_teardown(scope, SyncCMTeardown(cm))
            return value


def keyword_arguments(keywords: tuple[KeywordSlot, ...], ident: Ident, parameters: list[object]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    for keyword in keywords:
        match keyword:
            case ResolvedKeyword(name=name, position=position):
                if position < 0 or position >= len(parameters):
                    raise InvalidProviderError(
                        f'invalid parameter slot {position} in synchronous instruction program '
                        f'while resolving {render_ident(ident)}'
                    )
                kwargs[name] = parameters[position]
            case OptionalKeyword(name=name):
                kwargs[name] = None
            case DefaultKeyword():
                continue
    return kwargs


def compile_sync_instructions(plan: ResolutionPlan) -> SyncInstructionProgram:
    operations: list[SyncOperation] = []
    roots: dict[Ident, int] = {}
    frame_sensitive: set[Ident] = set()

    for spec in plan.order:
        if spec.needs_async:
            continue

        compiled = compile_operation(spec, plan, roots)
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

    return SyncInstructionProgram(tuple(operations), MappingProxyType(roots), frozenset(frame_sensitive))


def compile_operation(
    spec: ProviderSpec, plan: ResolutionPlan, roots: dict[Ident, int]
) -> tuple[SyncOperation, bool] | None:
    ident = (spec.key, spec.tag)
    positional = sync_positional_factory(spec)
    if positional is not None:
        if not spec.params:
            return Operation(positional, (), ident, spec.scope), False
        if len(spec.params) == 1:
            only = spec.params[0]
            dependency = roots.get((only.key, only.tag))
            if dependency is not None:
                return Operation(positional, (dependency,), ident, spec.scope), False
        else:
            positional_dependencies: list[int] = []
            for param in spec.params:
                dependency = roots.get((param.key, param.tag))
                if dependency is None:
                    break
                positional_dependencies.append(dependency)
            else:
                return Operation(positional, tuple(positional_dependencies), ident, spec.scope), False

    compiled_arguments = compile_keyword_slots(spec, plan, roots)
    if compiled_arguments is None:
        return None
    dependencies, keywords, reads_frame = compiled_arguments

    if spec.shape is ProviderShape.FUNCTION:
        return (
            KeywordOperation(as_factory(spec.source, spec.key), dependencies, keywords, ident, spec.scope),
            reads_frame,
        )
    if spec.shape is ProviderShape.CLASS:
        return KeywordOperation(as_class(spec.source, spec.key), dependencies, keywords, ident, spec.scope), reads_frame
    if spec.shape is ProviderShape.ALIAS:
        return AliasOperation(dependencies, ident, spec.scope), reads_frame
    if spec.shape is ProviderShape.COLLECTION:
        return CollectionOperation(dependencies, ident, spec.scope), reads_frame
    if spec.shape is ProviderShape.VALUE:
        return ValueOperation(spec.source, dependencies, ident, spec.scope), reads_frame
    if spec.shape is ProviderShape.FRAME:
        return FrameOperation(dependencies, ident, spec.scope), reads_frame
    if spec.shape is ProviderShape.GENERATOR:
        return (
            GeneratorOperation(as_factory(spec.source, spec.key), dependencies, keywords, ident, spec.scope),
            reads_frame,
        )
    if spec.shape is ProviderShape.CONTEXT_MANAGER:
        return (
            ContextManagerOperation(as_factory(spec.source, spec.key), dependencies, keywords, ident, spec.scope),
            reads_frame,
        )
    return None


def compile_keyword_slots(
    spec: ProviderSpec, plan: ResolutionPlan, roots: dict[Ident, int]
) -> tuple[tuple[int, ...], tuple[KeywordSlot, ...], bool] | None:
    dependencies: list[int] = []
    keywords: list[KeywordSlot] = []
    reads_frame = False

    for param in spec.params:
        dependency_ident = (param.key, param.tag)
        dependency = roots.get(dependency_ident)
        if dependency is not None:
            keywords.append(ResolvedKeyword(param.name, len(dependencies)))
            dependencies.append(dependency)
        elif dependency_ident in plan.by_key:
            return None
        elif param.has_default:
            keywords.append(DefaultKeyword(param.name))
            reads_frame = True
        elif param.optional:
            keywords.append(OptionalKeyword(param.name))
            reads_frame = True
        else:
            return None

    return tuple(dependencies), tuple(keywords), reads_frame


def render_ident(ident: Ident) -> str:
    tag = f' (tag={ident[1]!r})' if ident[1] is not None else ''
    return f'{fmt_key(ident[0])}{tag}'


EMPTY_SYNC_INSTRUCTION_PROGRAM = SyncInstructionProgram((), MappingProxyType({}))
