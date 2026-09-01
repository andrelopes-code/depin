"""The examples under `examples/` are executed here so they cannot rot."""

import pytest
from click.testing import CliRunner
from httpx import ASGITransport, AsyncClient

from depin import ProviderShape, optional_hosted_container
from examples.aliasing.main import Page, RedisStore
from examples.aliasing.main import build as build_aliasing
from examples.click_app.main import build_cli
from examples.click_app.main import build_container as build_click_container
from examples.click_app.registries import Database as ClickDatabase
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
from examples.eviction.main import Clock as EvictionClock
from examples.eviction.main import FakeClock as EvictionFakeClock
from examples.eviction.main import Report as EvictionReport
from examples.eviction.main import build as build_eviction
from examples.fastapi_app.main import build_container, create_app
from examples.fastapi_app.registries import Database
from examples.generic_keys.main import Order, ReportService, User
from examples.generic_keys.main import Repo as GenericRepo
from examples.generic_keys.main import build as build_generic_keys
from examples.graph_diagnostics.main import Repo, Settings
from examples.graph_diagnostics.main import build as build_diagnostics
from examples.health.main import Cache as HealthCache
from examples.health.main import Database as HealthDatabase
from examples.health.main import build as build_health
from examples.integration.main import LOG as INTEGRATION_LOG
from examples.integration.main import JobRunner
from examples.integration.main import Metrics as IntegrationMetrics
from examples.integration.main import build as build_integration
from examples.minimal_sync.main import Database as MinimalDatabase
from examples.minimal_sync.main import UserRepo, build
from examples.optional_dependencies.main import Checkout, MetricsSink
from examples.optional_dependencies.main import build as build_optional_dependencies
from examples.scopes.main import AUDIT, Connection, UnitOfWork
from examples.scopes.main import build as build_scopes
from examples.starlette_app.main import build_container as build_starlette_container
from examples.starlette_app.main import create_app as create_starlette_app
from examples.starlette_app.registries import Database as StarletteDatabase
from examples.testing.main import Clock, FrozenClock, Report
from examples.testing.main import build as build_testing
from examples.warmup.main import BUILT as WARMUP_BUILT
from examples.warmup.main import Config as WarmupConfig
from examples.warmup.main import Pool as WarmupPool
from examples.warmup.main import Session as WarmupSession
from examples.warmup.main import build as build_warmup


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


def test_eviction_example_evicts_a_consumer_built_before_the_override() -> None:
    di = build_eviction()
    real = di[EvictionReport]
    assert real.render() == 'report at real-time'

    with di.override(EvictionClock, EvictionFakeClock()):
        assert di[EvictionClock].now() == 'fake-time'
        # Report was built and cached above; the override alone does not
        # touch it.
        assert di[EvictionReport].render() == 'report at real-time'

        di.reset()
        assert di[EvictionReport].render() == 'report at fake-time'

    di.reset()
    assert di[EvictionReport].render() == 'report at real-time'


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


def test_warmup_example_builds_singletons_and_leaves_the_scoped_one_alone() -> None:
    WARMUP_BUILT.clear()
    di = build_warmup()

    report = di.warmup()
    assert [node.key for node in report.constructed] == [WarmupConfig, WarmupPool]
    assert report.cached == ()
    assert WARMUP_BUILT == ['Config', 'Pool']

    # Idempotent: nothing left to build the second time.
    second = di.warmup()
    assert second.constructed == ()
    assert [node.key for node in second.cached] == [WarmupConfig, WarmupPool]

    # Session is scoped and warmup never touches it; it is only built once a
    # scope opens and something resolves it.
    assert WarmupSession not in [node.key for node in report.constructed]
    with di.scope():
        _ = di[WarmupSession]
    assert WARMUP_BUILT == ['Config', 'Pool', 'Session']


def test_health_example_reports_one_passing_and_one_failing_check() -> None:
    di = build_health()

    declared = di.checks()
    assert [check.key for check in declared] == [HealthDatabase, HealthCache]

    report = di.health()
    assert report.healthy is False
    assert [(result.key, result.healthy) for result in report.results] == [
        (HealthDatabase, True),
        (HealthCache, False),
    ]


