import contextlib
from collections.abc import Generator

import pytest

from depin._core import frozen as frozen_module
from depin._core.container import Container
from depin._core.markers import Token
from depin._core.scope import Scope, ScopeFrame
from depin._core.spec import ProviderSpec


def test_deep_singleton_generator_uses_instructions_and_closes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection: ...

    events: list[str] = []
    value = Connection()
    container = Container()
    for index in range(255):
        container.value(Token[int](f'generator-padding-{index}'), index)

    def connection() -> Generator[Connection]:
        events.append('setup')
        yield value
        events.append('teardown')

    frozen = container.bind(connection, scope=Scope.SINGLETON).freeze()

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('deep singleton generator used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    assert frozen.resolve(Connection) is value
    assert frozen.resolve(Connection) is value
    assert events == ['setup']
    frozen.close()
    assert events == ['setup', 'teardown']


def test_deep_scoped_context_manager_uses_instructions_and_closes_in_lifo_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Dependency: ...

    class Resource:
        def __init__(self, dependency: Dependency) -> None:
            self.dependency = dependency

    events: list[str] = []
    dependency_value = Dependency()
    container = Container()
    for index in range(254):
        container.value(Token[int](f'context-manager-padding-{index}'), index)

    def dependency() -> Generator[Dependency]:
        events.append('dependency setup')
        yield dependency_value
        events.append('dependency teardown')

    @contextlib.contextmanager
    def resource(dependency: Dependency) -> Generator[Resource]:
        events.append('resource setup')
        yield Resource(dependency)
        events.append('resource teardown')

    frozen = (
        container.bind(dependency, scope=Scope.SCOPED).bind(resource, provides=Resource, scope=Scope.SCOPED).freeze()
    )

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('deep scoped context manager used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    with frozen.scope():
        first = frozen.resolve(Resource)
        assert frozen.resolve(Resource) is first
        assert first.dependency is dependency_value
        assert events == ['dependency setup', 'resource setup']
    assert events == [
        'dependency setup',
        'resource setup',
        'resource teardown',
        'dependency teardown',
    ]


def test_deep_resource_decorator_owns_the_outer_teardown(monkeypatch: pytest.MonkeyPatch) -> None:
    class Store: ...

    events: list[str] = []
    value = Store()
    container = Container()
    for index in range(255):
        container.value(Token[int](f'resource-decorator-padding-{index}'), index)

    def store() -> Generator[Store]:
        events.append('store setup')
        yield value
        events.append('store teardown')

    def decorate(inner: Store) -> Generator[Store]:
        events.append('decorator setup')
        yield inner
        events.append('decorator teardown')

    frozen = container.bind(store).decorate(Store, decorate).freeze()

    def unexpected_iterative(_self: object, _spec: ProviderSpec) -> object:
        raise AssertionError('deep resource decorator used the interpreted executor')

    monkeypatch.setattr(frozen_module.FrozenContainer, '_resolve_sync_iterative', unexpected_iterative)

    assert frozen.resolve(Store) is value
    frozen.close()
    assert events == [
        'store setup',
        'decorator setup',
        'decorator teardown',
        'store teardown',
    ]


def test_interrupted_resource_publication_retains_teardown_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        def __init__(self, serial: int) -> None:
            self.serial = serial

    events: list[str] = []
    container = Container()
    for index in range(255):
        container.value(Token[int](f'resource-interruption-padding-{index}'), index)

    def connection() -> Generator[Connection]:
        value = Connection(events.count('setup'))
        events.append('setup')
        yield value
        events.append(f'teardown {value.serial}')

    frozen = container.bind(connection, scope=Scope.SINGLETON).freeze()
    original_publish = ScopeFrame.publish
    interrupted = False

    def interrupt_first_publish(
        frame: ScopeFrame,
        key: object,
        leader: object,
        value: object,
        *,
        signal: bool = False,
    ) -> object:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt('interrupt resource publication')
        return original_publish(frame, key, leader, value, signal=signal)

    monkeypatch.setattr(ScopeFrame, 'publish', interrupt_first_publish)

    with pytest.raises(KeyboardInterrupt, match='interrupt resource publication'):
        frozen.resolve(Connection)
    assert frozen.resolve(Connection).serial == 1
    frozen.close()
    assert events == ['setup', 'setup', 'teardown 1', 'teardown 0']
