"""The scenarios the regression gate watches: graph validation, resolution, scopes, injection."""

import asyncio
import types
from collections.abc import Callable
from typing import Protocol

import pytest

from benchmarks.graphs import build_chain
from depin import Container, Scope, injected


class Element(Protocol): ...


def _build_collection(size: int) -> tuple[Container, types.GenericAlias]:
    """A collection of `size` independently bound members, in the style of `build_chain`.

    Returns the unfrozen container and the ``list[Element]`` key the members are
    gathered under.
    """
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = type(f'Member{index}', (), {})

        def make(node: type[object] = member) -> object:
            return node()

        make.__annotations__ = {'return': member}
        container = container.bind(make, provides=member)
        members.append(member)
    return container.collect(Element, members), types.GenericAlias(list, (Element,))


class Benchmark(Protocol):
    """The subset of pytest-benchmark's fixture these cases use.

    Declared locally so the benchmarks do not depend on the plugin shipping
    accurate type information.
    """

    def __call__[T](self, function: Callable[[], T]) -> T: ...


@pytest.mark.parametrize('size', [10, 100, 1000])
def test_freeze_a_chain(benchmark: Benchmark, size: int) -> None:
    container, _ = build_chain(size)
    _ = benchmark(container.freeze)


def test_resolve_a_cached_singleton(benchmark: Benchmark) -> None:
    container, leaf = build_chain(100)
    frozen = container.freeze()
    _ = frozen.resolve(leaf)

    def resolve() -> object:
        return frozen.resolve(leaf)

    _ = benchmark(resolve)


def test_resolve_a_cached_singleton_through_an_alias(benchmark: Benchmark) -> None:
    """The alias hop, measured against `test_resolve_a_cached_singleton`.

    The two cases resolve the same target from the same graph; the difference
    between them is the cost of the extra transient node.
    """

    class Aliased(Protocol): ...

    container, leaf = build_chain(100)
    frozen = container.alias(Aliased, to=leaf).freeze()
    _ = frozen.resolve(Aliased)

    def resolve() -> object:
        return frozen.resolve(Aliased)

    _ = benchmark(resolve)


@pytest.mark.parametrize('size', [10, 100])
def test_resolve_a_collection(benchmark: Benchmark, size: int) -> None:
    container, key = _build_collection(size)
    frozen = container.freeze()
    _ = frozen.resolve(key)

    def resolve() -> object:
        return frozen.resolve(key)

    _ = benchmark(resolve)


def test_resolve_a_transient_chain(benchmark: Benchmark) -> None:
    container, leaf = build_chain(20, scope=Scope.TRANSIENT)
    frozen = container.freeze()

    def resolve() -> object:
        return frozen.resolve(leaf)

    _ = benchmark(resolve)


def test_open_and_close_a_scope(benchmark: Benchmark) -> None:
    container, leaf = build_chain(20, scope=Scope.SCOPED)
    frozen = container.freeze()

    def cycle() -> None:
        with frozen.scope():
            _ = frozen.resolve(leaf)

    _ = benchmark(cycle)


def test_call_through_an_inject_wrapper(benchmark: Benchmark) -> None:
    class Repo:
        def count(self) -> int:
            return 3

    frozen = Container().bind(Repo).freeze()

    @frozen.inject
    def handler(repo: Repo = injected(Repo)) -> int:
        return repo.count()

    _ = benchmark(handler)


def test_resolve_an_async_singleton(benchmark: Benchmark) -> None:
    class Pool: ...

    async def make() -> Pool:
        return Pool()

    frozen = Container().bind(make, provides=Pool, scope=Scope.SINGLETON).freeze()
    # One loop for the whole measurement: creating a loop per iteration would
    # benchmark asyncio's startup instead of depin's resolution.
    loop = asyncio.new_event_loop()
    try:
        _ = loop.run_until_complete(frozen.aresolve(Pool))

        def resolve() -> Pool:
            return loop.run_until_complete(frozen.aresolve(Pool))

        _ = benchmark(resolve)
    finally:
        loop.close()
