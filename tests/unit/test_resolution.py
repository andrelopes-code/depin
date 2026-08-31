"""Synchronous resolution: lookups, defaults, and the errors a bad key produces."""

import subprocess
import sys
import threading
from contextvars import copy_context
from pathlib import Path
from typing import Annotated, Protocol

import pytest

from depin._core import frozen as frozen_module
from depin._core.container import Container
from depin._core.frozen import FrozenContainer
from depin._core.markers import Tag, injected, provides
from depin._core.scope import Scope
from depin.errors import AsyncInSyncContextError, CircularDependencyError, MissingProviderError


def test_resolving_an_unregistered_key_names_the_key() -> None:
    class Unregistered: ...

    frozen = Container().freeze()
    with pytest.raises(MissingProviderError, match='Unregistered'):
        _ = frozen[Unregistered]


def test_resolving_a_value_that_is_not_a_provider_key_raises() -> None:
    frozen = Container().freeze()
    with pytest.raises(MissingProviderError, match='not a valid key type'):
        frozen.resolve(42)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType, reportUnusedCallResult]


def test_a_protocol_key_resolves_through_subscript() -> None:
    class Store(Protocol):
        def get(self) -> str: ...

    @provides(Store)
    class MemStore:
        def get(self) -> str:
            return 'v'

    frozen = Container().bind(MemStore).freeze()
    assert frozen[Store].get() == 'v'


def test_sync_resolution_of_an_async_provider_points_at_aresolve() -> None:
    class Service: ...

    async def make() -> Service:
        return Service()

    frozen = Container().bind(make, scope=Scope.SINGLETON, provides=Service).freeze()
    with pytest.raises(
        AsyncInSyncContextError,
        match=r'Service requires async resolution; call aresolve\(\) instead$',
    ):
        _ = frozen[Service]


def test_transient_provider_reads_scope_value_inside_a_scope() -> None:
    class RequestId: ...

    class Report:
        def __init__(self, request_id: RequestId) -> None:
            self.request_id = request_id

    request_id = RequestId()
    frozen = Container().scope_value(RequestId).bind(Report, scope=Scope.TRANSIENT).freeze()
    with frozen.scope() as frame:
        frame.provide(RequestId, request_id)
        assert frozen.resolve(Report).request_id is request_id


def test_sync_recursive_resolution_names_the_cyclic_provider() -> None:
    script = """
from depin import Container, Scope
from depin.errors import CircularDependencyError

frozen: object

def make() -> int:
    return frozen.resolve(int)

frozen = Container().bind(make, scope=Scope.SINGLETON, provides=int).freeze()
try:
    frozen.resolve(int)
except CircularDependencyError as exc:
    print(exc)
else:
    raise AssertionError('recursive resolution did not raise CircularDependencyError')
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        cwd=Path(frozen_module.__file__).parents[2],
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == (
        'int is already constructing in this context; '
        'resolve a different dependency or break the recursive provider call\n'
    )


def test_sync_dynamic_cycle_during_parameter_resolution_raises() -> None:
    frozen: FrozenContainer

    class A: ...

    class B: ...

    def make_a(value: B) -> A:
        return A()

    def make_b() -> B:
        _ = frozen.resolve(A)
        return B()

    frozen = Container().bind(make_a, provides=A).bind(make_b, provides=B).freeze()
    finished = threading.Event()
    errors: list[BaseException] = []

    def resolve() -> None:
        try:
            _ = frozen.resolve(A)
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=resolve, daemon=True)
    thread.start()
    assert finished.wait(1)
    assert len(errors) == 1
    assert str(errors[0]) == (
        f'{A.__qualname__} is already constructing in this context; '
        'resolve a different dependency or break the recursive provider call'
    )


def test_nested_scope_constructs_a_scoped_provider_once() -> None:
    constructed: list[object] = []

    class Value: ...

    def make() -> Value:
        constructed.append(object())
        return Value()

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=Value).freeze()
    with frozen.scope(), frozen.scope():
        first = frozen.resolve(Value)
        assert frozen.resolve(Value) is first
    assert len(constructed) == 1


def test_stale_inherited_scope_context_cannot_resolve_after_abort() -> None:
    frozen: FrozenContainer
    child_started = threading.Event()
    release_child = threading.Event()
    child_finished = threading.Event()
    child_errors: list[BaseException] = []
    attempts = 0

    class Value: ...

    def resolve_in_child() -> None:
        child_started.set()
        release_child.wait()
        try:
            _ = frozen.resolve(Value)
        except BaseException as exc:
            child_errors.append(exc)
        finally:
            child_finished.set()

    def make() -> Value:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            context = copy_context()
            thread = threading.Thread(target=context.run, args=(resolve_in_child,), daemon=True)
            thread.start()
            assert child_started.wait(1)
            raise RuntimeError('first construction fails')
        return Value()

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=Value).freeze()
    with frozen.scope(), frozen.scope():
        with pytest.raises(RuntimeError, match='first construction fails'):
            _ = frozen.resolve(Value)
        release_child.set()
        assert child_finished.wait(1)
        assert len(child_errors) == 1
        assert str(child_errors[0]) == (
            f'{Value.__qualname__} is already constructing in this context; '
            'resolve a different dependency or break the recursive provider call'
        )
        first = frozen.resolve(Value)
        assert frozen.resolve(Value) is first
    assert attempts == 2


def test_sync_nested_scope_self_resolution_raises() -> None:
    script = """
