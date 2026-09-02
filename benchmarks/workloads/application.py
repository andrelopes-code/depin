"""Tier 3: two FastAPI applications, driven in process, each paired with a hand-wired twin.

The tier answers one question the isolated tiers cannot: what a resolution costs
once a real framework is around it. That only means something when the framework
is on both sides, so every workload here is measured against *the same FastAPI
application performing the same service work*, wired with plain closures and an
explicit construction order instead of a container.

Two rules keep the numbers attributable.

The event loop and the `httpx.AsyncClient` are built in `prepare` and released
through `Prepared.close`. A measurement that creates a loop per call is dominated
by asyncio's startup: on the reference host `run_until_complete` of a bare
coroutine costs 16.1 us against 19.6 us for the same call resolving a cached
singleton, so 82% of that timed region is the loop boundary rather than `depin`.
What remains inside the timed region is one `run_until_complete` of an already
running loop, identical on both sides.

Startup is a separate workload. Declaration, `freeze()`, warmup and route
registration are paid once per process; folding them into a per-request figure
would misreport both.
"""

import asyncio
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from starlette.routing import Route

from benchmarks.contracts import Claim, Implementation, Metric, NoiseClass, Observation, Prepared, Tier, Workload
from depin import Container, Scope
from depin.ext.fastapi import Inject, RequestScope

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
class Cost:
    """What one timed call consumed, so throughput is never reported without CPU beside it.

    `pytest-benchmark` records wall time; the process CPU time a call spent is
    returned from the call itself, because a higher request rate bought with more
    CPU is not an improvement.
    """

    cpu_nanoseconds: int


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


def build_depin_sync_deployment(sink: Sink) -> Deployment:
    """The sync-service application: every provider is a plain callable, warmed synchronously."""

    def provide_settings() -> Settings:
        return Settings(sink)

    def provide_clock() -> Clock:
        return Clock(sink)

    def provide_catalog(settings: Settings) -> Catalog:
        return Catalog(settings, sink)

    def provide_request_id(clock: Clock) -> RequestId:
        return RequestId(clock, sink)

    def provide_session_store(request_id: RequestId) -> SessionStore:
        return SessionStore(request_id, sink)

    def provide_report_service(store: SessionStore, catalog: Catalog) -> ReportService:
        return ReportService(store, catalog, sink)

    def provide_cart(settings: Settings) -> Cart:
        return Cart(settings, sink)

    def provide_pricing_service(catalog: Catalog, cart: Cart) -> PricingService:
        return PricingService(catalog, cart, sink)

    frozen = (
        Container()
        .bind(provide_settings)
        .bind(provide_clock)
        .bind(provide_catalog)
        .bind(provide_request_id, scope=Scope.SCOPED)
        .bind(provide_session_store, scope=Scope.SCOPED)
        .bind(provide_report_service, scope=Scope.SCOPED)
        .bind(provide_cart, scope=Scope.TRANSIENT)
        .bind(provide_pricing_service, scope=Scope.TRANSIENT)
        .freeze()
    )
    _ = frozen.warmup()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    async def status(clock: Inject[Clock]) -> dict[str, str]:
        return {'stamp': clock.stamp()}

    async def report(service: Inject[ReportService]) -> dict[str, str]:
        return service.summary()

    async def price(service: Inject[PricingService]) -> dict[str, str]:
        return service.quote()

    app.add_api_route('/status', status, methods=['GET'])
    app.add_api_route('/report', report, methods=['GET'])
    app.add_api_route('/price', price, methods=['GET'])
    return Deployment(app=app, warm=_already_warm)


