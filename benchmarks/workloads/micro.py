"""Tier 1: one isolated operation per workload, on the smallest graph that isolates it.

Also carries `Session` and `implementation`, the shell every tier builds its
`Implementation` pair from. It lives here because tier 1 is where the pair is
smallest and the shape is easiest to read.
"""

import asyncio
from collections.abc import Callable
from typing import Protocol

from benchmarks.contracts import (
    Claim,
    Metric,
    NoiseClass,
    Observation,
    Tier,
    Workload,
)
from benchmarks.graphs import build_chain, chain_types
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation, recording_chain
from depin import Container, Scope, injected

HOT_GRAPH = 100
"""The graph size every cached-lookup workload uses.

The baseline measured a cached lookup at 2021, 1970, 2033 and 1992 ns over graphs
of 1, 10, 100 and 300 nodes — flat within 3%. The size therefore does not move the
number, and fixing one across the family is what lets the alias and decoration
workloads be read as differences from `resolve_cached_singleton` without the
reader having to know that.
"""

CHAIN_DEPTH = 20
"""The depth the transient and scoped chains construct through, as the suite has always used."""


class Wired:
    """What a hand-wired program holds: one object, reached by attribute access.

    The baseline measured a cached resolution against exactly this — 2.17 µs
    against 0.06 µs for an attribute read on a held object — so the direct
    implementations of the cached-lookup family read through one.
    """

    def __init__(self, value: object) -> None:
        self.value = value


class Element(Protocol):
    """The element key `resolve_collection` gathers its members under."""


class Aliased(Protocol):
    """The second name `resolve_cached_singleton_through_an_alias` resolves through."""


class Repo:
    """The one dependency the injected wrapper receives."""

    def count(self) -> int:
        return 3


class Pool:
    """The async singleton, whose provider is a coroutine function."""


class Decorated:
    """What a decorator returns: the wrapped value, held."""

    def __init__(self, inner: object) -> None:
        self.inner = inner


class Middle(Decorated):
    """The inner of the two decorators over the leaf."""


class Outer(Decorated):
    """The outer of the two decorators over the leaf."""


async def _ready(value: object) -> object:
    """The bare coroutine the async baseline drives through the same event loop."""
    return value


def _decoration(wrapper: type[Decorated], node: type[object]) -> Callable[..., object]:
    """A decorator over `node` returning a `wrapper`, annotated the way `graphs._provider` is."""

    def wrap(inner: object) -> object:
        return wrapper(inner)

    wrap.__annotations__ = {'inner': node, 'return': node}
    return wrap


def _construct_chain(nodes: tuple[type[object], ...]) -> object:
    """Construct every class in `nodes`, in order, and return the last."""
    made: object = None
    for node in nodes:
        made = node()
    return made


def _construct_recorded(nodes: tuple[type[object], ...], log: list[str]) -> object:
    """`_construct_chain`, naming each class in `log` as it is constructed."""
    made: object = None
    for node in nodes:
        log.append(node.__name__)
        made = node()
    return made


def _build_collection(size: int) -> Container:
    """`size` independently bound members, gathered under `list[Element]`."""
    container = Container()
    members: list[type[object]] = []
    for index in range(size):
        member = type(f'Member{index}', (), {})

        def make(node: type[object] = member) -> object:
            return node()

        make.__annotations__ = {'return': member}
        container = container.bind(make, provides=member)
        members.append(member)
    return container.collect(Element, members)


def _collection_result(members: list[Element]) -> str:
    return f'list[{len(members)}] {type(members[0]).__name__}..{type(members[-1]).__name__}'


