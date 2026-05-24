"""Reusable binding collections that compose into containers."""

from collections.abc import Callable, Iterable
from typing import Self, final, overload

from depin._core.markers import Token
from depin._core.scope import Scope
from depin._core.spec import BindRecord, FrameBinding, ValueBinding

type _BindFn = Callable[[type[object] | Callable[..., object], Scope, type[object] | None, str | None], None]


@final
class ScopeDecorator:
    """Callable returned by the ``singleton`` / ``scoped`` / ``transient`` methods.

    Applying it to a class or factory registers that target at the chosen scope and
    returns the target unchanged, so it works as a decorator.
    """

    __slots__ = ('_bind', '_provides', '_scope', '_tag')

    def __init__(
        self,
        bind: _BindFn,
        scope: Scope,
        provides: type[object] | None,
        tag: str | None,
    ) -> None:
        self._bind = bind
        self._scope = scope
        self._provides = provides
        self._tag = tag

    @overload
    def __call__[T](self, target: type[T]) -> type[T]: ...
    @overload
    def __call__[**P, R](self, target: Callable[P, R]) -> Callable[P, R]: ...
    def __call__(self, target: object) -> object:
        """Register ``target`` and return it unchanged."""
        assert isinstance(target, type) or callable(target)
        self._bind(target, self._scope, self._provides, self._tag)
        return target


class Registry:
    """A reusable, composable collection of bindings.

    A ``Registry`` holds the same kind of bindings as a `Container`
    but performs no validation or resolution: it is a module-level catalogue you
    declare once and feed into one or more containers via
    `Container.from_()` / `Container.merge()`. Registries
    compose with ``|`` to form a larger registry. The registration methods mirror
    `Container` exactly and each returns ``self`` for chaining.

    Args:
        name: Optional label, used only to identify the registry; merging two named
            registries keeps the first non-empty name.

    Example:
        >>> from depin import Container, Registry
        >>> class Logger: ...
        >>> class Metrics: ...
        >>> infra = Registry('infra').bind(Logger)
        >>> obs = Registry('obs').bind(Metrics)
        >>> di = Container.from_(infra | obs).freeze()
        >>> isinstance(di[Logger], Logger) and isinstance(di[Metrics], Metrics)
        True
    """

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
        """Register a class or factory; see `Container.bind()`."""
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag))
        return self

    def value[T](self, token: Token[T], value: T) -> Self:
        """Bind a ready-made value to a token; see `Container.value()`."""
        self._records.append(
            BindRecord(source=ValueBinding(token, value), scope=Scope.SINGLETON, provides=None, tag=None)
        )
        return self

    def frame_provides[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> Self:
        """Declare a frame-supplied key; see `Container.frame_provides()`."""
        self._records.append(BindRecord(source=FrameBinding(key), scope=Scope.SCOPED, provides=None, tag=tag))
        return self

    def singleton(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Singleton decorator; see `Container.singleton()`."""
        return ScopeDecorator(self._record_bind, Scope.SINGLETON, provides, tag)

    def scoped(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Scoped decorator; see `Container.scoped()`."""
        return ScopeDecorator(self._record_bind, Scope.SCOPED, provides, tag)

    def transient(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Transient decorator; see `Container.transient()`."""
        return ScopeDecorator(self._record_bind, Scope.TRANSIENT, provides, tag)

    def records(self) -> Iterable[BindRecord]:
        """Return a snapshot of the bindings (the `HasRecords` contract)."""
        return tuple(self._records)

    def __or__(self, other: 'Registry') -> 'Registry':
        """Combine two registries into a new one, concatenating their bindings."""
        merged = Registry(name=self.name or other.name)
        merged._records.extend(self._records)
        merged._records.extend(other._records)
        return merged

    def _record_bind(
        self,
        source: type[object] | Callable[..., object],
        scope: Scope,
        provides: type[object] | None,
        tag: str | None,
    ) -> None:
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag))
