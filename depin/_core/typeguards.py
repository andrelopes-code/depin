"""Runtime narrowing at the boundary where the plan's `object` meets a shape.

A `ProviderSpec` stores its source as ``object``: the plan is built from
heterogeneous records and no single static type covers a class, a factory, a
generator function and a bare value. Every place that has to treat that
``object`` as something specific goes through one of the ``as_*`` helpers here,
which check the assumption and raise `InvalidProviderError` naming the provider
when it does not hold.

Each check is written as a ``TypeGuard`` returning the ``[object]``
parameterisation: ``isinstance`` against a generic runtime protocol narrows the
element type to ``Unknown``, and the guard is what restates it as ``object``.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from types import GenericAlias
from typing import TypeGuard, get_args, get_origin

from depin._core.markers import Token
from depin._core.spec import ALIAS_PARAM, ProviderKey, fmt_key
from depin.errors import InvalidProviderError


def is_provider_key(value: object) -> TypeGuard[ProviderKey]:
    return isinstance(value, type | str | Token) or is_collection_key(value)


def is_collection_key(value: object) -> TypeGuard[ProviderKey]:
    """Whether ``value`` is a ``list[X]`` over something that is itself a key.

    Deliberately narrow. Widening `ProviderKey` to every parameterised generic is
    cycle 3's deliverable; a collection needs only this one origin, and admitting
    more now would ship the wider surface without the validation and rendering
    that go with it.
    """
    if not isinstance(value, GenericAlias) or get_origin(value) is not list:
        return False
    arguments = get_args(value)
    return len(arguments) == 1 and is_provider_key(arguments[0])


def as_class(source: object, key: object) -> type[object]:
    if isinstance(source, type):
        return source
    raise InvalidProviderError(f'provider for {fmt_key(key)} is bound as a class, but {source!r} is not a class')


def as_factory(source: object, key: object) -> Callable[..., object]:
    if callable(source):
        return source
    raise InvalidProviderError(f'provider for {fmt_key(key)} is bound as a factory, but {source!r} is not callable')


def _is_awaitable(value: object) -> TypeGuard[Awaitable[object]]:
    return isinstance(value, Awaitable)


def as_awaitable(value: object, key: object) -> Awaitable[object]:
    if _is_awaitable(value):
        return value
    raise InvalidProviderError(f'async provider for {fmt_key(key)} returned {value!r}, which is not awaitable')


def _is_sync_iterator(value: object) -> TypeGuard[Iterator[object]]:
    return isinstance(value, Iterator)


def as_sync_iterator(value: object, key: object) -> Iterator[object]:
    if _is_sync_iterator(value):
        return value
    raise InvalidProviderError(f'generator provider for {fmt_key(key)} returned {value!r}, which is not an iterator')


def _is_async_iterator(value: object) -> TypeGuard[AsyncIterator[object]]:
    return isinstance(value, AsyncIterator)


def as_async_iterator(value: object, key: object) -> AsyncIterator[object]:
    if _is_async_iterator(value):
        return value
    raise InvalidProviderError(
        f'async generator provider for {fmt_key(key)} returned {value!r}, which is not an async iterator'
    )


def _is_sync_context_manager(value: object) -> TypeGuard[AbstractContextManager[object]]:
    return isinstance(value, AbstractContextManager)


def as_sync_context_manager(value: object, key: object) -> AbstractContextManager[object]:
    if _is_sync_context_manager(value):
        return value
    raise InvalidProviderError(
        f'context-manager provider for {fmt_key(key)} returned {value!r}, which is not a context manager'
    )


def _is_async_context_manager(value: object) -> TypeGuard[AbstractAsyncContextManager[object]]:
    return isinstance(value, AbstractAsyncContextManager)


def as_async_context_manager(value: object, key: object) -> AbstractAsyncContextManager[object]:
    if _is_async_context_manager(value):
        return value
    raise InvalidProviderError(
        f'async context-manager provider for {fmt_key(key)} returned {value!r}, which is not an async context manager'
    )


def as_alias_target(kwargs: dict[str, object], key: object) -> object:
    """The value an alias node's single parameter resolved to.

    Unreachable through the public API: `Container.freeze()` gives every alias
    exactly one required parameter, and parameter resolution raises
    `MissingProviderError` before construction when it cannot be satisfied.
    The check keeps a defect inside the `DepinError` hierarchy instead of
    surfacing as a `KeyError` with no provider named.
    """
    if ALIAS_PARAM in kwargs:
        return kwargs[ALIAS_PARAM]
    raise InvalidProviderError(f'alias for {fmt_key(key)} resolved no target binding')


def as_collection_members(kwargs: dict[str, object], names: tuple[str, ...], key: object) -> list[object]:
    """The resolved members of a collection, in declaration order.

    Unreachable through the public API for the same reason `as_alias_target` is:
    every member is a required parameter, and parameter resolution raises
    `MissingProviderError` before construction when one cannot be satisfied. The
    check keeps a defect inside the `DepinError` hierarchy.
    """
    missing = tuple(name for name in names if name not in kwargs)
    if missing:
        raise InvalidProviderError(f'collection for {fmt_key(key)} resolved no value for {", ".join(missing)}')
    return [kwargs[name] for name in names]
