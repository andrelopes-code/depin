"""svcs implementations of comparable benchmark workloads."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Protocol

from svcs import Container, Registry

from benchmarks.comparison.contracts import Candidate, Competitor, Equivalence
from benchmarks.comparison.shapes import Chain, chain, observation
from benchmarks.contracts import Implementation, Observation, Prepared, Workload
from benchmarks.harness import HarnessError
from benchmarks.workloads.micro import HOT_GRAPH

if TYPE_CHECKING:
    from benchmarks.comparison.adapters import Adapter

_DISTRIBUTION = 'svcs'
_VERSION = '26.1.0'


class _Registry(Protocol):
    def register_factory(self, svc_type: type[object], factory: Callable[..., object]) -> None: ...


def require_installed_version() -> None:
    try:
        installed_version = version(_DISTRIBUTION)
    except PackageNotFoundError as error:
        raise HarnessError(f'{_DISTRIBUTION} is not installed in the bench group') from error
    if installed_version != _VERSION:
        raise HarnessError(f'{_DISTRIBUTION} {installed_version} is installed; {_VERSION} is required')


require_installed_version()


@dataclass(frozen=True, slots=True)
class SvcsChain:
    shape: Chain
    registry: Registry
    container: Container

    def close(self) -> None:
        self.container.close()
        self.registry.close()


def warm_chain(size: int) -> SvcsChain:
    shape = chain(size)
    registry = Registry()
    dependency: type[object] | None = None
    for node, factory in zip(shape.nodes, shape.factories, strict=True):
        _register_factory(registry, node, factory, dependency)
        dependency = node
    return SvcsChain(shape=shape, registry=registry, container=Container(registry))


def _register_factory(
    registry: _Registry,
    node: type[object],
    factory: Callable[..., object],
    dependency: type[object] | None,
) -> None:
    if dependency is None:
        registered = _factory_without_dependency(factory)
    else:
        registered = _factory_with_dependency(factory, dependency)
    registry.register_factory(node, registered)


def _factory_without_dependency(factory: Callable[..., object]) -> Callable[[Container], object]:
    def registered(svcs_container: Container) -> object:
        del svcs_container
        return factory()

    return registered


def _factory_with_dependency(factory: Callable[..., object], dependency: type[object]) -> Callable[[Container], object]:
    def registered(svcs_container: Container) -> object:
        return factory(svcs_container.get(dependency))

    return registered


def _implementation() -> Implementation:
    def prepare() -> Prepared:
        prepared = warm_chain(HOT_GRAPH)
        _ = prepared.container.get(prepared.shape.leaf)
        return Prepared(call=lambda: prepared.container.get(prepared.shape.leaf), close=prepared.close)

    def observe() -> Observation:
        observed = warm_chain(HOT_GRAPH)
        try:
            _ = observed.container.get(observed.shape.leaf)
            observed.shape.log.clear()
            value = observed.container.get(observed.shape.leaf)
            return observation(observed.shape, value)
        finally:
            observed.close()

    return Implementation(label=ADAPTER.competitor.label, prepare=prepare, observe=observe)


@dataclass(frozen=True, slots=True)
class SvcsAdapter:
    competitor: Competitor = field(default_factory=lambda: Competitor(_DISTRIBUTION, _VERSION))

    def candidates(self, workloads: Sequence[Workload]) -> tuple[Candidate, ...]:
        return tuple(self._candidate(workload) for workload in workloads)

    def _candidate(self, workload: Workload) -> Candidate:
        if workload.name == 'resolve_cached_singleton':
            return Candidate(
                workload.name,
                self.competitor,
                Equivalence.PARTIAL,
                'per-container caching has no singleton single-flight guarantee or nested lifetime contract',
                _implementation(),
            )
        if workload.name.startswith(('freeze_', 'warmup_', 'build_', 'explain_', 'export_')):
            reason = 'svcs has no separate frozen resolution plan or depin graph diagnostics operation'
        elif workload.name.startswith(('allocations_', 'retained_', 'scale_')):
            reason = 'the measured allocation, retention, or scaling source has no equivalent svcs operation'
        elif workload.name.startswith('fastapi_'):
            reason = 'svcs has no FastAPI integration with depin request lifecycle and declaration semantics'
        elif 'scope' in workload.name:
            reason = 'svcs containers have no nested scope frames with scoped caches'
        elif 'alias' in workload.name:
            reason = 'svcs has no depin typed-key alias resolution'
        elif 'collection' in workload.name:
            reason = 'svcs has no depin collection binding and aggregation operation'
        elif 'inject' in workload.name:
            reason = 'svcs has no depin injection wrapper calling semantics'
        elif 'override' in workload.name:
            reason = 'svcs has no depin context-local override frames'
        elif 'async' in workload.name or 'resource' in workload.name:
            reason = 'svcs async factories and cleanup do not share depin resolution and teardown semantics'
        elif 'generic' in workload.name:
            reason = 'svcs services are not resolved from depin parameterised generic keys'
        elif 'decorat' in workload.name:
            reason = 'svcs registrations do not model depin decoration chains'
        else:
            reason = 'svcs does not expose the depin provider operation this workload measures'
        return Candidate(workload.name, self.competitor, Equivalence.INCOMPARABLE, reason, None)


ADAPTER: Adapter = SvcsAdapter()
