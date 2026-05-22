from collections.abc import Callable, Iterable
from typing import Self

from depin._core.frozen import FrozenContainer
from depin._core.markers import Token
from depin._core.registry import Registry, ScopeDecorator
from depin._core.resolver import build_plan
from depin._core.scope import Scope
from depin._core.spec import BindRecord, FrameBinding, ValueBinding


class Container:
    __slots__ = ('_records',)

    def __init__(self) -> None:
        self._records: list[BindRecord] = []

    @classmethod
    def from_(cls, *registries: Registry) -> Self:
        container = cls()
        for reg in registries:
            _ = container.merge(reg)
        return container

    def merge(self, other: 'Registry | Container') -> Self:
        self._records.extend(other.records())
        return self

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

    def frame_provides[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> Self:
        """Declare a binding satisfied by the active scope frame (e.g. middleware-injected values)."""
        self._records.append(
            BindRecord(source=FrameBinding(key), scope=Scope.SCOPED, provides=None, tag=tag)
        )
        return self

    def singleton(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        return ScopeDecorator(self._record_bind, Scope.SINGLETON, provides, tag)

    def scoped(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        return ScopeDecorator(self._record_bind, Scope.SCOPED, provides, tag)

    def transient(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        return ScopeDecorator(self._record_bind, Scope.TRANSIENT, provides, tag)

    def records(self) -> Iterable[BindRecord]:
        return tuple(self._records)

    def freeze(self) -> FrozenContainer:
        return FrozenContainer(build_plan(self.records()))

    def _record_bind(
        self,
        source: type[object],
        scope: Scope,
        provides: type[object] | None,
        tag: str | None,
    ) -> None:
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag))
