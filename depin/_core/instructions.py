"""Linear immutable instructions for synchronous transient resolution."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from depin._core.call_contracts import sync_positional_factory
from depin._core.scope import Scope
from depin._core.spec import Ident, ResolutionPlan, fmt_key
from depin.errors import InvalidProviderError


@dataclass(frozen=True, slots=True)
class Operation:
    factory: Callable[..., object]
    dependencies: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SyncTransientProgram:
    operations: tuple[Operation, ...]
    roots: Mapping[Ident, int]

    def supports(self, ident: Ident) -> bool:
        return ident in self.roots

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
                raise InvalidProviderError(f'invalid operation slot {operation_index} in synchronous transient program')
            operation = self.operations[operation_index]
            dependency_position = dependency_stack[-1]
            if dependency_position < len(operation.dependencies):
                dependency_index = operation.dependencies[dependency_position]
                if dependency_index < 0 or dependency_index >= operation_count:
                    raise InvalidProviderError(
                        f'invalid dependency slot {dependency_index} in synchronous transient program'
                    )
                dependency_stack[-1] = dependency_position + 1
                operation_stack.append(dependency_index)
                dependency_stack.append(0)
                continue

            operation_stack.pop()
            dependency_stack.pop()
            parameter_count = len(operation.dependencies)
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

        return values[0]


def compile_sync_transient_instructions(plan: ResolutionPlan) -> SyncTransientProgram:
    operations: list[Operation] = []
    roots: dict[Ident, int] = {}

    for spec in plan.order:
        if spec.scope is not Scope.TRANSIENT:
            continue
        factory = sync_positional_factory(spec)
        if factory is None:
            continue

        dependencies: list[int] = []
        for param in spec.params:
            dependency = roots.get((param.key, param.tag))
            if dependency is None:
                break
            dependencies.append(dependency)
        else:
            ident = (spec.key, spec.tag)
            roots[ident] = len(operations)
            operations.append(Operation(factory, tuple(dependencies)))

    return SyncTransientProgram(tuple(operations), MappingProxyType(roots))


EMPTY_SYNC_TRANSIENT_PROGRAM = SyncTransientProgram((), MappingProxyType({}))
