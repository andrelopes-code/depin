"""Provider lifetimes and the scope machinery that backs scoped resolution."""

import asyncio
import contextlib
import threading
from collections.abc import Generator
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from typing import Final

from depin._core import teardown
from depin._core.teardown import Teardown
from depin.errors import OutsideScopeError


class Scope(Enum):
    """How long a provider's value lives and when it is rebuilt.

    Attributes:
        SINGLETON: Built once, on first resolution, and cached on the
            `FrozenContainer` for its whole lifetime. The default.
            Its lifecycle teardown runs on `FrozenContainer.close()` /
            `FrozenContainer.aclose()`. A singleton may not depend on a scoped
            provider (it would capture one scope's instance forever) —
            `Container.freeze()` rejects that.
        SCOPED: Built once per active scope
            (`FrozenContainer.scope()` / ``ascope``) and torn down when
            that scope exits. Resolving one with no active scope raises
            `OutsideScopeError`. Typically one scope per
            request.
        TRANSIENT: Built fresh on every resolution and never cached. Generator and
            context-manager providers cannot be transient.
    """

    SINGLETON = 'singleton'
    SCOPED = 'scoped'
    TRANSIENT = 'transient'


class _Missing:
    """Sentinel type for `MISSING`; distinguishes an absent key from a cached ``None``."""

    __slots__ = ()


MISSING: Final = _Missing()


@dataclass(eq=False, slots=True)
class _AsyncWaiter:
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[None]


class _Flight:
    __slots__ = ('_event', '_mutex', '_waiters', 'finished')

    def __init__(self) -> None:
        self._event = threading.Event()
        self._mutex = threading.Lock()
        self._waiters: list[_AsyncWaiter] = []
        self.finished = False

    def wait_sync(self) -> None:
        self._event.wait()

    async def wait_async(self) -> None:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        waiter = _AsyncWaiter(loop, future)
        with self._mutex:
            if self.finished:
                return
            self._waiters.append(waiter)
        try:
            await future
        finally:
            with self._mutex:
                for index, current in enumerate(self._waiters):
                    if current is waiter:
                        del self._waiters[index]
                        break

    def finish(self) -> None:
        with self._mutex:
            if self.finished:
                return
            self.finished = True
            waiters = tuple(self._waiters)
            self._waiters.clear()
        self._event.set()
        errors: list[RuntimeError] = []
        for waiter in waiters:
            try:
                waiter.loop.call_soon_threadsafe(self._complete_waiter, waiter.future)
            except RuntimeError as exc:
                if not waiter.loop.is_closed():
                    errors.append(exc)
        if errors:
            raise ExceptionGroup('depin flight completion errors', errors)

    @staticmethod
    def _complete_waiter(future: asyncio.Future[None]) -> None:
        if not future.done():
            future.set_result(None)


class ScopeFrame:
    """The per-scope store yielded by `FrozenContainer.scope()`.

    Holds the scope's cached instances and pending teardowns, and chains to its
    parent so nested scopes inherit outer instances. Scope-setup code — ASGI
    middleware, a CLI entry point — uses `provide()` to seed values that
    `Container.scope_value()` then exposes as providers.

    A frame is safe to use from several threads and several tasks at once. The
    root frame caches singletons and is shared by every caller of the container,
    so its bookkeeping is guarded by a mutex and construction of a given key is
    single-flighted.
    """

    __slots__ = ('_cache', '_flights', '_mutex', '_teardowns', 'parent')

    def __init__(self, parent: 'ScopeFrame | None' = None) -> None:
        self._cache: dict[object, object] = {}
        self._flights: dict[object, _Flight] = {}
        self._teardowns: list[Teardown] = []
        self._mutex = threading.Lock()
        self.parent = parent

    def provide(self, key: object, value: object) -> None:
        """Place ``value`` into this frame under ``key``.

        The counterpart of `Container.scope_value()`: whoever opens the scope
        supplies the value, and providers declared with ``scope_value`` read it
        back. Overwrites any value already stored under ``key`` in this frame.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Request: ...
            >>> di = Container().scope_value(Request).freeze()
            >>> with di.scope() as frame:
            ...     frame.provide(Request, Request())
            ...     isinstance(di[Request], Request)
            True

            ```
        """
        with self._mutex:
            self._cache[key] = value

    def get(self, key: object) -> object:
        """Return the value stored under ``key`` here or in an ancestor frame.

        Raises:
            KeyError: No frame in the chain holds ``key``.
        """
        value = self.lookup(key)
        if isinstance(value, _Missing):
            raise KeyError(key)
        return value

    def lookup(self, key: object) -> object:
        """Return the value for ``key``, or `MISSING` when no frame holds it.

        Unlike `get()` this reports absence without raising, so a caller can
        distinguish "not cached" from "cached as ``None``" in one traversal.
        """
        frame: ScopeFrame | None = self
        while frame is not None:
            with frame._mutex:
                if key in frame._cache:
                    return frame._cache[key]
            frame = frame.parent
        return MISSING

    def __contains__(self, key: object) -> bool:
        return not isinstance(self.lookup(key), _Missing)

    def add_teardown(self, record: Teardown) -> None:
        with self._mutex:
            self._teardowns.append(record)

    def drain_sync(self) -> None:
        """Run every pending teardown, newest first, without an event loop.

        Raises:
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported; none is allowed to hide another.
            TeardownError: An async provider left a teardown here, which needs
                an event loop to run.
        """
        errors: list[Exception] = []
        for record in self._take_teardowns():
            try:
                teardown.run_sync(record)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup('depin teardown errors', errors)

    async def drain_async(self) -> None:
        """Run every pending teardown, newest first, inside an event loop.

        Raises:
            ExceptionGroup: One or more teardowns failed.
        """
        errors: list[Exception] = []
        for record in self._take_teardowns():
            try:
                await teardown.run_async(record)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup('depin teardown errors', errors)

    def _take_teardowns(self) -> tuple[Teardown, ...]:
        with self._mutex:
            records = tuple(reversed(self._teardowns))
            self._teardowns.clear()
        return records

    def start_flight(self, key: object) -> tuple[_Flight, bool]:
        """Join a per-key construction flight, or start one when none is active."""
        with self._mutex:
            flight = self._flights.get(key)
            if flight is not None:
                return flight, False
            flight = _Flight()
            self._flights[key] = flight
            return flight, True

    def finish_flight(self, key: object, flight: _Flight) -> None:
        """Finish ``flight`` and remove it only when it remains active for ``key``."""
        with self._mutex:
            if self._flights.get(key) is flight:
                del self._flights[key]
        flight.finish()


_active: ContextVar[ScopeFrame | None] = ContextVar('depin_active_frame', default=None)


def active_frame() -> ScopeFrame:
    frame = _active.get()
    if frame is None:
        raise OutsideScopeError('no active scope frame; open one with FrozenContainer.scope() or .ascope()')
    return frame


def optional_frame() -> ScopeFrame | None:
    return _active.get()


@contextlib.contextmanager
def push_frame() -> Generator[ScopeFrame]:
    parent = _active.get()
    frame = ScopeFrame(parent=parent)
    token = _active.set(frame)
    try:
        yield frame
    finally:
        _active.reset(token)
