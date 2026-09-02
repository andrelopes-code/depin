"""Shared, observable provider shapes for competitor benchmarks."""

from collections.abc import Callable
from dataclasses import dataclass

from benchmarks.contracts import Observation
from benchmarks.harness import HarnessError


@dataclass(frozen=True, slots=True)
class Chain:
    nodes: tuple[type[object], ...]
    factories: tuple[Callable[..., object], ...]
    leaf: type[object]
    log: list[str]


def _factory(node: type[object], dependency: type[object] | None, log: list[str]) -> Callable[..., object]:
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


def chain(size: int) -> Chain:
    if size < 1:
        raise HarnessError('chain size must be at least one')
    nodes = tuple(type(f'Node{index}', (), {}) for index in range(size))
    log: list[str] = []
    factories = tuple(_factory(node, nodes[index - 1] if index else None, log) for index, node in enumerate(nodes))
    return Chain(nodes=nodes, factories=factories, leaf=nodes[-1], log=log)


def observation(chain: Chain, value: object) -> Observation:
    return Observation(result=type(value).__name__, constructed=tuple(chain.log), closed=())