def _resolve_cached_singleton() -> Workload:
    def depin_setup() -> Session:
        container, leaf = build_chain(HOT_GRAPH)
        frozen = container.freeze()
        _ = frozen.resolve(leaf)
        return Session(
            call=lambda: frozen.resolve(leaf),
            observe=lambda: Observation(result=type(frozen.resolve(leaf)).__name__, constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Wired(_construct_chain(chain_types(HOT_GRAPH)))
        return Session(
            call=lambda: held.value,
            observe=lambda: Observation(result=type(held.value).__name__, constructed=(), closed=()),
        )

    return Workload(
        name='resolve_cached_singleton',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does one resolution cost once the value is already built?',
            work='Return the singleton at the deep end of a 100-provider chain.',
            included='The key lookup, the override check, and the cache read.',
            excluded='Declaration, freeze, and the construction of the singleton, all done in setup.',
            semantics='Singleton. The cache is warm before the first timed call, so nothing is constructed.',
            shape=f'A linear chain of {HOT_GRAPH} providers; the leaf is resolved.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            noise=NoiseClass.MEDIUM,
            valid=(
                'The recurring cost of reaching a dependency through depin rather than holding it.',
                'The ratio to the direct implementation, which is an attribute read on a held object.',
            ),
            invalid=(
                'Not the cost of building the object; nothing is constructed in the timed region.',
                'Not a function of graph size: the baseline measured this flat within 3% over 1 to 300 nodes.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _resolve_cached_singleton_through_an_alias() -> Workload:
    def depin_setup() -> Session:
        container, leaf = build_chain(HOT_GRAPH)
        frozen = container.alias(Aliased, to=leaf).freeze()
        _ = frozen.resolve(Aliased)
        return Session(
            call=lambda: frozen.resolve(Aliased),
            observe=lambda: Observation(result=type(frozen.resolve(Aliased)).__name__, constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Wired(_construct_chain(chain_types(HOT_GRAPH)))
        return Session(
            call=lambda: held.value,
            observe=lambda: Observation(result=type(held.value).__name__, constructed=(), closed=()),
        )

    return Workload(
        name='resolve_cached_singleton_through_an_alias',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does a second name for a binding add to a resolution?',
            work='Return the same singleton `resolve_cached_singleton` returns, reached through an alias.',
            included='The alias node, then the key lookup, the override check, and the cache read.',
            excluded='Declaration, freeze, and the construction of the singleton, all done in setup.',
            semantics='Singleton. The alias caches nothing of its own; the target keeps the cache entry.',
            shape=f'A linear chain of {HOT_GRAPH} providers, with one alias over the leaf.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            noise=NoiseClass.MEDIUM,
            valid=('The alias hop, read as the difference from `resolve_cached_singleton` at the same graph size.',),
            invalid=(
                'Not an absolute alias cost: the number is one resolution, of which the hop is a part.',
                'Not comparable with the direct implementation as a ratio worth publishing: '
                'hand-wiring has no alias hop, so the baseline is the same held object under a second name.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _resolve_singleton_through_a_two_deep_decoration_chain() -> Workload:
    def depin_setup() -> Session:
        container, leaf = build_chain(HOT_GRAPH)
        frozen = container.decorate(leaf, _decoration(Middle, leaf)).decorate(leaf, _decoration(Outer, leaf)).freeze()
        _ = frozen.resolve(leaf)
        return Session(
            call=lambda: frozen.resolve(leaf),
            observe=lambda: Observation(result=type(frozen.resolve(leaf)).__name__, constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Wired(Outer(Middle(_construct_chain(chain_types(HOT_GRAPH)))))
        return Session(
            call=lambda: held.value,
            observe=lambda: Observation(result=type(held.value).__name__, constructed=(), closed=()),
        )

    return Workload(
        name='resolve_singleton_through_a_two_deep_decoration_chain',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What do two stacked decorators add to a resolution?',
            work='Return the twice-wrapped singleton at the deep end of a 100-provider chain.',
            included='Two decoration nodes, then the key lookup, the override check, and the cache read.',
            excluded='Declaration, freeze, and the construction of the value and its two wrappers.',
            semantics='Singleton. The wrapped value is cached, so the wrappers are built once, in setup.',
            shape=(
                f'A linear chain of {HOT_GRAPH} providers — the size `resolve_cached_singleton` uses — '
                'with two pass-through decorators over the leaf.'
            ),
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            noise=NoiseClass.MEDIUM,
            valid=(
                'The two decoration hops, read as the difference from `resolve_cached_singleton`. '
                'Both workloads use a 100-node chain, so the difference is the decoration.',
            ),
            invalid=(
                'Not a per-decorator cost: two hops are measured together, and they are not independent.',
                'Not the cost of applying decoration at freeze time, which is a separate workload.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _resolve_a_collection(size: int) -> Workload:
    def depin_setup() -> Session:
        frozen = _build_collection(size).freeze()
        _ = frozen.resolve(list[Element])
        return Session(
            call=lambda: frozen.resolve(list[Element]),
            observe=lambda: Observation(
                result=_collection_result(frozen.resolve(list[Element])),
                constructed=(),
                closed=(),
            ),
        )

    def direct_setup() -> Session:
        members = [type(f'Member{index}', (), {})() for index in range(size)]
        return Session(
            call=lambda: list(members),
            observe=lambda: Observation(result=_collection_result(list(members)), constructed=(), closed=()),
        )

    return Workload(
        name=f'resolve_a_collection_of_{size}',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does gathering a multi-binding into a list cost, by member count?',
            work=f'Return a list of the {size} members bound under one element key.',
            included='The collection node, one cache read per member, and the list that is assembled.',
            excluded='Declaration, freeze, and the construction of the members, all done in setup.',
            semantics=(
                'Singleton members, each built once and cached. The list itself is rebuilt per resolution, '
                'so no caller can mutate the list another caller holds.'
            ),
            shape=f'{size} independent providers with no dependencies, gathered under `list[Element]`.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            noise=NoiseClass.MEDIUM,
            valid=(
                'The per-member cost of a collection, read across the two sizes.',
                'The ratio to building the same list from held references.',
            ),
            invalid=(
                'Not the cost of constructing the members; they are cached before the first timed call.',
                'Not a scoped or transient collection, whose members are rebuilt per resolution.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _resolve_a_transient_chain() -> Workload:
    def depin_setup() -> Session:
        container, leaf = build_chain(CHAIN_DEPTH, scope=Scope.TRANSIENT)
        frozen = container.freeze()
        log: list[str] = []
        observed, observed_leaf = recording_chain(CHAIN_DEPTH, Scope.TRANSIENT, log)
        observed_frozen = observed.freeze()

        def observe() -> Observation:
            log.clear()
            value = observed_frozen.resolve(observed_leaf)
            return Observation(result=type(value).__name__, constructed=tuple(log), closed=())

        return Session(call=lambda: frozen.resolve(leaf), observe=observe)

    def direct_setup() -> Session:
        nodes = chain_types(CHAIN_DEPTH)

        def observe() -> Observation:
            log: list[str] = []
            value = _construct_recorded(nodes, log)
            return Observation(result=type(value).__name__, constructed=tuple(log), closed=())

        return Session(call=lambda: _construct_chain(nodes), observe=observe)

    return Workload(
        name='resolve_a_transient_chain',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does depin add to constructing a dependency chain that is never cached?',
            work=f'Construct {CHAIN_DEPTH} objects, each depending on the one before it, and return the last.',
            included='One resolution per node: lookup, override check, parameter resolution, and construction.',
            excluded='Declaration and freeze, both done in setup.',
            semantics='Transient. Nothing is cached, so every timed call constructs the whole chain.',
            shape=f'A linear chain of {CHAIN_DEPTH} transient providers; the leaf is resolved.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            noise=NoiseClass.LOW,
            valid=(
                'The construction overhead per node, as the ratio to constructing the same chain by hand.',
                'The increment over `resolve_cached_singleton`, which is the same lookup without construction.',
            ),
            invalid=(
                'Not a general depth cost: the baseline measured cold resolution failing beyond 332 providers.',
                'Not applicable to singletons, which pay this once rather than per resolution.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _open_and_close_a_scope() -> Workload:
    def depin_setup() -> Session:
        container, leaf = build_chain(CHAIN_DEPTH, scope=Scope.SCOPED)
        frozen = container.freeze()
        log: list[str] = []
        observed, observed_leaf = recording_chain(CHAIN_DEPTH, Scope.SCOPED, log)
        observed_frozen = observed.freeze()

        def cycle() -> object:
            with frozen.scope():
                return frozen.resolve(leaf)

        def observe() -> Observation:
            log.clear()
            with observed_frozen.scope():
                value = observed_frozen.resolve(observed_leaf)
            return Observation(result=type(value).__name__, constructed=tuple(log), closed=())

        return Session(call=cycle, observe=observe)

    def direct_setup() -> Session:
        nodes = chain_types(CHAIN_DEPTH)

        def cycle() -> object:
            cache: dict[type[object], object] = {}
            for node in nodes:
                cache[node] = node()
            made = cache[nodes[-1]]
            cache.clear()
            return made

        def observe() -> Observation:
            log: list[str] = []
            cache: dict[type[object], object] = {}
            for node in nodes:
                log.append(node.__name__)
                cache[node] = node()
            made = cache[nodes[-1]]
            cache.clear()
            return Observation(result=type(made).__name__, constructed=tuple(log), closed=())

        return Session(call=cycle, observe=observe)

    return Workload(
        name='open_and_close_a_scope',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does one scope cost, from entry to teardown?',
            work=f'Enter a scope, construct {CHAIN_DEPTH} scoped objects through one resolution, and leave it.',
            included='Frame creation, one resolution per node, the scoped cache, and the drain on exit.',
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Scoped. Every value is built once per scope and dropped on exit. No provider here registers a '
                'teardown, so the drain runs over an empty record list.'
            ),
            shape=f'A linear chain of {CHAIN_DEPTH} scoped providers; the leaf is resolved inside one scope.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            noise=NoiseClass.HIGH,
            valid=('A regression alarm on the scope path, against its own measured band.',),
            invalid=(
                'Not an absolute figure worth publishing: the baseline measured this the noisiest case in the '
                'suite, 7.0% run to run and 13.8% under the paired protocol, and both mitigations tried on it '
                'were rejected on their own data.',
                'Not the cost of teardown: no provider here has one to run.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _call_through_an_inject_wrapper() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(Repo).freeze()

        @frozen.inject
        def handler(repo: Repo = injected(Repo)) -> int:
            return repo.count()

        _ = handler()
        return Session(
            call=handler,
            observe=lambda: Observation(result=str(handler()), constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Repo()

        def handler(repo: Repo = held) -> int:
            return repo.count()

        return Session(
            call=handler,
            observe=lambda: Observation(result=str(handler()), constructed=(), closed=()),
        )

    return Workload(
        name='call_through_an_inject_wrapper',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does calling a function whose dependency depin supplies cost?',
            work='Call a one-parameter function that returns a value read off its dependency.',
            included='The wrapper dispatch, the resolution of the one injected parameter, and the call itself.',
            excluded='Declaration, freeze, wrapping, and the construction of the dependency, all done in setup.',
            semantics='Singleton dependency, cached before the first timed call.',
            shape='One provider with no dependencies, injected into one function.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            noise=NoiseClass.MEDIUM,
            valid=('The dispatch overhead of `@inject`, as the ratio to calling the same function directly.',),
            invalid=(
                'Not a per-parameter cost: one parameter is injected, and the wrapper is entered once either way.',
                'Not an async call, which goes through a different wrapper.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _resolve_an_async_singleton() -> Workload:
    def depin_setup() -> Session:
        async def make() -> Pool:
            return Pool()

        frozen = Container().bind(make, provides=Pool, scope=Scope.SINGLETON).freeze()
        loop = asyncio.new_event_loop()
        _ = loop.run_until_complete(frozen.aresolve(Pool))
        return Session(
            call=lambda: loop.run_until_complete(frozen.aresolve(Pool)),
            observe=lambda: Observation(
                result=type(loop.run_until_complete(frozen.aresolve(Pool))).__name__,
                constructed=(),
                closed=(),
            ),
            close=loop.close,
        )

    def direct_setup() -> Session:
        held = Pool()
        loop = asyncio.new_event_loop()
        _ = loop.run_until_complete(_ready(held))
        return Session(
            call=lambda: loop.run_until_complete(_ready(held)),
            observe=lambda: Observation(
                result=type(loop.run_until_complete(_ready(held))).__name__,
                constructed=(),
                closed=(),
            ),
            close=loop.close,
        )

    return Workload(
        name='resolve_an_async_singleton',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does depin add to driving one coroutine through an event loop?',
            work='Await a cached singleton whose provider is a coroutine function, and return it.',
            included=(
                'The event loop boundary. The baseline measured 19.614 µs for this against 16.093 µs for the '
                'bare coroutine, so 82% of the timed region is asyncio.'
            ),
            excluded='Loop creation, declaration, freeze, and the construction of the singleton, all done in setup.',
            semantics='Singleton. The cache is warm before the first timed call, so nothing is constructed.',
            shape='One provider with no dependencies, bound from a coroutine function.',
            concurrency='Single-threaded; one event loop for the whole measurement, driven by run_until_complete.',
            metric=Metric.LATENCY,
            unit='seconds per operation',
            noise=NoiseClass.MEDIUM,
            valid=(
                'The difference from the direct implementation, which drives a bare coroutine through the same '
                'loop boundary. That difference — about 3.5 µs when the baseline measured it — is depin.',
            ),
            invalid=(
                'Not the cost of an async resolution: most of the timed region is asyncio, which is why the '
                'direct implementation is the same loop call around a coroutine that does nothing.',
                'Not the cost of constructing an async provider, which happens once, in setup.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


WORKLOADS: tuple[Workload, ...] = (
    _resolve_cached_singleton(),
    _resolve_cached_singleton_through_an_alias(),
    _resolve_singleton_through_a_two_deep_decoration_chain(),
    _resolve_a_collection(10),
    _resolve_a_collection(100),
    _resolve_a_transient_chain(),
    _open_and_close_a_scope(),
    _call_through_an_inject_wrapper(),
    _resolve_an_async_singleton(),
)
