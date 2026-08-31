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
from depin.errors import DepinError, OutsideScopeError


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
    __slots__ = ('_event', '_mutex', '_waiters', 'finished', 'leader')

    def __init__(self, leader: '_Leader') -> None:
        self._event: threading.Event | None = None
        self._mutex = threading.Lock()
        self._waiters: list[_AsyncWaiter] = []
        self.finished = False
        self.leader = leader

    def wait_sync(self) -> None:
        with self._mutex:
            if self.finished:
                return
            if self._event is None:
                self._event = threading.Event()
            event = self._event
        event.wait()

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
            event = self._event
        if event is not None:
            event.set()
        for waiter in waiters:
            if waiter.loop.is_closed():
                continue
            try:
                waiter.loop.call_soon_threadsafe(self._complete_waiter, waiter.future)
            except RuntimeError:
                # A compliant event loop raises only when it closed after the precheck.
                continue

    @staticmethod
    def _complete_waiter(future: asyncio.Future[None]) -> None:
        if not future.done():
            future.set_result(None)


class _Leader:
    __slots__ = ('flight',)

    def __init__(self) -> None:
        self.flight: _Flight | None = None

    @property
    def finished(self) -> bool:
        return self.flight is not None and self.flight.finished


def _run_teardowns_sync(records: tuple[Teardown, ...]) -> None:
    errors: list[Exception] = []
    for record in records:
        try:
            teardown.run_sync(record)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup('depin teardown errors', errors)