from depin import Container, Scope
from depin.errors import CircularDependencyError

frozen: object

class Value: ...

def make() -> Value:
    with frozen.scope():
        return frozen.resolve(Value)

frozen = Container().bind(make, scope=Scope.SCOPED, provides=Value).freeze()
try:
    with frozen.scope():
        frozen.resolve(Value)
except CircularDependencyError as exc:
    print(exc)
else:
    raise AssertionError('nested-scope self resolution did not raise CircularDependencyError')
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
        cwd=Path(frozen_module.__file__).parents[2],
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == (
        'Value is already constructing in this context; '
        'resolve a different dependency or break the recursive provider call\n'
    )


def test_sync_single_flight_keeps_unrelated_singletons_independent() -> None:
    script = """
import threading

from depin import Container

first_started = threading.Event()
finish_first = threading.Event()
second_finished = threading.Event()
results: list[str] = []

def first() -> str:
    first_started.set()
    if not finish_first.wait(1):
        raise RuntimeError('first provider was not released')
    return 'first'

def second() -> int:
    second_finished.set()
    return 2

frozen = Container().bind(first, provides=str).bind(second, provides=int).freeze()
first_thread = threading.Thread(target=lambda: results.append(frozen.resolve(str)))
second_thread = threading.Thread(target=lambda: results.append(str(frozen.resolve(int))))
first_thread.start()
if not first_started.wait(1):
    raise RuntimeError('first provider did not start')
second_thread.start()
if not second_finished.wait(1):
    raise RuntimeError('unrelated singleton provider did not start')
finish_first.set()
first_thread.join(1)
second_thread.join(1)
if first_thread.is_alive() or second_thread.is_alive():
    raise RuntimeError('unrelated singleton resolution did not finish')
if not second_finished.is_set() or sorted(results) != ['2', 'first']:
    raise RuntimeError(f'unexpected results: {results!r}')
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
        cwd=Path(frozen_module.__file__).parents[2],
    )
    assert completed.returncode == 0, completed.stderr
    frozen = Container().bind(lambda: 1, provides=int).freeze()
    assert frozen[int] == 1
    frozen = Container().bind(lambda: 1, provides=int).freeze()
    assert frozen[int] == 1


def test_sync_single_flight_is_removed_after_construction_fails() -> None:
    script = """
from depin import Container

attempts = 0

def make() -> int:
    global attempts
    attempts += 1
    if attempts == 1:
        raise RuntimeError('first attempt fails')
    return attempts

frozen = Container().bind(make, provides=int).freeze()
try:
    frozen.resolve(int)
except RuntimeError as exc:
    if str(exc) != 'first attempt fails':
        raise
else:
    raise RuntimeError('first resolution unexpectedly succeeded')
if frozen.resolve(int) != 2:
    raise RuntimeError('second resolution did not reconstruct the singleton')
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
        cwd=Path(frozen_module.__file__).parents[2],
    )
    assert completed.returncode == 0, completed.stderr
    frozen = Container().bind(lambda: 1, provides=int).freeze()
    assert frozen[int] == 1