def build_direct_sync_deployment(sink: Sink) -> Deployment:
    """The same application and the same service work, wired by hand.

    Singletons are constructed once here — the hand-written counterpart of
    `warmup()` — and captured by the route closures. Scoped values are built in
    dependency order inside the handler, transients on every request.
    """
    settings = Settings(sink)
    clock = Clock(sink)
    catalog = Catalog(settings, sink)

    app = FastAPI()

    async def status() -> dict[str, str]:
        return {'stamp': clock.stamp()}

    async def report() -> dict[str, str]:
        request_id = RequestId(clock, sink)
        store = SessionStore(request_id, sink)
        return ReportService(store, catalog, sink).summary()

    async def price() -> dict[str, str]:
        cart = Cart(settings, sink)
        return PricingService(catalog, cart, sink).quote()

    app.add_api_route('/status', status, methods=['GET'])
    app.add_api_route('/report', report, methods=['GET'])
    app.add_api_route('/price', price, methods=['GET'])
    return Deployment(app=app, warm=_already_warm)


def build_depin_async_deployment(sink: Sink) -> Deployment:
    """The async-service application: async factories, async-generator resources, scope teardown."""

    async def provide_settings() -> Settings:
        return Settings(sink)

    async def provide_catalog(settings: Settings) -> Catalog:
        return Catalog(settings, sink)

    async def provide_ledger(settings: Settings) -> AsyncGenerator[Ledger]:
        ledger = Ledger(settings, sink)
        try:
            yield ledger
        finally:
            ledger.close()

    async def provide_audit_trail(ledger: Ledger) -> AsyncGenerator[AuditTrail]:
        trail = AuditTrail(ledger, sink)
        try:
            yield trail
        finally:
            trail.close()

    async def provide_repository(settings: Settings) -> Repository:
        return Repository(settings, sink)

    async def provide_order_service(repository: Repository, catalog: Catalog) -> OrderService:
        return OrderService(repository, catalog, sink)

    frozen = (
        Container()
        .bind(provide_settings)
        .bind(provide_catalog)
        .bind(provide_ledger, scope=Scope.SCOPED)
        .bind(provide_audit_trail, scope=Scope.SCOPED)
        .bind(provide_repository, scope=Scope.SCOPED)
        .bind(provide_order_service, scope=Scope.SCOPED)
        .freeze()
    )

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    async def ledger(trail: Inject[AuditTrail]) -> dict[str, str]:
        return _ledger_payload(trail)

    async def order(service: Inject[OrderService]) -> dict[str, str]:
        return _order_payload(service)

    app.add_api_route('/ledger', ledger, methods=['GET'])
    app.add_api_route('/order', order, methods=['GET'])

    async def warm() -> None:
        _ = await frozen.awarmup()

    return Deployment(app=app, warm=warm)


def build_direct_async_deployment(sink: Sink) -> Deployment:
    """The async application wired by hand, closing its resources in reverse construction order."""
    settings = Settings(sink)
    catalog = Catalog(settings, sink)

    app = FastAPI()

    async def ledger() -> dict[str, str]:
        opened = Ledger(settings, sink)
        try:
            trail = AuditTrail(opened, sink)
            try:
                return _ledger_payload(trail)
            finally:
                trail.close()
        finally:
            opened.close()

    async def order() -> dict[str, str]:
        repository = Repository(settings, sink)
        service = OrderService(repository, catalog, sink)
        return _order_payload(service)

    app.add_api_route('/ledger', ledger, methods=['GET'])
    app.add_api_route('/order', order, methods=['GET'])
    return Deployment(app=app, warm=_already_warm)


type Builder = Callable[[Sink], Deployment]


def _prepare_request(build: Builder, path: str) -> Prepared:
    """Open the loop, the transport and the client, prime the route, and hand back one request.

    Everything a request does not pay for on the steady path is done here: the
    loop, the ASGI transport, the client, the singleton warmup, and one primed
    request that absorbs route-matching and first-scope costs.
    """
    deployment = build(NullSink())
    loop = asyncio.new_event_loop()
    client = AsyncClient(transport=ASGITransport(app=deployment.app), base_url='http://bench')

    def close() -> None:
        loop.run_until_complete(client.aclose())
        loop.close()

    try:
        loop.run_until_complete(deployment.warm())
        primed = loop.run_until_complete(client.get(path))
        if primed.status_code != 200:
            raise WorkloadError(f'{path} answered {primed.status_code}: {primed.text}')
    except BaseException:
        close()
        raise

    def call() -> object:
        started = time.process_time_ns()
        _: Response = loop.run_until_complete(client.get(path))
        return Cost(cpu_nanoseconds=time.process_time_ns() - started)

    return Prepared(call=call, close=close)


