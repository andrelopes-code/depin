"""Linear immutable instructions for synchronous transient resolution."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from depin._core.call_contracts import sync_positional_factory
from depin._core.scope import Scope
from depin._core.spec import Ident, ProviderShape, ProviderSpec, ResolutionPlan, fmt_key
from depin._core.typeguards import as_class, as_factory
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


@dataclass(frozen=True, slots=True)
class Operation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    ident: Ident


@dataclass(frozen=True, slots=True)
class KeywordOperation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]
    keywords: tuple[KeywordSlot, ...]
    ident: Ident


@dataclass(frozen=True, slots=True)
class AliasOperation:
    dependencies: tuple[int, ...]
    ident: Ident


@dataclass(frozen=True, slots=True)
class CollectionOperation:
    dependencies: tuple[int, ...]
    ident: Ident


type SyncOperation = Operation | KeywordOperation | AliasOperation | CollectionOperation
type StructuredOperation = KeywordOperation | AliasOperation | CollectionOperation


@dataclass(frozen=True, slots=True)
class SyncTransientProgram:
    operations: tuple[SyncOperation, ...]
    roots: Mapping[Ident, int]
    frame_sensitive: frozenset[Ident] = frozenset()

    def supports(self, ident: Ident, *, frame_active: bool = False) -> bool:
        return ident in self.roots and (not frame_active or ident not in self.frame_sensitive)

    def resolve(self, ident: Ident) -> object:
        root = self.roots.get(ident)
        if root is None:
            tag = f' with tag {ident[1]!r}' if ident[1] is not None else ''
            raise InvalidProviderError(
                f'{fmt_key(ident[0])}{tag} has no synchronous transient instruction program; use the interpreted path'
            )

        operation_stack = [root]
        dependency_stack = [0]
        values: list[object] = []
        operation_count = len(self.operations)

        while operation_stack:
            operation_index = operation_stack[-1]
            if operation_index < 0 or operation_index >= operation_count:
                raise InvalidProviderError(
                    f'invalid operation slot {operation_index} in synchronous transient program'
                    f'{self._chain(operation_stack[:-1])}'
                )
            operation = self.operations[operation_index]
            dependency_position = dependency_stack[-1]
            if dependency_position < len(operation.dependencies):
                dependency_index = operation.dependencies[dependency_position]
                if dependency_index < 0 or dependency_index >= operation_count:
                    raise InvalidProviderError(
                        f'invalid dependency slot {dependency_index} in synchronous transient program'
                        f'{self._chain(operation_stack)}'
                    )
                dependency_stack[-1] = dependency_position + 1
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
                values.append(resolved)
                continue

            first_parameter = len(values) - parameter_count
            parameters = values[first_parameter:] if parameter_count else []
            if parameter_count:
                del values[first_parameter:]
            values.append(_invoke(operation, parameters))

        return values[0]

    def _chain(self, operation_stack: list[int]) -> str:
        idents = [self.operations[index].ident for index in operation_stack if 0 <= index < len(self.operations)]
        if not idents:
            return ''
        rendered = ' -> '.join(_render_ident(ident) for ident in idents)
        return f' while resolving {rendered}'


def _invoke(operation: StructuredOperation, parameters: list[object]) -> object:
    match operation:
        case KeywordOperation(factory=factory, keywords=keywords, ident=ident):
            kwargs: dict[str, object] = {}
            for keyword in keywords:
                match keyword:
                    case ResolvedKeyword(name=name, position=position):
                        if position < 0 or position >= len(parameters):
                            raise InvalidProviderError(
                                f'invalid parameter slot {position} in synchronous transient program '
                                f'while resolving {_render_ident(ident)}'
                            )
                        kwargs[name] = parameters[position]
                    case OptionalKeyword(name=name):
                        kwargs[name] = None
                    case DefaultKeyword():
                        continue
            return factory(**kwargs)
        case AliasOperation(ident=ident):
            if len(parameters) != 1:
                raise InvalidProviderError(
                    f'alias instruction for {_render_ident(ident)} requires exactly one dependency'
                )
            return parameters[0]
        case CollectionOperation():
            return list(parameters)


def compile_sync_transient_instructions(plan: ResolutionPlan) -> SyncTransientProgram:
    operations: list[SyncOperation] = []
    roots: dict[Ident, int] = {}
    frame_sensitive: set[Ident] = set()

    for spec in plan.order:
        if spec.scope is not Scope.TRANSIENT or spec.needs_async:
            continue

        compiled = _compile_operation(spec, plan, roots)
        if compiled is None:
            continue
        operation, reads_frame = compiled
        ident = (spec.key, spec.tag)
        roots[ident] = len(operations)
        operations.append(operation)
        if reads_frame or any(operations[index].ident in frame_sensitive for index in operation.dependencies):
            frame_sensitive.add(ident)

    return SyncTransientProgram(tuple(operations), MappingProxyType(roots), frozenset(frame_sensitive))


def _compile_operation(
    spec: ProviderSpec, plan: ResolutionPlan, roots: dict[Ident, int]
) -> tuple[SyncOperation, bool] | None:
    compiled_arguments = _compile_keyword_slots(spec, plan, roots)
    if compiled_arguments is None:
        return None
    dependencies, keywords, reads_frame = compiled_arguments
    ident = (spec.key, spec.tag)

    if spec.shape is ProviderShape.FUNCTION:
        positional = sync_positional_factory(spec)
        if positional is not None and not reads_frame:
            return Operation(positional, dependencies, ident), False
        return KeywordOperation(as_factory(spec.source, spec.key), dependencies, keywords, ident), reads_frame
    if spec.shape is ProviderShape.CLASS:
        return KeywordOperation(as_class(spec.source, spec.key), dependencies, keywords, ident), reads_frame
    if spec.shape is ProviderShape.ALIAS:
        return AliasOperation(dependencies, ident), reads_frame
    if spec.shape is ProviderShape.COLLECTION:
        return CollectionOperation(dependencies, ident), reads_frame
    return None


def _compile_keyword_slots(
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


def _render_ident(ident: Ident) -> str:
    tag = f' (tag={ident[1]!r})' if ident[1] is not None else ''
    return f'{fmt_key(ident[0])}{tag}'


EMPTY_SYNC_TRANSIENT_PROGRAM = SyncTransientProgram((), MappingProxyType({}))
