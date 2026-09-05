"""Dishka implementations of comparable benchmark workloads."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version

from dishka import Container, Provider, Scope, make_container

from benchmarks.comparison.adapters import Adapter
from benchmarks.comparison.contracts import Candidate, Competitor, Equivalence
from benchmarks.comparison.shapes import Chain, observation
from benchmarks.comparison.shapes import chain as chain_shape
from benchmarks.contracts import Implementation, Observation, Prepared, Workload
from benchmarks.harness import HarnessError
from benchmarks.workloads.micro import CHAIN_DEPTH, HOT_GRAPH

_DISTRIBUTION = 'dishka'
_VERSION = '1.10.1'

try:
    _installed_version = version(_DISTRIBUTION)
except PackageNotFoundError as error:
    raise HarnessError(f'{_DISTRIBUTION} is not installed in the bench group') from error
if _installed_version != _VERSION:
    raise HarnessError(f'{_DISTRIBUTION} {_installed_version} is installed; {_VERSION} is required')


class _ChainProvider(Provider):
    def __init__(self, shape: Chain, scope: Scope, *, cache: bool) -> None:
        super().__init__()
        for index, factory in enumerate(shape.factories):
            setattr(self, f'factory_{index}', self.provide(staticmethod(factory), scope=scope, cache=cache))


@dataclass(frozen=True, slots=True)
class DishkaChain:
    shape: Chain
    container: Container

    def close(self) -> None:
        self.container.close()


def chain(size: int, scope: Scope, *, cache: bool) -> DishkaChain:
    shape = chain_shape(size)
    return DishkaChain(shape=shape, container=make_container(_ChainProvider(shape, scope, cache=cache)))


def warm_chain(size: int) -> DishkaChain:
    return chain(size, Scope.APP, cache=True)


def transient_chain(size: int) -> DishkaChain:
    return chain(size, Scope.APP, cache=False)


def scoped_chain(size: int) -> DishkaChain:
    return chain(size, Scope.REQUEST, cache=True)


def _implementation(build: Callable[[], DishkaChain], *, warm: bool) -> Implementation:
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


def _scoped_implementation(build: Callable[[], DishkaChain]) -> Implementation:
    def cycle(prepared: DishkaChain) -> object:
        with prepared.container() as request_container:
            return request_container.get(prepared.shape.leaf)

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
class DishkaAdapter:
    competitor: Competitor = field(default_factory=lambda: Competitor(_DISTRIBUTION, _VERSION))

    def candidates(self, workloads: Sequence[Workload]) -> tuple[Candidate, ...]:
        return tuple(self._candidate(workload) for workload in workloads)

    def _candidate(self, workload: Workload) -> Candidate:
        if workload.name == 'resolve_cached_singleton':
            implementation = _implementation(lambda: warm_chain(HOT_GRAPH), warm=True)
        elif workload.name == 'resolve_a_transient_chain':
            implementation = _implementation(lambda: transient_chain(CHAIN_DEPTH), warm=False)
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
            reason = 'Dishka has no separate frozen resolution plan or depin graph diagnostics operation'
        elif workload.name.startswith(('allocations_', 'retained_', 'scale_')):
            reason = 'the measured allocation, retention, or scaling source has no equivalent Dishka operation'
        elif workload.name.startswith('fastapi_'):
            reason = 'the FastAPI integration has different request lifecycle and dependency declaration semantics'
        elif 'alias' in workload.name:
            reason = 'Dishka alias resolution does not demonstrate depin typed-key alias cache semantics'
        elif 'collection' in workload.name:
            reason = 'Dishka has no depin collection binding and aggregation operation'
        elif 'inject' in workload.name:
            reason = 'Dishka injection does not share depin injection wrapper calling semantics'
        elif 'override' in workload.name:
            reason = 'Dishka provider substitution is not a depin context-local override frame'
        elif 'async' in workload.name or 'resource' in workload.name:
            reason = 'Dishka async and resource providers have different resolution and teardown semantics'
        elif 'generic' in workload.name:
            reason = 'Dishka providers are not resolved from depin parameterised generic keys'
        elif 'decorat' in workload.name:
            reason = 'Dishka provider composition does not model depin decoration chains'
        else:
            reason = 'Dishka does not expose the depin provider operation this workload measures'
        return Candidate(workload.name, self.competitor, Equivalence.INCOMPARABLE, reason, None)


ADAPTER: Adapter = DishkaAdapter()
