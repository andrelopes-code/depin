"""Internal binding and resolution data structures, plus the public `Bindings` protocol."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import GenericAlias, UnionType
from typing import Final, Protocol, TypeGuard, final, get_args, get_origin, runtime_checkable

from depin._core.markers import Token, TokenKey
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
        ALIAS: A second name for another binding, declared with
            `Container.alias`. Nothing is called and nothing is cached here —
            the target owns the value, its cache entry, and its teardown.
        COLLECTION: A list of several bindings, declared with
            `Container.collect`. Nothing is cached here — each member keeps its
            own lifetime, and every resolution returns a new list over them.

    Example:
        ```pycon
        >>> from depin import Container, ProviderShape
        >>> class Config: ...
        >>> di = Container().bind(Config).freeze()
        >>> di.graph().node(Config).shape is ProviderShape.CLASS
        True

        ```
    """

    CLASS = 'class'
    FUNCTION = 'function'
    ASYNC_FUNCTION = 'async function'
    GENERATOR = 'generator'
    ASYNC_GENERATOR = 'async generator'
    CONTEXT_MANAGER = 'context manager'
    ASYNC_CONTEXT_MANAGER = 'async context manager'
    VALUE = 'value'
    FRAME = 'frame'
    ALIAS = 'alias'
    COLLECTION = 'collection'


@final
@dataclass(frozen=True, slots=True)
class Underlying:
    """The key a decorated binding's inner form is registered under.

    `Container.decorate` leaves the wrapper on the public key and moves what it
    wraps here, so both are ordinary nodes of the validated graph: the wrapper
    reaches its inner form over a real edge, and the inner form keeps the
    lifetime, the cache entry, and the teardown it had undecorated.

    ``applied`` counts the decorators already applied below the public key, so
    the registered binding is ``Underlying(key, 0)`` and a second decorator over
    the same key sees ``Underlying(key, 1)``. Construct one to inspect a
    decorated binding — `FrozenContainer.explain` and `DependencyGraph.find`
    accept it — not to register anything.

    Example:
        ```pycon
        >>> from depin import Container, ProviderShape, Underlying
        >>> class Store:
        ...     def get(self) -> str:
        ...         return 'plain'
        >>> class Loud:
        ...     def __init__(self, inner: Store) -> None:
        ...         self.inner = inner
        ...     def get(self) -> str:
        ...         return self.inner.get().upper()
        >>> di = Container().bind(Store).decorate(Store, Loud).freeze()
        >>> di.graph().node(Underlying(Store, 0)).shape is ProviderShape.CLASS
        True

        ```
    """

    key: 'ProviderKey'
    applied: int


type ProviderKey = type[object] | TokenKey | str | GenericAlias | Underlying
"""What a provider can be bound and resolved under: a class, a `Token`, a name, or a parameterised generic.

The parameterised case needs no member of its own. A generic written in
expression position — ``Repo[User]``, ``Reader[User]`` — has the static type
``type[Repo[User]]``, which ``type[object]`` already covers; the
`types.GenericAlias` member covers the runtime object a builtin or ABC origin
produces, such as ``list[Handler]``. A deprecated ``typing`` alias
(``typing.List[X]``) is a key at neither level: `Container.freeze()` rejects it
and names the canonical spelling to write instead.

An `Underlying` is the fifth: the identity `Container.decorate` moves a
decorated binding's inner form to, so the wrapper can occupy the public key.
"""

type Ident = tuple[ProviderKey, str | None]
"""A provider's identity: its key paired with its tag. Private to `_core`."""


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

    key: 'type[object] | TokenKey'


def is_frame_binding(value: object) -> TypeGuard[FrameBinding]:
    return isinstance(value, FrameBinding)


ALIAS_PARAM: Final[str] = 'target'
"""The parameter an alias node declares for the binding it delegates to.

It is a real `ParamSpec` name, so it is what `explain()` prints as the edge
label and what the `dot` and `mermaid` exports write on the arrow.
"""


@dataclass(frozen=True, slots=True)
class AliasBinding:
    """Marker source for `Container.alias(key, to=...)`.

    The alias carries its own key because an alias needs two — the name it adds
    and the binding it delegates to — and a record has one `BindRecord.provides`.
    The alias's own tag rides on `BindRecord.tag`, where every other binding's tag rides;
    ``target_tag`` selects among tagged bindings on the other end.
    """

    key: ProviderKey
    target: ProviderKey
    target_tag: str | None


def is_alias_binding(value: object) -> TypeGuard[AliasBinding]:
    return isinstance(value, AliasBinding)


COLLECTION_PARAM_PREFIX: Final[str] = 'member_'
"""Prefix of the parameter names a collection node declares, one per member.

The names must be distinct because they key the resolved arguments, and they are
what `explain()` prints and what the `dot` and `mermaid` exports write on each
edge.
"""


