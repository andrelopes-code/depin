import inspect
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, TypeGuard, get_args, get_origin, get_type_hints

from depin._core.markers import Inject, Named, Tag, Token
from depin._core.spec import ProviderShape


@lru_cache(maxsize=None)
def cached_signature(target: Callable[..., object]) -> inspect.Signature:
    return inspect.signature(target)


@lru_cache(maxsize=None)
def cached_type_hints(target: Callable[..., object]) -> dict[str, object]:
    return dict(get_type_hints(target, include_extras=True))


def detect_shape(source: object) -> ProviderShape:
    if isinstance(source, type):
        return ProviderShape.CLASS
    if inspect.isasyncgenfunction(source):
        return ProviderShape.ASYNC_GENERATOR
    if inspect.iscoroutinefunction(source):
        return ProviderShape.ASYNC_FUNCTION
    if _wraps_async_generator(source):
        return ProviderShape.ASYNC_CONTEXT_MANAGER
    if _wraps_sync_generator(source):
        return ProviderShape.CONTEXT_MANAGER
    if inspect.isgeneratorfunction(source):
        return ProviderShape.GENERATOR
    if callable(source):
        return ProviderShape.FUNCTION
    raise TypeError(f'cannot determine provider shape for {source!r}')


def _wraps_sync_generator(source: object) -> bool:
    if inspect.isgeneratorfunction(source):
        return False
    wrapped = getattr(source, '__wrapped__', None)
    return inspect.isgeneratorfunction(wrapped)


def _wraps_async_generator(source: object) -> bool:
    if inspect.isasyncgenfunction(source):
        return False
    wrapped = getattr(source, '__wrapped__', None)
    return inspect.isasyncgenfunction(wrapped)


@dataclass(frozen=True, slots=True)
class AnnotatedMeta:
    base: object
    token: Token[object] | None
    inject: Inject | None
    tag: str | None
    named: 'Token[object] | str | None'


def _is_object_token(value: object) -> TypeGuard[Token[object]]:
    """Token's T is type-only; at runtime every Token can be treated as Token[object]."""
    return isinstance(value, Token)


def extract_annotated_meta(annotation: object) -> AnnotatedMeta:
    base, extras = _split_annotated(annotation)

    token: Token[object] | None = None
    inject: Inject | None = None
    tag: str | None = None
    named: Token[object] | str | None = None

    for extra in extras:
        if _is_object_token(extra):
            if token is None:
                token = extra
        elif isinstance(extra, Inject):
            if inject is None:
                inject = extra
        elif isinstance(extra, Tag):
            if tag is None:
                tag = extra.name
        elif isinstance(extra, Named) and token is None and named is None:
            named = extra.key

    return AnnotatedMeta(base=base, token=token, inject=inject, tag=tag, named=named)


def _split_annotated(annotation: object) -> tuple[object, tuple[object, ...]]:
    if get_origin(annotation) is not Annotated:
        return annotation, ()
    raw = get_args(annotation)
    return raw[0], tuple(raw[1:])
