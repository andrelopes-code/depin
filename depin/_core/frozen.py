"""The immutable runtime: resolve values, open scopes, inject, and override."""

import asyncio
import contextlib
import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from contextvars import ContextVar
from contextvars import Token as ContextToken
from dataclasses import dataclass
from typing import TypeGuard, final, overload

from depin._core import construct, injection, overrides
from depin._core.diagnostics import DependencyGraph, build_graph
from depin._core.health import (
    HealthCheck,
    HealthReport,
    HealthResult,
    checked_specs,
    declared_checks,
    reject_async_checks,
    run_check,
    run_check_async,
)
from depin._core.lifecycle import LifecycleState, create_lifecycle_gate
from depin._core.markers import Token
from depin._core.render import render_tree
from depin._core.scope import MISSING, Scope, ScopeFrame, active_frame, optional_frame, push_frame
from depin._core.spec import ParamSpec, ProviderKey, ProviderSpec, ResolutionPlan, fmt_key
from depin._core.teardown import Teardown
from depin._core.typeguards import is_provider_key
from depin._core.warmup import WarmupReport, reject_async_singletons, singleton_specs, warmup_report
from depin.errors import (
    AsyncInSyncContextError,
    CircularDependencyError,
    ContainerClosedError,
    ContainerLifecycleError,
    DepinError,
    MissingProviderError,
)


class _Constructing:
    __slots__ = ('cache_id', 'frame', 'parent')

    def __init__(self, frame: ScopeFrame, cache_id: object, parent: '_Constructing | None') -> None:
        self.frame = frame
        self.cache_id = cache_id
        self.parent = parent


_constructing: ContextVar[_Constructing | None] = ContextVar('depin_constructing', default=None)
_PENDING = object()
_RECURSIVE_PLAN_LIMIT = 256


@dataclass(slots=True)
class _PendingResolution:
    spec: ProviderSpec
    frame: ScopeFrame | None
    cache_id: object | None
    leader: object | None
    token: ContextToken[_Constructing | None] | None
    kwargs: dict[str, object]
    param_index: int = 0
    waiting_name: str | None = None