def test_integration_example_opens_one_scope_per_job() -> None:
    INTEGRATION_LOG.clear()
    di = build_integration()
    runner = JobRunner(di)

    assert runner.run('reindex') == 'reindex (completed=1)'
    assert runner.run('vacuum') == 'vacuum (completed=2)'
    assert INTEGRATION_LOG == ['open reindex', 'close reindex', 'open vacuum', 'close vacuum']
    assert di[IntegrationMetrics].completed == 2
    di.close()


def test_integration_example_leaves_no_container_hosted() -> None:
    di = build_integration()
    _ = JobRunner(di).run('reindex')

    assert optional_hosted_container() is None
    di.close()


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
    # Mutating the singleton before the requests is what turns the assertion
    # below into an identity check: a second `Database` would report the URL
    # `Settings` carries, not this one.
    (await di.aresolve(Database)).url = 'postgres://pinned'

    async with AsyncClient(transport=transport, base_url='http://t') as client:
        first = await client.get('/health')
        second = await client.get('/health')

    assert first.json()['db'] == second.json()['db'] == 'postgres://pinned'
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


@pytest.mark.asyncio
async def test_starlette_example_serves_a_request_per_scope() -> None:
    app = create_starlette_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        user = await client.get('/users', params={'uid': 1}, headers={'user-agent': 'probe/1.0'})
        health = await client.get('/health')

    # `path` and `agent` were read off the request the middleware seeded into the frame.
    assert user.json() == {
        'id': 1,
        'name': 'Ana',
        'db': 'postgres://example',
        'path': '/users',
        'agent': 'probe/1.0',
    }
    # The per-request session was opened and closed again with the scope.
    assert health.json()['open_sessions'] == 0


@pytest.mark.asyncio
async def test_starlette_example_accepts_an_injected_container() -> None:
    di = build_starlette_container()
    app = create_starlette_app(di)
    transport = ASGITransport(app=app)
    # Mutating the singleton before the requests is what turns the assertion
    # below into an identity check: a second `Database` would report the URL
    # `Settings` carries, not this one.
    database = await di.aresolve(StarletteDatabase)
    database.url = 'postgres://pinned'

    async with AsyncClient(transport=transport, base_url='http://t') as client:
        first = await client.get('/health')
        second = await client.get('/health')

    assert first.json()['db'] == second.json()['db'] == 'postgres://pinned'
    assert database.open_sessions == 0
    await di.aclose()


def test_click_example_opens_one_scope_per_invocation() -> None:
    cli = build_cli(build_click_container())
    runner = CliRunner()

    first = runner.invoke(cli, ['--tenant', 'acme', 'report'])
    second = runner.invoke(cli, ['--tenant', 'globex', 'report'])
    health = runner.invoke(cli, ['health'])

    assert first.exit_code == second.exit_code == health.exit_code == 0
    # `tenant` came off an option through the frame `install` returned;
    # `subcommand` off the `click.Context` the integration seeded.
    assert first.output == 'tenant=acme subcommand=report db=postgres://example sessions=1\n'
    assert second.output == 'tenant=globex subcommand=report db=postgres://example sessions=1\n'
    # The per-invocation session was opened and closed again with the scope.
    assert health.output == 'db=postgres://example open_sessions=0\n'
    assert optional_hosted_container() is None


def test_click_example_accepts_an_injected_container() -> None:
    di = build_click_container()
    cli = build_cli(di)
    # Mutating the singleton before the invocations is what turns the assertion
    # below into an identity check: a second `Database` would report the URL
    # `Settings` carries, not this one.
    database = di[ClickDatabase]
    database.url = 'postgres://pinned'

    runner = CliRunner()
    assert runner.invoke(cli, ['health']).output == 'db=postgres://pinned open_sessions=0\n'
    assert runner.invoke(cli, ['report']).output.startswith('tenant=acme subcommand=report db=postgres://pinned')

    di.close()
    assert database.closed
