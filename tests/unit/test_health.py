"""`health()` / `ahealth()` run the checks a graph declared, and report what each said."""

from collections.abc import Coroutine, Generator

import pytest

from depin import Container, Scope, Token, Underlying
from depin._core.health import HealthCheck, HealthReport, HealthResult
from depin.errors import AsyncInSyncContextError, InvalidProviderError, OutsideScopeError


def test_a_check_returning_none_is_healthy() -> None:
    class Database: ...

    def ping(db: Database) -> None:
        return None

    di = Container().bind(Database, check=ping).freeze()
    report = di.health()
    assert report.results == (HealthResult(key=Database, tag=None, healthy=True, error=None),)


def test_a_check_returning_true_is_healthy() -> None:
    class Database: ...

    def ping(db: Database) -> bool:
        return True

    di = Container().bind(Database, check=ping).freeze()
    report = di.health()
    assert report.results == (HealthResult(key=Database, tag=None, healthy=True, error=None),)


def test_a_check_returning_false_is_unhealthy_with_no_error() -> None:
    class Database: ...

    def ping(db: Database) -> bool:
        return False

    di = Container().bind(Database, check=ping).freeze()
    report = di.health()
    assert report.results == (HealthResult(key=Database, tag=None, healthy=False, error=None),)


def test_a_raising_check_is_unhealthy_with_the_exception_on_the_result() -> None:
    class Database: ...

    error = ConnectionError('down')

    def ping(db: Database) -> bool:
        raise error

    di = Container().bind(Database, check=ping).freeze()
    report = di.health()
    (result,) = report.results
    assert result.healthy is False
    assert result.error is error


def test_a_check_returning_zero_or_empty_string_is_healthy() -> None:
    class Zero: ...

    class Empty: ...

    def zero_check(_: Zero) -> int:
        return 0

    def empty_check(_: Empty) -> str:
        return ''

    di = Container().bind(Zero, check=zero_check).bind(Empty, check=empty_check).freeze()
    report = di.health()
    assert all(result.healthy for result in report.results)


def test_every_check_runs_even_when_an_earlier_one_failed() -> None:
    ran: list[str] = []

    class First: ...

    class Second: ...

    def broken(_: First) -> None:
        ran.append('first')
        raise RuntimeError('boom')

    def fine(_: Second) -> None:
        ran.append('second')

    di = Container().bind(First, check=broken).bind(Second, check=fine).freeze()
    report = di.health()
    assert ran == ['first', 'second']
    assert len(report.results) == 2
    assert report.results[0].healthy is False
    assert report.results[1].healthy is True


def test_checks_resolves_nothing() -> None:
    built: list[str] = []

    class Database:
        def __init__(self) -> None:
            built.append('database')

    def ping(db: Database) -> None: ...

    di = Container().bind(Database, check=ping).freeze()
    checks = di.checks()
    assert built == []
    assert checks == (HealthCheck(key=Database, tag=None, needs_async=False),)


def test_health_report_healthy_over_all_healthy() -> None:
    report = HealthReport(
        results=(
            HealthResult(key=object, tag=None, healthy=True, error=None),
            HealthResult(key=object, tag=None, healthy=True, error=None),
        )
    )
    assert report.healthy is True


def test_health_report_healthy_over_mixed() -> None:
    report = HealthReport(
        results=(
            HealthResult(key=object, tag=None, healthy=True, error=None),
            HealthResult(key=object, tag=None, healthy=False, error=None),
        )
    )
    assert report.healthy is False


def test_health_report_healthy_over_empty_is_true() -> None:
    assert HealthReport(results=()).healthy is True


def test_checks_reports_needs_async_for_an_async_provider() -> None:
    class Service: ...

    async def service() -> Service:
        return Service()

    def ping(svc: Service) -> None: ...

    di = Container().bind(service, check=ping).freeze()
    (check,) = di.checks()
    assert check.needs_async is True


def test_checks_reports_needs_async_for_an_async_check() -> None:
    class Database: ...

    async def ping(db: Database) -> None: ...

    di = Container().bind(Database, check=ping).freeze()
    (check,) = di.checks()
    assert check.needs_async is True


def test_health_raises_async_in_sync_context_for_an_async_provider() -> None:
    class Service: ...

    async def service() -> Service:
        return Service()

    def ping(svc: Service) -> None: ...

    di = Container().bind(service, check=ping).freeze()
    with pytest.raises(AsyncInSyncContextError, match='ahealth'):
        _ = di.health()


def test_health_raises_async_in_sync_context_for_an_async_check() -> None:
    class Database: ...

    async def ping(db: Database) -> None: ...

    di = Container().bind(Database, check=ping).freeze()
    with pytest.raises(AsyncInSyncContextError, match='ahealth'):
        _ = di.health()


