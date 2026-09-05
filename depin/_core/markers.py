"""Public marker types and decorators for keys, tags, and injection."""

from dataclasses import dataclass
from types import GenericAlias
from typing import TYPE_CHECKING, Never, final, override

from depin.errors import DepinError, InvalidProviderError


class TokenKeyBase:
    """A named provider key, without the phantom type parameter `Token` carries.

    `Token` is the only intended implementation. This private nominal base exists so a
    position that holds a named key but has no type argument to name — the
    `ProviderKey` alias, the key a `Named` marker carries, the ``provides=``
    keyword — can be spelled without writing ``Token[object]``, whose phantom
    parameter has no variance every type checker agrees on.

    Subclassing is unsupported. Nothing prevents it — `Token` inherits from this
    class, so it cannot be final — and a subclass will compare equal to a
    `Token` of the same name and be accepted wherever a key is expected. That is
    a consequence of the shape, not a promise.

    Two instances are equal iff they share the same ``name``.

    """

    __slots__ = ('name',)

    def __init__(self, name: str) -> None:
        self.name = name

    @override
    def __repr__(self) -> str:
        return f'Token({self.name!r})'

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, TokenKeyBase) and self.name == other.name

    @override
    def __hash__(self) -> int:
        return hash(('depin.Token', self.name))


@final
class Token[T](TokenKeyBase):
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

    __slots__ = ()

    if TYPE_CHECKING:

        def witness(self, value: T) -> T: ...


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

    key: 'TokenKeyBase | str'


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
class _Injected:
    """The value `injected` holds: a parameter default that `inject` replaces.

    Attribute access raises rather than returning something meaningless: a
    marked parameter still holding this value inside the function body means the
    function was called without ``@container.inject`` wrapping it.
    """

    __slots__ = ()

    @override
    def __repr__(self) -> str:
        return 'depin.injected'

    def __call__(self, *args: object, **kwargs: object) -> Never:
        del args, kwargs
        raise DepinError(
            'depin.injected is a marker value, not a function: write '
            '`svc: Svc = injected`. The key comes from the annotation, and '
            'Annotated[Svc, Tag(...)] or Annotated[str, Named(...)] selects a '
            'tag or a named key.'
        )

    def __getattr__(self, name: str) -> object:
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        raise DepinError(
            'a parameter defaulting to depin.injected was accessed as a value. '
            'Such a parameter must be filled by @container.inject; wrap the '
            'function with the inject decorator.'
        )


if TYPE_CHECKING:
    # A default must be assignable to the parameter it stands in for, whatever
    # that parameter's type is. `Never` is the one type that is, and unlike
    # `Any` it erases nothing: a checker configured with `reportAny` stays
    # silent, and the parameter keeps its declared type. The declaration is
    # type-only because no value of type `Never` exists to write.
    injected: Never
    """Parameter default marking a parameter that `FrozenContainer.inject` fills.

    The parameter's annotation carries the key: a class,
    ``Annotated[T, Tag(...)]``, ``Annotated[T, Named(...)]``, or ``T | None``
    for a dependency that may be absent. Because it is a default, a marked
    parameter follows the non-default parameters or is keyword-only.
    """
else:
    injected = _Injected()


def is_inject_marker(value: object) -> bool:
    return isinstance(value, _Injected)


_PROVIDES_ATTR = '__depin_provides__'


def _reject_invalid_key(value: object, /) -> None:
    """Raise unless ``value`` can serve as the key ``provides`` records.

    Narrower than a provider key in general: a string and a `Token` are keys
    everywhere else, but neither is something a class decorator records.
    Everything a key may never be is reported by the same code `freeze()` uses,
    so the two positions never disagree about why a value was refused.

    Takes ``object`` rather than the annotated type so the check still runs for
    an untyped caller that breaks the promise the annotation makes to a checker.
    """
    # Deferred: depin._core.typeguards imports Token from this module, so a
    # module-level import here would be circular.
    from depin._core.typeguards import invalid_key_error, is_generic_key, is_parameterised_generic, is_union

    if isinstance(value, type) or is_generic_key(value):
        return
    if is_parameterised_generic(value) or is_union(value):
        raise invalid_key_error(value)
    raise InvalidProviderError(
        f'cannot use {value!r} as a @provides target: expected a class, a Protocol, '
        'an abstract base class, or a parameterised generic such as Repo[User]'
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
            including a ``Protocol`` and an abstract base class, or a
            parameterised generic such as ``Repo[User]``, spelled by
            subscripting its own origin rather than a deprecated ``typing``
            alias.

    Raises:
        InvalidProviderError: ``abstract`` is neither a class nor a
            parameterised generic depin can key by, so it could never serve as
            the provider key the decorator promises to record. A deprecated
            ``typing`` alias, a union, and a generic whose arguments are not
            themselves keys each report why in their own terms.

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
    _reject_invalid_key(abstract)
    return _ProvidesDecorator(abstract)


def get_provides(cls: type) -> type[object] | GenericAlias | None:
    return getattr(cls, _PROVIDES_ATTR, None)
