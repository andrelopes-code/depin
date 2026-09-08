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
type Expression = tuple[str, int, int]

_FILENAME = '<depin generated resolver>'
_MAX_EXPRESSION_DEPTH = 200
_MAX_EXPANDED_CALLS = 512
_MAX_SOURCE_CHARS = 16_384
_MAX_TOTAL_EXPANDED_CALLS = 32_768
_MAX_TOTAL_SOURCE_CHARS = 1_000_000


def compile_sync_transients(plan: ResolutionPlan) -> Mapping[Ident, Program]:
    expressions: dict[Ident, Expression] = {}
    program_expressions: dict[Ident, str] = {}
    sources: list[Callable[..., object]] = []
    total_expanded_calls = 0
    total_source_chars = 0

    for spec in plan.order:
        generated = _expression(spec, expressions, sources)
        if generated is None:
            continue
        expression, _, expanded_calls = generated
        if total_expanded_calls + expanded_calls > _MAX_TOTAL_EXPANDED_CALLS:
            sources.pop()
            continue
        if total_source_chars + len(expression) > _MAX_TOTAL_SOURCE_CHARS:
            sources.pop()
            continue
        ident = (spec.key, spec.tag)
        expressions[ident] = generated
        program_expressions[ident] = expression
        total_expanded_calls += expanded_calls
        total_source_chars += len(expression)

    provider_namespace = tuple(sources)
    programs = {ident: _program(expression, provider_namespace) for ident, expression in program_expressions.items()}
    return MappingProxyType(programs)


def _expression(
    spec: ProviderSpec,
    expressions: Mapping[Ident, Expression],
    sources: list[Callable[..., object]],
) -> Expression | None:
    if spec.scope is not Scope.TRANSIENT or spec.shape is not ProviderShape.FUNCTION or spec.needs_async:
        return None
    if any(param.has_default or param.optional for param in spec.params):
        return None

    factory = as_factory(spec.source, spec.key)
    if not _accepts_positional_dependencies(factory, spec):
        return None

    dependencies: list[str] = []
    depth = 1
    expanded_calls = 1
    for param in spec.params:
        dependency = expressions.get((param.key, param.tag))
        if dependency is None:
            return None
        dependency_expression, dependency_depth, dependency_calls = dependency
        dependencies.append(dependency_expression)
        depth = max(depth, dependency_depth + 1)
        expanded_calls += dependency_calls
        if expanded_calls > _MAX_EXPANDED_CALLS:
            return None
    if depth > _MAX_EXPRESSION_DEPTH:
        return None

    index = len(sources)
    source_chars = len(f'_sources[{index}]()') + sum(map(len, dependencies)) + max(0, len(dependencies) - 1)
    if source_chars > _MAX_SOURCE_CHARS:
        return None
    sources.append(factory)
    return f'_sources[{index}]({",".join(dependencies)})', depth, expanded_calls


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
    expected_names = tuple(param.name for param in spec.params)
    actual_names = code.co_varnames[: code.co_argcount]
    return (
        not code.co_posonlyargcount
        and not code.co_kwonlyargcount
        and not code.co_flags & inspect.CO_VARARGS
        and code.co_argcount == len(expected_names)
        and actual_names == expected_names
    )


def _program(expression: str, sources: tuple[Callable[..., object], ...]) -> Program:
    namespace: dict[str, object] = {'__builtins__': {}, '_sources': sources}
    try:
        code = compile(f'def _resolve(_sources=_sources):\n    return {expression}\n', _FILENAME, 'exec')
        exec(code, namespace)
    except (MemoryError, SyntaxError) as error:
        raise InvalidProviderError(
            'depin could not build its generated resolver; use the interpreted provider path'
        ) from error
    candidate = namespace.pop('_resolve', None)
    namespace.pop('_sources', None)
    if not _is_program(candidate):
        raise InvalidProviderError('depin could not build its generated resolver; use the interpreted provider path')
    return candidate


def _is_program(candidate: object) -> TypeGuard[Program]:
    return callable(candidate)
