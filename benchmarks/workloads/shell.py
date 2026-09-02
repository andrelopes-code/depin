"""The pair every tier builds its implementations from: what to time, and what it observes.

A tier module describes workloads; this describes how a workload is run. Keeping
the two apart is what lets a tier be read as a list of claims rather than as a
list of closures.
"""

from collections.abc import Callable
from dataclasses import dataclass

from benchmarks.contracts import Implementation, Observation, Prepared
from benchmarks.graphs import chain_types
from depin import Container, Scope

CONCURRENCY = 'single-threaded; one container, no scope crossing a thread boundary'


@dataclass(frozen=True, slots=True)
class Session:
    """One prepared run of an implementation: what to time, what it observes, what to release."""

    call: Callable[[], object]
    observe: Callable[[], Observation]
    close: Callable[[], None] | None = None


def implementation(label: str, setup: Callable[[], Session]) -> Implementation:
    """An `Implementation` running `setup` once per `prepare` and once per `observe`.

    The two never share a session, so an observation cannot be read off state a
    timed run left behind, and a timed run cannot inherit a cache an observation
    warmed.
    """

    def prepare() -> Prepared:
        session = setup()
        return Prepared(call=session.call, close=session.close)

    def observe() -> Observation:
        session = setup()
        try:
            return session.observe()
        finally:
            if session.close is not None:
                session.close()

    return Implementation(label=label, prepare=prepare, observe=observe)


def recording_provider(node: type[object], dependency: type[object] | None, log: list[str]) -> Callable[..., object]:
    """`graphs._provider`, naming `node` in `log` as it constructs it."""
    if dependency is None:

        def make() -> object:
            log.append(node.__name__)
            return node()

        make.__annotations__ = {'return': node}
        return make

    def make_with_dependency(upstream: object) -> object:
        del upstream
        log.append(node.__name__)
        return node()

    make_with_dependency.__annotations__ = {'upstream': dependency, 'return': node}
    return make_with_dependency


def recording_chain(size: int, scope: Scope, log: list[str]) -> tuple[Container, type[object]]:
    """`graphs.build_chain`, with every provider naming its node in `log` as it constructs it.

    The observed graph, never the timed one: the append is what makes an
    `Observation` record construction order rather than assert it, and it has no
    business inside a measurement.
    """
    container = Container()
    previous: type[object] | None = None
    leaf: type[object] = object
    for node in chain_types(size):
        leaf = node
        container = container.bind(recording_provider(leaf, previous, log), provides=leaf, scope=scope)
        previous = leaf
    return container, leaf
