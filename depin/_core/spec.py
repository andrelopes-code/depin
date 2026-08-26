"""Internal binding and resolution data structures, plus the public `Bindings` protocol."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, TypeGuard, runtime_checkable

from depin._core.markers import Token
from depin._core.scope import Scope


class ProviderShape(Enum):
    CLASS = auto()
    FUNCTION = auto()
    ASYNC_FUNCTION = auto()
    GENERATOR = auto()
    ASYNC_GENERATOR = auto()
    CONTEXT_MANAGER = auto()
    ASYNC_CONTEXT_MANAGER = auto()
    VALUE = auto()
    FRAME = auto()


type ProviderKey = type[object] | Token[object] | str


@dataclass(frozen=True, slots=True)
class ValueBinding[T]:
    """Marker source carried by BindRecord for `Container.value(token, x)` bindings."""

    token: Token[T]
    value: T


def is_value_binding(value: object) -> TypeGuard[ValueBinding[object]]:
    """ValueBinding's T is erased at runtime; any instance is observable as ValueBinding[object]."""
    return isinstance(value, ValueBinding)


@dataclass(frozen=True, slots=True)
class FrameBinding:
    """Marker source for `Container.scope_value(key)`.

    The provider value is expected to be in the active scope frame keyed by
    ``key``; the resolver does no factory call. Used for values supplied by
    middleware or other scope-setup code (for example ``fastapi.Request``).
    """

    key: 'type[object] | Token[object]'


def is_frame_binding(value: object) -> TypeGuard[FrameBinding]:
    return isinstance(value, FrameBinding)


@dataclass(frozen=True, slots=True)
class BindRecord:
    source: object
    scope: Scope
    provides: type[object] | None
    tag: str | None


@dataclass(frozen=True, slots=True)
class ParamSpec:
    name: str
    key: ProviderKey
    tag: str | None
    has_default: bool
    default: object


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    key: ProviderKey
    tag: str | None
    source: object
    scope: Scope
    shape: ProviderShape
    needs_async: bool
    params: tuple[ParamSpec, ...]


@dataclass(frozen=True, slots=True)
class ResolutionPlan:
    order: tuple[ProviderSpec, ...]
    by_key: Mapping[tuple[ProviderKey, str | None], ProviderSpec]


@runtime_checkable
class Bindings(Protocol):
    """Anything that can hand a container a set of bindings.

    Both `Registry` and `Container` satisfy it, so either can seed a new
    container: ``Container(infra, services)``. Implement it on your own type to
    plug a custom binding source into the same call.

    Example:
        ```pycon
        >>> from depin import Container, Registry, Bindings
        >>> class Svc: ...
        >>> registry = Registry('infra').bind(Svc)
        >>> isinstance(registry, Bindings)
        True
        >>> di = Container(registry).freeze()
        >>> isinstance(di[Svc], Svc)
        True

        ```
    """

    def records(self) -> Iterable[BindRecord]:
        """Return this source's bindings, in declaration order."""
        ...


def fmt_key(key: object) -> str:
    if isinstance(key, type):
        return key.__qualname__
    return repr(key)