def _observe_request(build: Builder, path: str) -> Observation:
    """Run one request with a recording sink, after warmup, and report what it built and closed."""
    sink = TraceSink()
    deployment = build(sink)
    loop = asyncio.new_event_loop()
    client = AsyncClient(transport=ASGITransport(app=deployment.app), base_url='http://bench')
    try:
        loop.run_until_complete(deployment.warm())
        sink.reset()
        response = loop.run_until_complete(client.get(path))
        loop.run_until_complete(client.aclose())
    finally:
        loop.close()
    return Observation(
        result=f'{response.status_code} {response.text}',
        constructed=sink.constructed,
        closed=sink.disposed,
    )


def _prepare_startup(build: Builder) -> Prepared:
    def call() -> object:
        started = time.process_time_ns()
        _ = build(NullSink())
        return Cost(cpu_nanoseconds=time.process_time_ns() - started)

    return Prepared(call=call)


def _observe_startup(build: Builder) -> Observation:
    sink = TraceSink()
    deployment = build(sink)
    paths = sorted(route.path for route in deployment.app.routes if isinstance(route, Route))
    return Observation(result=' '.join(paths), constructed=sink.constructed, closed=sink.disposed)


def _request_implementations(label: str, build: Builder, path: str) -> Implementation:
    return Implementation(
        label=label,
        prepare=lambda: _prepare_request(build, path),
        observe=lambda: _observe_request(build, path),
    )


_REQUEST_INCLUDED = (
    'one httpx request through the in-process ASGI transport: Starlette routing, the RequestScope '
    'middleware, FastAPI dependency solving, provider resolution, the handler, response serialisation, '
    'scope teardown, one run_until_complete of an already running loop, and the two process_time_ns '
    'reads that report CPU beside wall time'
)
_REQUEST_EXCLUDED = (
    'the event loop, the ASGI transport, the httpx client, container declaration, freeze, singleton '
    'warmup, and one primed request that absorbs route matching and first-scope costs; no socket, DNS '
    'or network stack exists in this measurement'
)
_REQUEST_CONCURRENCY = 'one event loop, one request in flight at a time; no concurrency and no threads'

_TIER_THREE_INVALID = (
    'It is not a throughput figure for a served application: there is no socket, no worker process, no '
    'load generator, and one request is in flight at a time.',
    'It is not a statement about FastAPI, uvicorn or httpx performance. Those are constants of the pair; '
    'only the difference between the two sides is attributable to depin.',
    'It does not cover a `def` route handler. Both applications use `async def` handlers so the provider '
    'shape is what differs between them, which means neither number includes the threadpool hop FastAPI '
    'performs for a synchronous handler.',
    'It is host-specific. What transfers is the ratio to the hand-wired baseline, not the absolute time.',
)


_STATUS_CLAIM = Claim(
    question='On the cheapest possible endpoint, how much of a request does depin account for?',
    work='Resolve one cached singleton through Inject and return a two-field JSON body.',
    included=_REQUEST_INCLUDED,
    excluded=_REQUEST_EXCLUDED,
    semantics='One singleton, already constructed by warmup; the request scope opens and closes empty.',
    shape='One node, no edges.',
    concurrency=_REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    noise=NoiseClass.HIGH,
    valid=(
        'The largest share of a request that depin can account for in this suite, because the endpoint '
        'does no application work at all.',
        'An upper bound on the relative overhead the other tier 3 endpoints can show.',
    ),
    invalid=_TIER_THREE_INVALID,
)

