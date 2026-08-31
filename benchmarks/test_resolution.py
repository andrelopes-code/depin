"""The scenarios the regression gate watches: graph validation, resolution, scopes, injection."""

import asyncio
import types
from collections.abc import Callable
from typing import Annotated, Protocol

import pytest

from benchmarks.graphs import build_chain, build_decorated_chain, build_generic_chain
from depin import Container, FrozenContainer, Scope, Token, WarmupReport, injected


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
    def pedantic[T](
        self,
        target: Callable[..., T],
        *,
        setup: Callable[[], tuple[tuple[object, ...], dict[str, object]]],
        rounds: int = 1,
    ) -> T: ...


@pytest.mark.parametrize('size', [10, 100, 1000])
def test_freeze_a_chain(benchmark: Benchmark, size: int) -> None:
    container, _ = build_chain(size)
    _ = benchmark(container.freeze)


@pytest.mark.parametrize('size', [10, 100, 1000])
def test_freeze_a_chain_of_generic_keys(benchmark: Benchmark, size: int) -> None:
    """`test_freeze_a_chain`, with every key parameterised, so the canonical-form
    check's cost on the freeze path is visible against the plain-key baseline."""
    container, _ = build_generic_chain(size)
    _ = benchmark(container.freeze)


@pytest.mark.parametrize('size', [10, 100, 1000])
def test_freeze_a_chain_with_every_node_decorated(benchmark: Benchmark, size: int) -> None:
    """`test_freeze_a_chain`, with one decorator over every node, so the cost of
    folding decorations into the plan is visible against the plain-chain baseline."""
    container, _ = build_decorated_chain(size)
    _ = benchmark(container.freeze)


def test_warmup_a_chain(benchmark: Benchmark) -> None:
    """Constructing every singleton in one pass, against `test_freeze_a_chain`'s cost
    for the same graph size.

    `setup` freezes a fresh container before each round, outside the window
    `pytest-benchmark` times, so the timed callable is `warmup()` alone rather than
    `freeze()` plus `warmup()`. A fresh container per round, rather than one frozen
    container reused: a warmed container caches every singleton, so a second
    `warmup()` on the same one would measure the cached branch instead of
    construction.
    """
    container, _ = build_chain(1000)

    def setup() -> tuple[tuple[FrozenContainer], dict[str, object]]:
        return (container.freeze(),), {}

    def warm(frozen: FrozenContainer) -> WarmupReport:
        return frozen.warmup()

    _ = benchmark.pedantic(warm, setup=setup, rounds=50)


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


def test_resolve_a_singleton_through_a_two_deep_decoration_chain(benchmark: Benchmark) -> None:
    """`test_resolve_a_cached_singleton`, with two decorators wrapping the leaf.

    Measures the cost of the two extra nodes decoration inserts between the
    cached value and the public key.
    """

    class Store: ...

    class Middle:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    class Outer:
        def __init__(self, inner: Store) -> None:
            self.inner = inner

    frozen = Container().bind(Store).decorate(Store, Middle).decorate(Store, Outer).freeze()
    _ = frozen.resolve(Store)

    def resolve() -> object:
        return frozen.resolve(Store)

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


def test_open_a_request_shaped_scope(benchmark: Benchmark) -> None:
    """A scope opened, seeded, and resolved from — the shape every integration runs per request."""
    request = Token[str]('request')

    class Session:
        def __init__(self, incoming: Annotated[str, request]) -> None:
            self.incoming = incoming

    class Handler:
        def __init__(self, session: Session, incoming: Annotated[str, request]) -> None:
            self.session = session
            self.incoming = incoming

    di = Container().scope_value(request).bind(Session, scope=Scope.SCOPED).bind(Handler, scope=Scope.SCOPED).freeze()

    def run() -> object:
        with di.scope() as frame:
            frame.provide(request, 'r-1')
            return di.resolve(Handler)

    _ = benchmark(run)


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
