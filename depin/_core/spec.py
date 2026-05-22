from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import TypeGuard

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