_REPORT_CLAIM = Claim(
    question='What does a request-scoped service graph cost inside a real request?',
    work='Resolve a three-node scoped chain — RequestId, SessionStore, ReportService — and serialise its summary.',
    included=_REQUEST_INCLUDED,
    excluded=_REQUEST_EXCLUDED,
    semantics=(
        'Three scoped providers built once per request and dropped when the request scope closes; one '
        'cached singleton read on the way through. Nothing is torn down, because none of them is a resource.'
    ),
    shape='A chain of three scoped nodes over two singletons.',
    concurrency=_REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    noise=NoiseClass.HIGH,
    valid=(
        'What per-request construction of a small scoped graph costs against writing the same three '
        'constructor calls in the handler.',
    ),
    invalid=(
        *_TIER_THREE_INVALID,
        'It does not scale to a larger graph by multiplication: tier 4 measures the curve, this is one point.',
    ),
)

_PRICE_CLAIM = Claim(
    question='What does mixing cached singletons with transient request services cost?',
    work='Resolve a transient PricingService over a transient Cart and two cached singletons, and serialise its quote.',
    included=_REQUEST_INCLUDED,
    excluded=_REQUEST_EXCLUDED,
    semantics=(
        'Two transients constructed per request and never cached, over singletons constructed once at '
        'warmup. A transient is not registered for teardown, so the request scope closes with nothing to run.'
    ),
    shape='Two transient nodes over two singleton nodes.',
    concurrency=_REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    noise=NoiseClass.HIGH,
    valid=(
        'The cost of the cache-hit path and the transient path in the same request, against the same two '
        'constructor calls written by hand.',
    ),
    invalid=(
        *_TIER_THREE_INVALID,
        'It does not separate the singleton lookup from the transient construction. Tier 1 isolates each; '
        'this endpoint deliberately measures them together.',
    ),
)

_LEDGER_CLAIM = Claim(
    question='What does an async resource with deterministic teardown cost inside a request?',
    work=(
        'Resolve a scoped AuditTrail over a scoped Ledger, both async-generator resources, and close both '
        'when the scope exits.'
    ),
    included=_REQUEST_INCLUDED,
    excluded=_REQUEST_EXCLUDED,
    semantics=(
        'Two async-generator providers built once per request, registered for teardown, and closed in '
        'reverse construction order when the request scope exits. The hand-wired twin closes them in the '
        'same order but inside the handler, so its teardown runs before the response is serialised rather '
        'than after — the order is identical, the position in the request is not.'
    ),
    shape='Two scoped resource nodes over one singleton.',
    concurrency=_REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    noise=NoiseClass.HIGH,
    valid=(
        'What registering and draining two async resources per request costs against a hand-written '
        'try/finally pair around the same two objects.',
    ),
    invalid=(
        *_TIER_THREE_INVALID,
        'It does not measure a resource that performs I/O. Both sides close an in-memory object, so the '
        'figure is the bookkeeping cost of teardown and nothing else.',
        'It does not compare teardown position. depin drains after the response is sent and the baseline '
        'drains before; the two are not interchangeable for a resource whose close is observable to a client.',
    ),
)

_ORDER_CLAIM = Claim(
    question='At what amount of application work does the resolution cost stop mattering?',
    work=(
        'Resolve a scoped OrderService over a scoped Repository and a cached Catalog, where the provider '
        'performs 500 units and the handler 1500 units of deterministic integer work.'
    ),
    included=_REQUEST_INCLUDED,
    excluded=_REQUEST_EXCLUDED,
    semantics=(
        'Two scoped providers per request over one singleton, with the simulated work inside the provider '
        'and inside the handler.'
    ),
    shape='Two scoped nodes over two singleton nodes.',
    concurrency=_REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    noise=NoiseClass.HIGH,
    valid=(
        'The relative overhead of depin once an endpoint performs an amount of work comparable to a small '
        'query and a small serialisation, read against the same endpoint with no simulated work.',
    ),
    invalid=(
        *_TIER_THREE_INVALID,
        'The simulated work is CPU-bound integer arithmetic. A real endpoint that awaits I/O releases the '
        'loop, and this measurement says nothing about that case.',
        'The chosen work sizes are arbitrary. The number is a demonstration that the ratio falls as work '
        'rises, not a claim that any particular endpoint is this cheap.',
    ),
)