def test_sync_single_flight_leader_constructs_without_waiting() -> None:
    script = """
from depin import Container

frozen = Container().bind(lambda: 42, provides=int).freeze()
if frozen.resolve(int) != 42:
    raise RuntimeError('singleton did not resolve')
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
        cwd=Path(frozen_module.__file__).parents[2],
    )
    assert completed.returncode == 0, completed.stderr
    frozen = Container().bind(lambda: 1, provides=int).freeze()
    assert frozen[int] == 1


def test_an_unbound_parameter_with_a_default_keeps_its_default() -> None:
    class Settings:
        def __init__(self, retries: int = 11) -> None:
            self.retries = retries

    frozen = Container().bind(Settings, scope=Scope.SINGLETON).freeze()
    assert frozen[Settings].retries == 11


def test_defaulted_dependency_does_not_skip_a_later_required_dependency() -> None:
    class OptionalDependency: ...

    default = OptionalDependency()

    class Result:
        def __init__(self, optional: OptionalDependency = default, *, number: int) -> None:
            self.optional = optional
            self.number = number

    frozen = Container().bind(lambda: 7, provides=int).bind(Result).freeze()
    assert frozen[Result].optional is default
    assert frozen[Result].number == 7


def test_a_tagged_provider_is_only_reachable_through_its_tag() -> None:
    class Store: ...

    frozen = Container().bind(Store, scope=Scope.SINGLETON, tag='primary').freeze()
    assert isinstance(frozen.resolve(Store, tag='primary'), Store)
    with pytest.raises(MissingProviderError):
        _ = frozen[Store]


@pytest.mark.asyncio
async def test_async_injection_preserves_a_dependency_tag() -> None:
    class Store:
        def __init__(self, label: str) -> None:
            self.label = label

    frozen = (
        Container()
        .bind(lambda: Store('default'), provides=Store)
        .bind(lambda: Store('primary'), provides=Store, tag='primary')
        .freeze()
    )

    @frozen.inject
    async def handler(store: Annotated[Store, Tag('primary')] = injected(Store, tag='primary')) -> str:
        return store.label

    assert await handler() == 'primary'


@pytest.mark.asyncio
async def test_async_recursive_resolution_has_the_full_actionable_message() -> None:
    frozen: FrozenContainer

    async def make() -> int:
        return await frozen.aresolve(int)

    frozen = Container().bind(make, provides=int).freeze()
    with pytest.raises(
        CircularDependencyError,
        match=(
            r'^int is already constructing in this context; '
            r'resolve a different dependency or break the recursive provider call$'
        ),
    ):
        await frozen.aresolve(int)


@pytest.mark.asyncio
async def test_async_defaulted_dependency_does_not_skip_a_later_required_dependency() -> None:
    class OptionalDependency: ...

    default = OptionalDependency()

    class Result:
        def __init__(self, optional: OptionalDependency = default, *, number: int) -> None:
            self.optional = optional
            self.number = number

    async def make_result(optional: OptionalDependency = default, *, number: int) -> Result:
        return Result(optional, number=number)

    frozen = Container().bind(lambda: 7, provides=int).bind(make_result).freeze()
    result = await frozen.aresolve(Result)
    assert result.optional is default
    assert result.number == 7


def test_a_seeded_key_that_also_has_a_binding_resolves_to_its_binding() -> None:
    class Clock:
        def __init__(self, label: str = 'bound') -> None:
            self.label = label

    class Report:
        def __init__(self, clock: Clock) -> None:
            self.clock = clock

    frozen = Container().bind(Clock).bind(Report, scope=Scope.SCOPED).freeze()

    with frozen.scope() as frame:
        frame.provide(Clock, Clock('seeded'))
        report = frozen.resolve(Report)

    assert report.clock.label == 'bound'
    assert frozen.resolve(Clock).label == 'bound'


def test_a_tagged_parameter_ignores_a_frame_value_seeded_under_the_bare_key() -> None:
    class Store:
        def __init__(self, label: str) -> None:
            self.label = label

    class Page:
        def __init__(self, store: Annotated[Store, Tag('primary')]) -> None:
            self.store = store

    frozen = (
        Container()
        .bind(lambda: Store('primary'), provides=Store, tag='primary')
        .bind(Page, scope=Scope.SCOPED)
        .freeze()
    )

    with frozen.scope() as frame:
        frame.provide(Store, Store('seeded'))
        page = frozen.resolve(Page)

    assert page.store.label == 'primary'
