"""Application workload claims and ordered inventory."""

from benchmarks.contracts import Claim, Implementation, Metric, Tier, Workload

from .async_ import build_depin_async_deployment, build_direct_async_deployment
from .measurement import observe_startup, prepare_startup, request_implementations
from .sync import build_depin_sync_deployment, build_direct_sync_deployment

REQUEST_INCLUDED = (
    'one httpx request through the in-process ASGI transport: Starlette routing, the RequestScope '
    'middleware, FastAPI dependency solving, provider resolution, the handler, response serialisation, '
    'scope teardown, one run_until_complete of an already running loop, and the two process_time_ns '
    'reads that report CPU beside wall time'
)
REQUEST_EXCLUDED = (
    'the event loop, the ASGI transport, the httpx client, container declaration, freeze, singleton '
    'warmup, and one primed request that absorbs route matching and first-scope costs; no socket, DNS '
    'or network stack exists in this measurement'
)
REQUEST_CONCURRENCY = 'one event loop, one request in flight at a time; no concurrency and no threads'

TIER_THREE_INVALID = (
    'It is not a throughput figure for a served application: there is no socket, no worker process, no '
    'load generator, and one request is in flight at a time.',
    'It is not a statement about FastAPI, uvicorn or httpx performance. Those are constants of the pair; '
    'only the difference between the two sides is attributable to depin.',
    'It does not cover a `def` route handler. Both applications use `async def` handlers so the provider '
    'shape is what differs between them, which means neither number includes the threadpool hop FastAPI '
    'performs for a synchronous handler.',
    'It is host-specific. What transfers is the ratio to the hand-wired baseline, not the absolute time.',
)

STATUS_CLAIM = Claim(
    question='On the cheapest possible endpoint, how much of a request does depin account for?',
    work='Resolve one cached singleton through Inject and return a two-field JSON body.',
    included=REQUEST_INCLUDED,
    excluded=REQUEST_EXCLUDED,
    semantics='One singleton, already constructed by warmup; the request scope opens and closes empty.',
    shape='One node, no edges.',
    concurrency=REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    valid=(
        'The largest share of a request that depin can account for in this suite, because the endpoint '
        'does no application work at all.',
        'An upper bound on the relative overhead the other tier 3 endpoints can show.',
    ),
    invalid=TIER_THREE_INVALID,
)

REPORT_CLAIM = Claim(
    question='What does a request-scoped service graph cost inside a real request?',
    work='Resolve a three-node scoped chain — RequestId, SessionStore, ReportService — and serialise its summary.',
    included=REQUEST_INCLUDED,
    excluded=REQUEST_EXCLUDED,
    semantics=(
        'Three scoped providers built once per request and dropped when the request scope closes; one '
        'cached singleton read on the way through. Nothing is torn down, because none of them is a resource.'
    ),
    shape='A chain of three scoped nodes over two singletons.',
    concurrency=REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    valid=(
        'What per-request construction of a small scoped graph costs against writing the same three '
        'constructor calls in the handler.',
    ),
    invalid=(
        *TIER_THREE_INVALID,
        'It does not scale to a larger graph by multiplication: tier 4 measures the curve, this is one point.',
    ),
)

PRICE_CLAIM = Claim(
    question='What does mixing cached singletons with transient request services cost?',
    work='Resolve a transient PricingService over a transient Cart and two cached singletons, and serialise its quote.',
    included=REQUEST_INCLUDED,
    excluded=REQUEST_EXCLUDED,
    semantics=(
        'Two transients constructed per request and never cached, over singletons constructed once at '
        'warmup. A transient is not registered for teardown, so the request scope closes with nothing to run.'
    ),
    shape='Two transient nodes over two singleton nodes.',
    concurrency=REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    valid=(
        'The cost of the cache-hit path and the transient path in the same request, against the same two '
        'constructor calls written by hand.',
    ),
    invalid=(
        *TIER_THREE_INVALID,
        'It does not separate the singleton lookup from the transient construction. Tier 1 isolates each; '
        'this endpoint deliberately measures them together.',
    ),
)

