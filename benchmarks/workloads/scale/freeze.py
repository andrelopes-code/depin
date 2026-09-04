"""Scaling workloads for freeze and resolution shapes."""

from collections.abc import Callable
from functools import partial

from benchmarks.contracts import Observation, Prepared
from depin import Scope

from .builders import COLLECTION_KEY, Trace, chain, collection, fan_out, members, node


def freeze_prepare(size: int) -> Prepared:
    container, _ = chain(size, Scope.SINGLETON, Trace(recording=False))
    return Prepared(call=container.freeze)


def freeze_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, _ = chain(size, Scope.SINGLETON, trace)
    frozen = container.freeze()
    return Observation(result=str(len(frozen.graph().nodes)), constructed=tuple(trace.events), closed=())


def resolve_prepare(size: int) -> Prepared:
    container, leaf = chain(size, Scope.TRANSIENT, Trace(recording=False))
    frozen = container.freeze()
    return Prepared(call=partial(frozen.resolve, leaf))


def resolve_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, leaf = chain(size, Scope.TRANSIENT, trace)
    value = container.freeze().resolve(leaf)
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _direct_chain(size: int, trace: Trace) -> Callable[[], object]:
    nodes = tuple(node(index) for index in range(size))

    def run() -> object:
        built: object = None
        for node_type in nodes:
            trace.record(node_type.__name__)
            built = node_type()
        return built

    return run


def direct_resolve_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_chain(size, Trace(recording=False)))


def direct_resolve_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    value = _direct_chain(size, trace)()
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def fan_out_prepare(size: int) -> Prepared:
    container, root = fan_out(size, Trace(recording=False))
    frozen = container.freeze()
    return Prepared(call=partial(frozen.resolve, root))


def fan_out_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    container, root = fan_out(size, trace)
    value = container.freeze().resolve(root)
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def _direct_fan_out(size: int, trace: Trace) -> Callable[[], object]:
    leaves = tuple(node(index) for index in range(size))
    root = type('Root', (), {})

    def run() -> object:
        for leaf in leaves:
            trace.record(leaf.__name__)
        trace.record(root.__name__)
        return root()

    return run


def direct_fan_out_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_fan_out(size, Trace(recording=False)))


def direct_fan_out_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    value = _direct_fan_out(size, trace)()
    return Observation(result=type(value).__name__, constructed=tuple(trace.events), closed=())


def collection_prepare(size: int) -> Prepared:
    frozen = collection(size, Trace(recording=False)).freeze()
    return Prepared(call=partial(frozen.resolve, COLLECTION_KEY))


def collection_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    values = collection(size, trace).freeze().resolve(COLLECTION_KEY)
    return Observation(result=members(values), constructed=tuple(trace.events), closed=())


def _direct_collection(size: int, trace: Trace) -> Callable[[], list[object]]:
    members = tuple(node(index) for index in range(size))

    def run() -> list[object]:
        built: list[object] = []
        for member in members:
            trace.record(member.__name__)
            built.append(member())
        return built

    return run


def direct_collection_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_collection(size, Trace(recording=False)))


def direct_collection_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    values = _direct_collection(size, trace)()
    return Observation(result=members(values), constructed=tuple(trace.events), closed=())
