"""`warmup()` builds every singleton at boot, and refuses to block an event loop."""

from collections.abc import Generator

import pytest

from depin import Container, Scope, Underlying
from depin._core.spec import fmt_key
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
    assert report.constructed == (di.graph().node(Config), di.graph().node(Service))
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
    assert report.cached == (di.graph().node(Config),)
    assert report.constructed == (di.graph().node(Service),)


def test_warmup_reports_the_binding_tag_on_a_constructed_node() -> None:
    class Config: ...

    di = Container().bind(Config, tag='primary').freeze()
    report = di.warmup()
    assert report.constructed == (di.graph().node(Config, tag='primary'),)


def test_warmup_reports_the_binding_tag_on_a_cached_node() -> None:
    class Config: ...

    di = Container().bind(Config, tag='primary').freeze()
    _ = di.resolve(Config, tag='primary')
    report = di.warmup()
    assert report.cached == (di.graph().node(Config, tag='primary'),)


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
    assert report.constructed == (di.graph().node(Underlying(Config, 0)), di.graph().node(Config))
    assert report.cached == ()


def test_warmup_refuses_an_async_singleton_before_constructing_anything() -> None:
    built: list[str] = []

    class Config:
        def __init__(self) -> None:
            built.append('config')

    class Service: ...

    async def service() -> Service:
        return Service()

    di = Container().bind(Config).bind(service).freeze()
    with pytest.raises(AsyncInSyncContextError) as excinfo:
        _ = di.warmup()
    assert built == []
    assert str(excinfo.value) == (
        f'warmup() cannot construct {fmt_key(Service)}: it requires async resolution. Call awarmup() instead.'
    )


def test_warmup_refusal_message_names_every_pending_singleton() -> None:
    class First: ...

    class Second: ...

    async def build_first() -> First:
        return First()

    async def build_second() -> Second:
        return Second()

    di = Container().bind(build_first).bind(build_second).freeze()
    with pytest.raises(AsyncInSyncContextError) as excinfo:
        _ = di.warmup()
    assert str(excinfo.value) == (
        f'warmup() cannot construct {fmt_key(First)}, {fmt_key(Second)}: they require async resolution. '
        'Call awarmup() instead.'
    )


async def test_awarmup_constructs_an_async_singleton() -> None:
    class Service: ...

    async def service() -> Service:
        return Service()

    di = Container().bind(service).freeze()
    report = await di.awarmup()
    assert [node.key for node in report.constructed] == [Service]


async def test_a_second_awarmup_reports_everything_cached() -> None:
    class Service: ...

    async def service() -> Service:
        return Service()

    di = Container().bind(service).freeze()
    _ = await di.awarmup()
    report = await di.awarmup()
    assert report.constructed == ()
    assert [node.key for node in report.cached] == [Service]


def test_warmup_honours_an_active_override() -> None:
    class Config:
        value = 'real'

    class FakeConfig(Config):
        value = 'fake'

    di = Container().bind(Config).freeze()
    with di.override(Config, FakeConfig()):
        report = di.warmup()
        assert di[Config].value == 'fake'
    assert [node.key for node in report.constructed] == [Config]
