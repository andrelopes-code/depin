"""Admission and terminal shutdown coordination for frozen containers."""

import asyncio
import threading
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from contextvars import Token as ContextToken
from dataclasses import dataclass
from enum import Enum

from depin.errors import AsyncInSyncContextError, ContainerClosedError, ContainerLifecycleError


class LifecycleState(Enum):
    OPEN = 'open'
    QUIESCING = 'quiescing'
    DRAINING = 'draining'
    CLOSED = 'closed'


def _no_async_flights() -> bool:
    return False


def _noop() -> None:
    pass


@dataclass(eq=False, slots=True)
class _Ticket:
    gate: 'LifecycleGate'
    kind: str
    loop: asyncio.AbstractEventLoop | None
    thread_id: int
    active: bool = True
    context_token: ContextToken[tuple['_Ticket', ...]] | None = None


_held_tickets: ContextVar[tuple[_Ticket, ...]] = ContextVar('depin_lifecycle_tickets', default=())


class LifecycleGate:
    """Coordinates admission without holding its mutex across user code."""

    __slots__ = (
        'active',
        'active_async',
        'flights',
        'gate_waiters',
        'generation',
        'has_async_flights',
        'mutex',
        'on_quiesce',
        'on_reopen',
        'state',
    )

    def __init__(self) -> None:
        self.mutex = threading.Lock()
        self.state = LifecycleState.OPEN
        self.active = 0
        self.active_async = 0
        self.flights: Mapping[object, object] = {}
        self.has_async_flights: Callable[[], bool] = _no_async_flights
        self.on_quiesce: Callable[[], None] = _noop
        self.on_reopen: Callable[[], None] = _noop
        self.generation = 0
        self.gate_waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = []

    def admit(self, kind: str, *, asynchronous: bool) -> _Ticket:
        loop = asyncio.get_running_loop() if asynchronous else None
        with self.mutex:
            if self.state is LifecycleState.CLOSED:
                raise ContainerClosedError(
                    'container is closed; build a new FrozenContainer before resolving or opening a scope'
                )
            if self.state is not LifecycleState.OPEN and not self._has_active_ancestor():
                raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
            ticket = _Ticket(self, kind, loop, threading.get_ident())
            self.active += 1
            if asynchronous:
                self.active_async += 1
        ticket.context_token = _held_tickets.set((*_held_tickets.get(), ticket))
        return ticket

    def release(self, ticket: _Ticket) -> None:
        if not ticket.active:
            return
        ticket.active = False
        if ticket.context_token is not None:
            _held_tickets.reset(ticket.context_token)
        with self.mutex:
            self.active -= 1
            if ticket.loop is not None:
                self.active_async -= 1
            quiet = self.active == 0
        if quiet:
            self.wake_waiters()

    def has_active_ticket(self) -> bool:
        return self._has_active_ancestor()

    def begin_sync_close(self, has_async_teardowns: bool) -> bool:
        if self.has_active_ticket():
            raise ContainerLifecycleError(
                'cannot close this container from inside its active resolution or scope; '
                'exit that operation, then call close(), or await aclose() from outside it'
            )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise AsyncInSyncContextError('close() cannot run inside an event loop; await aclose() instead')
        with self.mutex:
            if self.state is LifecycleState.CLOSED:
                return False
            if self.state is not LifecycleState.OPEN:
                raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
            if self.active_async or self.has_async_flights():
                raise AsyncInSyncContextError(
                    'close() cannot run while asynchronous resolutions or scopes are active; '
                    'await aclose() so their event loops can continue'
                )
            if self.active or self.flights:
                raise ContainerLifecycleError(
                    'close() cannot run while resolutions or scopes are active; let them finish, then call close()'
                )
            self.state = LifecycleState.QUIESCING
            self.generation += 1
            if has_async_teardowns:
                self.state = LifecycleState.OPEN
                raise AsyncInSyncContextError('close() cannot drain async singleton teardowns; await aclose() instead')
            self.state = LifecycleState.DRAINING
            self.on_quiesce()
            return True

    def begin_async_close(self) -> bool:
        if self.has_active_ticket():
            raise ContainerLifecycleError(
                'cannot close this container from inside its active resolution or scope; '
                'exit that operation, then call close(), or await aclose() from outside it'
            )
        with self.mutex:
            if self.state is LifecycleState.CLOSED:
                return False
            if self.state is LifecycleState.OPEN:
                self.state = LifecycleState.QUIESCING
                self.generation += 1
                self.on_quiesce()
                return True
            return False

    async def wait_until_quiet(self) -> None:
        while True:
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            with self.mutex:
                if self.active == 0:
                    return
                waiter = (loop, future)
                self.gate_waiters.append(waiter)
            try:
                await future
            finally:
                with self.mutex:
                    if waiter in self.gate_waiters:
                        self.gate_waiters.remove(waiter)

    def begin_draining(self) -> None:
        with self.mutex:
            if self.state is LifecycleState.QUIESCING:
                self.state = LifecycleState.DRAINING

    def reopen(self) -> None:
        with self.mutex:
            self.state = LifecycleState.OPEN
            self.on_reopen()
        self.wake_waiters()

    def close(self) -> None:
        with self.mutex:
            self.state = LifecycleState.CLOSED
        self.wake_waiters()

    async def join(self) -> None:
        while True:
            with self.mutex:
                if self.state is LifecycleState.CLOSED or self.state is LifecycleState.OPEN:
                    return
            await self.wait_until_quiet()
            await asyncio.sleep(0)

    def _has_active_ancestor(self) -> bool:
        return any(ticket.gate is self and ticket.active for ticket in _held_tickets.get())

    def wake_waiters(self) -> None:
        with self.mutex:
            waiters = tuple(self.gate_waiters)
            self.gate_waiters.clear()
        for loop, future in waiters:
            if loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(self._complete, future)
            except RuntimeError:
                continue

    @staticmethod
    def _complete(future: asyncio.Future[None]) -> None:
        if not future.done():
            future.set_result(None)


def create_lifecycle_gate() -> LifecycleGate:
    """Create the gate owned by one frozen container."""
    return LifecycleGate()
