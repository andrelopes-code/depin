from collections.abc import Callable
from dataclasses import dataclass
from typing import final, override


@final
class Token[T]:
    __slots__ = ('name',)

    def __init__(self, name: str) -> None:
        self.name = name

    @override
    def __repr__(self) -> str:
        return f'Token({self.name!r})'


@final
@dataclass(frozen=True, slots=True)
class Inject:
    factory: Callable[..., object]


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
