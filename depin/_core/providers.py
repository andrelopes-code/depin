"""Turns a `BindRecord` into a `ProviderSpec`: infers the key, shape and parameters."""

import inspect
from collections.abc import Iterable
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from depin._core.introspect import AnnotatedMeta, detect_shape, extract_annotated_meta, is_object_token
from depin._core.markers import get_provides
from depin._core.scope import Scope
from depin._core.spec import (
    ALIAS_PARAM,
    BindRecord,
    ParamSpec,
    ProviderKey,
    ProviderShape,
    ProviderSpec,
    is_alias_binding,
    is_frame_binding,
    is_value_binding,
)
from depin._core.typeguards import as_class, as_factory
from depin.errors import InvalidProviderError, InvalidScopeError

LIFECYCLE_SHAPES = frozenset(
    {
        ProviderShape.GENERATOR,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.CONTEXT_MANAGER,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
    }
)

ASYNC_SHAPES = frozenset(
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
    """Convert every record into a spec, resolving forward references between them."""
    records = tuple(records)
    localns = _registered_classes(records)
    return tuple(_record_to_spec(rec, localns) for rec in records)


def _registered_classes(records: Iterable[BindRecord]) -> dict[str, object]:
    """Namespace of bound classes, so `from __future__ import annotations` hints resolve."""
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

    if is_alias_binding(rec.source):
        alias = rec.source
        return ProviderSpec(
            key=as_provider_key(alias.key),
            tag=rec.tag,
            source=alias,
            scope=rec.scope,
            shape=ProviderShape.ALIAS,
            needs_async=False,
            params=(
                ParamSpec(
                    name=ALIAS_PARAM,
                    key=as_provider_key(alias.target),
                    tag=alias.target_tag,
                    has_default=False,
                    default=None,
                ),
            ),
        )

    source = rec.source
    shape = detect_shape(source)

    if shape in LIFECYCLE_SHAPES and rec.scope is Scope.TRANSIENT:
        raise InvalidScopeError(
            f'cannot bind {source!r} as transient: a generator or context-manager provider '
            'owns a teardown, and a transient value is never cached, so nothing would drain it. '
            'Use Scope.SINGLETON or Scope.SCOPED.'
        )

    return ProviderSpec(
        key=_resolve_key(source, rec.provides, shape, localns),
        tag=rec.tag,
        source=source,
        scope=rec.scope,
        shape=shape,
        needs_async=False,
        params=_extract_params(source, shape, localns),
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
    hints = _safe_type_hints(source, localns)
    ret = hints.get('return')
    if ret is None:
        raise InvalidProviderError(
            f'cannot infer the provider key for {source!r}: add a return type annotation, or pass provides=...'
        )
    if shape in _UNWRAP_SHAPES:
        unwrapped = unwrap_container_type(ret)
        if unwrapped is not None:
            return unwrapped
    return as_provider_key(ret)


def unwrap_container_type(annotation: object) -> ProviderKey | None:
    """Read ``T`` out of ``Generator[T]``, ``AsyncIterator[T]``, ``Awaitable[T]``, and friends."""
    if get_origin(annotation) is None:
        return None
    args = get_args(annotation)
    if not args:
        return None
    return as_provider_key(args[0])


def as_provider_key(value: object) -> ProviderKey:
    if isinstance(value, type | str):
        return value
    if is_object_token(value):
        return value
    if get_origin(value) in (UnionType, Union):
        raise InvalidProviderError(
            f'cannot use {value} as a provider key: depin reads `T | None` as an optional '
            'dependency, but a union of two or more providers names no single key. Annotate '
            'the parameter with the one you want, or select it with Annotated[..., Tag(...)].'
        )
    raise InvalidProviderError(f'cannot use {value!r} as a provider key: a key must be a class, a Token, or a string')


def _extract_params(source: object, shape: ProviderShape, localns: dict[str, object]) -> tuple[ParamSpec, ...]:
    target = as_class(source, source).__init__ if shape is ProviderShape.CLASS else as_factory(source, source)
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        # `inspect.signature` rejects some C-implemented callables outright;
        # such a provider simply declares no injectable parameters.
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
            if param.annotation is not inspect.Parameter.empty:
                raise InvalidProviderError(
                    f"the annotation on parameter '{name}' of {source!r} could not be resolved "
                    f'({param.annotation!r}). Import the name at module level, or bind the class '
                    'so depin can resolve the forward reference.'
                )
            if param.default is inspect.Parameter.empty:
                raise InvalidProviderError(
                    f"parameter '{name}' of {source!r} has no type annotation and no default, "
                    'so depin cannot tell what to inject'
                )
            params.append(ParamSpec(name=name, key=object, tag=None, has_default=True, default=param.default))
            continue

        meta = extract_annotated_meta(raw_annotation)
        has_default = param.default is not inspect.Parameter.empty
        params.append(
            ParamSpec(
                name=name,
                key=param_key_from_meta(meta),
                tag=meta.tag,
                has_default=has_default,
                default=param.default if has_default else None,
                optional=meta.optional,
            )
        )

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
    """Resolve annotations, returning nothing when a name in them cannot be resolved.

    Callers decide what an empty result means: `_resolve_key` reports an
    un-inferrable provider key, `_extract_params` distinguishes a missing
    annotation from an unresolvable one.
    """
    try:
        return dict(get_type_hints(target, localns=localns, include_extras=True))
    except (NameError, TypeError):
        return {}
