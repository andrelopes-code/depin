"""Shared graph builders and scaling-workload claim factory."""

import inspect
import types
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from typing import Protocol

from benchmarks.contracts import Claim, Metric
from depin import Container, Scope

FREEZE_SIZES = (100, 200, 400)


DEPTH_SIZES = (10, 40, 160)


FAN_OUT_SIZES = (10, 20, 40)


COLLECTION_SIZES = (10, 100, 200)


TEARDOWN_SIZES = (10, 20, 40)


ASYNC_TEARDOWN_SIZES = (10, 20, 40)


OVERRIDE_NESTING_SIZES = (8, 32, 128)


OVERRIDE_GRAPH = 1


class Element(Protocol):
    """The element key every collection curve gathers its members under."""


COLLECTION_KEY = list[Element]


class Trace:
    """Construction and teardown order, recorded only where an observation needs it.

    The same builders serve `prepare` and `observe`. A timed callable runs
    unbounded times, so recording during preparation would grow a list for the
    length of the measurement and change what is being measured.
    """

    __slots__ = ('events', 'recording')

    def __init__(self, *, recording: bool) -> None:
        self.recording = recording
        self.events: list[str] = []

    def record(self, event: str) -> None:
        if self.recording:
            self.events.append(event)


def node(index: int) -> type[object]:
    return type(f'Node{index}', (), {})


def _source(node: type[object], trace: Trace) -> Callable[..., object]:
    def make() -> object:
        trace.record(node.__name__)
        return node()

    make.__annotations__ = {'return': node}
    return make


def _link(node: type[object], dependency: type[object], trace: Trace) -> Callable[..., object]:
    def make(upstream: object) -> object:
        del upstream
        trace.record(node.__name__)
        return node()

    make.__annotations__ = {'upstream': dependency, 'return': node}
    return make


def _joiner(node: type[object], dependencies: Sequence[type[object]], trace: Trace) -> Callable[..., object]:
    """A provider with one real parameter per dependency.

    `depin` reads parameters from `inspect.signature`, which honours
    `__signature__`. Assigning annotations onto a `**kwargs` function alone would
    declare no parameters at all, and the graph would come out with no edges.
    """

    def make(**parts: object) -> object:
        del parts
        trace.record(node.__name__)
        return node()

    names = [f'part{index}' for index in range(len(dependencies))]
    # `__signature__` is not declared on `FunctionType`, and `inspect.signature`
    # reads it straight out of the function's `__dict__`.
    vars(make)['__signature__'] = inspect.Signature(
        [
            inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=dependency)
            for name, dependency in zip(names, dependencies, strict=True)
        ],
        return_annotation=node,
    )
    make.__annotations__ = dict(zip(names, dependencies, strict=True)) | {'return': node}
    return make


def _resource(node: type[object], trace: Trace) -> Callable[..., object]:
    def make() -> Iterator[object]:
        trace.record(node.__name__)
        yield node()
        trace.record(f'close {node.__name__}')

    make.__annotations__ = {'return': types.GenericAlias(Iterator, (node,))}
    return make


def chain(size: int, scope: Scope, trace: Trace) -> tuple[Container, type[object]]:
    container = Container()
    previous: type[object] | None = None
    leaf: type[object] = object
    for index in range(size):
        leaf = node(index)
        provider = _source(leaf, trace) if previous is None else _link(leaf, previous, trace)
        container = container.bind(provider, provides=leaf, scope=scope)
        previous = leaf
    return container, leaf


def fan_out(size: int, trace: Trace) -> tuple[Container, type[object]]:
    container = Container()
    leaves: list[type[object]] = []
    for index in range(size):
        leaf = node(index)
        container = container.bind(_source(leaf, trace), provides=leaf, scope=Scope.TRANSIENT)
        leaves.append(leaf)
    root = type('Root', (), {})
    return container.bind(_joiner(root, leaves, trace), provides=root, scope=Scope.TRANSIENT), root


def collection(size: int, trace: Trace) -> Container:
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = node(index)
        container = container.bind(_source(member, trace), provides=member, scope=Scope.TRANSIENT)
        members.append(member)
    return container.collect(Element, members)


def resources(size: int, trace: Trace) -> Container:
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = node(index)
        container = container.bind(_resource(member, trace), provides=member, scope=Scope.SCOPED)
        members.append(member)
    return container.collect(Element, members)


def claim(
    *,
    question: str,
    work: str,
    included: str,
    excluded: str,
    semantics: str,
    shape: str,
    valid: tuple[str, ...],
    invalid: tuple[str, ...],
) -> Claim:
    return Claim(
        question=question,
        work=work,
        included=included,
        excluded=excluded,
        semantics=semantics,
        shape=shape,
        concurrency='single-threaded, no event loop, no scope shared between operations',
        metric=Metric.SCALING,
        unit='seconds per operation',
        valid=valid,
        invalid=invalid,
    )


def _async_resource(node: type[object], trace: Trace) -> Callable[..., object]:
    async def make() -> AsyncIterator[object]:
        trace.record(node.__name__)
        yield node()
        trace.record(f'close {node.__name__}')

    make.__annotations__ = {'return': types.GenericAlias(AsyncIterator, (node,))}
    return make


def async_resources(size: int, trace: Trace) -> Container:
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = node(index)
        container = container.bind(_async_resource(member, trace), provides=member, scope=Scope.SCOPED)
        members.append(member)
    return container.collect(Element, members)


def members(values: Sequence[object]) -> str:
    """The constructed members, by type name and in order: what a collection observably produced."""
    return ','.join(type(value).__name__ for value in values)


def split_events(trace: Trace) -> tuple[tuple[str, ...], tuple[str, ...]]:
    opened = tuple(event for event in trace.events if not event.startswith('close '))
    closed = tuple(event.removeprefix('close ') for event in trace.events if event.startswith('close '))
    return opened, closed
