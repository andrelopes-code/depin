import inspect
from collections.abc import Iterable
from typing import get_args, get_origin, get_type_hints

from depin._core.introspect import AnnotatedMeta, is_object_token, extract_annotated_meta
from depin._core.markers import get_provides
from depin._core.scope import Scope
from depin._core.spec import (
    BindRecord,
    ParamSpec,
    ProviderKey,
    ProviderShape,
    ProviderSpec,
    ResolutionPlan,
    is_value_binding,
)
from depin.errors import CircularDependencyError, MissingProviderError


_LIFECYCLE_SHAPES = frozenset(
    {
        ProviderShape.GENERATOR,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.CONTEXT_MANAGER,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
    }
)

_ASYNC_SHAPES = frozenset(
    {
        ProviderShape.ASYNC_FUNCTION,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
    }
)

_UNWRAP_SHAPES = frozenset(
    {
        ProviderShape.GENERATOR,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.CONTEXT_MANAGER,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
        ProviderShape.ASYNC_FUNCTION,
    }
)


def build_specs(records: Iterable[BindRecord]) -> tuple[ProviderSpec, ...]:
    records = tuple(records)
    localns = _registered_classes(records)
    return tuple(_record_to_spec(rec, localns) for rec in records)


def build_plan(records: Iterable[BindRecord]) -> ResolutionPlan:
    records = tuple(records)
    localns = _registered_classes(records)
    specs = tuple(_record_to_spec(rec, localns) for rec in records)
    by_key = _index(specs)
    _validate_params(specs, by_key)
    order = _toposort(specs, by_key)
    specs_with_async = tuple(_compute_needs_async(order, by_key))
    return ResolutionPlan(order=specs_with_async, by_key=_index(specs_with_async))


def _registered_classes(records: Iterable[BindRecord]) -> dict[str, object]:
    out: dict[str, object] = {}
    for rec in records:
        src = rec.source
        if isinstance(src, type):
            out[src.__name__] = src
    return out


def _record_to_spec(rec: BindRecord, localns: dict[str, object]) -> ProviderSpec:
    if is_value_binding(rec.source):
        binding = rec.source
        return ProviderSpec(
            key=binding.token,
            tag=rec.tag,
            source=binding.value,
            scope=rec.scope,
            shape=ProviderShape.VALUE,
            needs_async=False,
            params=(),
        )

    source = rec.source
    from depin._core.introspect import detect_shape

    shape = detect_shape(source)

    if shape in _LIFECYCLE_SHAPES and rec.scope is Scope.TRANSIENT:
        raise ValueError(
            f'cannot bind {source!r} as transient: '
            'generator and context-manager providers require singleton or scoped scope'
        )

    key = _resolve_key(source, rec.provides, shape, localns)
    params = _extract_params(source, shape, localns)

    return ProviderSpec(
        key=key,
        tag=rec.tag,
        source=source,
        scope=rec.scope,
        shape=shape,
        needs_async=False,
        params=params,
    )


def _resolve_key(
    source: object,
    explicit: type[object] | None,
    shape: ProviderShape,
    localns: dict[str, object],
) -> ProviderKey:
    if explicit is not None:
        return explicit
    if isinstance(source, type):
        attr = get_provides(source)
        return attr if attr is not None else source
    if not callable(source):
        raise TypeError(f'cannot register {source!r}: not a class, callable, or value-binding')

    hints = _safe_type_hints(source, localns)
    ret = hints.get('return')
    if ret is None:
        raise TypeError(
            f'cannot infer provider key for {source!r}: '
            'add a return type annotation or pass provides=...'
        )
    if shape in _UNWRAP_SHAPES:
        unwrapped = _unwrap_container_type(ret)
        if unwrapped is not None:
            return unwrapped
    return _as_provider_key(ret)


def _unwrap_container_type(annotation: object) -> ProviderKey | None:
    if get_origin(annotation) is None:
        return None
    args = get_args(annotation)
    if not args:
        return None
    return _as_provider_key(args[0])


def _as_provider_key(value: object) -> ProviderKey:
    if isinstance(value, type):
        return value
    if is_object_token(value):
        return value
    if isinstance(value, str):
        return value
    raise TypeError(f'cannot use {value!r} as a provider key')


