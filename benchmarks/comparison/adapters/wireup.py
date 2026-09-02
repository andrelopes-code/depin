"""Wireup implementations of comparable benchmark workloads."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from wireup import SyncContainer, create_sync_container, injectable

from benchmarks.comparison.adapters import Adapter
from benchmarks.comparison.contracts import Candidate, Competitor, Equivalence
from benchmarks.comparison.shapes import Chain, chain, observation
from benchmarks.contracts import Implementation, Observation, Prepared, Workload
from benchmarks.harness import HarnessError
from benchmarks.workloads.micro import CHAIN_DEPTH, HOT_GRAPH

_DISTRIBUTION = 'wireup'
_VERSION = '2.12.0'

type Lifetime = Literal['singleton', 'transient', 'scoped']

try:
    _installed_version = version(_DISTRIBUTION)
except PackageNotFoundError as error:
    raise HarnessError(f'{_DISTRIBUTION} is not installed in the bench group') from error
if _installed_version != _VERSION:
    raise HarnessError(f'{_DISTRIBUTION} {_installed_version} is installed; {_VERSION} is required')


@dataclass(frozen=True, slots=True)
class WireupChain:
    shape: Chain
    container: SyncContainer

    def close(self) -> None:
        self.container.close()


def _injectable_factory(factory: Callable[..., object], lifetime: Lifetime) -> Callable[..., object]:
    if lifetime == 'singleton':
        return injectable(factory, lifetime='singleton')
    if lifetime == 'transient':
        return injectable(factory, lifetime='transient')
    return injectable(factory, lifetime='scoped')


def _chain(size: int, lifetime: Lifetime) -> WireupChain:
    shape = chain(size)
    factories = [_injectable_factory(factory, lifetime) for factory in shape.factories]
    return WireupChain(shape=shape, container=create_sync_container(injectables=factories))


def warm_chain(size: int) -> WireupChain:
    return _chain(size, 'singleton')


def transient_chain(size: int) -> WireupChain:
    return _chain(size, 'transient')


def scoped_chain(size: int) -> WireupChain:
    return _chain(size, 'scoped')


def _implementation(build: Callable[[], WireupChain], *, warm: bool) -> Implementation:
    def prepare() -> Prepared:
        prepared = build()
        if warm:
            _ = prepared.container.get(prepared.shape.leaf)
        return Prepared(call=lambda: prepared.container.get(prepared.shape.leaf), close=prepared.close)

    def observe() -> Observation:
        observed = build()
        try:
            if warm:
                _ = observed.container.get(observed.shape.leaf)
                observed.shape.log.clear()
            value = observed.container.get(observed.shape.leaf)
            return observation(observed.shape, value)
        finally:
            observed.close()

    return Implementation(label=ADAPTER.competitor.label, prepare=prepare, observe=observe)


def _scoped_implementation(build: Callable[[], WireupChain]) -> Implementation:
    def cycle(prepared: WireupChain) -> object:
        with prepared.container.enter_scope() as scope:
            return scope.get(prepared.shape.leaf)

    def prepare() -> Prepared:
        prepared = build()
        return Prepared(call=lambda: cycle(prepared), close=prepared.close)

    def observe() -> Observation:
        observed = build()
        try:
            value = cycle(observed)
            return observation(observed.shape, value)
        finally:
            observed.close()

    return Implementation(label=ADAPTER.competitor.label, prepare=prepare, observe=observe)


@dataclass(frozen=True, slots=True)
class WireupAdapter:
    competitor: Competitor = field(default_factory=lambda: Competitor(_DISTRIBUTION, _VERSION))

    def candidates(self, workloads: Sequence[Workload]) -> tuple[Candidate, ...]:
        return tuple(self._candidate(workload) for workload in workloads)

    def _candidate(self, workload: Workload) -> Candidate:
        if workload.name == 'resolve_cached_singleton':
            implementation = _implementation(lambda: warm_chain(HOT_GRAPH), warm=True)
        elif workload.name == 'resolve_a_transient_chain':
            implementation = _scoped_implementation(lambda: transient_chain(CHAIN_DEPTH))
        elif workload.name == 'open_and_close_a_scope':
            implementation = _scoped_implementation(lambda: scoped_chain(CHAIN_DEPTH))
        else:
            implementation = None
        if implementation is not None:
            return Candidate(
                workload.name,
                self.competitor,
                Equivalence.EQUIVALENT,
                'matches the singleton, transient, or request-scoped provider lifecycle and construction shape',
                implementation,
            )
        if workload.name.startswith(('freeze_', 'warmup_', 'build_', 'explain_', 'export_')):
            reason = 'Wireup has no separate frozen resolution plan or depin graph diagnostics operation'
        elif workload.name.startswith(('allocations_', 'retained_', 'scale_')):
            reason = 'the measured allocation, retention, or scaling source has no equivalent Wireup operation'
        elif workload.name.startswith('fastapi_'):
            reason = 'the FastAPI integration has different request lifecycle and dependency declaration semantics'
        elif 'alias' in workload.name:
            reason = 'Wireup alias resolution does not demonstrate depin typed-key alias cache semantics'
        elif 'collection' in workload.name:
            reason = 'Wireup has no depin collection binding and aggregation operation'
        elif 'inject' in workload.name:
            reason = 'Wireup injection does not share depin injection wrapper calling semantics'
        elif 'override' in workload.name:
            reason = 'Wireup provider substitution is not a depin context-local override frame'
        elif 'async' in workload.name or 'resource' in workload.name:
            reason = 'Wireup async and resource providers have different resolution and teardown semantics'
        elif 'generic' in workload.name:
            reason = 'Wireup providers are not resolved from depin parameterised generic keys'
        elif 'decorat' in workload.name:
            reason = 'Wireup provider composition does not model depin decoration chains'
        else:
            reason = 'Wireup does not expose the depin provider operation this workload measures'
        return Candidate(workload.name, self.competitor, Equivalence.INCOMPARABLE, reason, None)


ADAPTER: Adapter = WireupAdapter()
