"""Freeze-time generation of bounded synchronous transient resolvers."""

import inspect
from collections.abc import Callable, Mapping
from types import FunctionType, MappingProxyType
from typing import TypeGuard

from depin._core.scope import Scope
from depin._core.spec import Ident, ProviderShape, ProviderSpec, ResolutionPlan
from depin._core.typeguards import as_factory
from depin.errors import InvalidProviderError

type Program = Callable[[], object]

_FILENAME = '<depin generated resolver>'
_MAX_EXPRESSION_DEPTH = 200


def compile_sync_transients(plan: ResolutionPlan) -> Mapping[Ident, Program]:
    expressions: dict[Ident, tuple[str, int]] = {}
    programs: dict[Ident, Program] = {}
    sources: list[Callable[..., object]] = []

    for spec in plan.order:
        generated = _expression(spec, expressions, sources)
        if generated is None:
            continue
        expression, depth = generated
        ident = (spec.key, spec.tag)
        expressions[ident] = (expression, depth)
        programs[ident] = _program(expression, tuple(sources))

    return MappingProxyType(programs)


def _expression(
    spec: ProviderSpec,
    expressions: Mapping[Ident, tuple[str, int]],
    sources: list[Callable[..., object]],
) -> tuple[str, int] | None:
    if spec.scope is not Scope.TRANSIENT or spec.shape is not ProviderShape.FUNCTION or spec.needs_async:
        return None
    if any(param.has_default or param.optional for param in spec.params):
        return None

    factory = as_factory(spec.source, spec.key)
    if not _accepts_positional_dependencies(factory, spec):
        return None

    dependencies: list[str] = []
    depth = 1
    for param in spec.params:
        dependency = expressions.get((param.key, param.tag))
        if dependency is None:
            return None
        dependency_expression, dependency_depth = dependency
        dependencies.append(dependency_expression)
        depth = max(depth, dependency_depth + 1)
    if depth > _MAX_EXPRESSION_DEPTH:
        return None

    index = len(sources)
    sources.append(factory)
    return f'_sources[{index}]({",".join(dependencies)})', depth


def _accepts_positional_dependencies(factory: Callable[..., object], spec: ProviderSpec) -> bool:
    try:
        parameters = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return False
    advertised_positionals = all(
        (parameter := parameters.get(param.name)) is not None
        and parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        for param in spec.params
    )
    if not advertised_positionals or not spec.params:
        return advertised_positionals
    if not isinstance(factory, FunctionType):
        return False
    code = factory.__code__
    return code.co_argcount >= len(spec.params) or bool(code.co_flags & inspect.CO_VARARGS)


def _program(expression: str, sources: tuple[Callable[..., object], ...]) -> Program:
    namespace: dict[str, object] = {'_sources': sources}
    code = compile(f'def _resolve():\n    return {expression}\n', _FILENAME, 'exec')
    exec(code, namespace)
    candidate = namespace.get('_resolve')
    if not _is_program(candidate):
        raise InvalidProviderError('depin could not build its generated resolver; use the interpreted provider path')
    return candidate


def _is_program(candidate: object) -> TypeGuard[Program]:
    return callable(candidate)
