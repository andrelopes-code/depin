"""`warmup()` builds every singleton at boot, and refuses to block an event loop."""

from collections.abc import Generator

import pytest

from depin import Container, Scope, Underlying
from depin.errors import AsyncInSyncContextError


def test_warmup_on_an_empty_container_reports_nothing() -> None:
    report = Container().freeze().warmup()
    assert report.constructed == ()
    assert report.cached == ()


def test_warmup_constructs_every_singleton() -> None:
    built: list[str] = []

    class Config:
        def __init__(self) -> None:
            built.append('config')

    class Service:
        def __init__(self, config: Config) -> None:
            built.append('service')

    di = Container().bind(Config).bind(Service).freeze()
    report = di.warmup()
    assert built == ['config', 'service']
    assert [node.key for node in report.constructed] == [Config, Service]
    assert report.cached == ()


def test_warmup_reports_an_already_built_singleton_as_cached() -> None:
    class Config: ...

    class Service:
        def __init__(self, config: Config) -> None: ...

    di = Container().bind(Config).bind(Service).freeze()
    _ = di[Config]
    report = di.warmup()
    assert [node.key for node in report.cached] == [Config]
    assert [node.key for node in report.constructed] == [Service]


def test_a_second_warmup_constructs_nothing() -> None:
    class Config: ...

    di = Container().bind(Config).freeze()
    _ = di.warmup()
    report = di.warmup()
    assert report.constructed == ()
    assert [node.key for node in report.cached] == [Config]


def test_warmup_leaves_scoped_and_transient_providers_alone() -> None:
    built: list[str] = []

    class Session:
        def __init__(self) -> None:
            built.append('session')

    class Ticket:
        def __init__(self) -> None:
            built.append('ticket')

    di = Container().bind(Session, scope=Scope.SCOPED).bind(Ticket, scope=Scope.TRANSIENT).freeze()
    report = di.warmup()
    assert built == []
    assert report.constructed == ()
    assert report.cached == ()


def test_a_construction_failure_propagates_and_leaves_earlier_singletons_built() -> None:
    built: list[str] = []

    class Config:
        def __init__(self) -> None:
            built.append('config')

    class Broken:
        def __init__(self, config: Config) -> None:
            raise RuntimeError('boom')

    di = Container().bind(Config).bind(Broken).freeze()
    with pytest.raises(RuntimeError, match='boom'):
        _ = di.warmup()
    assert built == ['config']
    assert di[Config] is di[Config]


def test_a_lifecycle_singleton_is_entered_once_and_drained_once() -> None:
    events: list[str] = []

    class Pool: ...

    def pool() -> Generator[Pool]:
        events.append('open')
        yield Pool()
        events.append('close')

    di = Container().bind(pool).freeze()
    _ = di.warmup()
    _ = di.warmup()
    di.close()
    assert events == ['open', 'close']


def test_a_decorated_singleton_reports_both_nodes() -> None:
    class Config: ...

    class Loud(Config):
        def __init__(self, inner: Config) -> None: ...

    di = Container().bind(Config).decorate(Config, Loud).freeze()
    report = di.warmup()
    assert [node.key for node in report.constructed] == [Underlying(Config, 0), Config]


def test_warmup_refuses_an_async_singleton_before_constructing_anything() -> None:
    built: list[str] = []

    class Config:
        def __init__(self) -> None:
            built.append('config')

    class Service: ...

    async def service() -> Service:
        return Service()

    di = Container().bind(Config).bind(service).freeze()
    with pytest.raises(AsyncInSyncContextError, match='awarmup'):
        _ = di.warmup()
    assert built == []


async def test_awarmup_constructs_an_async_singleton() -> None:
    class Service: ...

    async def service() -> Service:
        return Service()

    di = Container().bind(service).freeze()
    report = await di.awarmup()
    assert [node.key for node in report.constructed] == [Service]
