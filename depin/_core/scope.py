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
from depin._core.lifecycle import LifecycleGate, LifecycleState
from depin._core.teardown import AsyncCMTeardown, AsyncGenTeardown, Teardown
from depin.errors import ContainerClosedError, ContainerLifecycleError, DepinError, OutsideScopeError


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
    __slots__ = ('asynchronous', 'flight')

    def __init__(self, *, asynchronous: bool = False) -> None:
        self.asynchronous = asynchronous
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

    __slots__ = (
        '_active',
        '_cache',
        '_flights',
        '_lifecycle',
        '_mutex',
        '_teardowns',
        'active',
        'context_parent',
        'owner',
        'parent',
    )

    def __init__(
        self,
        parent: 'ScopeFrame | None' = None,
        *,
        context_parent: 'ScopeFrame | None' = None,
        lifecycle: LifecycleGate | None = None,
        owner: 'ScopeFrame | None' = None,
    ) -> None:
        self._cache: dict[object, object] = {}
        self._flights: dict[object, _Flight | _Leader] = {}
        self._teardowns: list[Teardown] = []
        self._lifecycle = lifecycle
        self._mutex = lifecycle.mutex if lifecycle is not None else threading.Lock()
        self.active = True
        self.context_parent = context_parent
        self.owner = owner
        self.parent = parent
        if lifecycle is not None:
            lifecycle.flights = self._flights
            lifecycle.has_async_flights = self.has_async_flights

    def provide(self, key: object, value: object, *, tag: str | None = None) -> None:
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
            identity = key if tag is None else (MISSING, key, tag)
            self._cache[identity] = value

    def lookup_provided(self, key: object, tag: str | None = None) -> object:
        frame: ScopeFrame | None = self
        identity = key if tag is None else (MISSING, key, tag)
        while frame is not None:
            with frame._mutex:
                value = frame._cache.get(identity, MISSING)
            if value is not MISSING:
                return value
            frame = frame.parent
        return MISSING

    def deactivate(self) -> None:
        with self._mutex:
            self.active = False

    def is_active(self) -> bool:
        with self._mutex:
            return self.active

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

    def has_async_teardown(self) -> bool:
        with self._mutex:
            return any(isinstance(record, AsyncGenTeardown | AsyncCMTeardown) for record in self._teardowns)

    def drain_sync(self) -> None:
        """Run every pending teardown, newest first, without an event loop.

        Raises:
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported; none is allowed to hide another. Protocol violations,
                including an async teardown in this synchronous drain, appear as
                `TeardownError` members; use `drain_async()` for async providers.
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

        Do not call this while another thread or task may be resolving through
        this frame: the cache is dropped without coordinating with an in-flight
        construction, so a resolution racing with the drop can be handed a
        value whose teardown already ran. `FrozenContainer.reset()` is this
        operation on the root frame and carries the same hazard.

        Raises:
            ExceptionGroup: One or more teardowns failed. Every failure is
                reported, and the cache is dropped either way. Protocol
                violations, including an async teardown in this synchronous
                drain, appear as `TeardownError` members; use `drop_async()` for
                async providers.
        """
        _run_teardowns_sync(self._take_all())

    async def drop_async(self) -> None:
        """Drain every pending teardown and drop the cache, inside an event loop.

        The counterpart to `drop_sync()`, for a frame holding an async
        provider's teardown, and carrying the same hazard: do not call it while
        another thread or task may be resolving through this frame, because the
        cache is dropped without coordinating with an in-flight construction.

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
        `[tool.mutmut]` gate's two-second-per-test budget. The deterministic
        fault-injection seam keeps the concurrency invariant testable instead.
        """
        with self._mutex:
            records = tuple(reversed(self._teardowns))
            self._teardowns.clear()
            self._cache.clear()
        return records

    def claim_cached(
        self,
        key: object,
        provided_identity: tuple[object, str | None] | None = None,
        *,
        asynchronous: bool = False,
    ) -> tuple[object, _Flight | _Leader | None]:
        """Atomically return a cached value or claim/join its construction flight."""
        if self.parent is None:
            with self._mutex:
                cache_key: object = key
                value = self._cache.get(cache_key, MISSING)
                if value is not MISSING:
                    return value, None
                lifecycle = self._lifecycle
                if lifecycle is not None:
                    if lifecycle.state is LifecycleState.CLOSED:
                        raise ContainerClosedError(
                            'container is closed; build a new FrozenContainer before resolving or opening a scope'
                        )
                    if lifecycle.state is not LifecycleState.OPEN and not lifecycle.flights and lifecycle.active == 0:
                        raise ContainerLifecycleError(
                            'container shutdown is already in progress; await aclose() to join it'
                        )
                flight = self._flights.get(cache_key)
                if flight is None:
                    leader = _Leader(asynchronous=asynchronous)
                    self._flights[cache_key] = leader
                    return MISSING, leader
                if isinstance(flight, _Flight):
                    return MISSING, flight
                joined = _Flight(flight)
                flight.flight = joined
                self._flights[cache_key] = joined
                return MISSING, joined
        cache_key = key
        if provided_identity is None:
            identity = key
        elif provided_identity[1] is None:
            identity = provided_identity[0]
        else:
            identity = (MISSING, *provided_identity)
        provided_frame: ScopeFrame | None = self
        while provided_frame is not None:
            with provided_frame._mutex:
                provided = provided_frame._cache.get(identity, MISSING)
            if provided is not MISSING:
                return provided, None
            provided_frame = provided_frame.parent
        frames = self._visible_frames()
        with contextlib.ExitStack() as locks:
            for frame in frames:
                locks.enter_context(frame._mutex)
            for frame in reversed(frames):
                value = frame._cache.get(cache_key, MISSING)
                if value is not MISSING:
                    return value, None
                flight = frame._flights.get(cache_key)
                if flight is None:
                    continue
                if isinstance(flight, _Flight):
                    return MISSING, flight
                joined = _Flight(flight)
                flight.flight = joined
                frame._flights[cache_key] = joined
                return MISSING, joined
            leader = _Leader(asynchronous=asynchronous)
            self._flights[cache_key] = leader
            return MISSING, leader

    def claim_root_cached(self, key: object, *, asynchronous: bool = False) -> tuple[object, _Flight | _Leader | None]:
        with self._mutex:
            value = self._cache.get(key, MISSING)
            if value is not MISSING:
                return value, None
            lifecycle = self._lifecycle
            if lifecycle is not None:
                state = lifecycle.state
                if state is not LifecycleState.OPEN:
                    if state is LifecycleState.CLOSED:
                        raise ContainerClosedError(
                            'container is closed; build a new FrozenContainer before resolving or opening a scope'
                        )
                    if not lifecycle.flights and lifecycle.active == 0:
                        raise ContainerLifecycleError(
                            'container shutdown is already in progress; await aclose() to join it'
                        )
            flight = self._flights.get(key)
            if flight is None:
                leader = _Leader(asynchronous=asynchronous)
                self._flights[key] = leader
                return MISSING, leader
            if isinstance(flight, _Flight):
                return MISSING, flight
            joined = _Flight(flight)
            flight.flight = joined
            self._flights[key] = joined
            return MISSING, joined

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
        follower: _Flight | None = None
        with self._mutex:
            active = self._flights.get(key)
            if active is leader:
                self._cache[key] = value
                del self._flights[key]
            elif isinstance(leader, _Leader) and isinstance(active, _Flight) and active.leader is leader:
                self._cache[key] = value
                del self._flights[key]
                follower = active
            else:
                return None
        return follower

    def abort(self, key: object, leader: object) -> _Flight | None:
        """Remove a failed leader's flight and return any followers to signal after unlocking."""
        follower: _Flight | None = None
        with self._mutex:
            active = self._flights.get(key)
            if active is leader:
                del self._flights[key]
            elif isinstance(leader, _Leader) and isinstance(active, _Flight) and active.leader is leader:
                del self._flights[key]
                follower = active
            else:
                return None
        return follower

    def has_async_flights(self) -> bool:
        return any(
            active.asynchronous if isinstance(active, _Leader) else active.leader.asynchronous
            for active in self._flights.values()
        )

    async def wait_until_idle(self) -> None:
        while True:
            with self._mutex:
                pending: list[_Flight] = []
                for key, active in self._flights.items():
                    if isinstance(active, _Leader):
                        flight = _Flight(active)
                        active.flight = flight
                        self._flights[key] = flight
                    else:
                        flight = active
                    pending.append(flight)
                if not pending:
                    return
            await asyncio.gather(*(flight.wait_async() for flight in pending))

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


