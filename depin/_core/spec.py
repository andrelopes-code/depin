"""Internal binding and resolution data structures, plus the public `Bindings` protocol."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, TypeGuard, runtime_checkable

from depin._core.markers import Token
from depin._core.scope import Scope


class ProviderShape(Enum):
    """How a provider produces its value, and whether it owns a teardown.

    Reported by `GraphNode.shape`. `Container.freeze()` infers it from the
    binding: a class, a factory's kind, or a value.

    Attributes:
        CLASS: A class, instantiated with its resolved constructor arguments.
        FUNCTION: A synchronous factory, called with its resolved arguments.
        ASYNC_FUNCTION: A coroutine factory, awaited. Requires `aresolve`.
        GENERATOR: A generator factory that yields once and resumes at
            teardown. Cannot be transient.
        ASYNC_GENERATOR: An async generator factory that yields once and
            resumes at teardown. Requires `aresolve` and cannot be transient.
        CONTEXT_MANAGER: A factory returning a context manager, entered on
            construction and exited at teardown. Cannot be transient.
        ASYNC_CONTEXT_MANAGER: A factory returning an async context manager.
            Requires `aresolve` and cannot be transient.
        VALUE: A value bound directly with `Container.value`; nothing is called.
        FRAME: A value the active scope frame supplies, bound with
            `Container.scope_value`; nothing is called.

    Example:
        ```pycon
        >>> from depin import Container, ProviderShape
        >>> class Config: ...
        >>> di = Container().bind(Config).freeze()
        >>> di.graph().node(Config).shape is ProviderShape.CLASS
        True

        ```
    """

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
"""What a provider can be bound and resolved under: a class, a `Token`, or a name."""


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


def fmt_chain(keys: Iterable[object]) -> str:
    """Render a resolution path as ``A -> B -> C``, in walk order.

    Every rendered path in the library goes through here, so an error message
    and a diagnostic can never disagree about how a chain is spelled.
    """
    return ' -> '.join(fmt_key(key) for key in keys)
