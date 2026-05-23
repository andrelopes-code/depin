import inspect
from dataclasses import dataclass
from typing import Annotated, TypeGuard, get_args, get_origin

from depin._core.markers import Named, Tag, Token
from depin._core.spec import ProviderShape


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
    tag: str | None
    named: 'Token[object] | str | None'


def is_object_token(value: object) -> TypeGuard[Token[object]]:
    """Token's T is type-only; at runtime every Token can be treated as Token[object]."""
    return isinstance(value, Token)


def extract_annotated_meta(annotation: object) -> AnnotatedMeta:
    base, extras = _split_annotated(annotation)

    token: Token[object] | None = None
    tag: str | None = None
    named: Token[object] | str | None = None

    for extra in extras:
        if is_object_token(extra):
            if token is None:
                token = extra
        elif isinstance(extra, Tag):
            if tag is None:
                tag = extra.name
        elif isinstance(extra, Named) and token is None and named is None:
            named = extra.key

    return AnnotatedMeta(base=base, token=token, tag=tag, named=named)


def _split_annotated(annotation: object) -> tuple[object, tuple[object, ...]]:
    if get_origin(annotation) is not Annotated:
        return annotation, ()
    raw = get_args(annotation)
    return raw[0], tuple(raw[1:])