_manualowner = ScopeFrame()
_active: ContextVar[ScopeFrame | None] = ContextVar('depin_active_frame', default=None)


def active_frame(owner: ScopeFrame | None = None) -> ScopeFrame:
    if owner is None:
        owner = _manualowner
    frame = _active.get()
    while frame is not None:
        if frame.owner is owner:
            if frame.active:
                return frame
            break
        frame = frame.context_parent
    if frame is not None:
        raise OutsideScopeError('the active scope frame has already exited; open a new scope')
    raise OutsideScopeError('no active scope frame; open one with FrozenContainer.scope() or .ascope()')


def optional_frame(owner: ScopeFrame | None = None) -> ScopeFrame | None:
    if owner is None:
        owner = _manualowner
    frame = _active.get()
    while frame is not None:
        if frame.owner is owner:
            return frame if frame.active else None
        frame = frame.context_parent
    return None


@contextlib.contextmanager
def push_frame(owner: ScopeFrame | None = None) -> Generator[ScopeFrame]:
    if owner is None:
        owner = _manualowner
    context_parent = _active.get()
    parent = context_parent
    while parent is not None and parent.owner is not owner:
        parent = parent.context_parent
    if parent is not None and not parent.active:
        parent = None
    frame = ScopeFrame(parent=parent, context_parent=context_parent, owner=owner)
    token = _active.set(frame)
    try:
        yield frame
    finally:
        frame.active = False
        _active.reset(token)
