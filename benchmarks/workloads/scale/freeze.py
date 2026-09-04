"""Scaling workloads for freeze and resolution shapes."""

from collections.abc import Callable
from functools import partial

from benchmarks.contracts import Observation, Prepared
from depin import Scope

from .builders import COLLECTION_KEY, Trace, _chain, _collection, _fan_out, _members, _node


def _freeze_prepare(size: int) -> Prepared:
    container, _ = _chain(size, Scope.SINGLETON, Trace(recording=False))
    return Prepared(call=container.freeze)


def _freeze_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, _ = _chain(size, Scope.SINGLETON, trace)
    frozen = container.freeze()
    return Observation(result=str(len(frozen.graph().nodes)), constructed=tuple(trace.events), closed=())


def _resolve_prepare(size: int) -> Prepared:
    container, leaf = _chain(size, Scope.TRANSIENT, Trace(recording=False))
    frozen = container.freeze()
    return Prepared(call=partial(frozen.resolve, leaf))


def _resolve_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, leaf = _chain(size, Scope.TRANSIENT, trace)
    value = container.freeze().resolve(leaf)
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _direct_chain(size: int, trace: Trace) -> Callable[[], object]:
    nodes = tuple(_node(index) for index in range(size))

    def run() -> object:
        built: object = None
        for node in nodes:
            trace.record(node.__name__)
            built = node()
        return built

    return run


def _direct_resolve_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_chain(size, Trace(recording=False)))


def _direct_resolve_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    value = _direct_chain(size, trace)()
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _fan_out_prepare(size: int) -> Prepared:
    container, root = _fan_out(size, Trace(recording=False))
    frozen = container.freeze()
    return Prepared(call=partial(frozen.resolve, root))


def _fan_out_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, root = _fan_out(size, trace)
    value = container.freeze().resolve(root)
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _direct_fan_out(size: int, trace: Trace) -> Callable[[], object]:
    leaves = tuple(_node(index) for index in range(size))
    root = type('Root', (), {})

    def run() -> object:
        for leaf in leaves:
            trace.record(leaf.__name__)
        trace.record(root.__name__)
        return root()

    return run


def _direct_fan_out_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_fan_out(size, Trace(recording=False)))


def _direct_fan_out_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    value = _direct_fan_out(size, trace)()
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _collection_prepare(size: int) -> Prepared:
    frozen = _collection(size, Trace(recording=False)).freeze()
    return Prepared(call=partial(frozen.resolve, COLLECTION_KEY))


def _collection_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    values = _collection(size, trace).freeze().resolve(COLLECTION_KEY)
    return Observation(result=_members(values), constructed=tuple(trace.events), closed=())


def _direct_collection(size: int, trace: Trace) -> Callable[[], list[object]]:
    members = tuple(_node(index) for index in range(size))

    def run() -> list[object]:
        built: list[object] = []
        for member in members:
            trace.record(member.__name__)
            built.append(member())
        return built

    return run


def _direct_collection_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_collection(size, Trace(recording=False)))


def _direct_collection_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    values = _direct_collection(size, trace)()
    return Observation(result=_members(values), constructed=tuple(trace.events), closed=())
