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
from types import GenericAlias, NoneType, UnionType
from typing import Generic, TypeGuard, Union, get_args, get_origin

from depin._core.markers import Token
from depin._core.spec import ALIAS_PARAM, ParamSpec, ProviderKey, Underlying, fmt_key, fmt_parameterised
from depin.errors import InvalidProviderError


def is_provider_key(value: object) -> TypeGuard[ProviderKey]:
    return isinstance(value, type | str | Token | Underlying) or is_generic_key(value)


def generic_origin(value: object) -> type[object] | None:
    """The class ``value`` parameterises, or ``None`` when it parameterises no class.

    A union is excluded by name: `types.UnionType` is a class, so it would
    otherwise pass, and optionality is a parameter-position feature rather than
    a key.
    """
    origin = get_origin(value)
    if isinstance(origin, type) and origin is not UnionType:
        return origin
    return None


def is_parameterised_generic(value: object) -> bool:
    """Whether ``value`` subscripts a class with at least one argument.

    Shape only: it says nothing about how the parameterisation is spelled, nor
    about what it is parameterised with. `is_generic_key` adds both.
    """
    return generic_origin(value) is not None and bool(get_args(value))


def is_generic_key(value: object) -> TypeGuard[ProviderKey]:
    """Whether ``value`` is a parameterised generic usable as a provider key.

    The parameterisation must be canonically spelled, and every argument must
    itself be a provider key. That second rule recurses back through
    `is_provider_key`, so canonicity holds at every level of nesting:
    `list[typing.List[X]]` is rejected as surely as `typing.List[X]` is.
    `Callable[[int], str]` and `tuple[X, ...]` fall out of the same rule,
    carrying a list and an `Ellipsis` respectively, with no special case.
    """
    return (
        is_parameterised_generic(value)
        and is_canonical_generic(value)
        and all(is_provider_key(argument) for argument in get_args(value))
    )


def is_union(value: object) -> bool:
    """Whether ``value`` is a union, in either spelling: ``X | Y`` or ``typing.Union[X, Y]``."""
    return get_origin(value) in (UnionType, Union)


def is_canonical_generic(value: object) -> bool:
    """Whether a parameterised generic is spelled the way depin keys it.

    A builtin or ABC origin produces a `types.GenericAlias`; a `Generic`
    subclass produces `typing`'s own alias. Everything else with a class origin
    is a deprecated `typing` alias — `typing.List[X]` and its kin — which is a
    different object from `list[X]` and would become a second key that renders
    identically to the first.
    """
    origin = get_origin(value)
    if not isinstance(origin, type):
        return False
    return isinstance(value, GenericAlias) or issubclass(origin, Generic)


def invalid_key_error(value: object) -> InvalidProviderError:
    """The error explaining why ``value`` cannot serve as a provider key.

    Shared by `as_provider_key` and the guard behind `provides`, so a value
    rejected in either position is explained the same way. Only ever called for
    a value `is_provider_key` rejects.
    """
    deprecated = _deprecated_alias_error_within(value)
    if deprecated is not None:
        return deprecated
    if is_parameterised_generic(value):
        rejected = ', '.join(repr(argument) for argument in get_args(value) if not is_provider_key(argument))
        return InvalidProviderError(
            f'cannot use {value} as a provider key: its argument {rejected} is not itself a provider '
            'key, and every argument of a parameterised key must be one. That is why '
            'Callable[[int], str] and tuple[X, ...] are never keys.'
        )
    if is_union(value):
        return _invalid_union_error(value)
    return InvalidProviderError(
        f'cannot use {value!r} as a provider key: a key must be a class, a Token, a string, or a '
        'parameterised generic built by subscripting its origin, such as list[X] or Repo[X] '
        '(not the deprecated typing.List[X] form).'
    )


def _deprecated_alias_error_within(value: object) -> InvalidProviderError | None:
    """The error for the outermost deprecated `typing` alias in ``value``, ``value`` itself included.

    Searched at every depth because canonicity is required at every depth:
    `list[typing.List[X]]` is as unusable as `typing.List[X]`, and naming the
    inner spelling is the only advice a caller can act on.
    """
    origin = generic_origin(value)
    if origin is None:
        return None
    if not is_canonical_generic(value):
        canonical = fmt_parameterised(origin, get_args(value))
        return InvalidProviderError(
            f'cannot use {value} as a provider key: it is the deprecated typing alias for '
            f'{canonical}, and a different object at runtime, so the two would be two keys that '
            f'print alike. Write {canonical} instead, subscripting '
            f'{origin.__module__}.{origin.__qualname__} itself.'
        )
    for argument in get_args(value):
        found = _deprecated_alias_error_within(argument)
        if found is not None:
            return found
    return None


def _invalid_union_error(value: object) -> InvalidProviderError:
    members = tuple(argument for argument in get_args(value) if argument is not NoneType)
    if len(members) == 1:
        return InvalidProviderError(
            f'cannot use {value} as a provider key: depin reads `T | None` as an optional '
            f"dependency only on a provider's parameter, and this is not one. Use "
            f'{fmt_key(members[0])} directly.'
        )
    return InvalidProviderError(
        f'cannot use {value} as a provider key: depin reads `T | None` as an optional '
        'dependency, but a union of two or more providers names no single key wherever it is used — '
        'as a parameter annotation, an alias target, or a collection element. Write the one key you '
        'mean instead, or, for a parameter, disambiguate with Annotated[..., Tag(...)].'
    )


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


def as_collection_members(kwargs: dict[str, object], params: tuple[ParamSpec, ...], key: object) -> list[object]:
    """The resolved members of a collection, in declaration order.

    Unreachable through the public API for the same reason `as_alias_target` is:
    every member is a required parameter, and parameter resolution raises
    `MissingProviderError` before construction when one cannot be satisfied. The
    check keeps a defect inside the `DepinError` hierarchy.
    """
    missing = tuple(param.name for param in params if param.name not in kwargs)
    if missing:
        raise InvalidProviderError(f'collection for {fmt_key(key)} resolved no value for {", ".join(missing)}')
    return [kwargs[param.name] for param in params]
