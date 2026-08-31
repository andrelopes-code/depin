"""The immutable runtime: resolve values, open scopes, inject, and override."""

import contextlib
import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from contextvars import ContextVar
from typing import overload

from depin._core import construct, injection, overrides
from depin._core.diagnostics import DependencyGraph, build_graph
from depin._core.markers import Token
from depin._core.render import render_tree
from depin._core.scope import MISSING, Scope, ScopeFrame, active_frame, optional_frame, push_frame
from depin._core.spec import ProviderKey, ProviderSpec, ResolutionPlan, fmt_key
from depin._core.teardown import Teardown
from depin._core.typeguards import is_provider_key
from depin.errors import AsyncInSyncContextError, CircularDependencyError, MissingProviderError


class _Constructing:
    __slots__ = ('cache_id', 'frame', 'parent')

    def __init__(self, frame: ScopeFrame, cache_id: object, parent: '_Constructing | None') -> None:
        self.frame = frame
        self.cache_id = cache_id
        self.parent = parent


_constructing: ContextVar[_Constructing | None] = ContextVar('depin_constructing', default=None)


class FrozenContainer:
    """Immutable, validated view of a dependency graph.

    Produced by `Container.freeze()`. Resolve values by key with `resolve()` /
    `aresolve()` or the ``frozen[key]`` shorthand, scope short-lived values with
    `scope()` / `ascope()`, wire functions with `inject()`, and substitute
    providers in tests with `override()`.

    The container registers no new providers; it holds only the singleton cache
    and the root scope. It is safe to share across threads and tasks: scopes are
    tracked per `contextvars.Context`, so concurrent requests never see each
    other's scoped instances, and construction of a cached provider is
    single-flighted across threads and event loops — a singleton is built
    exactly once no matter how many threads or tasks race for it.

    Example:
        ```pycon
        >>> from depin import Container
        >>> class Greeter:
        ...     def hello(self) -> str:
        ...         return 'hi'
        >>> di = Container().bind(Greeter).freeze()
        >>> di[Greeter].hello()
        'hi'

        ```
    """

    __slots__ = ('_plan', '_root')

    def __init__(self, plan: ResolutionPlan) -> None:
        self._plan = plan
        self._root = ScopeFrame()

    def __getitem__[T](self, key: type[T] | Token[T]) -> T:
        """Resolve ``key`` synchronously; shorthand for `resolve()`.

        Example:
            ```pycon
            >>> from depin import Container, Token
            >>> port = Token[int]('port')
            >>> di = Container().value(port, 8080).freeze()
            >>> di[port]
            8080

            ```
        """
        return self.resolve(key)

    def resolve[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> T:
        """Resolve a value by key, synchronously.

        Returns the cached singleton or scoped instance if present, otherwise
        builds it (resolving its dependencies first). Synchronous resolution cannot
        drive async providers: if ``key`` or anything it depends on is async, this
        raises rather than blocking an event loop — use `aresolve()` instead.

        Args:
            key: A class or `Token` to resolve.
            tag: Selects among providers registered under ``key`` with a tag.

        Raises:
            MissingProviderError: No provider is registered for ``key`` / ``tag``.
            AsyncInSyncContextError: The provider, or a dependency, is async.
            OutsideScopeError: ``key`` is scoped and no scope is active.
            CircularDependencyError: This context re-enters construction of the same cached provider.

        Example:
            ```pycon
            >>> from depin import Container
            >>> from depin.errors import MissingProviderError
            >>> di = Container().freeze()
            >>> try:
            ...     di.resolve(int)
            ... except MissingProviderError as exc:
            ...     print(exc)
            no provider for int (tag=None)

            ```
        """
        spec = self._lookup(key, tag)
        # spec.source is type-erased `object` in the plan; the runtime contract
        # (enforced by build_plan) is that providers return values matching the
        # static type of their declared key, so we restate the static type here.
        return self._resolve_sync(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]

    async def aresolve[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> T:
        """Resolve a value by key, asynchronously.

        The async counterpart to `resolve()`. Handles both sync and async
        providers, awaiting async factories, async generators, and async context
        managers. Concurrent resolutions of the same cached provider are
        single-flighted, so a singleton or scoped value is built exactly once even
        under concurrency.

        Args:
            key: A class or `Token` to resolve.
            tag: Selects among providers registered under ``key`` with a tag.

        Raises:
            MissingProviderError: No provider is registered for ``key`` / ``tag``.
            OutsideScopeError: ``key`` is scoped and no scope is active.
            CircularDependencyError: This task re-enters construction of the same cached provider.
        """
        spec = self._lookup(key, tag)
        # See the matching note in `resolve`: plan-level erasure of provider
        # return types forces a single documented widening at this boundary.
        return await self._resolve_async(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]

    @contextlib.contextmanager
    def scope(self) -> Generator[ScopeFrame]:
        """Open a synchronous scope for scoped providers and their teardown.

        Scoped providers resolved inside the ``with`` block are built once for the
        block and cached in the yielded frame. On exit, their teardowns run in
        reverse order of construction; if several fail, the errors are collected
        into an `ExceptionGroup` so no failure hides another. Singletons are
        unaffected — they live on the container, not the scope.

        Scopes nest: a scoped value built in an outer scope is reused inside a
        nested scope, not rebuilt. Open sibling scopes for independent instances.
        Use `ascope()` when any provider in the scope is async.

        Raises:
            TeardownError: An async provider left a teardown in this sync scope.

        Example:
            ```pycon
            >>> from collections.abc import Generator
            >>> from depin import Container, Scope
            >>> events: list[str] = []
            >>> class Conn: ...
            >>> def connect() -> Generator[Conn]:
            ...     events.append('open')
            ...     yield Conn()
            ...     events.append('close')
            >>> di = Container().bind(connect, scope=Scope.SCOPED).freeze()
            >>> with di.scope():
            ...     conn = di.resolve(Conn)
            >>> events
            ['open', 'close']

            ```
        """
        with push_frame() as frame:
            try:
                yield frame
            finally:
                frame.drain_sync()

    @contextlib.asynccontextmanager
    async def ascope(self) -> AsyncGenerator[ScopeFrame]:
        """Open an asynchronous scope; the async counterpart to `scope()`.

        Required when scoped providers are async (async factories, async
        generators, async context managers). Teardowns — sync and async alike —
        run in reverse order on exit, with failures collected into an
        `ExceptionGroup`. The per-request scope opened by the FastAPI integration
        is an ``ascope``.
        """
        with push_frame() as frame:
            try:
                yield frame
            finally:
                await frame.drain_async()

    def close(self) -> None:
        """Tear down singleton providers that own lifecycle resources, synchronously.

        Drains the root scope, running the teardown half of every singleton
        generator / context-manager provider in reverse order of construction.
        Call this once on shutdown of a synchronous application. Scoped providers
        do not need it — they are drained when their `scope()` block exits.
        Failures are collected into an `ExceptionGroup`.

        Raises:
            TeardownError: A singleton is an async provider; use `aclose()`.

        Example:
            ```pycon
            >>> from collections.abc import Generator
            >>> from depin import Container
            >>> events: list[str] = []
            >>> class Pool: ...
            >>> def pool() -> Generator[Pool]:
            ...     events.append('open')
            ...     yield Pool()
            ...     events.append('close')
            >>> di = Container().bind(pool).freeze()
            >>> _ = di[Pool]
            >>> di.close()
            >>> events
            ['open', 'close']

            ```
        """
        self._root.drain_sync()

    async def aclose(self) -> None:
        """Tear down singleton providers that own lifecycle resources, asynchronously.

        The async counterpart to `close()`, and the one to call when any
        singleton is an async provider. Drains the root scope in reverse order of
        construction, collecting failures into an `ExceptionGroup`.
        """
        await self._root.drain_async()

    @overload
    def inject[**P, R](self, fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]: ...
    @overload
    def inject[**P, R](self, fn: Callable[P, R]) -> Callable[P, R]: ...
    def inject(self, fn: Callable[..., object]) -> Callable[..., object]:
        """Wrap a function so parameters defaulting to ``injected(...)`` are filled.

        Returns a wrapper that, on each call, resolves every parameter whose
        default is `injected()` and leaves the rest to the caller.
        Already-supplied arguments are never overridden, so an injected parameter
        can still be passed explicitly (handy in tests). The wrapper preserves the
        sync/async nature of ``fn``. Injected keys are validated at decoration
        time, not call time: decorating raises immediately if a marked key is
        unregistered. Because the markers sit in default position, injected
        parameters must follow non-default ones or be keyword-only.

        Raises:
            MissingProviderError: A parameter requests an unregistered key.

        Example:
            ```pycon
            >>> from depin import Container, injected
            >>> class Repo:
            ...     def count(self) -> int:
            ...         return 3
            >>> di = Container().bind(Repo).freeze()
            >>> @di.inject
            ... def handler(label: str, repo: Repo = injected(Repo)) -> str:
            ...     return f'{label}={repo.count()}'
            >>> handler(label='n')
            'n=3'

            ```
        """
        sig = inspect.signature(fn)
        injectables = injection.collect(sig, self._is_registered)
        return injection.wrap(fn, sig, injectables, self._resolve_any, self._aresolve_any)

    @contextlib.contextmanager
    def override[T](
        self,
        key: type[T] | Token[T],
        replacement: T,
        *,
        tag: str | None = None,
    ) -> Generator['FrozenContainer']:
        """Temporarily replace a provider's value within a ``with`` block.

        Inside the block, every resolution of ``key`` (and ``tag``) returns
        ``replacement`` instead of the registered provider — including
        resolutions deep in the graph, as a dependency of another provider, not
        only top-level lookups. If ``replacement`` is a callable and not a class
        it is invoked as a factory per resolution; otherwise it is returned
        as-is. The override is bound to the current `contextvars.Context` and
        undone on exit, so concurrent contexts are unaffected; overrides nest,
        innermost wins. Primarily a testing seam — swap a real dependency for a
        fake without rebuilding the container.

        Raises:
            MissingProviderError: ``key`` is not a valid provider key type.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Clock:
            ...     def now(self) -> str:
            ...         return 'real'
            >>> class FakeClock:
            ...     def now(self) -> str:
            ...         return 'fake'
            >>> di = Container().bind(Clock).freeze()
            >>> with di.override(Clock, FakeClock()):
            ...     di[Clock].now()
            'fake'
            >>> di[Clock].now()
            'real'

            ```
        """
        if not is_provider_key(key):
            raise MissingProviderError(f'cannot override {key!r}: not a valid key type')
        with overrides.pushed(key, tag, replacement):
            yield self

    def graph(self) -> DependencyGraph:
        """Return the validated dependency graph as data.

        The view describes the plan `Container.freeze()` validated. An active
        `override()` does not change it, so the graph and both of its exports
        are the same on every call and in every context.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Config: ...
            >>> class Service:
            ...     def __init__(self, config: Config) -> None: ...
            >>> di = Container().bind(Config).bind(Service).freeze()
            >>> len(di.graph().nodes)
            2
            >>> di.graph().node(Service).dependencies[0].parameter
            'config'

            ```
        """
        return build_graph(self._plan)

    def explain(self, key: ProviderKey, *, tag: str | None = None) -> str:
        """Return the resolution tree below a key, as text.

        Each line names the parameter that requires the node, the node's key,
        its scope and provider shape, `async` when the node needs asynchronous
        resolution, and its tag when it has one. A subtree already shown is
        marked rather than repeated. A parameter that nothing provides is marked
        ``(unbound, default)`` when it carries a default, or ``(unbound, optional)``
        when it does not but admits `None`.

        A key no binding provides returns the line `MissingProviderError`
        carries for it, including the resolution chain when some provider
        requires that key. Like `graph()`, the output describes the validated
        plan, not an active `override()`.

        Raises:
            MissingProviderError: The value cannot be a provider key at all.
                An unregistered key of a valid type is described in the
                returned text instead.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Config: ...
            >>> class Service:
            ...     def __init__(self, config: Config) -> None: ...
            >>> di = Container().bind(Config).bind(Service).freeze()
            >>> print(di.explain(Service))
            Service  [singleton, class]
              config: Config  [singleton, class]

            ```
        """
        if not is_provider_key(key):
            raise MissingProviderError(f'cannot look up provider for {key!r}: not a valid key type')
        return render_tree(self.graph(), key, tag)

    def _is_registered(self, key: ProviderKey, tag: str | None) -> bool:
        return (key, tag) in self._plan.by_key

    def _resolve_any(self, key: ProviderKey, tag: str | None) -> object:
        return self._resolve_sync(self._lookup(key, tag))

    async def _aresolve_any(self, key: ProviderKey, tag: str | None) -> object:
        return await self._resolve_async(self._lookup(key, tag))

    def _lookup(self, key: object, tag: str | None) -> ProviderSpec:
        if not is_provider_key(key):
            raise MissingProviderError(f'cannot look up provider for {key!r}: not a valid key type')
        spec = self._lookup_optional(key, tag)
        if spec is None:
            raise MissingProviderError(f'no provider for {fmt_key(key)} (tag={tag!r})')
        return spec

    def _lookup_optional(self, key: ProviderKey, tag: str | None) -> ProviderSpec | None:
        """Resolve ``(key, tag)`` to a spec, honouring any active override.

        Dependency resolution routes through here rather than reading
        ``self._plan.by_key`` directly, so an ``override`` substitutes a key
        everywhere it appears in the graph — not only at the top-level lookup.
        """
        override = overrides.active(key, tag)
        if override is not None:
            return override
        return self._plan.by_key.get((key, tag))

    def _cache_target(self, spec: ProviderSpec) -> ScopeFrame | None:
        """Return the frame that caches this spec, or None for transient scope."""
        if spec.scope is Scope.SINGLETON:
            return self._root
        if spec.scope is Scope.SCOPED:
            return active_frame()
        return None

    def _resolve_sync(self, spec: ProviderSpec) -> object:
        if spec.needs_async:
            raise AsyncInSyncContextError(f'{fmt_key(spec.key)} requires async resolution; call aresolve() instead')
        if spec.scope is Scope.TRANSIENT:
            return self._construct_sync(spec)
        if spec.scope is Scope.SINGLETON:
            return self._resolve_cached_sync(spec, self._root)
        return self._resolve_cached_sync(spec, active_frame())

    def _resolve_cached_sync(self, spec: ProviderSpec, frame: ScopeFrame) -> object:
        cache_id = (spec.key, spec.tag)
        while True:
            cached, claim = frame.claim_cached(cache_id)
            if cached is not MISSING:
                return cached
            if not frame.is_leader(claim) or (frame.parent is not None and self._is_constructing(frame, cache_id)):
                if frame.is_leader(claim) and claim is not None:
                    follower = frame.abort(cache_id, claim)
                    if follower is not None:
                        follower.finish()
                if self._is_constructing(frame, cache_id):
                    raise CircularDependencyError(
                        f'{fmt_key(spec.key)} is already constructing in this context; '
                        'resolve a different dependency or break the recursive provider call'
                    )
            if not frame.is_leader(claim):
                if claim is not None:
                    frame.wait_sync(claim)
                continue
            leader = claim
            token = _constructing.set(_Constructing(frame, cache_id, _constructing.get()))
            try:
                kwargs = self._resolve_params_sync(spec) if spec.params else {}
                value = construct.sync(spec, kwargs, self._teardown_sink(spec), self._read_frame)
            except BaseException:
                follower = frame.abort(cache_id, leader)
                if follower is not None:
                    follower.finish()
                raise
            finally:
                _constructing.reset(token)
            follower = frame.publish(cache_id, leader, value)
            if follower is not None:
                follower.finish()
            return value

    async def _resolve_async(self, spec: ProviderSpec) -> object:
        frame = self._cache_target(spec)
        if frame is None:
            return await self._construct_async(spec)
        cache_id = (spec.key, spec.tag)
        while True:
            cached, claim = frame.claim_cached(cache_id)
            if cached is not MISSING:
                return cached
            if not frame.is_leader(claim) or (frame.parent is not None and self._is_constructing(frame, cache_id)):
                if frame.is_leader(claim) and claim is not None:
                    follower = frame.abort(cache_id, claim)
                    if follower is not None:
                        follower.finish()
                if self._is_constructing(frame, cache_id):
                    raise CircularDependencyError(
                        f'{fmt_key(spec.key)} is already constructing in this context; '
                        'resolve a different dependency or break the recursive provider call'
                    )
            if not frame.is_leader(claim):
                if claim is not None:
                    await frame.wait_async(claim)
                continue
            leader = claim
            token = _constructing.set(_Constructing(frame, cache_id, _constructing.get()))
            try:
                kwargs = await self._resolve_params_async(spec) if spec.params else {}
                value = await construct.asynchronous(spec, kwargs, self._teardown_sink(spec), self._read_frame)
            except BaseException:
                follower = frame.abort(cache_id, leader)
                if follower is not None:
                    follower.finish()
                raise
            finally:
                _constructing.reset(token)
            follower = frame.publish(cache_id, leader, value)
            if follower is not None:
                follower.finish()
            return value

    def _is_constructing(self, frame: ScopeFrame, cache_id: object) -> bool:
        current = _constructing.get()
        while current is not None:
            if current.cache_id == cache_id:
                candidate: ScopeFrame | None = frame
                while candidate is not None:
                    if current.frame is candidate:
                        return True
                    candidate = candidate.parent
            current = current.parent
        return False

    def _construct_sync(self, spec: ProviderSpec) -> object:
        kwargs = self._resolve_params_sync(spec) if spec.params else {}
        return construct.sync(spec, kwargs, self._teardown_sink(spec), self._read_frame)

    async def _construct_async(self, spec: ProviderSpec) -> object:
        kwargs = await self._resolve_params_async(spec) if spec.params else {}
        return await construct.asynchronous(spec, kwargs, self._teardown_sink(spec), self._read_frame)

    def _teardown_sink(self, spec: ProviderSpec) -> Callable[[Teardown], None]:
        """Register a teardown on the frame that owns this spec, so it drains with it.

        The frame is looked up only when a teardown actually appears: a transient
        provider has no frame, and resolving one outside a scope must not fail
        merely because the sink was prepared.
        """

        def register(record: Teardown) -> None:
            self._frame_for(spec).add_teardown(record)

        return register

    def _resolve_params_sync(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        frame = optional_frame()
        for param in spec.params:
            if frame is not None and param.key in frame:
                out[param.name] = frame.get(param.key)
                continue
            dep = self._lookup_optional(param.key, param.tag)
            if dep is None:
                if param.has_default:
                    continue
                if param.optional:
                    out[param.name] = None
                    continue
                raise MissingProviderError(f"missing provider for parameter '{param.name}' of {fmt_key(spec.key)}")
            out[param.name] = self._resolve_sync(dep)
        return out

    async def _resolve_params_async(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        frame = optional_frame()
        for param in spec.params:
            if frame is not None and param.key in frame:
                out[param.name] = frame.get(param.key)
                continue
            dep = self._lookup_optional(param.key, param.tag)
            if dep is None:
                if param.has_default:
                    continue
                if param.optional:
                    out[param.name] = None
                    continue
                raise MissingProviderError(f"missing provider for parameter '{param.name}' of {fmt_key(spec.key)}")
            out[param.name] = await self._resolve_async(dep)
        return out

    def _frame_for(self, spec: ProviderSpec) -> ScopeFrame:
        if spec.scope is Scope.SINGLETON:
            return self._root
        return active_frame()

    def _read_frame(self, spec: ProviderSpec) -> object:
        value = active_frame().lookup(spec.key)
        if value is MISSING:
            raise MissingProviderError(
                f'no value in the active scope for {fmt_key(spec.key)}; '
                'a key declared with scope_value() must be supplied by whoever opens the scope, '
                'with frame.provide(key, value)'
            )
        return value
