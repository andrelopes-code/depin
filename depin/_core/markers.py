from dataclasses import dataclass
from typing import final, override


@final
class Token[T]:
    """A typed, named provider key.

    Two ``Token`` instances are equal iff they share the same ``name``. This makes
    ``Token`` safe to redeclare across modules: ``Token[str]('db.url')`` in module
    A resolves to the same provider as ``Token[str]('db.url')`` in module B. The
    type parameter is phantom — it exists only for the static checker and does not
    affect equality or hashing.
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
    key: 'Token[object] | str'


@final
@dataclass(frozen=True, slots=True)
class Tag:
    name: str


_PROVIDES_ATTR = '__depin_provides__'


@final
class _ProvidesDecorator[A]:
    __slots__ = ('_abstract',)

    def __init__(self, abstract: type[A]) -> None:
        self._abstract = abstract

    def __call__[C](self, cls: type[C]) -> type[C]:
        setattr(cls, _PROVIDES_ATTR, self._abstract)
        return cls


def provides[A](abstract: type[A]) -> _ProvidesDecorator[A]:
    return _ProvidesDecorator(abstract)


def get_provides(cls: type) -> type | None:
    return getattr(cls, _PROVIDES_ATTR, None)
