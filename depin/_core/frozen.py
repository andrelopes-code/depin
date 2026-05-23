import contextlib
import functools
import inspect
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Generator, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeGuard, get_type_hints, overload

from depin._core.introspect import extract_annotated_meta, is_object_token
from depin._core.markers import Token
from depin._core.scope import Scope, ScopeFrame, active_frame, push_frame
from depin._core.spec import ProviderKey, ProviderShape, ProviderSpec, ResolutionPlan
from depin.errors import AsyncInSyncContextError, MissingProviderError, OutsideScopeError


@dataclass(frozen=True, slots=True)
class SyncGenTeardown:
    gen: Iterator[object]


@dataclass(frozen=True, slots=True)
class AsyncGenTeardown:
    gen: AsyncIterator[object]


@dataclass(frozen=True, slots=True)
class SyncCMTeardown:
    cm: AbstractContextManager[object]


@dataclass(frozen=True, slots=True)
class AsyncCMTeardown:
    cm: AbstractAsyncContextManager[object]


type _Teardown = SyncGenTeardown | AsyncGenTeardown | SyncCMTeardown | AsyncCMTeardown


type _OverrideFrame = dict[tuple[ProviderKey, str | None], object]


_overrides: ContextVar[tuple[_OverrideFrame, ...]] = ContextVar('depin_overrides', default=())

_ASYNC_SHAPES = frozenset(
    {
        ProviderShape.ASYNC_FUNCTION,
        ProviderShape.ASYNC_GENERATOR,
        ProviderShape.ASYNC_CONTEXT_MANAGER,
    }
)


