"""Reads shape and key metadata off a provider's signature and annotations."""

import inspect
from dataclasses import dataclass
from types import NoneType, UnionType
from typing import Annotated, TypeGuard, Union, get_args, get_origin

from depin._core.markers import Named, Tag, _TokenKey
from depin._core.spec import ProviderShape
from depin.errors import InvalidProviderError


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
    raise InvalidProviderError(
        f'cannot determine how to call {source!r}: '
        'bind a class, a function, a generator function, or a context-manager factory'
    )


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
    token: _TokenKey | None
    tag: str | None
    named: '_TokenKey | str | None'
    optional: bool


def is_token_key(value: object) -> TypeGuard[_TokenKey]:
    """A Token's T is type-only; at runtime a named key is observable only as its untyped supertype."""
    return isinstance(value, _TokenKey)


def extract_annotated_meta(annotation: object) -> AnnotatedMeta:
    base, extras = _split_annotated(annotation)

    token: _TokenKey | None = None
    tag: str | None = None
    named: _TokenKey | str | None = None

    for extra in extras:
        if is_token_key(extra):
            if token is None:
                token = extra
        elif isinstance(extra, Tag):
            if tag is None:
                tag = extra.name
        elif isinstance(extra, Named) and token is None and named is None:
            named = extra.key

    reduced, optional = _reduce_optional(base)
    return AnnotatedMeta(base=reduced, token=token, tag=tag, named=named, optional=optional)


def _split_annotated(annotation: object) -> tuple[object, tuple[object, ...]]:
    if get_origin(annotation) is not Annotated:
        return annotation, ()
    raw = get_args(annotation)
    return raw[0], tuple(raw[1:])


def _reduce_optional(annotation: object) -> tuple[object, bool]:
    """Read ``T`` out of ``T | None``, reporting whether the union admitted None.

    Both spellings reach here: ``T | None`` carries a `types.UnionType` origin and
    `typing.Optional[T]` carries `typing.Union`. A union that names no ``None``,
    or that names two or more providers besides it, is returned unchanged — there
    is no single key to reduce it to, and `as_provider_key` reports it.
    """
    if get_origin(annotation) not in (UnionType, Union):
        return annotation, False
    members = tuple(arg for arg in get_args(annotation) if arg is not NoneType)
    if len(members) == len(get_args(annotation)) or len(members) != 1:
        return annotation, False
    return members[0], True