_STARTUP_CLAIM = Claim(
    question='What does wiring the application through depin add to process startup?',
    work=(
        'Declare eight providers, freeze the container, warm every singleton, construct the FastAPI '
        'application, install the RequestScope middleware, and register three routes.'
    ),
    included=(
        'container declaration, freeze and graph validation, synchronous warmup of every singleton, '
        'FastAPI application construction, middleware installation, route registration, and the two '
        'process_time_ns reads that report CPU beside wall time'
    ),
    excluded=(
        'module import, because the interpreter caches it and re-importing measures the import system '
        'rather than the application; and every per-request cost, which the other five workloads carry'
    ),
    semantics='Paid once per process. Three singletons are constructed here so no request pays for them.',
    shape='Eight providers: three singletons, three scoped, two transient.',
    concurrency='Single-threaded, no event loop.',
    metric=Metric.LATENCY,
    unit='seconds per operation',
    noise=NoiseClass.MEDIUM,
    valid=(
        'The one-off cost of choosing depin over hand-wiring for an application of this size.',
        'A figure to compare against process start and framework import, both of which dominate it.',
    ),
    invalid=(
        'It is not amortisable into the per-request figures. Those exclude it deliberately.',
        'It does not scale linearly with provider count: freeze validation is measured as a curve in tier 4.',
        'It includes FastAPI application construction and route registration, which are the same on both '
        'sides and larger than the container work; the difference between the sides is the depin part.',
        'It is host-specific. What transfers is the ratio to the hand-wired baseline.',
    ),
)


WORKLOADS: tuple[Workload, ...] = (
    Workload(
        name='fastapi_cpu_light_endpoint',
        tier=Tier.APPLICATION,
        claim=_STATUS_CLAIM,
        subject=_request_implementations('depin', build_depin_sync_deployment, '/status'),
        baseline=_request_implementations('direct', build_direct_sync_deployment, '/status'),
    ),
    Workload(
        name='fastapi_request_scoped_graph',
        tier=Tier.APPLICATION,
        claim=_REPORT_CLAIM,
        subject=_request_implementations('depin', build_depin_sync_deployment, '/report'),
        baseline=_request_implementations('direct', build_direct_sync_deployment, '/report'),
    ),
    Workload(
        name='fastapi_singletons_and_transients',
        tier=Tier.APPLICATION,
        claim=_PRICE_CLAIM,
        subject=_request_implementations('depin', build_depin_sync_deployment, '/price'),
        baseline=_request_implementations('direct', build_direct_sync_deployment, '/price'),
    ),
    Workload(
        name='fastapi_async_resource_teardown',
        tier=Tier.APPLICATION,
        claim=_LEDGER_CLAIM,
        subject=_request_implementations('depin', build_depin_async_deployment, '/ledger'),
        baseline=_request_implementations('direct', build_direct_async_deployment, '/ledger'),
    ),
    Workload(
        name='fastapi_endpoint_with_work',
        tier=Tier.APPLICATION,
        claim=_ORDER_CLAIM,
        subject=_request_implementations('depin', build_depin_async_deployment, '/order'),
        baseline=_request_implementations('direct', build_direct_async_deployment, '/order'),
    ),
    Workload(
        name='fastapi_application_startup',
        tier=Tier.APPLICATION,
        claim=_STARTUP_CLAIM,
        subject=Implementation(
            label='depin',
            prepare=lambda: _prepare_startup(build_depin_sync_deployment),
            observe=lambda: _observe_startup(build_depin_sync_deployment),
        ),
        baseline=Implementation(
            label='direct',
            prepare=lambda: _prepare_startup(build_direct_sync_deployment),
            observe=lambda: _observe_startup(build_direct_sync_deployment),
        ),
    ),
)
