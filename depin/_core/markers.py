"""Public marker types and decorators for keys, tags, and injection."""

from dataclasses import dataclass
from typing import TypeGuard, final, override

from depin.errors import DepinError, InvalidProviderError


@final
class Token[T]:
    """A typed, named provider key.

    Two ``Token`` instances are equal iff they share the same ``name``. This makes
    ``Token`` safe to redeclare across modules: ``Token[str]('db.url')`` in module
    A resolves to the same provider as ``Token[str]('db.url')`` in module B. The
    type parameter is phantom — it exists only for the static checker and does not
    affect equality or hashing.

    Example:
        ```pycon
        >>> from depin import Token
        >>> Token[str]('db.url') == Token[str]('db.url')
        True
        >>> Token[str]('db.url') == Token[int]('db.url')
        True

        ```
    """

    __slots__ = ('name',)

    def __init__(self, name: str) -> None:
        self.name = name

    @override
    def __repr__(self) -> str:
        return f'Token({self.name!r})'

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Token) and self.name == other.name

    @override
    def __hash__(self) -> int:
        return hash(('depin.Token', self.name))


@final
@dataclass(frozen=True, slots=True)
class Named:
    """Annotated-metadata marker that selects a provider by key.

    Use inside ``Annotated[...]`` on a provider parameter when the parameter's
    type alone does not identify the provider — for example to pull a
    `Token` value, or a string-keyed binding, into a constructor. Given
    ``db_url = Token[str]('db.url')``::

        def make_pool(url: Annotated[str, Named(db_url)]) -> Pool: ...

    ``key`` is the provider key to resolve: a `Token` or a plain string. A
    bare ``Token`` placed directly in ``Annotated[...]`` has the same effect;
    ``Named`` is the explicit form and the only way to reference a string key.
    """

    key: 'Token[object] | str'


@final
@dataclass(frozen=True, slots=True)
class Tag:
    """Annotated-metadata marker that selects a tagged provider.

    When several providers share a key (registered with different ``tag=``
    values), ``Tag`` picks one for a parameter::

        def report(store: Annotated[Store, Tag('primary')]) -> Report: ...

    ``name`` must match the ``tag`` given at registration. Pairs with the
    ``tag=`` argument of `Container.bind()`.
    """

    name: str


@final
@dataclass(frozen=True, slots=True)
class _InjectMarker:
    """Default-value marker produced by `injected()`.

    Carries the provider key (and optional tag) for a parameter that
    `FrozenContainer.inject()` fills. It stands in for the parameter's
    declared type at the type level; ``inject`` replaces it with the resolved
    value before the wrapped function body runs.
    """

    key: 'type[object] | Token[object]'
    tag: str | None = None

    def __getattr__(self, name: str) -> object:
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        raise DepinError(
            f'depin injection marker for {self.key!r} was accessed as a value. '
            'A parameter defaulting to injected(...) must be filled by '
            '@container.inject; wrap the function with the inject decorator.'
        )


def is_inject_marker(value: object) -> TypeGuard[_InjectMarker]:
    return isinstance(value, _InjectMarker)


def injected[T](key: type[T] | Token[T], *, tag: str | None = None) -> T:
    """Mark a parameter for injection by `FrozenContainer.inject()`.

    Use as the parameter default::

        @container.inject
        def handler(prefix: str, svc: Svc = injected(Svc)) -> ...: ...

    Because the marker is a default, a marked parameter must follow non-default
    parameters or be keyword-only. ``key`` may be a class or a ``Token``; ``tag``
    selects among tagged providers.
    """
    # Python's type system has no opaque/branded generics: a function cannot
    # declare it returns T while producing an unrelated _InjectMarker. This is the
    # narrowest possible boundary; inject() substitutes the resolved value before
    # any caller observes the default.
    return _InjectMarker(key, tag)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]


_PROVIDES_ATTR = '__depin_provides__'


def _reject_non_class(value: object, /) -> None:
    """Raise unless ``value`` is a class.

    Takes ``object`` rather than ``type[object]`` so the check still runs for an
    untyped caller that breaks the promise the annotation makes to a type checker.
    """
    if not isinstance(value, type):
        raise InvalidProviderError(
            f'cannot use {value!r} as a @provides target: expected a class, a Protocol, or an abstract base class'
        )


@final
class _ProvidesDecorator:
    __slots__ = ('_abstract',)

    def __init__(self, abstract: type[object]) -> None:
        self._abstract = abstract

    def __call__[C](self, cls: type[C]) -> type[C]:
        setattr(cls, _PROVIDES_ATTR, self._abstract)
        return cls


def provides(abstract: type[object]) -> _ProvidesDecorator:
    """Tag a class with the abstract type it implements.

    Decorating ``@provides(Abstract)`` records ``Abstract`` as the class's provider
    key, so `Container.bind()` registers the concrete class under the
    abstract type without an explicit ``provides=`` argument. Useful for binding an
    implementation against a `typing.Protocol` or base class.

    The decorated class is returned unchanged and keeps its own type, so nothing
    downstream of the decorator sees a different class.

    Args:
        abstract: The key to register the decorated class under. Any class,
            including a ``Protocol`` and an abstract base class.

    Raises:
        InvalidProviderError: ``abstract`` is not a class, so it could never
            serve as the provider key the decorator promises to record.

    Example:
        ```pycon
        >>> from typing import Protocol
        >>> from depin import Container, provides
        >>> class Store(Protocol):
        ...     def get(self) -> str: ...
        >>> @provides(Store)
        ... class MemStore:
        ...     def get(self) -> str:
        ...         return 'mem'
        >>> di = Container().bind(MemStore).freeze()
        >>> di.resolve(Store).get()
        'mem'

        ```
    """
    _reject_non_class(abstract)
    return _ProvidesDecorator(abstract)


def get_provides(cls: type) -> type | None:
    return getattr(cls, _PROVIDES_ATTR, None)
