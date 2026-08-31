"""The examples under `examples/` are executed here so they cannot rot."""

import pytest
from httpx import ASGITransport, AsyncClient

from depin import ProviderShape
from examples.aliasing.main import Page, RedisStore
from examples.aliasing.main import build as build_aliasing
from examples.collections.main import Dispatcher, EmailHandler, Handler, SmsHandler, WebhookHandler
from examples.collections.main import build as build_collections
from examples.conditional.main import Checkout as SwitchedCheckout
from examples.conditional.main import MemoryStore, Metrics, PostgresStore
from examples.conditional.main import Settings as CheckoutSettings
from examples.conditional.main import build as build_conditional
from examples.decoration.main import LOG as DECORATION_LOG
from examples.decoration.main import READS as DECORATION_READS
from examples.decoration.main import Page as DecoratedPage
from examples.decoration.main import Store as DecoratedStore
from examples.decoration.main import build as build_decoration
from examples.fastapi_app.main import build_container, create_app
from examples.fastapi_app.registries import Database
from examples.generic_keys.main import Order, ReportService, User
from examples.generic_keys.main import Repo as GenericRepo
from examples.generic_keys.main import build as build_generic_keys
from examples.graph_diagnostics.main import Repo, Settings
from examples.graph_diagnostics.main import build as build_diagnostics
from examples.minimal_sync.main import Database as MinimalDatabase
from examples.minimal_sync.main import UserRepo, build
from examples.optional_dependencies.main import Checkout, MetricsSink
from examples.optional_dependencies.main import build as build_optional_dependencies
from examples.scopes.main import AUDIT, Connection, UnitOfWork
from examples.scopes.main import build as build_scopes
from examples.testing.main import Clock, FrozenClock, Report
from examples.testing.main import build as build_testing


def test_minimal_sync_example_resolves_and_tears_down() -> None:
    di = build()
    repo = di[UserRepo]
    assert repo.all() == ['ana', 'bia']
    assert repo.db.url == 'postgres://example'
    assert not repo.db.closed

    di.close()
    assert repo.db.closed


def test_minimal_sync_example_shares_the_singleton_database() -> None:
    di = build()
    assert di[UserRepo].db is di[MinimalDatabase]
    di.close()


def test_scopes_example_rebuilds_per_scope_and_reuses_in_nested_scopes() -> None:
    AUDIT.clear()
    di = build_scopes()

    with di.scope():
        first = di[UnitOfWork]
        assert di[UnitOfWork] is first
        with di.scope():
            assert di[Connection] is first.connection

    with di.scope():
        assert di[UnitOfWork] is not first

    assert AUDIT.count('pool created') == 1
    assert AUDIT.count('connection checked out') == 2
    assert AUDIT.count('connection returned') == 2


def test_testing_example_overrides_a_protocol_deep_in_the_graph() -> None:
    di = build_testing()
    assert di[Report].render() == 'report at real-time'

    with di.override(Clock, FrozenClock('2026-01-01')):
        assert di[Report].render() == 'report at 2026-01-01'

    assert di[Report].render() == 'report at real-time'


def test_aliasing_example_serves_one_instance_under_both_names() -> None:
    di = build_aliasing()
    page = di[Page]
    assert page.store is page.cache is di[RedisStore]
    assert page.render() == 'value-for-head + value-for-body'
    assert di[RedisStore].reads == ['head', 'body']


def test_optional_dependencies_example_resolves_to_none_without_the_sink() -> None:
    di = build_optional_dependencies(with_metrics=False)
    assert di[Checkout].metrics is None


def test_optional_dependencies_example_resolves_to_the_sink_when_bound() -> None:
    di = build_optional_dependencies(with_metrics=True)
    assert di[Checkout].metrics is di[MetricsSink]


def test_collections_example_gathers_every_handler_in_declaration_order() -> None:
    di = build_collections()
    handlers = di.resolve(list[Handler])
    assert handlers == [di[EmailHandler], di[SmsHandler], di[WebhookHandler]]
    assert di[Dispatcher].handlers == handlers
    assert di.graph().node(list[Handler]).shape is ProviderShape.COLLECTION


def test_decoration_example_caches_repeated_reads_and_logs_every_call() -> None:
    DECORATION_LOG.clear()
    DECORATION_READS.clear()
    di = build_decoration()
    page = di[DecoratedPage]

    assert page.render('a') == 'row-a'
    assert page.render('a') == 'row-a'
    assert page.render('b') == 'row-b'

    # Logged (outermost) sees every call; Cached (inner) hides the repeated
    # read for 'a' from SqlStore.
    assert DECORATION_LOG == ['a', 'a', 'b']
    assert DECORATION_READS == ['a', 'b']

    tree = di.explain(DecoratedStore)
    assert 'decorated x1' in tree
    assert 'undecorated' in tree


def test_conditional_example_switches_the_store_by_environment() -> None:
    di = build_conditional(CheckoutSettings(environment='production', use_metrics=True))
    checkout = di[SwitchedCheckout]

    assert isinstance(checkout.store, PostgresStore)
    assert checkout.metrics is not None
    assert checkout.complete() == 'pg'
    assert checkout.metrics.events == ['checkout.completed']


def test_conditional_example_resolves_an_inactive_binding_to_none() -> None:
    di = build_conditional(CheckoutSettings(environment='development', use_metrics=False))
    checkout = di[SwitchedCheckout]

    assert isinstance(checkout.store, MemoryStore)
    assert checkout.metrics is None
    assert 'registered but inactive' in di.explain(Metrics)


def test_generic_keys_example_resolves_each_parameterisation_to_its_own_repo() -> None:
    di = build_generic_keys()
    user_repo = di.resolve(GenericRepo[User])
    order_repo = di.resolve(GenericRepo[Order])

    assert [user.name for user in user_repo.rows] == ['ana', 'bia']
    assert [order.reference for order in order_repo.rows] == ['#1001']
    assert di[ReportService].users is user_repo
    assert di[ReportService].orders is order_repo
    assert di.explain(GenericRepo[User]) == 'Repo[User]  [singleton, function]'


def test_graph_diagnostics_example_explains_and_exports_its_graph() -> None:
    di = build_diagnostics()
    tree = di.explain(Repo)

    assert tree.splitlines()[0] == 'Repo  [scoped, class]'
    assert '(shown above)' in tree
    assert di.graph().node(Settings).scope.value == 'singleton'
    assert di.graph().mermaid().startswith('graph LR')
    assert di.graph().dot().startswith('digraph depin {')


@pytest.mark.asyncio
async def test_fastapi_example_serves_a_request_per_scope() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        user = await client.get('/users/1')
        health = await client.get('/health')

    assert user.json() == {'id': 1, 'name': 'Ana', 'db': 'postgres://example'}
    # The per-request session was opened and closed again with the scope.
    assert health.json()['open_sessions'] == 0


@pytest.mark.asyncio
async def test_fastapi_example_accepts_an_injected_container() -> None:
    di = build_container()
    app = create_app(di)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url='http://t') as client:
        first = await client.get('/health')
        second = await client.get('/health')

    assert first.json()['db'] == second.json()['db']
    await di.aclose()


@pytest.mark.asyncio
async def test_fastapi_example_closes_its_container_on_shutdown() -> None:
    di = build_container()
    app = create_app(di)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url='http://t') as client:
        _ = await client.get('/health')

    database = await di.aresolve(Database)
    assert database.open_sessions == 0