@final
class ProviderOverride:
    """A selected provider override that can receive a temporary replacement.

    Obtain one from `FrozenContainer.override()`, then call `using()` to enter
    the override context. A callable replacement that is not a class is invoked
    as a transient factory; every other replacement is returned as-is.

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
        >>> with di.override(Clock).using(FakeClock()):
        ...     di[Clock].now()
        'fake'

        ```
    """

    __slots__ = ('_container', '_key', '_tag')

    def __init__(self, container: 'FrozenContainer', key: ProviderKey, tag: str | None) -> None:
        self._container = container
        self._key = key
        self._tag = tag

    def using(self, replacement: object, /) -> contextlib.AbstractContextManager['FrozenContainer']:
        """Temporarily replace the selected provider with ``replacement``.

        The returned context manager is bound to the current `contextvars.Context`,
        so concurrent tasks and threads do not see the replacement. Overrides
        nest and the innermost one wins.

        Returns:
            A context manager yielding the container while this replacement is active.
        """
        return self._using(replacement)

    @contextlib.contextmanager
    def _using(self, replacement: object, /) -> Generator['FrozenContainer']:
        with overrides.pushed(self._key, self._tag, replacement):
            yield self._container


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

    __slots__ = ('_lifecycle', '_plan', '_root', '_validate_key')

    def __init__(self, plan: ResolutionPlan) -> None:
        self._plan = plan
        self._lifecycle = create_lifecycle_gate()
        self._root = ScopeFrame(lifecycle=self._lifecycle)
        self._validate_key: Callable[[object], TypeGuard[ProviderKey]] = is_provider_key
        self._lifecycle.on_quiesce = self._quiesce_resolution
        self._lifecycle.on_reopen = self._resume_resolution

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
        if spec.scope is Scope.TRANSIENT:
            if spec.needs_async:
                raise AsyncInSyncContextError(f'{fmt_key(spec.key)} requires async resolution; call aresolve() instead')
            if len(self._plan.order) >= _RECURSIVE_PLAN_LIMIT:
                resolved = self._resolve_sync_iterative(spec)
            else:
                kwargs = self._resolve_params_sync(spec) if spec.params else {}
                resolved = construct.sync(spec, kwargs, self._teardown_sink(spec), self._read_frame)
        else:
            resolved = self._resolve_sync(spec)
        # spec.source is type-erased `object` in the plan; the runtime contract
        # (enforced by build_plan) is that providers return values matching the
        # static type of their declared key, so we restate the static type here.
        return resolved  # type: ignore[return-value]  # pyright: ignore[reportReturnType]

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
        resolved = await (
            self._resolve_async_iterative(spec)
            if spec.scope is Scope.TRANSIENT and len(self._plan.order) >= _RECURSIVE_PLAN_LIMIT
            else self._resolve_async(spec)
        )
        return resolved  # type: ignore[return-value]  # pyright: ignore[reportReturnType]

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
            ExceptionGroup: One or more teardowns failed. Protocol violations,
                including an async teardown in this synchronous scope, appear as
                `TeardownError` members of the group.

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
        lifecycle = self._lifecycle
        with lifecycle.mutex:
            if lifecycle.state is LifecycleState.CLOSED:
                raise ContainerClosedError(
                    'container is closed; build a new FrozenContainer before resolving or opening a scope'
                )
            if lifecycle.state is not LifecycleState.OPEN:
                raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
            lifecycle.active += 1
        with push_frame(self._root) as frame:
            try:
                yield frame
            finally:
                try:
                    frame.drain_sync()
                finally:
                    with lifecycle.mutex:
                        lifecycle.active -= 1
                        wake = lifecycle.active == 0 and bool(lifecycle.gate_waiters)
                    if wake:
                        lifecycle.wake_waiters()

    @contextlib.asynccontextmanager
    async def ascope(self) -> AsyncGenerator[ScopeFrame]:
        """Open an asynchronous scope; the async counterpart to `scope()`.

        Required when scoped providers are async (async factories, async
        generators, async context managers). Teardowns — sync and async alike —
        run in reverse order on exit, with failures collected into an
        `ExceptionGroup`. The per-request scope opened by the FastAPI integration
        is an ``ascope``.

        Raises:
            ExceptionGroup: One or more teardowns failed. A generator provider
                that violates its teardown protocol appears as a `TeardownError`
                member of the group.
        """
        lifecycle = self._lifecycle
        with lifecycle.mutex:
            if lifecycle.state is LifecycleState.CLOSED:
                raise ContainerClosedError(
                    'container is closed; build a new FrozenContainer before resolving or opening a scope'
                )
            if lifecycle.state is not LifecycleState.OPEN:
                raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
            lifecycle.active += 1
            lifecycle.active_async += 1
        with push_frame(self._root) as frame:
            try:
                yield frame
            finally:
                try:
                    await frame.drain_async()
                finally:
                    with lifecycle.mutex:
                        lifecycle.active -= 1
                        lifecycle.active_async -= 1
                        wake = lifecycle.active == 0 and bool(lifecycle.gate_waiters)
                    if wake:
                        lifecycle.wake_waiters()

    def close(self) -> None:
        """Tear down singleton providers that own lifecycle resources, synchronously.

        Drains the root scope, running the teardown half of every singleton
        generator / context-manager provider in reverse order of construction.
        Call this once on shutdown of a synchronous application. Scoped providers
        do not need it — they are drained when their `scope()` block exits.
        Failures are collected into an `ExceptionGroup`.

        Raises:
            AsyncInSyncContextError: A singleton requires an async teardown;
                use `aclose()` instead.
            ExceptionGroup: One or more synchronous teardowns failed. A
                generator provider that violates its teardown protocol appears
                as a `TeardownError` member of the group.

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
        if optional_frame(self._root) is not None:
            raise ContainerLifecycleError(
                'cannot close this container from inside its active resolution or scope; '
                'exit that operation, then call close(), or await aclose() from outside it'
            )
        current = _constructing.get()
        while current is not None:
            if current.frame is self._root:
                raise ContainerLifecycleError(
                    'cannot close this container from inside its active resolution or scope; '
                    'exit that operation, then call close(), or await aclose() from outside it'
                )
            current = current.parent
        if self._lifecycle.begin_sync_close(self._root.has_async_teardown()):
            try:
                self._root.drain_sync()
            finally:
                self._lifecycle.close()

    async def aclose(self) -> None:
        """Tear down singleton providers that own lifecycle resources, asynchronously.

        The async counterpart to `close()`, and the one to call when any
        singleton is an async provider. Drains the root scope in reverse order of
        construction, collecting failures into an `ExceptionGroup`.

        Raises:
            ExceptionGroup: One or more teardowns failed. A generator provider
                that violates its teardown protocol appears as a `TeardownError`
                member of the group.
        """
        if optional_frame(self._root) is not None:
            raise ContainerLifecycleError(
                'cannot close this container from inside its active resolution or scope; '
                'exit that operation, then call close(), or await aclose() from outside it'
            )
        current = _constructing.get()
        while current is not None:
            if current.frame is self._root:
                raise ContainerLifecycleError(
                    'cannot close this container from inside its active resolution or scope; '
                    'exit that operation, then call close(), or await aclose() from outside it'
                )
            current = current.parent
        if not self._lifecycle.begin_async_close():
            await self._lifecycle.join()
            return
        try:
            await self._lifecycle.wait_until_quiet()
            await self._root.wait_until_idle()
        except asyncio.CancelledError:
            self._lifecycle.reopen()
            raise
        self._lifecycle.begin_draining()
        drain = asyncio.create_task(self._root.drain_async())
        cancelled = False
        try:
            await asyncio.shield(drain)
        except asyncio.CancelledError:
            cancelled = True
            await asyncio.shield(drain)
        finally:
            self._lifecycle.close()
        if cancelled:
            raise asyncio.CancelledError

    def reset(self) -> None:
        """Tear down every built singleton and drop the cache, so the next resolution rebuilds.

        The difference from `close()` is what happens afterwards: `close()`
        drains the singletons and leaves them cached, while `reset()` drops
        them, so the container is usable again and builds fresh values on
        demand. Scoped and transient providers are untouched — a scoped value
        belongs to its scope, and a transient one is never cached.

        Primarily a testing seam: it is what makes an `override()` reach a
        consumer that was already built, and it is what the `depin.ext.pytest`
        fixtures use. Do not call it while another thread or task may be
        resolving through this container — it drops the cache without
        coordinating with an in-flight construction, so one racing with a
        resolution can hand a caller a value whose teardown already ran.

        Raises:
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported, and the cache is dropped either way. Protocol
                violations, including an async teardown in this synchronous
                drain, appear as `TeardownError` members; use `areset()` for
                async providers.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Clock: ...
            >>> di = Container().bind(Clock).freeze()
            >>> first = di[Clock]
            >>> di.reset()
            >>> di[Clock] is first
            False

            ```
        """
        state = self._lifecycle.state
        if state is not LifecycleState.OPEN:
            if state is LifecycleState.CLOSED:
                raise ContainerClosedError(
                    'container is closed; build a new FrozenContainer before resolving or opening a scope'
                )
            raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
        self._root.drop_sync()

    async def areset(self) -> None:
        """Tear down every built singleton and drop the cache; the counterpart to `reset()`.

        The one to call when any singleton is an async provider. Otherwise
        identical, including the same caveat about calling it while another
        thread or task may be resolving through this container.

        Raises:
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported, and the cache is dropped either way. A generator
                provider that violates its teardown protocol appears as a
                `TeardownError` member of the group.
        """
        state = self._lifecycle.state
        if state is not LifecycleState.OPEN:
            if state is LifecycleState.CLOSED:
                raise ContainerClosedError(
                    'container is closed; build a new FrozenContainer before resolving or opening a scope'
                )
            raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
        await self._root.drop_async()

    def warmup(self) -> WarmupReport:
        """Construct every singleton now, instead of on first resolution.

        Walks the plan in resolution order, building each singleton that is not
        built already, so a provider that fails does so at startup rather than
        on the first request that needs it. Scoped and transient providers are
        untouched: a scoped value belongs to a scope, and a transient one is
        never cached. Calling it twice constructs nothing the second time.

        A failure propagates unchanged — a container with some singletons built
        and one failed is a startup to abort, not a state to report.

        Raises:
            AsyncInSyncContextError: Some singleton needs async resolution.
                Nothing is constructed before this is raised; use `awarmup()`.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Config: ...
            >>> class Service:
            ...     def __init__(self, config: Config) -> None: ...
            >>> di = Container().bind(Config).bind(Service).freeze()
            >>> report = di.warmup()
            >>> len(report.constructed), len(report.cached)
            (2, 0)

            ```
        """
        lifecycle = self._lifecycle
        with lifecycle.mutex:
            if lifecycle.state is LifecycleState.CLOSED:
                raise ContainerClosedError(
                    'container is closed; build a new FrozenContainer before resolving or opening a scope'
                )
            if lifecycle.state is not LifecycleState.OPEN:
                raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
            lifecycle.active += 1
        try:
            return self._warmup_sync()
        finally:
            with lifecycle.mutex:
                lifecycle.active -= 1
                wake = lifecycle.active == 0 and bool(lifecycle.gate_waiters)
            if wake:
                lifecycle.wake_waiters()

    def _warmup_sync(self) -> WarmupReport:
        specs = singleton_specs(self._plan)
        reject_async_singletons(specs)
        constructed: list[ProviderSpec] = []
        cached: list[ProviderSpec] = []
        for spec in specs:
            if self._is_cached(spec):
                cached.append(spec)
                continue
            selected = self._lookup_optional(spec.key, spec.tag)
            if selected is None:
                raise MissingProviderError(f'no provider for {fmt_key(spec.key)} (tag={spec.tag!r})')
            _ = (
                self._resolve_root_cached_sync(spec, allow_iterative=False)
                if selected is spec
                else self._resolve_sync(selected)
            )
            constructed.append(spec)
        return warmup_report(self.graph(), constructed, cached)

    async def awarmup(self) -> WarmupReport:
        """Construct every singleton now; the async counterpart to `warmup()`.

        Drives async singletons as well as sync ones, so it is what an ASGI
        lifespan calls. Otherwise identical: resolution order, the same report,
        and a failure that propagates unchanged.

        Raises:
            CircularDependencyError: This task re-enters construction of the
                same cached provider.
        """
        lifecycle = self._lifecycle
        with lifecycle.mutex:
            if lifecycle.state is LifecycleState.CLOSED:
                raise ContainerClosedError(
                    'container is closed; build a new FrozenContainer before resolving or opening a scope'
                )
            if lifecycle.state is not LifecycleState.OPEN:
                raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
            lifecycle.active += 1
            lifecycle.active_async += 1
        try:
            return await self._warmup_async()
        finally:
            with lifecycle.mutex:
                lifecycle.active -= 1
                lifecycle.active_async -= 1
                wake = lifecycle.active == 0 and bool(lifecycle.gate_waiters)
            if wake:
                lifecycle.wake_waiters()

    async def _warmup_async(self) -> WarmupReport:
        specs = singleton_specs(self._plan)
        constructed: list[ProviderSpec] = []
        cached: list[ProviderSpec] = []
        for spec in specs:
            if self._is_cached(spec):
                cached.append(spec)
                continue
            _ = await self._aresolve_any(spec.key, spec.tag)
            constructed.append(spec)
        return warmup_report(self.graph(), constructed, cached)

    def checks(self) -> tuple[HealthCheck, ...]:
        """Return the verification callables the bindings declared, as data.

        Resolves nothing and runs nothing: this is the declaration, in
        resolution order. `health()` and `ahealth()` are what run them.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Database: ...
            >>> def ping(db: Database) -> None: ...
            >>> di = Container().bind(Database, check=ping).freeze()
            >>> [check.key.__qualname__ for check in di.checks()]
            ['Database']

            ```
        """
        return declared_checks(checked_specs(self._plan))

    def health(self) -> HealthReport:
        """Run every declared check and report what each said.

        Each check receives the value its provider resolves to, and is healthy
        unless it raises or returns ``False``. Every check runs: one failure
        never hides another, and a raised exception is carried on its
        `HealthResult` rather than propagating. An error raised while
        *resolving* a provider does propagate — a container that cannot build a
        provider is misused, not unhealthy.

        Raises:
            AsyncInSyncContextError: Some check needs an event loop, because its
                provider is async or the check is. Nothing runs before this is
                raised; use `ahealth()`.
            InvalidProviderError: A check returned an awaitable.
            OutsideScopeError: A check's provider is scoped and no scope is active.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Database:
            ...     ready = False
            >>> def ping(db: Database) -> bool:
            ...     return db.ready
            >>> di = Container().bind(Database, check=ping).freeze()
            >>> di.health().healthy
            False

            ```
        """
        ticket = self._lifecycle.admit('health', asynchronous=False)
        try:
            return self._health_sync()
        finally:
            self._lifecycle.release(ticket)

    def _health_sync(self) -> HealthReport:
        specs = checked_specs(self._plan)
        reject_async_checks(specs)
        return HealthReport(tuple(run_check(spec, self._resolve_any(spec.key, spec.tag)) for spec in specs))

    async def ahealth(self) -> HealthReport:
        """Run every declared check inside an event loop; the counterpart to `health()`.

        Drives async providers and `async def` checks. Otherwise identical.

        Raises:
            OutsideScopeError: A check's provider is scoped and no scope is active.
            CircularDependencyError: This task re-enters construction of the
                same cached provider.
        """
        ticket = self._lifecycle.admit('ahealth', asynchronous=True)
        try:
            return await self._health_async()
        finally:
            self._lifecycle.release(ticket)

    async def _health_async(self) -> HealthReport:
        specs = checked_specs(self._plan)
        results: list[HealthResult] = []
        for spec in specs:
            value = await self._aresolve_any(spec.key, spec.tag)
            results.append(await run_check_async(spec, value))
        return HealthReport(tuple(results))

    @overload
    def inject[**P, R](self, fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]: ...
    @overload
    def inject[**P, R](self, fn: Callable[P, R]) -> Callable[P, R]: ...
    def inject(self, fn: Callable[..., object]) -> Callable[..., object]:
        """Wrap a function so parameters defaulting to ``injected`` are filled.

        Returns a wrapper that, on each call, resolves every parameter whose
        default is `injected` and leaves the rest to the caller. The key comes
        from the parameter's annotation, in the same grammar a provider's
        parameters use: a class, ``Annotated[T, Tag(...)]``,
        ``Annotated[T, Named(...)]``, or ``T | None`` for a dependency that may
        be absent, which is filled with ``None`` when nothing provides it.
        Already-supplied arguments are never overridden, so an injected parameter
        can still be passed explicitly (handy in tests). The wrapper preserves the
        sync/async nature of ``fn``. Injected keys are validated at decoration
        time, not call time: decorating raises immediately if a marked key is
        unregistered. Because the marker sits in default position, injected
        parameters must follow non-default ones or be keyword-only.

        Raises:
            InvalidProviderError: A marked parameter carries no annotation, or
                one whose names do not resolve.
            MissingProviderError: A parameter requests an unregistered key and
                its annotation does not admit ``None``.

        Example:
            ```pycon
            >>> from depin import Container, injected
            >>> class Repo:
            ...     def count(self) -> int:
            ...         return 3
            >>> di = Container().bind(Repo).freeze()
            >>> @di.inject
            ... def handler(label: str, repo: Repo = injected) -> str:
            ...     return f'{label}={repo.count()}'
            >>> handler(label='n')
            'n=3'

            ```
        """
        sig = inspect.signature(fn)
        injectables = injection.collect(fn, sig, self._is_registered)
        return injection.wrap(fn, sig, injectables, self._resolve_any, self._aresolve_any)

    def override(self, key: ProviderKey, /, *, tag: str | None = None) -> ProviderOverride:
        """Select a provider to temporarily replace with `ProviderOverride.using()`.

        `using()` supplies a replacement for one block. Every resolution of the
        selected key and tag returns that replacement during the block, including
        resolutions deep in the graph. The override is bound to the current
        `contextvars.Context`, so concurrent contexts are unaffected; overrides
        nest and the innermost one wins.

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
            >>> with di.override(Clock).using(FakeClock()):
            ...     di[Clock].now()
            'fake'
            >>> di[Clock].now()
            'real'

            ```
        """
        if not is_provider_key(key):
            raise MissingProviderError(f'cannot override {key!r}: not a valid key type')
        return ProviderOverride(self, key, tag)

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

        When the key is registered behind a condition that did not hold, the
        line says so, in the same wording `Container.freeze()` uses.

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
        return render_tree(self.graph(), key, tag, self._plan.inactive)

    def _is_registered(self, key: ProviderKey, tag: str | None) -> bool:
        return (key, tag) in self._plan.by_key

    def _resolve_any(self, key: ProviderKey, tag: str | None) -> object:
        spec = self._lookup(key, tag)
        if spec.scope is not Scope.TRANSIENT:
            return self._resolve_sync(spec)
        if spec.needs_async:
            raise AsyncInSyncContextError(f'{fmt_key(spec.key)} requires async resolution; call aresolve() instead')
        if len(self._plan.order) >= _RECURSIVE_PLAN_LIMIT:
            return self._resolve_sync_iterative(spec)
        kwargs = self._resolve_params_sync(spec) if spec.params else {}
        return construct.sync(spec, kwargs, self._teardown_sink(spec), self._read_frame)

    async def _aresolve_any(self, key: ProviderKey, tag: str | None) -> object:
        spec = self._lookup(key, tag)
        return await (
            self._resolve_async_iterative(spec)
            if spec.scope is Scope.TRANSIENT and len(self._plan.order) >= _RECURSIVE_PLAN_LIMIT
            else self._resolve_async(spec)
        )

    def _lookup(self, key: object, tag: str | None) -> ProviderSpec:
        if not self._validate_key(key):
            raise MissingProviderError(f'cannot look up provider for {key!r}: not a valid key type')
        spec = self._lookup_optional(key, tag)
        if spec is None:
            raise MissingProviderError(f'no provider for {fmt_key(key)} (tag={tag!r})')
        return spec

    def _quiesce_resolution(self) -> None:
        self._validate_key = self._validate_quiescing

    def _resume_resolution(self) -> None:
        self._validate_key = is_provider_key

    def _validate_quiescing(self, key: object) -> TypeGuard[ProviderKey]:
        if self._lifecycle.state is LifecycleState.CLOSED:
            raise ContainerClosedError(
                'container is closed; build a new FrozenContainer before resolving or opening a scope'
            )
        if optional_frame(self._root) is not None or _constructing.get() is not None:
            return is_provider_key(key)
        raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')

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

    def _is_cached(self, spec: ProviderSpec) -> bool:
        return self._root.lookup((spec.key, spec.tag)) is not MISSING

    def _resolve_sync(self, spec: ProviderSpec) -> object:
        if spec.needs_async:
            raise AsyncInSyncContextError(f'{fmt_key(spec.key)} requires async resolution; call aresolve() instead')
        if spec.scope is Scope.TRANSIENT:
            return self._construct_sync(spec)
        if spec.scope is Scope.SINGLETON:
            return self._resolve_root_cached_sync(spec)
        return self._resolve_cached_sync(spec, active_frame(self._root))

    def _resolve_root_cached_sync(self, spec: ProviderSpec, *, allow_iterative: bool = True) -> object:
        cache_id = (spec.key, spec.tag)
        while True:
            cached, claim = self._root.claim_root_cached(cache_id)
            if cached is not MISSING:
                return cached
            if allow_iterative and self._root.is_leader(claim) and len(self._plan.order) >= _RECURSIVE_PLAN_LIMIT:
                if claim is not None:
                    follower = self._root.abort(cache_id, claim)
                    if follower is not None:
                        follower.finish()
                return self._resolve_sync_iterative(spec)
            if not self._root.is_leader(claim):
                if self._is_constructing(self._root, cache_id):
                    raise CircularDependencyError(
                        f'{fmt_key(spec.key)} is already constructing in this context; '
                        'resolve a different dependency or break the recursive provider call'
                    )
                if claim is not None:
                    self._root.wait_sync(claim)
                continue
            leader = claim
            token = _constructing.set(_Constructing(self._root, cache_id, _constructing.get()))
            try:
                kwargs = self._resolve_params_sync(spec) if spec.params else {}
                value = construct.sync(spec, kwargs, self._teardown_sink(spec), self._read_frame)
            except BaseException:
                follower = self._root.abort(cache_id, leader)
                if follower is not None:
                    follower.finish()
                raise
            finally:
                _constructing.reset(token)
            follower = self._root.publish(cache_id, leader, value)
            if follower is not None:
                follower.finish()
            return value

    def _resolve_cached_sync(self, spec: ProviderSpec, frame: ScopeFrame) -> object:
        cache_id = (spec.key, spec.tag)
        while True:
            cached, claim = frame.claim_cached(cache_id, cache_id)
            if cached is not MISSING:
                return cached
            if frame.is_leader(claim) and len(self._plan.order) >= _RECURSIVE_PLAN_LIMIT:
                if claim is not None:
                    follower = frame.abort(cache_id, claim)
                    if follower is not None:
                        follower.finish()
                return self._resolve_sync_iterative(spec)
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

    def _resolve_sync_iterative(self, spec: ProviderSpec) -> object:
        pending: list[_PendingResolution] = []
        if spec.needs_async:
            raise AsyncInSyncContextError(f'{fmt_key(spec.key)} requires async resolution; call aresolve() instead')
        initial = self._begin(spec, pending)
        if initial is not _PENDING:
            return initial
        try:
            while pending:
                current = pending[-1]
                if current.param_index < len(current.spec.params):
                    param = current.spec.params[current.param_index]
                    supplied = self._supplied_param(current.spec, param)
                    if supplied is not MISSING:
                        current.kwargs[param.name] = supplied
                        current.param_index += 1
                        continue
                    dependency = self._lookup_optional(param.key, param.tag)
                    if dependency is None:
                        if param.has_default:
                            current.param_index += 1
                            continue
                        if param.optional:
                            current.kwargs[param.name] = None
                            current.param_index += 1
                            continue
                        raise MissingProviderError(
                            f"missing provider for parameter '{param.name}' of {fmt_key(current.spec.key)}"
                        )
                    if dependency.needs_async:
                        raise AsyncInSyncContextError(
                            f'{fmt_key(dependency.key)} requires async resolution; call aresolve() instead'
                        )
                    resolved = self._begin(dependency, pending)
                    if resolved is _PENDING:
                        current.waiting_name = param.name
                        continue
                    current.kwargs[param.name] = resolved
                    current.param_index += 1
                    continue
                value = construct.sync(
                    current.spec, current.kwargs, self._teardown_sink(current.spec), self._read_frame
                )
                self._complete(pending, value)
                if not pending:
                    return value
        except BaseException:
            self._abort_pending(pending)
            raise
        raise DepinError('resolution completed without a value')

    async def _resolve_async(self, spec: ProviderSpec) -> object:
        frame = self._cache_target(spec)
        if frame is None:
            return await self._construct_async(spec)
        cache_id = (spec.key, spec.tag)
        while True:
            if frame is self._root:
                cached, claim = frame.claim_root_cached(cache_id, asynchronous=True)
            else:
                cached, claim = frame.claim_cached(cache_id, cache_id, asynchronous=True)
            if cached is not MISSING:
                return cached
            if frame.is_leader(claim) and len(self._plan.order) >= _RECURSIVE_PLAN_LIMIT:
                if claim is not None:
                    follower = frame.abort(cache_id, claim)
                    if follower is not None:
                        follower.finish()
                return await self._resolve_async_iterative(spec)
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

    async def _resolve_async_iterative(self, spec: ProviderSpec) -> object:
        pending: list[_PendingResolution] = []
        initial = await self._begin_async(spec, pending)
        if initial is not _PENDING:
            return initial
        try:
            while pending:
                current = pending[-1]
                if current.param_index < len(current.spec.params):
                    param = current.spec.params[current.param_index]
                    supplied = self._supplied_param(current.spec, param)
                    if supplied is not MISSING:
                        current.kwargs[param.name] = supplied
                        current.param_index += 1
                        continue
                    dependency = self._lookup_optional(param.key, param.tag)
                    if dependency is None:
                        if param.has_default:
                            current.param_index += 1
                            continue
                        if param.optional:
                            current.kwargs[param.name] = None
                            current.param_index += 1
                            continue
                        raise MissingProviderError(
                            f"missing provider for parameter '{param.name}' of {fmt_key(current.spec.key)}"
                        )
                    resolved = await self._begin_async(dependency, pending)
                    if resolved is _PENDING:
                        current.waiting_name = param.name
                        continue
                    current.kwargs[param.name] = resolved
                    current.param_index += 1
                    continue
                value = await construct.asynchronous(
                    current.spec, current.kwargs, self._teardown_sink(current.spec), self._read_frame
                )
                self._complete(pending, value)
                if not pending:
                    return value
        except BaseException:
            self._abort_pending(pending)
            raise
        raise DepinError('resolution completed without a value')

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

    def _cache_target(self, spec: ProviderSpec) -> ScopeFrame | None:
        if spec.scope is Scope.SINGLETON:
            return self._root
        if spec.scope is Scope.SCOPED:
            return active_frame(self._root)
        return None

    def _construct_sync(self, spec: ProviderSpec) -> object:
        kwargs = self._resolve_params_sync(spec) if spec.params else {}
        return construct.sync(spec, kwargs, self._teardown_sink(spec), self._read_frame)

    async def _construct_async(self, spec: ProviderSpec) -> object:
        kwargs = await self._resolve_params_async(spec) if spec.params else {}
        return await construct.asynchronous(spec, kwargs, self._teardown_sink(spec), self._read_frame)

    def _resolve_params_sync(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        for param in spec.params:
            dependency = self._lookup_optional(param.key, param.tag)
            if dependency is None:
                frame = optional_frame(self._root)
                if frame is not None:
                    supplied = frame.lookup_provided(param.key, param.tag)
                    if supplied is not MISSING:
                        out[param.name] = supplied
                        continue
                if param.has_default:
                    continue
                if param.optional:
                    out[param.name] = None
                    continue
                raise MissingProviderError(f"missing provider for parameter '{param.name}' of {fmt_key(spec.key)}")
            out[param.name] = self._resolve_sync(dependency)
        return out

    async def _resolve_params_async(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        for param in spec.params:
            dependency = self._lookup_optional(param.key, param.tag)
            if dependency is None:
                frame = optional_frame(self._root)
                if frame is not None:
                    supplied = frame.lookup_provided(param.key, param.tag)
                    if supplied is not MISSING:
                        out[param.name] = supplied
                        continue
                if param.has_default:
                    continue
                if param.optional:
                    out[param.name] = None
                    continue
                raise MissingProviderError(f"missing provider for parameter '{param.name}' of {fmt_key(spec.key)}")
            out[param.name] = await self._resolve_async(dependency)
        return out

    async def _begin_async(self, spec: ProviderSpec, pending: list[_PendingResolution]) -> object:
        if spec.scope is Scope.SINGLETON:
            frame = self._root
        elif spec.scope is Scope.SCOPED:
            frame = active_frame(self._root)
        else:
            frame = None
        if frame is None:
            pending.append(_PendingResolution(spec, None, None, None, None, {}))
            return _PENDING
        cache_id = (spec.key, spec.tag)
        while True:
            cached, claim = frame.claim_cached(cache_id, cache_id, asynchronous=True)
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
            token = _constructing.set(_Constructing(frame, cache_id, _constructing.get()))
            pending.append(_PendingResolution(spec, frame, cache_id, claim, token, {}))
            return _PENDING

    def _begin(self, spec: ProviderSpec, pending: list[_PendingResolution]) -> object:
        if spec.scope is Scope.SINGLETON:
            frame = self._root
        elif spec.scope is Scope.SCOPED:
            frame = active_frame(self._root)
        else:
            frame = None
        if frame is None:
            pending.append(_PendingResolution(spec, None, None, None, None, {}))
            return _PENDING
        cache_id = (spec.key, spec.tag)
        while True:
            cached, claim = frame.claim_cached(cache_id, cache_id)
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
            token = _constructing.set(_Constructing(frame, cache_id, _constructing.get()))
            pending.append(_PendingResolution(spec, frame, cache_id, claim, token, {}))
            return _PENDING

    def _complete(self, pending: list[_PendingResolution], value: object) -> None:
        current = pending.pop()
        if current.frame is not None and current.cache_id is not None and current.leader is not None:
            follower = current.frame.publish(current.cache_id, current.leader, value)
            if follower is not None:
                follower.finish()
        if current.token is not None:
            _constructing.reset(current.token)
        if pending:
            parent = pending[-1]
            if parent.waiting_name is None:
                raise DepinError('dependency completed without a waiting parameter')
            parent.kwargs[parent.waiting_name] = value
            parent.waiting_name = None
            parent.param_index += 1

    def _abort_pending(self, pending: list[_PendingResolution]) -> None:
        while pending:
            current = pending.pop()
            if current.frame is not None and current.cache_id is not None and current.leader is not None:
                follower = current.frame.abort(current.cache_id, current.leader)
                if follower is not None:
                    follower.finish()
            if current.token is not None:
                _constructing.reset(current.token)

    def _teardown_sink(self, spec: ProviderSpec) -> Callable[[Teardown], None]:
        """Register a teardown on the frame that owns this spec, so it drains with it.

        The frame is looked up only when a teardown actually appears: a transient
        provider has no frame, and resolving one outside a scope must not fail
        merely because the sink was prepared.
        """

        def register(record: Teardown) -> None:
            self._frame_for(spec).add_teardown(record)

        return register

    def _supplied_param(self, spec: ProviderSpec, param: ParamSpec) -> object:
        frame = optional_frame(self._root)
        if frame is None:
            return MISSING
        if self._lookup_optional(param.key, param.tag) is not None:
            return MISSING
        return frame.lookup_provided(param.key, param.tag)

    def _frame_for(self, spec: ProviderSpec) -> ScopeFrame:
        if spec.scope is Scope.SINGLETON:
            return self._root
        return active_frame(self._root)

    def _read_frame(self, spec: ProviderSpec) -> object:
        value = active_frame(self._root).lookup_provided(spec.key, spec.tag)
        if value is MISSING:
            raise MissingProviderError(
                f'no value in the active scope for {fmt_key(spec.key)}; '
                'a key declared with scope_value() must be supplied by whoever opens the scope, '
                'with frame.provide(key, value)'
            )
        return value