class FrozenContainer:
    """Immutable view of a resolved dependency graph.

    The internal resolver carries provider results as ``object`` because the graph
    spec is type-erased; the public API (``__getitem__``, ``resolve``, ``aresolve``)
    re-states the static result type. The narrowing is a single documented boundary:
    providers must produce values matching the static type of their declared key.
    """

    __slots__ = ('_plan', '_root')

    def __init__(self, plan: ResolutionPlan) -> None:
        self._plan = plan
        self._root = ScopeFrame()

    @overload
    def __getitem__[T](self, key: type[T]) -> T: ...
    @overload
    def __getitem__[T](self, key: Token[T]) -> T: ...
    def __getitem__[T](self, key: type[T] | Token[T]) -> T:
        return self.resolve(key)

    def resolve[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> T:
        spec = self._lookup(key, tag)
        # spec.source is type-erased `object` in the plan; the runtime contract
        # (enforced by build_plan) is that providers return values matching the
        # static type of their declared key, so we restate the static type here.
        return self._resolve_sync(spec)  # pyright: ignore[reportReturnType]

    async def aresolve[T](self, key: type[T] | Token[T], *, tag: str | None = None) -> T:
        spec = self._lookup(key, tag)
        # See the matching note in `resolve`: plan-level erasure of provider
        # return types forces a single documented widening at this boundary.
        return await self._resolve_async(spec)  # pyright: ignore[reportReturnType]

    def _resolve_any(self, key: ProviderKey, tag: str | None) -> object:
        return self._resolve_sync(self._lookup(key, tag))

    async def _aresolve_any(self, key: ProviderKey, tag: str | None) -> object:
        return await self._resolve_async(self._lookup(key, tag))

    @contextlib.contextmanager
    def scope(self) -> Generator[ScopeFrame]:
        with push_frame() as frame:
            try:
                yield frame
            finally:
                self._drain_sync(frame)

    @contextlib.asynccontextmanager
    async def ascope(self) -> AsyncGenerator[ScopeFrame]:
        with push_frame() as frame:
            try:
                yield frame
            finally:
                await self._drain_async(frame)

    async def aclose(self) -> None:
        await self._drain_async(self._root)

    @overload
    def inject[**P, R](self, fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]: ...
    @overload
    def inject[**P, R](self, fn: Callable[P, R]) -> Callable[P, R]: ...
    def inject(self, fn: Callable[..., object]) -> Callable[..., object]:
        sig = inspect.signature(fn)
        try:
            hints = dict(get_type_hints(fn, include_extras=True))
        except (NameError, TypeError):
            hints = dict(getattr(fn, '__annotations__', {}))

        injectable = self._compute_injectable_params(sig, hints)

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def wrapper_async(*args: object, **kwargs: object) -> object:
                bound = sig.bind_partial(*args, **kwargs)
                for name, (key, tag) in injectable.items():
                    if name not in bound.arguments:
                        bound.arguments[name] = await self._aresolve_any(key, tag)
                return await _as_awaitable(fn(*bound.args, **bound.kwargs))

            return wrapper_async

        @functools.wraps(fn)
        def wrapper_sync(*args: object, **kwargs: object) -> object:
            bound = sig.bind_partial(*args, **kwargs)
            for name, (key, tag) in injectable.items():
                if name not in bound.arguments:
                    bound.arguments[name] = self._resolve_any(key, tag)
            return fn(*bound.args, **bound.kwargs)

        return wrapper_sync

    def _compute_injectable_params(
        self,
        sig: inspect.Signature,
        hints: dict[str, object],
    ) -> dict[str, tuple[ProviderKey, str | None]]:
        out: dict[str, tuple[ProviderKey, str | None]] = {}
        for name, param in sig.parameters.items():
            if name in ('self', 'cls'):
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            annotation = hints.get(name)
            if annotation is None:
                continue
            meta = extract_annotated_meta(annotation)
            key: ProviderKey | None = None
            if meta.token is not None:
                key = meta.token
            elif isinstance(meta.named, str) or is_object_token(meta.named):
                key = meta.named
            elif _is_provider_key(meta.base):
                key = meta.base
            if key is not None and (key, meta.tag) in self._plan.by_key:
                out[name] = (key, meta.tag)
        return out

    @contextlib.contextmanager
    def override[T](
        self,
        key: type[T] | Token[T],
        *,
        with_: T,
        tag: str | None = None,
    ) -> Generator['FrozenContainer']:
        if not _is_provider_key(key):
            raise MissingProviderError(f'cannot override {key!r}: not a valid key type')
        frame: _OverrideFrame = {(key, tag): with_}
        token = _overrides.set((*_overrides.get(), frame))
        try:
            yield self
        finally:
            _overrides.reset(token)

    def _lookup(self, key: object, tag: str | None) -> ProviderSpec:
        if not _is_provider_key(key):
            raise MissingProviderError(f'cannot look up provider for {key!r}: not a valid key type')
        spec = self._lookup_optional(key, tag)
        if spec is None:
            raise MissingProviderError(f'no provider for {key!r} (tag={tag!r})')
        return spec

    def _lookup_optional(self, key: ProviderKey, tag: str | None) -> ProviderSpec | None:
        """Resolve ``(key, tag)`` to a spec, honouring any active override.

        Dependency resolution routes through here rather than reading
        ``self._plan.by_key`` directly, so an ``override`` substitutes a key
        everywhere it appears in the graph — not only at the top-level lookup.
        Returns the synthetic override spec when one is active, else the planned
        provider, else ``None``.
        """
        for frame in reversed(_overrides.get()):
            if (key, tag) in frame:
                return _override_spec(key, tag, frame[(key, tag)])
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
            raise AsyncInSyncContextError(f'{spec.key!r} requires async resolution; call aresolve() instead')
        frame = self._cache_target(spec)
        cache_id = (spec.key, spec.tag)
        if frame is not None and cache_id in frame:
            return frame.get(cache_id)
        kwargs = self._resolve_params_sync(spec) if spec.params else {}
        value = self._build_sync_value(spec, kwargs)
        if frame is not None:
            frame.put(cache_id, value)
        return value

    async def _resolve_async(self, spec: ProviderSpec) -> object:
        frame = self._cache_target(spec)
        if frame is None:
            return await self._construct_async(spec)
        cache_id = (spec.key, spec.tag)
        if cache_id in frame:
            return frame.get(cache_id)
        # Single-flight: concurrent resolutions of the same cached spec must
        # build it once. The await below would otherwise let a second task miss
        # the cache and construct a duplicate (a second singleton, leaked
        # teardown). The lock lives on the caching frame, so it is dropped when
        # the scope ends.
        async with frame.lock_for(cache_id):
            if cache_id in frame:
                return frame.get(cache_id)
            value = await self._construct_async(spec)
            frame.put(cache_id, value)
            return value

    async def _construct_async(self, spec: ProviderSpec) -> object:
        kwargs = await self._resolve_params_async(spec) if spec.params else {}
        if spec.shape in _ASYNC_SHAPES:
            return await self._build_async_value(spec, kwargs)
        return self._build_sync_value(spec, kwargs)

    def _build_sync_value(self, spec: ProviderSpec, kwargs: dict[str, object]) -> object:
        """Construct a value for any non-async shape. Shared by sync and async paths."""
        shape = spec.shape
        source = spec.source
        if shape is ProviderShape.VALUE:
            return source
        if shape is ProviderShape.FRAME:
            return self._read_frame(spec)
        if shape in _ASYNC_SHAPES:
            raise AsyncInSyncContextError(f'{spec.key!r} is async; use aresolve inside ascope()')
        if shape is ProviderShape.CLASS:
            assert isinstance(source, type)
            return source(**kwargs)
        if shape is ProviderShape.FUNCTION:
            assert callable(source)
            return source(**kwargs)
        if shape is ProviderShape.GENERATOR:
            assert callable(source)
            gen = _as_sync_iter(source(**kwargs))
            value = next(gen)
            self._frame_for(spec).teardowns.append(SyncGenTeardown(gen))
            return value
        if shape is ProviderShape.CONTEXT_MANAGER:
            assert callable(source)
            cm = _as_sync_cm(source(**kwargs))
            value = cm.__enter__()
            self._frame_for(spec).teardowns.append(SyncCMTeardown(cm))
            return value
        raise AssertionError(f'unhandled shape: {shape}')

    async def _build_async_value(self, spec: ProviderSpec, kwargs: dict[str, object]) -> object:
        """Construct a value for an async shape. Only reached when shape ∈ _ASYNC_SHAPES."""
        shape = spec.shape
        source = spec.source
        assert callable(source)
        if shape is ProviderShape.ASYNC_FUNCTION:
            return await _as_awaitable(source(**kwargs))
        if shape is ProviderShape.ASYNC_GENERATOR:
            agen = _as_async_iter(source(**kwargs))
            value = await agen.__anext__()
            self._frame_for(spec).teardowns.append(AsyncGenTeardown(agen))
            return value
        if shape is ProviderShape.ASYNC_CONTEXT_MANAGER:
            acm = _as_async_cm(source(**kwargs))
            value = await acm.__aenter__()
            self._frame_for(spec).teardowns.append(AsyncCMTeardown(acm))
            return value
        raise AssertionError(f'unhandled async shape: {shape}')

    def _resolve_params_sync(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        frame = self._optional_frame()
        for param in spec.params:
            if frame is not None and param.key in frame:
                out[param.name] = frame.get(param.key)
                continue
            dep = self._lookup_optional(param.key, param.tag)
            if dep is None:
                if param.has_default:
                    continue
                raise MissingProviderError(f"missing provider for parameter '{param.name}' of {spec.key!r}")
            out[param.name] = self._resolve_sync(dep)
        return out

    async def _resolve_params_async(self, spec: ProviderSpec) -> dict[str, object]:
        out: dict[str, object] = {}
        frame = self._optional_frame()
        for param in spec.params:
            if frame is not None and param.key in frame:
                out[param.name] = frame.get(param.key)
                continue
            dep = self._lookup_optional(param.key, param.tag)
            if dep is None:
                if param.has_default:
                    continue
                raise MissingProviderError(f"missing provider for parameter '{param.name}' of {spec.key!r}")
            out[param.name] = await self._resolve_async(dep)
        return out

    def _frame_for(self, spec: ProviderSpec) -> ScopeFrame:
        if spec.scope is Scope.SINGLETON:
            return self._root
        return active_frame()

    def _read_frame(self, spec: ProviderSpec) -> object:
        frame = active_frame()
        if spec.key in frame:
            return frame.get(spec.key)
        raise MissingProviderError(
            f'no value in active scope for {spec.key!r}; '
            'was the value placed in the frame by middleware or scope-setup code?'
        )

    def _optional_frame(self) -> ScopeFrame | None:
        try:
            return active_frame()
        except OutsideScopeError:
            return None

    def _drain_sync(self, frame: ScopeFrame) -> None:
        errors: list[Exception] = []
        for td in reversed(frame.teardowns):
            try:
                run_sync_teardown(td)
            except Exception as exc:
                errors.append(exc)
        frame.teardowns.clear()
        if errors:
            raise ExceptionGroup('depin teardown errors', errors)

    async def _drain_async(self, frame: ScopeFrame) -> None:
        errors: list[Exception] = []
        for td in reversed(frame.teardowns):
            try:
                await run_async_teardown(td)
            except Exception as exc:
                errors.append(exc)
        frame.teardowns.clear()
        if errors:
            raise ExceptionGroup('depin teardown errors', errors)


def run_sync_teardown(td: object) -> None:
    if isinstance(td, SyncGenTeardown):
        try:
            _ = next(td.gen)
        except StopIteration:
            return
        raise RuntimeError('generator provider yielded more than once')
    if isinstance(td, SyncCMTeardown):
        _ = td.cm.__exit__(None, None, None)
        return
    if isinstance(td, AsyncGenTeardown | AsyncCMTeardown):
        raise RuntimeError('async teardown registered in sync scope; use ascope() instead')
    raise AssertionError(f'unknown teardown record: {td!r}')


async def run_async_teardown(td: object) -> None:
    if isinstance(td, SyncGenTeardown):
        try:
            _ = next(td.gen)
        except StopIteration:
            return
        raise RuntimeError('generator provider yielded more than once')
    if isinstance(td, AsyncGenTeardown):
        try:
            _ = await td.gen.__anext__()
        except StopAsyncIteration:
            return
        raise RuntimeError('async generator provider yielded more than once')
    if isinstance(td, SyncCMTeardown):
        _ = td.cm.__exit__(None, None, None)
        return
    if isinstance(td, AsyncCMTeardown):
        _ = await td.cm.__aexit__(None, None, None)
        return
    raise AssertionError(f'unknown teardown record: {td!r}')


def _override_spec(key: ProviderKey, tag: str | None, replacement: object) -> ProviderSpec:
    """Build a synthetic transient ProviderSpec for an active override entry."""
    if callable(replacement) and not isinstance(replacement, type):
        return ProviderSpec(
            key=key,
            tag=tag,
            source=replacement,
            scope=Scope.TRANSIENT,
            shape=ProviderShape.FUNCTION,
            needs_async=False,
            params=(),
        )
    return ProviderSpec(
        key=key,
        tag=tag,
        source=replacement,
        scope=Scope.TRANSIENT,
        shape=ProviderShape.VALUE,
        needs_async=False,
        params=(),
    )


def _is_provider_key(value: object) -> TypeGuard[ProviderKey]:
    return isinstance(value, type) or is_object_token(value) or isinstance(value, str)


def _is_object_awaitable(value: object) -> TypeGuard[Awaitable[object]]:
    return isinstance(value, Awaitable)


def _as_awaitable(value: object) -> Awaitable[object]:
    """Narrow the resolver's `object` to `Awaitable[object]` for `await` dispatch."""
    assert _is_object_awaitable(value), f'async provider returned non-awaitable {value!r}'
    return value


def _is_sync_iter(value: object) -> TypeGuard[Iterator[object]]:
    return isinstance(value, Iterator)


def _as_sync_iter(value: object) -> Iterator[object]:
    assert _is_sync_iter(value), f'generator provider returned non-iterator {value!r}'
    return value


def _is_async_iter(value: object) -> TypeGuard[AsyncIterator[object]]:
    return isinstance(value, AsyncIterator)


def _as_async_iter(value: object) -> AsyncIterator[object]:
    assert _is_async_iter(value), f'async generator provider returned non-async-iterator {value!r}'
    return value


def _is_sync_cm(value: object) -> TypeGuard[AbstractContextManager[object]]:
    return isinstance(value, AbstractContextManager)


def _as_sync_cm(value: object) -> AbstractContextManager[object]:
    assert _is_sync_cm(value), f'context manager provider returned non-context-manager {value!r}'
    return value


def _is_async_cm(value: object) -> TypeGuard[AbstractAsyncContextManager[object]]:
    return isinstance(value, AbstractAsyncContextManager)


def _as_async_cm(value: object) -> AbstractAsyncContextManager[object]:
    assert _is_async_cm(value), f'async context manager provider returned non-async-CM {value!r}'
    return value
