"""Shared application model for tier 3 workloads."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI

_PROVIDER_WORK = 500
_HANDLER_WORK = 1500


class WorkloadError(RuntimeError):
    """A benchmark application answered with something the workload cannot be measured against."""


class Sink(Protocol):
    """Where a service reports that it was constructed or closed.

    The recording sink is used by `Implementation.observe`, the null sink by
    `Implementation.prepare`. Both make the same calls, so the timed path and the
    observed path differ by two list appends and nothing else.
    """

    def built(self, name: str) -> None: ...
    def closed(self, name: str) -> None: ...


class NullSink:
    """The sink used inside the timed region: same call, no retention."""

    __slots__ = ()

    def built(self, name: str) -> None: ...
    def closed(self, name: str) -> None: ...


class TraceSink:
    """The sink used to prove two implementations equivalent, keeping order."""

    __slots__ = ('_built', '_closed')

    def __init__(self) -> None:
        self._built: list[str] = []
        self._closed: list[str] = []

    def built(self, name: str) -> None:
        self._built.append(name)

    def closed(self, name: str) -> None:
        self._closed.append(name)

    def reset(self) -> None:
        """Drop everything recorded so far, so a request is observed without its warmup."""
        self._built.clear()
        self._closed.clear()

    @property
    def constructed(self) -> tuple[str, ...]:
        return tuple(self._built)

    @property
    def disposed(self) -> tuple[str, ...]:
        return tuple(self._closed)


@dataclass(frozen=True, slots=True)
class Deployment:
    """A built application and the coroutine that constructs its singletons.

    `warm` is separated from construction because `depin` builds async singletons
    through `awarmup()`, which needs a running loop, while the hand-wired twin
    builds them in the builder. Both run outside every timed region.
    """

    app: FastAPI
    warm: Callable[[], Awaitable[None]]


async def _already_warm() -> None:
    return None


def simulated_work(units: int) -> int:
    """Deterministic CPU work standing in for what an endpoint actually does.

    Integer arithmetic rather than a sleep: a sleep yields the loop and measures
    the scheduler, and the same call has to cost the same on both sides of a pair.
    """
    total = 0
    for index in range(units):
        total = (total * 31 + index) % 1000003
    return total


class Settings:
    __slots__ = ('currency', 'rate')

    def __init__(self, sink: Sink) -> None:
        self.currency = 'EUR'
        self.rate = 3
        sink.built('Settings')


class Clock:
    __slots__ = ()

    def __init__(self, sink: Sink) -> None:
        sink.built('Clock')

    def stamp(self) -> str:
        return '2026-09-02T00:00:00Z'


class Catalog:
    __slots__ = ('_rate',)

    def __init__(self, settings: Settings, sink: Sink) -> None:
        self._rate = settings.rate
        sink.built('Catalog')

    def price(self, sku: int) -> int:
        return sku * self._rate + 100


class RequestId:
    __slots__ = ('value',)

    def __init__(self, clock: Clock, sink: Sink) -> None:
        self.value = clock.stamp()
        sink.built('RequestId')


class SessionStore:
    __slots__ = ('key',)

    def __init__(self, request_id: RequestId, sink: Sink) -> None:
        self.key = f'session:{request_id.value}'
        sink.built('SessionStore')


class ReportService:
    __slots__ = ('_catalog', '_store')

    def __init__(self, store: SessionStore, catalog: Catalog, sink: Sink) -> None:
        self._store = store
        self._catalog = catalog
        sink.built('ReportService')

    def summary(self) -> dict[str, str]:
        return {'session': self._store.key, 'total': str(self._catalog.price(7))}


class Cart:
    __slots__ = ('currency',)

    def __init__(self, settings: Settings, sink: Sink) -> None:
        self.currency = settings.currency
        sink.built('Cart')


class PricingService:
    __slots__ = ('_cart', '_catalog')

    def __init__(self, catalog: Catalog, cart: Cart, sink: Sink) -> None:
        self._catalog = catalog
        self._cart = cart
        sink.built('PricingService')

    def quote(self) -> dict[str, str]:
        return {'currency': self._cart.currency, 'amount': str(self._catalog.price(3))}


class Ledger:
    __slots__ = ('_sink', 'entries')

    def __init__(self, settings: Settings, sink: Sink) -> None:
        self.entries = settings.rate
        self._sink = sink
        sink.built('Ledger')

    def append(self, amount: int) -> None:
        self.entries += amount

    def close(self) -> None:
        self._sink.closed('Ledger')


class AuditTrail:
    __slots__ = ('_ledger', '_sink')

    def __init__(self, ledger: Ledger, sink: Sink) -> None:
        self._ledger = ledger
        self._sink = sink
        sink.built('AuditTrail')

    def record(self, amount: int) -> int:
        self._ledger.append(amount)
        return self._ledger.entries

    def close(self) -> None:
        self._sink.closed('AuditTrail')


class Repository:
    __slots__ = ('digest',)

    def __init__(self, settings: Settings, sink: Sink) -> None:
        self.digest = simulated_work(_PROVIDER_WORK) + settings.rate
        sink.built('Repository')


class OrderService:
    __slots__ = ('_catalog', '_repository')

    def __init__(self, repository: Repository, catalog: Catalog, sink: Sink) -> None:
        self._repository = repository
        self._catalog = catalog
        sink.built('OrderService')

    def place(self) -> dict[str, str]:
        return {'digest': str(self._repository.digest), 'price': str(self._catalog.price(11))}


def _order_payload(service: OrderService) -> dict[str, str]:
    """The endpoint body shared by both implementations of the realistic route."""
    payload = service.place()
    payload['handled'] = str(simulated_work(_HANDLER_WORK))
    return payload


def _ledger_payload(trail: AuditTrail) -> dict[str, str]:
    return {'entries': str(trail.record(5))}


type Builder = Callable[[Sink], Deployment]
