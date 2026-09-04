"""Admission and terminal shutdown coordination for frozen containers."""

import asyncio
import threading
from contextvars import ContextVar
from contextvars import Token as ContextToken
from dataclasses import dataclass
from enum import Enum

from depin.errors import AsyncInSyncContextError, ContainerClosedError, ContainerLifecycleError


class _LifecycleState(Enum):
    OPEN = 'open'
    QUIESCING = 'quiescing'
    DRAINING = 'draining'
    CLOSED = 'closed'


@dataclass(eq=False, slots=True)
class _Ticket:
    gate: '_LifecycleGate'
    kind: str
    loop: asyncio.AbstractEventLoop | None
    thread_id: int
    active: bool = True
    context_token: ContextToken[tuple['_Ticket', ...]] | None = None


_held_tickets: ContextVar[tuple[_Ticket, ...]] = ContextVar('depin_lifecycle_tickets', default=())


class _LifecycleGate:
    """Coordinates admission without holding its mutex across user code."""

    __slots__ = ('_active', '_active_async', '_gate_waiters', '_generation', '_mutex', '_state')

    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._state = _LifecycleState.OPEN
        self._active = 0
        self._active_async = 0
        self._generation = 0
        self._gate_waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = []

    def admit(self, kind: str, *, asynchronous: bool) -> _Ticket:
        loop = asyncio.get_running_loop() if asynchronous else None
        with self._mutex:
            if self._state is _LifecycleState.CLOSED:
                raise ContainerClosedError(
                    'container is closed; build a new FrozenContainer before resolving or opening a scope'
                )
            if self._state is not _LifecycleState.OPEN and not self._has_active_ancestor():
                raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
            ticket = _Ticket(self, kind, loop, threading.get_ident())
            self._active += 1
            if asynchronous:
                self._active_async += 1
        ticket.context_token = _held_tickets.set((*_held_tickets.get(), ticket))
        return ticket

    def release(self, ticket: _Ticket) -> None:
        if not ticket.active:
            return
        ticket.active = False
        if ticket.context_token is not None:
            _held_tickets.reset(ticket.context_token)
        with self._mutex:
            self._active -= 1
            if ticket.loop is not None:
                self._active_async -= 1
            quiet = self._active == 0
        if quiet:
            self._wake_waiters()

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
        with self._mutex:
            if self._state is _LifecycleState.CLOSED:
                return False
            if self._state is not _LifecycleState.OPEN:
                raise ContainerLifecycleError('container shutdown is already in progress; await aclose() to join it')
            if self._active_async:
                raise AsyncInSyncContextError(
                    'close() cannot run while asynchronous resolutions or scopes are active; '
                    'await aclose() so their event loops can continue'
                )
            if self._active:
                raise ContainerLifecycleError(
                    'close() cannot run while resolutions or scopes are active; let them finish, then call close()'
                )
            self._state = _LifecycleState.QUIESCING
            self._generation += 1
            if has_async_teardowns:
                self._state = _LifecycleState.OPEN
                raise AsyncInSyncContextError('close() cannot drain async singleton teardowns; await aclose() instead')
            self._state = _LifecycleState.DRAINING
            return True

    def begin_async_close(self) -> bool:
        if self.has_active_ticket():
            raise ContainerLifecycleError(
                'cannot close this container from inside its active resolution or scope; '
                'exit that operation, then call close(), or await aclose() from outside it'
            )
        with self._mutex:
            if self._state is _LifecycleState.CLOSED:
                return False
            if self._state is _LifecycleState.OPEN:
                self._state = _LifecycleState.QUIESCING
                self._generation += 1
                return True
            return False

    async def wait_until_quiet(self) -> None:
        while True:
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            with self._mutex:
                if self._active == 0:
                    return
                waiter = (loop, future)
                self._gate_waiters.append(waiter)
            try:
                await future
            finally:
                with self._mutex:
                    if waiter in self._gate_waiters:
                        self._gate_waiters.remove(waiter)

    def begin_draining(self) -> None:
        with self._mutex:
            if self._state is _LifecycleState.QUIESCING:
                self._state = _LifecycleState.DRAINING

    def reopen(self) -> None:
        with self._mutex:
            self._state = _LifecycleState.OPEN
        self._wake_waiters()

    def close(self) -> None:
        with self._mutex:
            self._state = _LifecycleState.CLOSED
        self._wake_waiters()

    async def join(self) -> None:
        while True:
            with self._mutex:
                if self._state is _LifecycleState.CLOSED or self._state is _LifecycleState.OPEN:
                    return
            await self.wait_until_quiet()
            await asyncio.sleep(0)

    def _has_active_ancestor(self) -> bool:
        return any(ticket.gate is self and ticket.active for ticket in _held_tickets.get())

    def _wake_waiters(self) -> None:
        with self._mutex:
            waiters = tuple(self._gate_waiters)
            self._gate_waiters.clear()
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


def create_lifecycle_gate() -> _LifecycleGate:
    """Create the gate owned by one frozen container."""
    return _LifecycleGate()
