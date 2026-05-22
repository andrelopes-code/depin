from collections.abc import Callable, Iterable
from typing import Self, final

from depin._core.markers import Token
from depin._core.scope import Scope
from depin._core.spec import BindRecord, ValueBinding


@final
class _ScopeDecorator:
    __slots__ = ('_provides', '_registry', '_scope', '_tag')

    def __init__(
        self,
        registry: 'Registry',
        scope: Scope,
        provides: type[object] | None,
        tag: str | None,
    ) -> None:
        self._registry = registry
        self._scope = scope
        self._provides = provides
        self._tag = tag

    def __call__[T](self, cls: type[T]) -> type[T]:
        _ = self._registry.bind(cls, scope=self._scope, provides=self._provides, tag=self._tag)
        return cls


class Registry:
    __slots__ = ('_records', 'name')

    def __init__(self, name: str = '') -> None:
        self.name = name
        self._records: list[BindRecord] = []

    def bind[T](
        self,
        source: type[T] | Callable[..., T],
        *,
        scope: Scope = Scope.SINGLETON,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> Self:
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag))
        return self

    def value[T](self, token: Token[T], value: T) -> Self:
        self._records.append(
            BindRecord(source=ValueBinding(token, value), scope=Scope.SINGLETON, provides=None, tag=None)
        )
        return self

    def singleton(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> _ScopeDecorator:
        return _ScopeDecorator(self, Scope.SINGLETON, provides, tag)

    def scoped(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> _ScopeDecorator:
        return _ScopeDecorator(self, Scope.SCOPED, provides, tag)

    def transient(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> _ScopeDecorator:
        return _ScopeDecorator(self, Scope.TRANSIENT, provides, tag)

    def records(self) -> Iterable[BindRecord]:
        return tuple(self._records)

    def __or__(self, other: 'Registry') -> 'Registry':
        merged = Registry(name=self.name or other.name)
        merged._records.extend(self._records)
        merged._records.extend(other._records)
        return merged
