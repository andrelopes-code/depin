"""Asynchronous-service application deployments."""

from collections.abc import AsyncGenerator

from fastapi import FastAPI

from depin import Container, Scope
from depin.ext.fastapi import Inject, RequestScope

from .model import (
    AuditTrail,
    Catalog,
    Deployment,
    Ledger,
    OrderService,
    Repository,
    Settings,
    Sink,
    already_warm,
    ledger_payload,
    order_payload,
)


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
        return ledger_payload(trail)

    async def order(service: Inject[OrderService]) -> dict[str, str]:
        return order_payload(service)

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
                return ledger_payload(trail)
            finally:
                trail.close()
        finally:
            opened.close()

    async def order() -> dict[str, str]:
        repository = Repository(settings, sink)
        service = OrderService(repository, catalog, sink)
        return order_payload(service)

    app.add_api_route('/ledger', ledger, methods=['GET'])
    app.add_api_route('/order', order, methods=['GET'])
    return Deployment(app=app, warm=already_warm)
