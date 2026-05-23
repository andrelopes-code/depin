import asyncio
import contextlib
from collections.abc import Generator
from contextvars import ContextVar
from enum import Enum

from depin.errors import OutsideScopeError


class Scope(Enum):
    SINGLETON = 'singleton'
    SCOPED = 'scoped'
    TRANSIENT = 'transient'


class ScopeFrame:
    __slots__ = ('_cache', '_locks', 'parent', 'teardowns')

    def __init__(self, parent: 'ScopeFrame | None' = None) -> None:
        self._cache: dict[object, object] = {}
        self._locks: dict[object, asyncio.Lock] = {}
        self.parent = parent
        self.teardowns: list[object] = []

    def put(self, key: object, value: object) -> None:
        self._cache[key] = value

    def get(self, key: object) -> object:
        if key in self._cache:
            return self._cache[key]
        if self.parent is not None:
            return self.parent.get(key)
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if key in self._cache:
            return True
        return self.parent is not None and key in self.parent

    def lock_for(self, key: object) -> asyncio.Lock:
        """Return a per-key async lock, created on first use, for single-flight construction."""
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock


_active: ContextVar[ScopeFrame | None] = ContextVar('depin_active_frame', default=None)


def active_frame() -> ScopeFrame:
    frame = _active.get()
    if frame is None:
        raise OutsideScopeError('no active scope frame; open one with FrozenContainer.scope() or .ascope()')
    return frame


@contextlib.contextmanager
def push_frame() -> Generator[ScopeFrame]:
    parent = _active.get()
    frame = ScopeFrame(parent=parent)
    token = _active.set(frame)
    try:
        yield frame
    finally:
        _active.reset(token)
