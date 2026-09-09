"""Context-local request scopes that allocate a frame only when it is needed."""

import contextlib
from collections.abc import AsyncGenerator, Callable, Iterable
from contextvars import ContextVar
from contextvars import Token as ContextToken
from dataclasses import dataclass
from typing import TYPE_CHECKING

from depin._core.markers import Token
from depin._core.scope import MISSING, ScopeFrame

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


class LazyScopeState:
    __slots__ = ('_container', '_lease', '_on_open', '_seeds')

    def __init__[T](
        self,
        container: 'FrozenContainer',
        seeds: Iterable[LazyScopeSeed[T]],
        on_open: Callable[[ScopeFrame], None] | None,
    ) -> None:
        self._container = container
        self._lease: AsyncScopeLease | None = None
        self._on_open = on_open
        self._seeds: dict[SeedIdentity, _Seed] = {
            (seed.key, seed.tag): _Seed(seed.key, seed.factory, seed.tag) for seed in seeds
        }

    def belongs_to(self, owner: ScopeFrame) -> bool:
        return self._container.scope_owner() is owner

    def frame(self) -> ScopeFrame:
        if self._lease is None:
            self._lease = self._container.begin_async_scope()
            if self._on_open is not None:
                self._on_open(self._lease.frame)
        return self._lease.frame

    def provide(self, seed: _Seed) -> object:
        frame = self.frame()
        value = frame.lookup_provided(seed.key, seed.tag)
        if value is MISSING:
            value = seed.factory()
            frame.provide(seed.key, value, tag=seed.tag)
        return value

    def seed(self, key: object, tag: str | None) -> object:
        seed = self._seeds.get((key, tag))
        return MISSING if seed is None else self.provide(seed)

    async def aclose(self, body_error: BaseException | None) -> None:
        if self._lease is not None:
            await self._container.end_async_scope(self._lease, body_error)


_lazy_state: ContextVar[LazyScopeState | None] = ContextVar('depin_lazy_scope_state', default=None)


def active_lazy_scope(owner: ScopeFrame) -> LazyScopeState | None:
    state = _lazy_state.get()
    return state if state is not None and state.belongs_to(owner) else None


def lazy_seed_value(key: object, tag: str | None) -> object:
    state = _lazy_state.get()
    return MISSING if state is None else state.seed(key, tag)


def provide_lazy_seed[T](seed: LazyScopeSeed[T]) -> None:
    state = _lazy_state.get()
    if state is not None:
        state.provide(_Seed(seed.key, seed.factory, seed.tag))


@contextlib.asynccontextmanager
async def lazy_host[T](
    container: 'FrozenContainer',
    *,
    seeds: Iterable[LazyScopeSeed[T]] = (),
    on_open: Callable[[ScopeFrame], None] | None = None,
) -> AsyncGenerator[None]:
    from depin._core.hosting import Host

    state = LazyScopeState(container, seeds, on_open)
    token: ContextToken[LazyScopeState | None] = _lazy_state.set(state)
    try:
        with Host(container).activated():
            try:
                yield
            except BaseException as error:
                await state.aclose(error)
                raise
            else:
                await state.aclose(None)
    finally:
        _lazy_state.reset(token)


_lazy_host = lazy_host
_provide_lazy_seed = provide_lazy_seed