def _extract_params(source: object, shape: ProviderShape, localns: dict[str, object]) -> tuple[ParamSpec, ...]:
    target: object
    if shape is ProviderShape.CLASS:
        assert isinstance(source, type)
        target = source.__init__
    else:
        target = source

    if not callable(target):
        return ()

    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        return ()

    hints = _safe_type_hints(target, localns)

    params: list[ParamSpec] = []
    for name, param in sig.parameters.items():
        if name in ('self', 'cls'):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        raw_annotation = hints.get(name)
        if raw_annotation is None:
            if param.default is inspect.Parameter.empty:
                raise TypeError(f"parameter '{name}' of {source!r} is missing a type annotation")
            params.append(ParamSpec(name=name, key=object, tag=None, has_default=True, default=param.default))
            continue

        meta = extract_annotated_meta(raw_annotation)
        key = _param_key(meta)
        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None

        params.append(ParamSpec(name=name, key=key, tag=meta.tag, has_default=has_default, default=default))

    return tuple(params)


def _param_key(meta: AnnotatedMeta) -> ProviderKey:
    if meta.token is not None:
        return meta.token
    if isinstance(meta.named, str):
        return meta.named
    if is_object_token(meta.named):
        return meta.named
    return _as_provider_key(meta.base)


def _safe_type_hints(target: object, localns: dict[str, object]) -> dict[str, object]:
    if not callable(target):
        return {}
    try:
        return dict(get_type_hints(target, localns=localns, include_extras=True))
    except (NameError, TypeError):
        return {}


def _index(specs: Iterable[ProviderSpec]) -> dict[tuple[ProviderKey, str | None], ProviderSpec]:
    out: dict[tuple[ProviderKey, str | None], ProviderSpec] = {}
    for spec in specs:
        out[(spec.key, spec.tag)] = spec
    return out


def _validate_params(
    specs: Iterable[ProviderSpec],
    by_key: dict[tuple[ProviderKey, str | None], ProviderSpec],
) -> None:
    for spec in specs:
        for param in spec.params:
            if param.has_default:
                continue
            if (param.key, param.tag) not in by_key:
                raise MissingProviderError(
                    f"no provider for {_fmt(param.key)} "
                    f"(required by {_fmt(spec.key)}, parameter '{param.name}')"
                )


def _toposort(
    specs: Iterable[ProviderSpec],
    by_key: dict[tuple[ProviderKey, str | None], ProviderSpec],
) -> tuple[ProviderSpec, ...]:
    ordered: list[ProviderSpec] = []
    visiting: set[tuple[ProviderKey, str | None]] = set()
    visited: set[tuple[ProviderKey, str | None]] = set()
    stack: list[tuple[ProviderKey, str | None]] = []

    def visit(spec: ProviderSpec) -> None:
        ident = (spec.key, spec.tag)
        if ident in visited:
            return
        if ident in visiting:
            chain = ' -> '.join(_fmt(k) for k, _ in [*stack, ident])
            raise CircularDependencyError(f'cycle detected: {chain}')
        visiting.add(ident)
        stack.append(ident)
        for param in spec.params:
            dep = by_key.get((param.key, param.tag))
            if dep is not None:
                visit(dep)
        _ = stack.pop()
        visiting.remove(ident)
        visited.add(ident)
        ordered.append(spec)

    for spec in specs:
        visit(spec)
    return tuple(ordered)


def _compute_needs_async(
    order: Iterable[ProviderSpec],
    by_key: dict[tuple[ProviderKey, str | None], ProviderSpec],
) -> Iterable[ProviderSpec]:
    needs: dict[tuple[ProviderKey, str | None], bool] = {}
    for spec in order:
        own = spec.shape in _ASYNC_SHAPES
        for param in spec.params:
            dep = by_key.get((param.key, param.tag))
            if dep is not None and needs.get((dep.key, dep.tag), False):
                own = True
                break
        needs[(spec.key, spec.tag)] = own
        yield ProviderSpec(
            key=spec.key,
            tag=spec.tag,
            source=spec.source,
            scope=spec.scope,
            shape=spec.shape,
            needs_async=own,
            params=spec.params,
        )


def _fmt(key: object) -> str:
    if isinstance(key, type):
        return key.__qualname__
    return repr(key)
