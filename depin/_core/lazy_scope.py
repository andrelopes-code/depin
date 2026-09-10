"""Context-local request scopes that allocate a frame only when it is needed."""

import contextlib
import threading
from collections.abc import AsyncGenerator, Callable, Iterable
from contextvars import Token as ContextToken
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from depin._core.host_context import HostedBinding, get_hosted_binding, reset_hosted_binding, set_hosted_binding
from depin._core.markers import Token
from depin._core.scope import MISSING, ScopeFrame
from depin.errors import OutsideScopeError

__all__ = ('_lazy_host', '_provide_lazy_seed')

if TYPE_CHECKING:
    from depin._core.frozen import AsyncScopeLease, FrozenContainer


type SeedIdentity = tuple[object, str | None]


@dataclass(frozen=True, slots=True)
class LazyScopeSeed[T]:
    key: type[T] | Token[T]
    factory: Callable[[], T]
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class _Seed:
    key: object
    factory: Callable[[], object]
    tag: str | None


class _State(Enum):
    HOSTED = 'hosted'
    FRAME_OPEN = 'frame-open'
    DRAINED = 'drained'


class LazyScopeState:
    __slots__ = ('_container', '_first_seed', '_lease', '_lock', '_on_open', '_seeds', '_state')

    def __init__[T](
        self,
        container: 'FrozenContainer',
        seeds: Iterable[LazyScopeSeed[T]],
        on_open: Callable[[ScopeFrame], None] | None,
    ) -> None:
        self._container = container
        self._lease: AsyncScopeLease | None = None
        self._lock = threading.RLock()
        self._on_open = on_open
        self._state = _State.HOSTED
        self._first_seed: _Seed | None = None
        self._seeds: dict[SeedIdentity, _Seed] | None = None
        for seed in seeds:
            self.register(_Seed(seed.key, seed.factory, seed.tag))

    @property
    def container(self) -> 'FrozenContainer':
        return self._container

    def has_seed_mapping(self) -> bool:
        return self._seeds is not None

    def belongs_to(self, owner: ScopeFrame) -> bool:
        return self._container.scope_owner() is owner

    def frame(self) -> ScopeFrame:
        with self._lock:
            return self._frame()

    def _frame(self) -> ScopeFrame:
        if self._state is _State.DRAINED:
            raise OutsideScopeError('the lazy scope frame has already exited; open a new scope')
        if self._lease is None:
            self._lease = self._container.begin_lazy_async_scope()
            self._state = _State.FRAME_OPEN
            if self._on_open is not None:
                self._on_open(self._lease.frame)
        return self._lease.frame

    def provide(self, seed: _Seed) -> object:
        with self._lock:
            frame = self._frame()
            value = frame.lookup_provided(seed.key, seed.tag)
            if value is MISSING:
                value = seed.factory()
                frame.provide(seed.key, value, tag=seed.tag)
            return value

    def seed(self, key: object, tag: str | None) -> object:
        with self._lock:
            first = self._first_seed
            if first is not None and first.key == key and first.tag == tag:
                return self.provide(first)
            seeds = self._seeds
            seed = None if seeds is None else seeds.get((key, tag))
            return MISSING if seed is None else self.provide(seed)

    def register(self, seed: _Seed) -> None:
        with self._lock:
            if self._state is _State.DRAINED:
                raise OutsideScopeError('the lazy scope frame has already exited; open a new scope')
            first = self._first_seed
            if first is None or (first.key == seed.key and first.tag == seed.tag):
                self._first_seed = seed
            elif self._seeds is None:
                self._seeds = {(first.key, first.tag): first, (seed.key, seed.tag): seed}
            else:
                self._seeds[(seed.key, seed.tag)] = seed

    async def aclose(self, body_error: BaseException | None) -> None:
        with self._lock:
            if self._state is _State.DRAINED:
                return
            self._state = _State.DRAINED
            lease = self._lease
        if lease is not None:
            await self._container.end_async_scope(lease, body_error)


def active_lazy_scope(owner: ScopeFrame) -> LazyScopeState | None:
    binding = get_hosted_binding()
    return binding if isinstance(binding, LazyScopeState) and binding.belongs_to(owner) else None


def lazy_seed_value(key: object, tag: str | None) -> object:
    binding = get_hosted_binding()
    return MISSING if not isinstance(binding, LazyScopeState) else binding.seed(key, tag)


def provide_lazy_seed[T](seed: LazyScopeSeed[T]) -> None:
    binding = get_hosted_binding()
    if isinstance(binding, LazyScopeState):
        binding.register(_Seed(seed.key, seed.factory, seed.tag))


def begin_lazy_host[T](
    container: 'FrozenContainer',
    *,
    seeds: Iterable[LazyScopeSeed[T]] = (),
    on_open: Callable[[ScopeFrame], None] | None = None,
) -> tuple[LazyScopeState, ContextToken[HostedBinding | None]]:
    state = LazyScopeState(container, seeds, on_open)
    return state, set_hosted_binding(state)


async def finish_lazy_host(
    state: LazyScopeState, publication: ContextToken[HostedBinding | None], body_error: BaseException | None
) -> None:
    try:
        await state.aclose(body_error)
    finally:
        reset_hosted_binding(publication)


@contextlib.asynccontextmanager
async def lazy_host[T](
    container: 'FrozenContainer',
    *,
    seeds: Iterable[LazyScopeSeed[T]] = (),
    on_open: Callable[[ScopeFrame], None] | None = None,
) -> AsyncGenerator[None]:
    state, publication = begin_lazy_host(container, seeds=seeds, on_open=on_open)
    try:
        yield
    except BaseException as error:
        await finish_lazy_host(state, publication, error)
        raise
    else:
        await finish_lazy_host(state, publication, None)


_lazy_host = lazy_host
_provide_lazy_seed = provide_lazy_seed