def test_health_refusal_message_names_every_pending_key() -> None:
    class First: ...

    class Second: ...

    async def build_first() -> First:
        return First()

    async def build_second() -> Second:
        return Second()

    def noop_first(_: First) -> None: ...

    def noop_second(_: Second) -> None: ...

    di = Container().bind(build_first, check=noop_first).bind(build_second, check=noop_second).freeze()
    with pytest.raises(AsyncInSyncContextError) as excinfo:
        _ = di.health()
    message = str(excinfo.value)
    assert 'First' in message
    assert 'Second' in message
    assert '->' not in message
    assert ', ' in message


async def test_every_check_runs_under_ahealth_even_when_an_earlier_one_failed() -> None:
    ran: list[str] = []

    class First: ...

    class Second: ...

    async def broken(_: First) -> None:
        ran.append('first')
        raise RuntimeError('boom')

    async def fine(_: Second) -> None:
        ran.append('second')

    di = Container().bind(First, check=broken).bind(Second, check=fine).freeze()
    report = await di.ahealth()
    assert ran == ['first', 'second']
    assert len(report.results) == 2
    assert report.results[0].healthy is False
    assert report.results[1].healthy is True


async def test_ahealth_runs_both_async_providers_and_async_checks() -> None:
    class Service: ...

    async def service() -> Service:
        return Service()

    async def ping(svc: Service) -> bool:
        return True

    di = Container().bind(service, check=ping).freeze()
    report = await di.ahealth()
    assert report.results == (HealthResult(key=Service, tag=None, healthy=True, error=None),)


async def test_ahealth_runs_a_sync_check_over_an_async_provider() -> None:
    class Service: ...

    async def service() -> Service:
        return Service()

    def ping(svc: Service) -> bool:
        return True

    di = Container().bind(service, check=ping).freeze()
    report = await di.ahealth()
    assert report.results == (HealthResult(key=Service, tag=None, healthy=True, error=None),)


async def test_a_raising_async_check_is_unhealthy_with_the_exception_on_the_result() -> None:
    class Database: ...

    error = ConnectionError('down')

    async def ping(db: Database) -> bool:
        raise error

    di = Container().bind(Database, check=ping).freeze()
    report = await di.ahealth()
    (result,) = report.results
    assert result.healthy is False
    assert result.error is error


async def test_ahealth_propagates_a_resolution_error_instead_of_reporting_it() -> None:
    class Unreachable:
        def __init__(self) -> None:
            raise RuntimeError('no route to host')

    def unreachable_check(value: object) -> bool:
        return True

    di = Container().bind(Unreachable, check=unreachable_check).freeze()
    with pytest.raises(RuntimeError, match='no route to host'):
        _ = await di.ahealth()


def test_a_sync_check_returning_an_awaitable_raises_invalid_provider_error() -> None:
    class Database: ...

    async def _coro() -> bool:
        return True

    made: list[Coroutine[object, object, bool]] = []

    def ping(db: Database) -> object:
        coroutine = _coro()
        made.append(coroutine)
        return coroutine

    di = Container().bind(Database, check=ping).freeze()
    try:
        with pytest.raises(InvalidProviderError):
            _ = di.health()
    finally:
        for coroutine in made:
            coroutine.close()


def test_a_check_on_a_scoped_binding_runs_inside_a_scope() -> None:
    class Session: ...

    def ping(session: Session) -> bool:
        return True

    di = Container().bind(Session, scope=Scope.SCOPED, check=ping).freeze()
    with di.scope():
        report = di.health()
    assert report.results == (HealthResult(key=Session, tag=None, healthy=True, error=None),)


def test_a_check_on_a_scoped_binding_raises_outside_a_scope() -> None:
    class Session: ...

    def ping(session: Session) -> bool:
        return True

    di = Container().bind(Session, scope=Scope.SCOPED, check=ping).freeze()
    with pytest.raises(OutsideScopeError):
        _ = di.health()


def test_a_check_on_a_decorated_binding_is_keyed_underlying() -> None:
    class Database: ...

    class Loud(Database):
        def __init__(self, inner: Database) -> None: ...

    def ping(db: Database) -> None: ...

    di = Container().bind(Database, check=ping).decorate(Database, Loud).freeze()
    keys = [check.key for check in di.checks()]
    assert keys == [Underlying(Database, 0)]


def test_an_inactive_conditional_binding_declares_no_check() -> None:
    class Database: ...

    def ping(db: Database) -> None: ...

    di = Container().bind(Database, check=ping, when=False).freeze()
    assert di.checks() == ()


def test_a_value_check_runs_against_the_bound_value() -> None:
    port = Token[int]('port')

    def positive(value: int) -> bool:
        return value > 0

    di = Container().value(port, 8080, check=positive).freeze()
    report = di.health()
    assert report.results == (HealthResult(key=port, tag=None, healthy=True, error=None),)


def test_a_lifecycle_binding_check_still_runs() -> None:
    class Pool: ...

    def pool() -> Generator[Pool]:
        yield Pool()

    def ping(_: Pool) -> bool:
        return True

    di = Container().bind(pool, check=ping).freeze()
    report = di.health()
    assert report.healthy is True
