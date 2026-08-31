"""The registration surface shared by `Container` and `Registry`."""

from collections.abc import Callable, Iterable
from typing import Self, final, overload

from depin._core.markers import Token
from depin._core.scope import Scope
from depin._core.spec import AliasBinding, BindRecord, Bindings, FrameBinding, ProviderKey, ValueBinding
from depin.errors import InvalidProviderError

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
        """Register ``target`` and return it unchanged.

        Raises:
            InvalidProviderError: ``target`` is neither a class nor a callable.
        """
        if not isinstance(target, type) and not callable(target):
            raise InvalidProviderError(
                f'cannot register {target!r} with a scope decorator: expected a class or a callable'
            )
        self._bind(target, self._scope, self._provides, self._tag)
        return target


class BindingCollector:
    """Collects bindings; the shared half of `Container` and `Registry`.

    Every registration method returns ``self``, so declarations chain. Nothing is
    validated or constructed here — a `Container` defers all checks to
    `Container.freeze()`, and a `Registry` never validates at all.
    """

    __slots__ = ('_records',)

    def __init__(self) -> None:
        self._records: list[BindRecord] = []

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
        whole graph is wired by type.

        Args:
            source: A class to instantiate, or a callable returning the value.
                Sync and async functions, generators, async generators, and
                ``@(async)contextmanager`` factories are all accepted.
            scope: Lifetime of the produced value. Defaults to
                `Scope.SINGLETON`.
            provides: Key to register under, overriding the inferred one — for
                example to bind a concrete class against a ``Protocol``.
            tag: Disambiguator when several providers share a key; resolve it with
                a matching ``tag`` or ``Annotated[..., Tag(...)]``.

        Returns:
            ``self``, for chaining.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Clock:
            ...     def now(self) -> str:
            ...         return 'noon'
            >>> di = Container().bind(Clock).freeze()
            >>> di[Clock].now()
            'noon'

            ```
        """
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag))
        return self

    def value[T](self, token: Token[T], value: T) -> Self:
        """Bind a ready-made value to a `Token`.

        The value is registered as a singleton and returned as-is on resolution —
        no construction, no parameter wiring. Use this for configuration and other
        plain values that have no factory.

        Example:
            ```pycon
            >>> from depin import Container, Token
            >>> max_conn = Token[int]('max.conn')
            >>> di = Container().value(max_conn, 10).freeze()
            >>> di[max_conn]
            10

            ```
        """
        self._records.append(
            BindRecord(source=ValueBinding(token, value), scope=Scope.SINGLETON, provides=None, tag=None)
        )
        return self

    def scope_value[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> Self:
        """Declare a key whose value is supplied by whoever opens the scope.

        No factory is called. At resolution time the value must already have been
        placed into the active scope with `ScopeFrame.provide()` — by ASGI
        middleware, a CLI entry point, a test fixture. The binding is
        `Scope.SCOPED`, so resolving it outside a scope raises
        `OutsideScopeError`, and resolving inside a scope that never received the
        value raises `MissingProviderError`. This is how the FastAPI integration
        exposes the per-request ``Request``.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Principal:
            ...     def __init__(self, name: str) -> None:
            ...         self.name = name
            >>> class Audit:
            ...     def __init__(self, who: Principal) -> None:
            ...         self.who = who
            >>> from depin import Scope
            >>> di = Container().scope_value(Principal).bind(Audit, scope=Scope.SCOPED).freeze()
            >>> with di.scope() as frame:
            ...     frame.provide(Principal, Principal('ana'))
            ...     di[Audit].who.name
            'ana'

            ```
        """
        self._records.append(BindRecord(source=FrameBinding(key), scope=Scope.SCOPED, provides=None, tag=tag))
        return self

    def alias(
        self,
        key: ProviderKey,
        *,
        to: ProviderKey,
        tag: str | None = None,
        to_tag: str | None = None,
    ) -> Self:
        """Register ``key`` as a second name for an existing binding.

        Resolving the alias resolves the target and returns its value. The target
        keeps its own lifetime, its own cache entry, and its own teardown, so a
        singleton reached through an alias is still built once and torn down
        once, and both names return the same object.

        The alias caches nothing itself, which is why it takes no scope. It is an
        ordinary node in the validated graph: an unbound target, a duplicate
        alias, a cycle through an alias, and a singleton that reaches a scoped
        provider through one are all rejected by `Container.freeze()`, and the
        alias appears in `FrozenContainer.explain()` and in both graph exports.

        depin does not check that the target satisfies the alias key. A
        ``Protocol`` that is not ``runtime_checkable`` cannot be checked at all,
        and a structural alias between unrelated classes is legitimate.

        Args:
            key: The new name to register. A class, a `Token`, or a string. A
                string key is reachable only from a parameter annotated
                ``Annotated[T, Named('...')]``; `FrozenContainer.resolve` and
                ``frozen[key]`` do not accept one, so prefer a class or a
                `Token` for a key resolved directly.
            to: The binding to delegate to. May itself be an alias.
            tag: Disambiguator for the alias, matching the ``tag`` of a
                resolution or of an ``Annotated[..., Tag(...)]`` parameter.
            to_tag: The target's tag, when the target is registered under one.

        Returns:
            ``self``, for chaining.

        Example:
            ```pycon
            >>> from typing import Protocol
            >>> from depin import Container
            >>> class Store(Protocol):
            ...     def get(self) -> str: ...
            >>> class PostgresStore:
            ...     def get(self) -> str:
            ...         return 'pg'
            >>> di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
            >>> di.resolve(Store) is di[PostgresStore]
            True

            ```
        """
        self._records.append(
            BindRecord(
                source=AliasBinding(key=key, target=to, target_tag=to_tag),
                scope=Scope.TRANSIENT,
                provides=None,
                tag=tag,
            )
        )
        return self

    def singleton(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Decorator form of ``bind(..., scope=Scope.SINGLETON)``.

        Example:
            ```pycon
            >>> from depin import Registry
            >>> registry = Registry()
            >>> @registry.singleton()
            ... class Cache: ...
            >>> from depin import Container
            >>> di = Container(registry).freeze()
            >>> di[Cache] is di[Cache]
            True

            ```
        """
        return ScopeDecorator(self._record_bind, Scope.SINGLETON, provides, tag)

    def scoped(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Decorator form of ``bind(..., scope=Scope.SCOPED)``."""
        return ScopeDecorator(self._record_bind, Scope.SCOPED, provides, tag)

    def transient(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
    ) -> ScopeDecorator:
        """Decorator form of ``bind(..., scope=Scope.TRANSIENT)``."""
        return ScopeDecorator(self._record_bind, Scope.TRANSIENT, provides, tag)

    def include(self, *sources: Bindings) -> Self:
        """Append the bindings of one or more sources, in order.

        Each source is anything satisfying `Bindings` — usually a `Registry` or
        another `Container`. Records are concatenated, not de-duplicated: a key
        bound here and in a source raises `DuplicateProviderError` at
        `Container.freeze()`.

        Example:
            ```pycon
            >>> from depin import Container, Registry
            >>> class Logger: ...
            >>> class Metrics: ...
            >>> di = Container().include(Registry().bind(Logger), Registry().bind(Metrics)).freeze()
            >>> isinstance(di[Logger], Logger) and isinstance(di[Metrics], Metrics)
            True

            ```
        """
        for source in sources:
            self._records.extend(source.records())
        return self

    def records(self) -> Iterable[BindRecord]:
        """Return a snapshot of the bindings (the `Bindings` contract).

        The returned tuple is a copy; mutating it does not affect this collector.
        """
        return tuple(self._records)

    def _record_bind(
        self,
        source: type[object] | Callable[..., object],
        scope: Scope,
        provides: type[object] | None,
        tag: str | None,
    ) -> None:
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag))
