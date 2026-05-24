"""The mutable builder: register bindings, then ``freeze()`` into a runtime view."""

from collections.abc import Callable, Iterable
from typing import Self

from depin._core.frozen import FrozenContainer
from depin._core.markers import Token
from depin._core.registry import ScopeDecorator
from depin._core.resolver import build_plan
from depin._core.scope import Scope
from depin._core.spec import BindRecord, FrameBinding, HasRecords, ValueBinding


class Container:
    """Mutable builder for a dependency graph.

    Collect bindings with `bind()`, `value()`, `frame_provides()`, and
    the `singleton()` / `scoped()` / `transient()` decorators, then
    call `freeze()` to validate the graph and obtain an immutable
    `FrozenContainer`. A ``Container`` performs no resolution itself;
    nothing is constructed until you resolve from the frozen view. Registration
    order does not matter — providers are matched by key and ordered at
    `freeze()` time.

    Example:
        >>> from depin import Container
        >>> class Config:
        ...     value = 42
        >>> class Service:
        ...     def __init__(self, config: Config) -> None:
        ...         self.config = config
        >>> di = Container().bind(Config).bind(Service).freeze()
        >>> di[Service].config.value
        42
    """

    __slots__ = ('_records',)

    def __init__(self) -> None:
        self._records: list[BindRecord] = []

    @classmethod
    def from_(cls, *sources: HasRecords) -> Self:
        """Build a container pre-loaded with bindings from one or more sources.

        Each source is anything exposing ``records()`` — typically a
        `Registry` or another `Container`. Equivalent to
        creating an empty container and `merge()`-ing each source in order.

        Example:
            >>> from depin import Container, Registry
            >>> class Svc: ...
            >>> reg = Registry().bind(Svc)
            >>> di = Container.from_(reg).freeze()
            >>> isinstance(di[Svc], Svc)
            True
        """
        container = cls()
        for src in sources:
            _ = container.merge(src)
        return container

    def merge(self, other: HasRecords) -> Self:
        """Append another source's bindings to this container.

        Records are concatenated, not de-duplicated: a key bound here and in
        ``other`` raises `DuplicateProviderError` at
        `freeze()` time. Returns ``self`` for chaining.
        """
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
        """Register a class or factory as a provider.

        The provider key is inferred from ``source``: a class is keyed by itself
        (or by its ``@provides(...)`` target), a factory by its return annotation
        (unwrapped for generator and context-manager factories). Constructor and
        factory parameters are themselves resolved from their type hints, so the
        whole graph is wired by type. Validation is deferred to `freeze()`.

        Args:
            source: A class to instantiate, or a callable returning the value.
                Sync/async functions, generators, async generators, and
                ``@(async)contextmanager`` factories are all accepted.
            scope: Lifetime of the produced value. Defaults to
                `Scope.SINGLETON`.
            provides: Key to register under, overriding the inferred one — e.g. to
                bind a concrete class against a ``Protocol``.
            tag: Disambiguator when several providers share a key; resolve it with
                a matching ``tag`` or ``Annotated[..., Tag(...)]``.

        Returns:
            ``self``, for chaining.

        Example:
            >>> from depin import Container
            >>> class Clock:
            ...     def now(self) -> str:
            ...         return 'noon'
            >>> di = Container().bind(Clock).freeze()
            >>> di[Clock].now()
            'noon'
        """
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag))
        return self

    def value[T](self, token: Token[T], value: T) -> Self:
        """Bind a ready-made value to a `Token`.

        The value is registered as a singleton and returned as-is on resolution —
        no construction, no parameter wiring. Use this for configuration and other
        plain values that have no factory.

        Example:
            >>> from depin import Container, Token
            >>> max_conn = Token[int]('max.conn')
            >>> di = Container().value(max_conn, 10).freeze()
            >>> di[max_conn]
            10
        """
        self._records.append(
            BindRecord(source=ValueBinding(token, value), scope=Scope.SINGLETON, provides=None, tag=None)
        )
        return self

    def frame_provides[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> Self:
        """Declare a key whose value is supplied by the active scope frame.

        No factory is called: at resolution time the value must already have been
        placed into the active scope (by middleware or scope-setup code) under
        ``key``. The binding is `Scope.SCOPED`, so resolving it
        outside a scope raises `OutsideScopeError`, and
        resolving inside a scope that never received the value raises
        `MissingProviderError`. This is how the FastAPI
        integration exposes the per-request `fastapi.Request`; see
        `RequestScope`.
        """
        self._records.append(BindRecord(source=FrameBinding(key), scope=Scope.SCOPED, provides=None, tag=tag))
        return self

    def singleton(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Decorator form of `bind()` with ``scope=Scope.SINGLETON``.

        Applies to a class or factory and registers it without changing it; the
        value is built once and shared for the lifetime of the
        `FrozenContainer`. ``provides`` and ``tag`` behave as in
        `bind()`.

        Example:
            >>> from depin import Container
            >>> container = Container()
            >>> @container.singleton()
            ... class Cache:
            ...     pass
            >>> di = container.freeze()
            >>> di[Cache] is di[Cache]
            True
        """
        return ScopeDecorator(self._record_bind, Scope.SINGLETON, provides, tag)

    def scoped(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Decorator form of `bind()` with ``scope=Scope.SCOPED``.

        Like `singleton()`, but the value is built once per active scope
        (`FrozenContainer.scope()` / ``ascope``) and torn down when that
        scope exits. Resolving one with no active scope raises
        `OutsideScopeError`.
        """
        return ScopeDecorator(self._record_bind, Scope.SCOPED, provides, tag)

    def transient(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Decorator form of `bind()` with ``scope=Scope.TRANSIENT``.

        Like `singleton()`, but a fresh value is produced on every resolution
        and never cached. Generator and context-manager providers cannot be
        transient (they need a scope to own their teardown); binding one this way
        raises ``ValueError`` at `freeze()` time.
        """
        return ScopeDecorator(self._record_bind, Scope.TRANSIENT, provides, tag)

    def records(self) -> Iterable[BindRecord]:
        """Return a snapshot of the registered bindings.

        Satisfies the `HasRecords` protocol, so a container can be a
        source for `from_()` or `merge()`. The returned tuple is a copy.
        """
        return tuple(self._records)

    def freeze(self) -> FrozenContainer:
        """Validate the dependency graph and return an immutable runtime view.

        All static checks happen here, before anything is constructed:

        - every required provider exists
          (`MissingProviderError`);
        - the graph is acyclic
          (`CircularDependencyError`);
        - no key is bound twice
          (`DuplicateProviderError`);
        - no singleton depends on a scoped provider it would capture for life
          (`CaptiveDependencyError`);
        - factories expose enough type information to infer keys and parameters
          (``TypeError``); generator / context-manager providers are not transient
          (``ValueError``).

        The frozen container also pre-computes which providers need async
        resolution, so `FrozenContainer.resolve()` can reject async
        providers up front.

        Raises:
            MissingProviderError: A required dependency has no provider.
            CircularDependencyError: The dependency graph contains a cycle.
            DuplicateProviderError: Two bindings resolve to the same key and tag.
            CaptiveDependencyError: A singleton depends on a scoped provider.
            TypeError: A factory lacks a return annotation (and no ``provides=``)
                or a parameter has no type annotation.
            ValueError: A generator or context-manager provider is bound as
                transient.

        Example:
            >>> from depin import Container, Scope
            >>> from depin.errors import CaptiveDependencyError
            >>> class Session: ...
            >>> class Repo:
            ...     def __init__(self, session: Session) -> None: ...
            >>> builder = (
            ...     Container()
            ...     .bind(Session, scope=Scope.SCOPED)
            ...     .bind(Repo, scope=Scope.SINGLETON)
            ... )
            >>> try:
            ...     builder.freeze()
            ... except CaptiveDependencyError:
            ...     print('rejected')
            rejected
        """
        return FrozenContainer(build_plan(self.records()))

    def _record_bind(
        self,
        source: type[object] | Callable[..., object],
        scope: Scope,
        provides: type[object] | None,
        tag: str | None,
    ) -> None:
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag))
