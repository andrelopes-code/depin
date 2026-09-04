"""Synchronous-service application deployments."""

from fastapi import FastAPI

from depin import Container, Scope
from depin.ext.fastapi import Inject, RequestScope

from .model import (
    Cart,
    Catalog,
    Clock,
    Deployment,
    PricingService,
    ReportService,
    RequestId,
    SessionStore,
    Settings,
    Sink,
    _already_warm,
)


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