@dataclass(frozen=True, slots=True)
class CollectionBinding:
    """Marker source for `Container.collect(element, members)`.

    The collection's own tag rides on `BindRecord.tag`. Members are ordinary
    provider keys and stay bound under them, which is why an accidental duplicate
    registration still raises `DuplicateProviderError`.
    """

    element: ProviderKey
    members: tuple[ProviderKey, ...]


def is_collection_binding(value: object) -> TypeGuard[CollectionBinding]:
    return isinstance(value, CollectionBinding)


@dataclass(frozen=True, slots=True)
class DecorateBinding:
    """Marker source for `Container.decorate(key, wrapper)`.

    The binding carries its own key because `BindRecord.provides` names the key a
    registered source takes, and a decoration registers no source: its key names
    the binding it wraps. It carries no tag of its own: a decorator has no
    identity to tag, so the tag on `BindRecord` is the decorated binding's.
    """

    key: ProviderKey
    wrapper: object


def is_decorate_binding(value: object) -> TypeGuard[DecorateBinding]:
    return isinstance(value, DecorateBinding)


def collection_key(element: ProviderKey) -> ProviderKey:
    """The key a collection over ``element`` is registered under.

    Built through `types.GenericAlias` rather than written as ``list[element]``:
    subscripting a runtime value is `Variable "element" is not valid as a type`
    under mypy. The result is the same object a consumer writes by hand — equal
    to ``list[Element]``, hashing as it, and of the same type.
    """
    return GenericAlias(list, (element,))


def collection_param(index: int) -> str:
    return f'{COLLECTION_PARAM_PREFIX}{index}'


type Condition = bool | Callable[[], bool]
"""What `when=` accepts on a registration.

A ``bool`` is read where it is written. A callable is called once per
`Container.freeze()`, with no arguments, and its result is read for truth — so a
predicate over configuration or the environment is evaluated when the graph is
built, not when a value is resolved.
"""


@dataclass(frozen=True, slots=True)
class BindRecord:
    source: object
    scope: Scope
    provides: type[object] | TokenKey | str | None
    tag: str | None
    condition: Condition | None = None
    check: object | None = None


@dataclass(frozen=True, slots=True)
class ParamSpec:
    name: str
    key: ProviderKey
    tag: str | None
    has_default: bool
    default: object
    optional: bool = False


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    key: ProviderKey
    tag: str | None
    source: object
    scope: Scope
    shape: ProviderShape
    needs_async: bool
    params: tuple[ParamSpec, ...]
    check: object | None = None


@dataclass(frozen=True, slots=True)
class DecorationSpec:
    """One wrapper over one binding, before it is given a key of its own.

    `depin._core.decoration` decides the key: it depends on how many decorators
    target the same binding, which no single record knows. ``inner`` names the
    parameter that receives the value being wrapped.
    """

    key: ProviderKey
    tag: str | None
    source: object
    shape: ProviderShape
    params: tuple[ParamSpec, ...]
    inner: str


@dataclass(frozen=True, slots=True)
class SpecSet:
    """What `build_specs` reads out of a set of records.

    Decorations are kept apart from providers because a decorator claims no key
    of its own until `depin._core.decoration` knows how many decorators target
    the same binding. `inactive` names the keys that a condition kept out, so a
    missing-provider message can say so.
    """

    providers: tuple[ProviderSpec, ...]
    decorations: tuple[DecorationSpec, ...]
    inactive: frozenset[Ident]


@dataclass(frozen=True, slots=True)
class ResolutionPlan:
    order: tuple[ProviderSpec, ...]
    by_key: Mapping[tuple[ProviderKey, str | None], ProviderSpec]
    inactive: frozenset[Ident] = frozenset()


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
    if isinstance(key, Underlying):
        return fmt_underlying(key)
    origin = get_origin(key)
    if isinstance(origin, type) and origin is not UnionType:
        return fmt_parameterised(origin, get_args(key))
    return repr(key)


def fmt_underlying(key: Underlying) -> str:
    """Spell a decoration layer as ``Store (undecorated)`` or ``Store (decorated x2)``.

    The wrapped key goes through `fmt_key` itself, so a decorated `Token`,
    string, or parameterised key renders the way it does everywhere else.
    """
    layer = 'undecorated' if key.applied == 0 else f'decorated x{key.applied}'
    return f'{fmt_key(key.key)} ({layer})'


def fmt_parameterised(origin: type[object], arguments: tuple[object, ...]) -> str:
    """Spell a parameterised key as ``Origin[A, B]``, each part through `fmt_key`.

    Shared with the message a deprecated `typing` alias is rejected with, so the
    canonical form the user is told to write is spelled by the same code that
    will render it once they do.
    """
    return f'{fmt_key(origin)}[{", ".join(fmt_key(argument) for argument in arguments)}]'


def fmt_chain(keys: Iterable[object]) -> str:
    """Render a resolution path as ``A -> B -> C``, in walk order.

    Every rendered path in the library goes through here, so an error message
    and a diagnostic can never disagree about how a chain is spelled.
    """
    return ' -> '.join(fmt_key(key) for key in keys)
