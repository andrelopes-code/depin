"""The registration surface shared by `Container` and `Registry`."""

from collections.abc import Callable, Iterable, Sequence
from typing import Self, final, overload

from depin._core.markers import Token
from depin._core.scope import Scope
from depin._core.spec import (
    AliasBinding,
    BindRecord,
    Bindings,
    CollectionBinding,
    Condition,
    DecorateBinding,
    FrameBinding,
    ProviderKey,
    ValueBinding,
)
from depin.errors import InvalidProviderError

type _BindFn = Callable[
    [type[object] | Callable[..., object], Scope, type[object] | None, str | None, Condition | None],
    None,
]


@final
class ScopeDecorator:
    """Callable returned by the ``singleton`` / ``scoped`` / ``transient`` methods.

    Applying it to a class or factory registers that target at the chosen scope and
    returns the target unchanged, so it works as a decorator.
    """

    __slots__ = ('_bind', '_provides', '_scope', '_tag', '_when')

    def __init__(
        self,
        bind: _BindFn,
        scope: Scope,
        provides: type[object] | None,
        tag: str | None,
        when: Condition | None,
    ) -> None:
        self._bind = bind
        self._scope = scope
        self._provides = provides
        self._tag = tag
        self._when = when

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
        self._bind(target, self._scope, self._provides, self._tag, self._when)
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
        when: Condition | None = None,
        check: Callable[[T], object] | None = None,
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
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.
            check: Callable verifying the produced value, exposed by
                `FrozenContainer.checks` and run by `FrozenContainer.health`.
                It receives the value and is healthy unless it raises or
                returns ``False``.

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
        self._records.append(
            BindRecord(source=source, scope=scope, provides=provides, tag=tag, condition=when, check=check)
        )
        return self

    def value[T](
        self,
        token: Token[T],
        value: T,
        *,
        when: Condition | None = None,
        check: Callable[[T], object] | None = None,
    ) -> Self:
        """Bind a ready-made value to a `Token`.

        The value is registered as a singleton and returned as-is on resolution —
        no construction, no parameter wiring. Use this for configuration and other
        plain values that have no factory.

        Args:
            token: The key to register the value under.
            value: The value returned on resolution.
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.
            check: Callable verifying the produced value, exposed by
                `FrozenContainer.checks` and run by `FrozenContainer.health`.
                It receives the value and is healthy unless it raises or
                returns ``False``.

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
            BindRecord(
                source=ValueBinding(token, value),
                scope=Scope.SINGLETON,
                provides=None,
                tag=None,
                condition=when,
                check=check,
            )
        )
        return self

    def scope_value[T](self, key: type[T] | Token[T], *, tag: str | None = None, when: Condition | None = None) -> Self:
        """Declare a key whose value is supplied by whoever opens the scope.

        No factory is called. At resolution time the value must already have been
        placed into the active scope with `ScopeFrame.provide()` — by ASGI
        middleware, a CLI entry point, a test fixture. The binding is
        `Scope.SCOPED`, so resolving it outside a scope raises
        `OutsideScopeError`, and resolving inside a scope that never received the
        value raises `MissingProviderError`. This is how the FastAPI integration
        exposes the per-request ``Request``.

        Args:
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.

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
        self._records.append(
            BindRecord(source=FrameBinding(key), scope=Scope.SCOPED, provides=None, tag=tag, condition=when)
        )
        return self

    def alias(
        self,
        key: ProviderKey,
        *,
        to: ProviderKey,
        tag: str | None = None,
        to_tag: str | None = None,
        when: Condition | None = None,
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
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.

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
                condition=when,
            )
        )
        return self

    def collect(
        self,
        element: ProviderKey,
        members: Sequence[ProviderKey],
        *,
        tag: str | None = None,
        when: Condition | None = None,
    ) -> Self:
        """Register a list of existing bindings under the key ``list[element]``.

        Resolving that key returns each member's value, in the order given here.
        Members keep their own lifetimes, cache entries, and teardowns, so a
        singleton member is built once however many collections name it, and a
        scoped member is rebuilt per scope. Every resolution returns a new list,
        so no caller can mutate another's.

        The declaration is what makes a multi-binding explicit. Members stay bound
        under their own keys, so registering two implementations under one key by
        accident still raises `DuplicateProviderError`, and the collection
        occupies `list[element]`, which no ordinary binding claims.

        A collection is an ordinary node in the validated graph: an unbound
        member, a member listed twice, two collections over one element and tag,
        a cycle through a collection, and a singleton that reaches a scoped
        member through one are all rejected by `Container.freeze()`. An empty
        collection is legal and resolves to an empty list.

        Args:
            element: The key each member provides. The collection is registered
                under a list of it. A string element registers `list['name']`,
                which resolves directly through `FrozenContainer.resolve` or
                ``frozen[list['name']]``, but cannot be written as a parameter
                annotation: `get_type_hints` treats the string inside
                ``list[...]`` as a forward reference and fails to resolve it.
            members: The bindings to gather, in the order they should appear.
            tag: Disambiguator when several collections share an element.
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.

        Returns:
            ``self``, for chaining.

        Example:
            ```pycon
            >>> from typing import Protocol
            >>> from depin import Container
            >>> class Handler(Protocol):
            ...     def run(self) -> str: ...
            >>> class Email:
            ...     def run(self) -> str:
            ...         return 'email'
            >>> class Sms:
            ...     def run(self) -> str:
            ...         return 'sms'
            >>> di = Container().bind(Email).bind(Sms).collect(Handler, [Email, Sms]).freeze()
            >>> [handler.run() for handler in di.resolve(list[Handler])]
            ['email', 'sms']

            ```
        """
        self._records.append(
            BindRecord(
                source=CollectionBinding(element=element, members=tuple(members)),
                scope=Scope.TRANSIENT,
                provides=None,
                tag=tag,
                condition=when,
            )
        )
        return self

    def decorate(
        self,
        key: ProviderKey,
        wrapper: type[object] | Callable[..., object],
        *,
        tag: str | None = None,
        when: Condition | None = None,
    ) -> Self:
        """Wrap an existing binding without changing its registration.

        Every consumer of ``key`` receives what ``wrapper`` returns, including
        consumers deep in the graph. The binding that was registered keeps its
        lifetime, its cache entry, and its teardown: it is built once, in the
        position it would have occupied undecorated, and the wrapper is built
        after it and torn down before it.

        ``wrapper`` declares one parameter whose key and tag are the decorated
        ones — that parameter receives the value being wrapped — and any number
        of further parameters, which are ordinary dependencies resolved from the
        graph. The wrapper takes no scope of its own: it runs at the lifetime of
        the binding it wraps.

        Decorators stack. Two calls over one key apply in registration order, so
        the last registered is the outermost.

        Args:
            key: The binding to wrap. A class, a `Token`, a string, or a
                parameterised generic.
            wrapper: A class or factory producing the decorated value. Any
                provider shape is accepted, async ones included; an async
                wrapper makes the key resolvable only through
                `FrozenContainer.aresolve`.
            tag: The decorated binding's tag, when it has one.
            when: Condition deciding whether this decorator enters the plan.
                A callable is evaluated inside `Container.freeze()`.

        Returns:
            ``self``, for chaining.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Store:
            ...     def get(self) -> str:
            ...         return 'plain'
            >>> class Loud:
            ...     def __init__(self, inner: Store) -> None:
            ...         self.inner = inner
            ...     def get(self) -> str:
            ...         return self.inner.get().upper()
            >>> di = Container().bind(Store).decorate(Store, Loud).freeze()
            >>> di[Store].get()
            'PLAIN'

            ```
        """
        # The scope recorded here is never read: `depin._core.decoration` gives every wrapper node
        # the scope of the binding it wraps.
        self._records.append(
            BindRecord(
                source=DecorateBinding(key=key, wrapper=wrapper),
                scope=Scope.TRANSIENT,
                provides=None,
                tag=tag,
                condition=when,
            )
        )
        return self

    def singleton(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
        when: Condition | None = None,
    ) -> ScopeDecorator:
        """Decorator form of ``bind(..., scope=Scope.SINGLETON)``.

        Args:
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.

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
        return ScopeDecorator(self._record_bind, Scope.SINGLETON, provides, tag, when)

    def scoped(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
        when: Condition | None = None,
    ) -> ScopeDecorator:
        """Decorator form of ``bind(..., scope=Scope.SCOPED)``.

        Args:
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.
        """
        return ScopeDecorator(self._record_bind, Scope.SCOPED, provides, tag, when)

    def transient(
        self,
        *,
        provides: type[object] | None = None,
        tag: str | None = None,
        when: Condition | None = None,
    ) -> ScopeDecorator:
        """Decorator form of ``bind(..., scope=Scope.TRANSIENT)``.

        Args:
            when: Condition deciding whether this binding enters the plan.
                A callable is evaluated inside `Container.freeze()`.
        """
        return ScopeDecorator(self._record_bind, Scope.TRANSIENT, provides, tag, when)

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
        when: Condition | None,
    ) -> None:
        self._records.append(BindRecord(source=source, scope=scope, provides=provides, tag=tag, condition=when))
