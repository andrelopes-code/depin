import inspect
from collections.abc import Iterable
from typing import get_args, get_origin, get_type_hints

from depin._core.introspect import AnnotatedMeta, extract_annotated_meta, is_object_token
from depin._core.markers import get_provides
from depin._core.scope import Scope
from depin._core.spec import (
    BindRecord,
    ParamSpec,
    ProviderKey,
    ProviderShape,
    ProviderSpec,
    ResolutionPlan,
    is_frame_binding,
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

    if is_frame_binding(rec.source):
        frame = rec.source
        return ProviderSpec(
            key=as_provider_key(frame.key),
            tag=rec.tag,
            source=frame,
            scope=rec.scope,
            shape=ProviderShape.FRAME,
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
        raise TypeError(f'cannot infer provider key for {source!r}: add a return type annotation or pass provides=...')
    if shape in _UNWRAP_SHAPES:
        unwrapped = unwrap_container_type(ret)
        if unwrapped is not None:
            return unwrapped
    return as_provider_key(ret)


def unwrap_container_type(annotation: object) -> ProviderKey | None:
    if get_origin(annotation) is None:
        return None
    args = get_args(annotation)
    if not args:
        return None
    return as_provider_key(args[0])


def as_provider_key(value: object) -> ProviderKey:
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
        key = param_key_from_meta(meta)
        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None

        params.append(ParamSpec(name=name, key=key, tag=meta.tag, has_default=has_default, default=default))

    return tuple(params)


def param_key_from_meta(meta: AnnotatedMeta) -> ProviderKey:
    if meta.token is not None:
        return meta.token
    if isinstance(meta.named, str):
        return meta.named
    if is_object_token(meta.named):
        return meta.named
    return as_provider_key(meta.base)


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
    missing: dict[tuple[ProviderKey, str | None], tuple[tuple[ProviderSpec, ...], ProviderSpec, str]] = {}
    for root in specs:
        _collect_missing(root, by_key, (root,), missing)
    if not missing:
        return
    ident, (chain, owner, param_name) = max(missing.items(), key=lambda kv: len(kv[1][0]))
    key, _tag = ident
    path = ' -> '.join(fmt_key(s.key) for s in chain)
    suggestions = _suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    raise MissingProviderError(
        f'no provider for {fmt_key(key)} '
        f'(required by {fmt_key(owner.key)}.{param_name}; '
        f'resolution chain: {path} -> {fmt_key(key)}){extra}'
    )


def _collect_missing(
    root: ProviderSpec,
    by_key: dict[tuple[ProviderKey, str | None], ProviderSpec],
    chain: tuple[ProviderSpec, ...],
    missing: dict[tuple[ProviderKey, str | None], tuple[tuple[ProviderSpec, ...], ProviderSpec, str]],
) -> None:
    # Iterative DFS over the dependency graph. Each entry is the current spec
    # paired with the chain that led to it; cycles are broken by the
    # ``dep in chain_specs`` check below.
    stack: list[tuple[ProviderSpec, tuple[ProviderSpec, ...]]] = [(root, chain)]
    while stack:
        spec, current_chain = stack.pop()
        chain_specs = {id(c) for c in current_chain}
        for param in spec.params:
            if param.has_default:
                continue
            dep = by_key.get((param.key, param.tag))
            if dep is None:
                ident = (param.key, param.tag)
                if ident not in missing or len(current_chain) > len(missing[ident][0]):
                    missing[ident] = (current_chain, spec, param.name)
                continue
            if id(dep) in chain_specs:
                continue
            stack.append((dep, (*current_chain, dep)))


_SUGGEST_SCAN_LIMIT = 50_000
_SUGGEST_RESULT_LIMIT = 5


def _suggest_candidates(target: object) -> list[str]:
    """Scan live classes for `@provides(target)` hints. Used only at error time.

    Bounded by ``_SUGGEST_SCAN_LIMIT`` to keep error-path latency predictable in
    large processes where ``gc.get_objects()`` returns hundreds of thousands of
    references.
    """
    if not isinstance(target, type):
        return []
    import gc

    out: list[str] = []
    for i, obj in enumerate(gc.get_objects()):
        if i >= _SUGGEST_SCAN_LIMIT:
            break
        if not isinstance(obj, type):
            continue
        prov = get_provides(obj)
        if prov is target:
            out.append(f'{obj.__module__}.{obj.__qualname__}')
            if len(out) >= _SUGGEST_RESULT_LIMIT:
                break
    return out


def _toposort(
    specs: Iterable[ProviderSpec],
    by_key: dict[tuple[ProviderKey, str | None], ProviderSpec],
) -> tuple[ProviderSpec, ...]:
    """Iterative post-order DFS. Frames are ``(spec, next_param_index)``."""
    ordered: list[ProviderSpec] = []
    visited: set[tuple[ProviderKey, str | None]] = set()
    visiting: set[tuple[ProviderKey, str | None]] = set()

    for root in specs:
        if (root.key, root.tag) in visited:
            continue
        stack: list[tuple[ProviderSpec, int]] = [(root, 0)]
        visiting.add((root.key, root.tag))
        while stack:
            spec, i = stack[-1]
            if i >= len(spec.params):
                ident = (spec.key, spec.tag)
                visiting.remove(ident)
                visited.add(ident)
                ordered.append(spec)
                _ = stack.pop()
                continue
            stack[-1] = (spec, i + 1)
            param = spec.params[i]
            dep = by_key.get((param.key, param.tag))
            if dep is None:
                continue
            dep_ident = (dep.key, dep.tag)
            if dep_ident in visited:
                continue
            if dep_ident in visiting:
                cycle_path = [(s.key, s.tag) for s, _ in stack]
                cycle_path.append(dep_ident)
                chain = ' -> '.join(fmt_key(k) for k, _ in cycle_path)
                raise CircularDependencyError(f'cycle detected: {chain}')
            visiting.add(dep_ident)
            stack.append((dep, 0))
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


def fmt_key(key: object) -> str:
    if isinstance(key, type):
        return key.__qualname__
    return repr(key)
