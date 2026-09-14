"""Typed immutable declarations for explicit provider discovery."""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass, field
from types import FrameType
from typing import Never, Self, overload, override

from depin._core.scope import Scope
from depin._core.spec import Condition, ProviderKey
from depin._core.typeguards import is_provider_key
from depin.errors import InvalidProviderError


class _ProviderToken:
    __slots__ = ()


class _ProviderMeta(type):
    @override
    def __call__(cls, *args: object, **kwargs: object) -> Never:
        del cls, args, kwargs
        raise InvalidProviderError('Provider cannot be constructed directly; use provider(target) instead.')


@dataclass(frozen=True, slots=True)
class _SourceLocation:
    module: str
    filename: str
    line: int


@dataclass(frozen=True, slots=True)
class _ProviderData:
    target: object
    scope: Scope
    provides: ProviderKey | None
    tag: str | None
    condition: Condition | None
    check: object | None
    owner: str
    location: _SourceLocation


def _caller_location() -> _SourceLocation:
    frame = inspect.currentframe()
    public_frame: FrameType | None = None
    caller: FrameType | None = None
    try:
        if frame is not None:
            public_frame = frame.f_back
        if public_frame is not None:
            caller = public_frame.f_back
        if caller is None:
            raise InvalidProviderError(
                'cannot determine the provider declaration module; call provider(target) from a Python module.'
            )
        module = caller.f_globals.get('__name__')
        if not isinstance(module, str) or not module:
            raise InvalidProviderError(
                'cannot determine the provider declaration module because the caller has no non-empty __name__; '
                'call provider(target) from a Python module.'
            )
        return _SourceLocation(module=module, filename=caller.f_code.co_filename, line=caller.f_lineno)
    finally:
        del caller, public_frame, frame


@dataclass(frozen=True, slots=True, init=False)
class Provider[T](metaclass=_ProviderMeta):
    _data: _ProviderData = field(repr=False)

    def __new__(cls, _token: _ProviderToken, /) -> Self:
        del _token
        return object.__new__(cls)

    def configure[U](
        self: Provider[U],
        *,
        scope: Scope = Scope.SINGLETON,
        provides: ProviderKey | None = None,
        tag: str | None = None,
        when: Condition | None = None,
        check: Callable[[U], object] | None = None,
    ) -> Provider[U]:
        _validate_metadata(scope, provides, tag, when, check)
        data = _ProviderData(
            target=self._data.target,
            scope=scope,
            provides=provides,
            tag=tag,
            condition=when,
            check=check,
            owner=self._data.owner,
            location=self._data.location,
        )
        return _allocate_provider(type(self), data)


def _allocate_provider[T](provider_type: type[Provider[T]], data: _ProviderData) -> Provider[T]:
    declaration = object.__new__(provider_type)
    object.__setattr__(declaration, '_data', data)
    return declaration


def _validate_metadata(
    scope: object,
    provides: object,
    tag: object,
    when: object,
    check: object,
) -> None:
    if not isinstance(scope, Scope):
        raise InvalidProviderError(f'cannot use {scope!r} as provider scope; pass a Scope value.')
    if provides is not None and not is_provider_key(provides):
        raise InvalidProviderError(
            f'cannot use {provides!r} as provider provides metadata; pass a valid ProviderKey or None.'
        )
    if tag is not None and not isinstance(tag, str):
        raise InvalidProviderError(f'cannot use {tag!r} as provider tag; pass a string or None.')
    if when is not None and not isinstance(when, bool) and not callable(when):
        raise InvalidProviderError(
            f'cannot use {when!r} as provider when metadata; pass a bool, a zero-argument callable, or None.'
        )
    if check is not None and not callable(check):
        raise InvalidProviderError(f'cannot use {check!r} as provider check; pass a callable or None.')


@overload
def provider[T](target: type[T], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, Generator[T, None, None]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, AsyncGenerator[T, None]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, AbstractContextManager[T]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, AbstractAsyncContextManager[T]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, Awaitable[T]], /) -> Provider[T]: ...


@overload
def provider[**P, T](target: Callable[P, T], /) -> Provider[T]: ...


def provider(target: type[object] | Callable[..., object], /) -> Provider[object]:
    if not isinstance(target, type) and not callable(target):
        raise InvalidProviderError(f'cannot declare {target!r} as a provider; pass a class or callable instead.')
    location = _caller_location()
    data = _ProviderData(
        target=target,
        scope=Scope.SINGLETON,
        provides=None,
        tag=None,
        condition=None,
        check=None,
        owner=location.module,
        location=location,
    )
    return _allocate_provider(Provider, data)
