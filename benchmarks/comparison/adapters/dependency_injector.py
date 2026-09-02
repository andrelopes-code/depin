"""Dependency Injector implementations of comparable benchmark workloads."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol

from dependency_injector import providers

from benchmarks.comparison.adapters import Adapter
from benchmarks.comparison.contracts import Candidate, Competitor, Equivalence
from benchmarks.comparison.shapes import Chain, chain, observation
from benchmarks.contracts import Implementation, Observation, Prepared, Workload
from benchmarks.harness import HarnessError
from benchmarks.workloads.micro import CHAIN_DEPTH, HOT_GRAPH, Sole

_DISTRIBUTION = 'dependency-injector'
_VERSION = '4.49.1'

try:
    _installed_version = version(_DISTRIBUTION)
except PackageNotFoundError as error:
    raise HarnessError(f'{_DISTRIBUTION} is not installed in the bench group') from error
if _installed_version != _VERSION:
    raise HarnessError(f'{_DISTRIBUTION} {_installed_version} is installed; {_VERSION} is required')


class _Provider(Protocol):
    def __call__(self) -> object: ...


class _ResettableProvider(_Provider, Protocol):
    def reset(self) -> object: ...


@dataclass(frozen=True, slots=True)
class ProviderChain:
    shape: Chain
    leaf: _Provider
    close: Callable[[], None]


def warm_chain(size: int) -> ProviderChain:
    shape = chain(size)
    built: list[_ResettableProvider] = []
    previous: _Provider | None = None
    for factory in shape.factories:
        provider = (
            providers.ThreadSafeSingleton(factory)
            if previous is None
            else providers.ThreadSafeSingleton(factory, previous)
        )
        built.append(provider)
        previous = provider

    def close() -> None:
        for provider in built:
            _ = provider.reset()

    return ProviderChain(shape=shape, leaf=built[-1], close=close)


def _transient_chain(size: int) -> ProviderChain:
    shape = chain(size)
    built: list[_Provider] = []
    previous: _Provider | None = None
    for factory in shape.factories:
        provider = providers.Factory(factory) if previous is None else providers.Factory(factory, previous)
        built.append(provider)
        previous = provider
    return ProviderChain(shape=shape, leaf=built[-1], close=lambda: None)


def _implementation(build: Callable[[], ProviderChain], *, warm: bool) -> Implementation:
    def prepare() -> Prepared:
        prepared = build()
        if warm:
            _ = prepared.leaf()
        return Prepared(call=prepared.leaf, close=prepared.close)

    def observe() -> Observation:
        observed = build()
        try:
            if warm:
                _ = observed.leaf()
                observed.shape.log.clear()
            value = observed.leaf()
            return observation(observed.shape, value)
        finally:
            observed.close()

    return Implementation(label=ADAPTER.competitor.label, prepare=prepare, observe=observe)


def _cold_singleton() -> Implementation:
    def prepare() -> Prepared:
        provider: _ResettableProvider = providers.ThreadSafeSingleton(Sole)

        def call() -> object:
            _ = provider.reset()
            return provider()

        def close() -> None:
            _ = provider.reset()

        return Prepared(call=call, close=close)

    def observe() -> Observation:
        log: list[str] = []

        def make() -> Sole:
            log.append(Sole.__name__)
            return Sole()

        provider: _ResettableProvider = providers.ThreadSafeSingleton(make)
        try:
            value = provider()
            return Observation(result=type(value).__name__, constructed=tuple(log), closed=())
        finally:
            _ = provider.reset()

    return Implementation(label=ADAPTER.competitor.label, prepare=prepare, observe=observe)


@dataclass(frozen=True, slots=True)
class DependencyInjectorAdapter:
    competitor: Competitor = field(default_factory=lambda: Competitor(_DISTRIBUTION, _VERSION))

    def candidates(self, workloads: Sequence[Workload]) -> tuple[Candidate, ...]:
        candidates: list[Candidate] = []
        for workload in workloads:
            candidates.append(self._candidate(workload))
        return tuple(candidates)

    def _candidate(self, workload: Workload) -> Candidate:
        equivalent = {
            'resolve_cached_singleton': _implementation(lambda: warm_chain(HOT_GRAPH), warm=True),
            'resolve_a_transient_chain': _implementation(lambda: _transient_chain(CHAIN_DEPTH), warm=False),
            'construct_a_singleton_for_the_first_time': _cold_singleton(),
        }
        implementation = equivalent.get(workload.name)
        if implementation is not None:
            return Candidate(
                workload.name,
                self.competitor,
                Equivalence.EQUIVALENT,
                'matches the singleton or transient provider lifecycle and construction shape',
                implementation,
            )
        if 'scope' in workload.name:
            return Candidate(
                workload.name,
                self.competitor,
                Equivalence.INCOMPARABLE,
                'provider overrides are substitutions, not nested scope frames with scoped caches',
                None,
            )
        if workload.name.startswith(('freeze_', 'warmup_', 'build_', 'explain_', 'export_')):
            reason = 'Dependency Injector has no separate frozen resolution plan or depin graph diagnostics operation'
        elif workload.name.startswith(('allocations_', 'retained_', 'scale_')):
            reason = (
                'the measured allocation, retention, or scaling source has no equivalent Dependency Injector operation'
            )
        elif workload.name.startswith('fastapi_'):
            reason = 'the FastAPI integration has different request lifecycle and dependency declaration semantics'
        elif 'alias' in workload.name:
            reason = 'Dependency Injector delegates do not provide depin typed-key alias resolution'
        elif 'collection' in workload.name:
            reason = 'Dependency Injector has no depin collection binding and aggregation operation'
        elif 'inject' in workload.name:
            reason = 'Dependency Injector wiring does not share depin injection wrapper calling semantics'
        elif 'override' in workload.name:
            reason = 'Dependency Injector provider overrides are not depin context-local override frames'
        elif 'async' in workload.name or 'resource' in workload.name:
            reason = 'Dependency Injector async and resource providers have different resolution and teardown semantics'
        elif 'generic' in workload.name:
            reason = 'Dependency Injector providers are not resolved from depin parameterised generic keys'
        elif 'decorat' in workload.name:
            reason = 'Dependency Injector provider composition does not model depin decoration chains'
        else:
            reason = 'Dependency Injector does not expose the depin provider operation this workload measures'
        return Candidate(
            workload.name,
            self.competitor,
            Equivalence.INCOMPARABLE,
            reason,
            None,
        )


ADAPTER: Adapter = DependencyInjectorAdapter()
