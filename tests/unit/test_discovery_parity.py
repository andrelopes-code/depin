"""Behavioral parity between declarative providers and manual bindings."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass

import pytest

from depin import Catalog, Container, Manifest, Provider, Scope, provider
from depin._core.frozen import FrozenContainer
from depin._core.graph import build_plan
from depin._core.providers import build_specs
from depin._core.spec import ResolutionPlan, SpecSet
from depin.errors import InvalidScopeError

_TAG = 'parity'


@dataclass(frozen=True, slots=True)
class _Product:
    state: str = 'ready'


type _PairFactory = Callable[[Scope, list[str]], tuple[Container, Container]]


@dataclass(frozen=True, slots=True)
class _ProviderCase:
    pair: _PairFactory
    needs_async: bool
    owns_teardown: bool
    singleton_events: tuple[str, ...]
    scoped_events: tuple[str, ...]
    transient_events: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _RuntimeObservation:
    values: tuple[_Product, ...]
    same_within_lifetime: bool
    rebuilt_after_lifetime: bool | None
    events: tuple[str, ...]


def _healthy(product: _Product) -> bool:
    return product.state == 'ready'


def _declarative_container(declaration: Provider[_Product]) -> Container:
    catalog = Catalog(__name__, declaration)
    return Container(Manifest(__name__, catalog))


def _class_pair(scope: Scope, events: list[str]) -> tuple[Container, Container]:
    del events
    manual = Container().bind(_Product, scope=scope, tag=_TAG, when=True, check=_healthy)
    declaration = provider(_Product).configure(scope=scope, tag=_TAG, when=True, check=_healthy)
    return manual, _declarative_container(declaration)


def _sync_function_pair(scope: Scope, events: list[str]) -> tuple[Container, Container]:
    def make() -> _Product:
        events.append('acquire')
        return _Product()

    manual = Container().bind(make, scope=scope, tag=_TAG, when=True, check=_healthy)
    declaration = provider(make).configure(scope=scope, tag=_TAG, when=True, check=_healthy)
    return manual, _declarative_container(declaration)


def _coroutine_pair(scope: Scope, events: list[str]) -> tuple[Container, Container]:
    async def make() -> _Product:
        events.append('acquire')
        return _Product()

    manual = Container().bind(make, scope=scope, tag=_TAG, when=True, check=_healthy)
    declaration = provider(make).configure(scope=scope, tag=_TAG, when=True, check=_healthy)
    return manual, _declarative_container(declaration)


def _generator_pair(scope: Scope, events: list[str]) -> tuple[Container, Container]:
    def make() -> Generator[_Product, None, None]:
        events.append('acquire')
        try:
            yield _Product()
        finally:
            events.append('release')

    manual = Container().bind(make, scope=scope, tag=_TAG, when=True, check=_healthy)
    declaration = provider(make).configure(scope=scope, tag=_TAG, when=True, check=_healthy)
    return manual, _declarative_container(declaration)


def _async_generator_pair(scope: Scope, events: list[str]) -> tuple[Container, Container]:
    async def make() -> AsyncGenerator[_Product, None]:
        events.append('acquire')
        try:
            yield _Product()
        finally:
            events.append('release')

    manual = Container().bind(make, scope=scope, tag=_TAG, when=True, check=_healthy)
    declaration = provider(make).configure(scope=scope, tag=_TAG, when=True, check=_healthy)
    return manual, _declarative_container(declaration)


def _context_manager_pair(scope: Scope, events: list[str]) -> tuple[Container, Container]:
    @contextmanager
    def make() -> Generator[_Product, None, None]:
        events.append('acquire')
        try:
            yield _Product()
        finally:
            events.append('release')

    manual = Container().bind(make, scope=scope, tag=_TAG, when=True, check=_healthy)
    declaration = provider(make).configure(scope=scope, tag=_TAG, when=True, check=_healthy)
    return manual, _declarative_container(declaration)


def _async_context_manager_pair(scope: Scope, events: list[str]) -> tuple[Container, Container]:
    @asynccontextmanager
    async def make() -> AsyncGenerator[_Product, None]:
        events.append('acquire')
        try:
            yield _Product()
        finally:
            events.append('release')

    manual = Container().bind(make, scope=scope, tag=_TAG, when=True, check=_healthy)
    declaration = provider(make).configure(scope=scope, tag=_TAG, when=True, check=_healthy)
    return manual, _declarative_container(declaration)


def _representations(manual: Container, declarative: Container) -> tuple[SpecSet, ResolutionPlan]:
    manual_records = tuple(manual.records())
    declarative_records = tuple(declarative.records())
    assert declarative_records == manual_records
    assert declarative_records[0] == manual_records[0]

    manual_specs = build_specs(manual_records)
    declarative_specs = build_specs(declarative_records)
    assert declarative_specs.providers == manual_specs.providers
    assert declarative_specs == manual_specs

    manual_plan = build_plan(manual_records)
    declarative_plan = build_plan(declarative_records)
    assert declarative_plan == manual_plan
    return declarative_specs, declarative_plan


def _resolve_twice(container: FrozenContainer) -> tuple[_Product, _Product]:
    return container.resolve(_Product, tag=_TAG), container.resolve(_Product, tag=_TAG)


async def _aresolve_twice(container: FrozenContainer) -> tuple[_Product, _Product]:
    first = await container.aresolve(_Product, tag=_TAG)
    second = await container.aresolve(_Product, tag=_TAG)
    return first, second


def _observe_sync_runtime(builder: Container, scope: Scope, events: list[str]) -> _RuntimeObservation:
    events.clear()
    frozen = builder.freeze()

    if scope is Scope.SINGLETON:
        first, second = _resolve_twice(frozen)
        frozen.close()
        return _RuntimeObservation((first, second), first is second, None, tuple(events))

    if scope is Scope.SCOPED:
        with frozen.scope():
            first, second = _resolve_twice(frozen)
        with frozen.scope():
            third = frozen.resolve(_Product, tag=_TAG)
        frozen.close()
        return _RuntimeObservation((first, second, third), first is second, third is not first, tuple(events))

    first, second = _resolve_twice(frozen)
    frozen.close()
    return _RuntimeObservation((first, second), first is second, None, tuple(events))


async def _observe_async_runtime(builder: Container, scope: Scope, events: list[str]) -> _RuntimeObservation:
    events.clear()
    frozen = builder.freeze()

    if scope is Scope.SINGLETON:
        first, second = await _aresolve_twice(frozen)
        await frozen.aclose()
        return _RuntimeObservation((first, second), first is second, None, tuple(events))

    if scope is Scope.SCOPED:
        async with frozen.ascope():
            first, second = await _aresolve_twice(frozen)
        async with frozen.ascope():
            third = await frozen.aresolve(_Product, tag=_TAG)
        await frozen.aclose()
        return _RuntimeObservation((first, second, third), first is second, third is not first, tuple(events))

    first, second = await _aresolve_twice(frozen)
    await frozen.aclose()
    return _RuntimeObservation((first, second), first is second, None, tuple(events))


def _observe_runtime(builder: Container, case: _ProviderCase, scope: Scope, events: list[str]) -> _RuntimeObservation:
    if case.needs_async:
        return asyncio.run(_observe_async_runtime(builder, scope, events))
    return _observe_sync_runtime(builder, scope, events)


def _invalid_scope(action: Callable[[], object]) -> str:
    with pytest.raises(InvalidScopeError) as error:
        action()
    return str(error.value)


def _invalid_specs_scope(container: Container) -> str:
    return _invalid_scope(lambda: build_specs(container.records()))


def _invalid_plan_scope(container: Container) -> str:
    return _invalid_scope(lambda: build_plan(container.records()))


@pytest.mark.parametrize(
    'case',
    [
        pytest.param(_ProviderCase(_class_pair, False, False, (), (), ()), id='class'),
        pytest.param(
            _ProviderCase(
                _sync_function_pair, False, False, ('acquire',), ('acquire', 'acquire'), ('acquire', 'acquire')
            ),
            id='sync-function',
        ),
        pytest.param(
            _ProviderCase(_coroutine_pair, True, False, ('acquire',), ('acquire', 'acquire'), ('acquire', 'acquire')),
            id='coroutine',
        ),
        pytest.param(
            _ProviderCase(_generator_pair, False, True, ('acquire', 'release'), ('acquire', 'release') * 2, ()),
            id='generator',
        ),
        pytest.param(
            _ProviderCase(_async_generator_pair, True, True, ('acquire', 'release'), ('acquire', 'release') * 2, ()),
            id='async-generator',
        ),
        pytest.param(
            _ProviderCase(_context_manager_pair, False, True, ('acquire', 'release'), ('acquire', 'release') * 2, ()),
            id='context-manager',
        ),
        pytest.param(
            _ProviderCase(
                _async_context_manager_pair,
                True,
                True,
                ('acquire', 'release'),
                ('acquire', 'release') * 2,
                (),
            ),
            id='async-context-manager',
        ),
    ],
)
def test_declarative_provider_form_matches_manual_binding(case: _ProviderCase) -> None:
    for scope in Scope:
        events: list[str] = []
        manual, declarative = case.pair(scope, events)
        assert tuple(declarative.records()) == tuple(manual.records())

        if scope is Scope.TRANSIENT and case.owns_teardown:
            manual_specs_error = _invalid_specs_scope(manual)
            declarative_specs_error = _invalid_specs_scope(declarative)
            manual_plan_error = _invalid_plan_scope(manual)
            declarative_plan_error = _invalid_plan_scope(declarative)
            manual_freeze_error = _invalid_scope(manual.freeze)
            declarative_freeze_error = _invalid_scope(declarative.freeze)

            assert declarative_specs_error == manual_specs_error
            assert declarative_plan_error == manual_plan_error
            assert declarative_freeze_error == manual_freeze_error
            assert 'Use Scope.SINGLETON or Scope.SCOPED.' in declarative_freeze_error
            assert events == []
            continue

        specs, plan = _representations(manual, declarative)
        assert len(specs.providers) == 1
        assert len(plan.order) == 1
        assert plan.order[0].needs_async is case.needs_async

        manual_observation = _observe_runtime(manual, case, scope, events)
        declarative_observation = _observe_runtime(declarative, case, scope, events)
        expected_events = {
            Scope.SINGLETON: case.singleton_events,
            Scope.SCOPED: case.scoped_events,
            Scope.TRANSIENT: case.transient_events,
        }[scope]

        assert manual_observation == declarative_observation
        assert manual_observation.events == expected_events
        assert all(value == _Product() for value in manual_observation.values)
        if scope is Scope.TRANSIENT:
            assert manual_observation.same_within_lifetime is False
            assert manual_observation.rebuilt_after_lifetime is None
        elif scope is Scope.SCOPED:
            assert manual_observation.same_within_lifetime is True
            assert manual_observation.rebuilt_after_lifetime is True
        else:
            assert manual_observation.same_within_lifetime is True
            assert manual_observation.rebuilt_after_lifetime is None
