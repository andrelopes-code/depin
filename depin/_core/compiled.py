"""Compiles eligible synchronous transient provider paths into closures."""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from depin._core.scope import Scope
from depin._core.spec import Ident, ParamSpec, ProviderShape, ProviderSpec, ResolutionPlan
from depin._core.typeguards import as_factory

type Program = Callable[[], object]
type ParameterProgram = tuple[str, Program]


def compile_sync_transients(plan: ResolutionPlan) -> Mapping[Ident, Program]:
    """Return immutable zero-argument programs for self-contained transient factories."""
    programs: dict[Ident, Program] = {}
    for spec in plan.order:
        if not _is_eligible(spec):
            continue
        parameters = _parameter_programs(spec.params, plan, programs)
        if parameters is None:
            continue
        programs[(spec.key, spec.tag)] = _program(as_factory(spec.source, spec.key), parameters)
    return MappingProxyType(programs)


def _is_eligible(spec: ProviderSpec) -> bool:
    return spec.scope is Scope.TRANSIENT and spec.shape is ProviderShape.FUNCTION and not spec.needs_async


def _parameter_programs(
    params: tuple[ParamSpec, ...], plan: ResolutionPlan, programs: Mapping[Ident, Program]
) -> tuple[ParameterProgram, ...] | None:
    resolved: list[ParameterProgram] = []
    for param in params:
        dependency = plan.by_key.get((param.key, param.tag))
        if dependency is None:
            return None
        program = programs.get((dependency.key, dependency.tag))
        if program is None:
            return None
        resolved.append((param.name, program))
    return tuple(resolved)


def _program(factory: Callable[..., object], parameters: tuple[ParameterProgram, ...]) -> Program:
    def invoke() -> object:
        return factory(**{name: program() for name, program in parameters})

    return invoke