LEDGER_CLAIM = Claim(
    question='What does an async resource with deterministic teardown cost inside a request?',
    work=(
        'Resolve a scoped AuditTrail over a scoped Ledger, both async-generator resources, and close both '
        'when the scope exits.'
    ),
    included=REQUEST_INCLUDED,
    excluded=REQUEST_EXCLUDED,
    semantics=(
        'Two async-generator providers built once per request, registered for teardown, and closed in '
        'reverse construction order when the request scope exits. The hand-wired twin closes them in the '
        'same order but inside the handler, so its teardown runs before the response is serialised rather '
        'than after — the order is identical, the position in the request is not.'
    ),
    shape='Two scoped resource nodes over one singleton.',
    concurrency=REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    valid=(
        'What registering and draining two async resources per request costs against a hand-written '
        'try/finally pair around the same two objects.',
    ),
    invalid=(
        *TIER_THREE_INVALID,
        'It does not measure a resource that performs I/O. Both sides close an in-memory object, so the '
        'figure is the bookkeeping cost of teardown and nothing else.',
        'It does not compare teardown position. depin drains after the response is sent and the baseline '
        'drains before; the two are not interchangeable for a resource whose close is observable to a client.',
    ),
)

ORDER_CLAIM = Claim(
    question='At what amount of application work does the resolution cost stop mattering?',
    work=(
        'Resolve a scoped OrderService over a scoped Repository and a cached Catalog, where the provider '
        'performs 500 units and the handler 1500 units of deterministic integer work.'
    ),
    included=REQUEST_INCLUDED,
    excluded=REQUEST_EXCLUDED,
    semantics=(
        'Two scoped providers per request over one singleton, with the simulated work inside the provider '
        'and inside the handler.'
    ),
    shape='Two scoped nodes over two singleton nodes.',
    concurrency=REQUEST_CONCURRENCY,
    metric=Metric.LATENCY,
    unit='seconds per operation',
    valid=(
        'The relative overhead of depin once an endpoint performs an amount of work comparable to a small '
        'query and a small serialisation, read against the same endpoint with no simulated work.',
    ),
    invalid=(
        *TIER_THREE_INVALID,
        'The simulated work is CPU-bound integer arithmetic. A real endpoint that awaits I/O releases the '
        'loop, and this measurement says nothing about that case.',
        'The chosen work sizes are arbitrary. The number is a demonstration that the ratio falls as work '
        'rises, not a claim that any particular endpoint is this cheap.',
    ),
)

STARTUP_CLAIM = Claim(
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
        claim=STATUS_CLAIM,
        subject=request_implementations('depin', build_depin_sync_deployment, '/status'),
        baseline=request_implementations('direct', build_direct_sync_deployment, '/status'),
    ),
    Workload(
        name='fastapi_request_scoped_graph',
        tier=Tier.APPLICATION,
        claim=REPORT_CLAIM,
        subject=request_implementations('depin', build_depin_sync_deployment, '/report'),
        baseline=request_implementations('direct', build_direct_sync_deployment, '/report'),
    ),
    Workload(
        name='fastapi_singletons_and_transients',
        tier=Tier.APPLICATION,
        claim=PRICE_CLAIM,
        subject=request_implementations('depin', build_depin_sync_deployment, '/price'),
        baseline=request_implementations('direct', build_direct_sync_deployment, '/price'),
    ),
    Workload(
        name='fastapi_async_resource_teardown',
        tier=Tier.APPLICATION,
        claim=LEDGER_CLAIM,
        subject=request_implementations('depin', build_depin_async_deployment, '/ledger'),
        baseline=request_implementations('direct', build_direct_async_deployment, '/ledger'),
    ),
    Workload(
        name='fastapi_endpoint_with_work',
        tier=Tier.APPLICATION,
        claim=ORDER_CLAIM,
        subject=request_implementations('depin', build_depin_async_deployment, '/order'),
        baseline=request_implementations('direct', build_direct_async_deployment, '/order'),
    ),
    Workload(
        name='fastapi_application_startup',
        tier=Tier.APPLICATION,
        claim=STARTUP_CLAIM,
        subject=Implementation(
            label='depin',
            prepare=lambda: prepare_startup(build_depin_sync_deployment),
            observe=lambda: observe_startup(build_depin_sync_deployment),
        ),
        baseline=Implementation(
            label='direct',
            prepare=lambda: prepare_startup(build_direct_sync_deployment),
            observe=lambda: observe_startup(build_direct_sync_deployment),
        ),
    ),
)