async def _run_teardowns_async(records: tuple[Teardown, ...]) -> None:
    errors: list[Exception] = []
    for record in records:
        try:
            await teardown.run_async(record)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup('depin teardown errors', errors)


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
        self._flights: dict[object, _Flight | _Leader] = {}
        self._teardowns: list[Teardown] = []
        self._mutex = threading.Lock()
        self.parent = parent

    def provide(self, key: object, value: object) -> None:
        """Place ``value`` into this frame under ``key``.

        The counterpart of `Container.scope_value()`: whoever opens the scope
        supplies the value, and providers declared with ``scope_value`` read it
        back. Overwrites any value already stored under ``key`` in this frame.
        Seed before anything resolves: a ``scope_value`` key is cached in the
        scope on first use, so a later call here does not replace what a
        parameter already read.

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
            TeardownError: An async provider left a teardown here, reported
                inside the raised `ExceptionGroup` rather than bare; drain it
                with `drain_async()` instead.
        """
        _run_teardowns_sync(self._take_teardowns())

    async def drain_async(self) -> None:
        """Run every pending teardown, newest first, inside an event loop.

        Raises:
            ExceptionGroup: One or more teardowns failed.
        """
        await _run_teardowns_async(self._take_teardowns())

    def drop_sync(self) -> None:
        """Drain every pending teardown, newest first, and drop the cache, without an event loop.

        The counterpart to `drain_sync()`: where that leaves the cache
        populated with whatever it just drained, this drops it too, so a key
        resolved afterwards is rebuilt rather than handed the drained value.

        Raises:
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported, and the cache is dropped either way.
            TeardownError: An async provider left a teardown here, reported
                inside the raised `ExceptionGroup` rather than bare; drain it
                with `drop_async()` instead.
        """
        _run_teardowns_sync(self._take_all())

    async def drop_async(self) -> None:
        """Drain every pending teardown and drop the cache, inside an event loop.

        The counterpart to `drop_sync()`, for a frame holding an async
        provider's teardown.

        Raises:
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported, and the cache is dropped either way.
        """
        await _run_teardowns_async(self._take_all())

    def _take_teardowns(self) -> tuple[Teardown, ...]:
        with self._mutex:
            records = tuple(reversed(self._teardowns))
            self._teardowns.clear()
        return records

    def _take_all(self) -> tuple[Teardown, ...]:
        """Take every pending teardown and drop the cache, as one atomic step.

        The teardown list and the cache must move together under one lock. Two
        lock regions instead of one would open a gap: a construction finishing
        in that gap could register its teardown after the first region already
        ran, surviving unrun — left in the teardown list for some later,
        unrelated drop to sweep up — while the second region wipes its
        just-published value from the cache regardless. The result is a cache
        with no trace of the value and a teardown nothing is about to run.

        This property is guarded by construction — one `with self._mutex:`
        below, not two — rather than by a test: no test can distinguish one
        lock region from two without instrumenting the gap between them, which
        is not available through the public API. A test that tried to catch a
        regression here by racing real threads caught it in roughly four runs
        out of five and cost seconds per run, which does not clear the
        `[tool.mutmut]` gate's two-second-per-test budget; see the `Carried
        from Step 5` entry in `specs/2026-08-28-roadmap-1.0-design.md` for the
        fault-injection mechanism Step 6 owns building instead.
        """
        with self._mutex:
            records = tuple(reversed(self._teardowns))
            self._teardowns.clear()
            self._cache.clear()
        return records

    def claim_cached(self, key: object) -> tuple[object, _Flight | _Leader | None]:
        """Atomically return a cached value or claim/join its construction flight."""
        if self.parent is None:
            with self._mutex:
                value = self._cache.get(key, MISSING)
                if value is not MISSING:
                    return value, None
                flight = self._flights.get(key)
                if flight is None:
                    leader = _Leader()
                    self._flights[key] = leader
                    return MISSING, leader
                if isinstance(flight, _Flight):
                    return MISSING, flight
                joined = _Flight(flight)
                flight.flight = joined
                self._flights[key] = joined
                return MISSING, joined
        frames = self._visible_frames()
        with contextlib.ExitStack() as locks:
            for frame in frames:
                locks.enter_context(frame._mutex)
            for frame in reversed(frames):
                value = frame._cache.get(key, MISSING)
                if value is not MISSING:
                    return value, None
                flight = frame._flights.get(key)
                if flight is None:
                    continue
                if isinstance(flight, _Flight):
                    return MISSING, flight
                joined = _Flight(flight)
                flight.flight = joined
                frame._flights[key] = joined
                return MISSING, joined
            leader = _Leader()
            self._flights[key] = leader
            return MISSING, leader

    def _visible_frames(self) -> tuple['ScopeFrame', ...]:
        frames: list[ScopeFrame] = []
        frame: ScopeFrame | None = self
        while frame is not None:
            frames.append(frame)
            frame = frame.parent
        return tuple(reversed(frames))

    def is_leader(self, claim: _Flight | _Leader | None) -> bool:
        return isinstance(claim, _Leader)

    def publish(self, key: object, leader: object, value: object) -> _Flight | None:
        """Cache a leader's value and return any followers to signal after unlocking."""
        with self._mutex:
            active = self._flights.get(key)
            if active is leader:
                self._cache[key] = value
                del self._flights[key]
                return None
            if isinstance(leader, _Leader) and isinstance(active, _Flight) and active.leader is leader:
                self._cache[key] = value
                del self._flights[key]
                return active
            return None

    def abort(self, key: object, leader: object) -> _Flight | None:
        """Remove a failed leader's flight and return any followers to signal after unlocking."""
        with self._mutex:
            active = self._flights.get(key)
            if active is leader:
                del self._flights[key]
                return None
            if isinstance(leader, _Leader) and isinstance(active, _Flight) and active.leader is leader:
                del self._flights[key]
                return active
            return None

    def start_flight(self, key: object) -> tuple[_Flight | _Leader, bool]:
        """Join a per-key construction flight, or start one when none is active."""
        value, flight = self.claim_cached(key)
        if value is not MISSING or flight is None:
            raise DepinError(f'cannot begin construction flight for key {key!r}: value is already cached')
        return flight, isinstance(flight, _Leader)

    def wait_sync(self, flight: _Flight | _Leader) -> None:
        if isinstance(flight, _Flight):
            flight.wait_sync()

    async def wait_async(self, flight: _Flight | _Leader) -> None:
        if isinstance(flight, _Flight):
            await flight.wait_async()

    def finish_flight(self, key: object, flight: _Flight | _Leader) -> None:
        """Finish ``flight`` and remove it only when it remains active for ``key``."""
        if isinstance(flight, _Leader):
            follower = self.abort(key, flight)
            if follower is not None:
                follower.finish()


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
