"""Tier 1: one isolated operation per workload, on the smallest graph that isolates it.

Also carries `Session` and `implementation`, the shell every tier builds its
`Implementation` pair from. It lives here because tier 1 is where the pair is
smallest and the shape is easiest to read.
"""

import asyncio
import contextlib
from collections.abc import Callable, Generator, Iterator
from typing import Protocol

from benchmarks.contracts import (
    Claim,
    Metric,
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


class Sole:
    """The single provider the override pair and the generic-key workload resolve.

    One provider rather than the hundred `resolve_cached_singleton` uses, because
    the three of them are read as differences from each other and a chain would
    add a setup cost none of the differences are about. The cached lookup is flat
    in graph size — the baseline measured it within 3% over 1 to 300 nodes — so
    the two families stay comparable anyway.
    """


class Substitute(Sole):
    """What the active override returns in place of the registered provider."""


class Indirect:
    """One level of indirection over a held object.

    The direct counterpart of an active override: hand-wiring reaches the
    substitute through the holder that stands in for the override frame, so the
    baseline performs one more hop than `Wired` alone.
    """

    def __init__(self, inner: Wired) -> None:
        self.inner = inner


class Boxed[T]:
    """The generic origin `resolve_a_generic_key` resolves a parameterisation of.

    Spelled as a subscript rather than built through `types.GenericAlias`, because
    this key is fixed at authoring time and every checker reads `Boxed[Repo]` as a
    key without help. It holds its parameter rather than only declaring one, so
    the argument is inferred at every construction instead of being asserted at
    one.
    """

    def __init__(self, value: T) -> None:
        self.value = value


class Connection:
    """The resource `resolve_a_sync_resource_with_teardown` opens and drains."""


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


def _boxed() -> Boxed[Repo]:
    return Boxed(Repo())


def _sole() -> Sole:
    return Sole()


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
        def handler(repo: Repo = injected) -> int:
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


def _resolve_with_no_active_override() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(_sole).freeze()
        _ = frozen.resolve(Sole)
        return Session(
            call=lambda: frozen.resolve(Sole),
            observe=lambda: Observation(result=type(frozen.resolve(Sole)).__name__, constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Wired(Sole())
        return Session(
            call=lambda: held.value,
            observe=lambda: Observation(result=type(held.value).__name__, constructed=(), closed=()),
        )

    return Workload(
        name='resolve_with_no_active_override',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does the override check cost on a resolution nothing has overridden?',
            work='Return a cached singleton from a one-provider graph with the override stack empty.',
            included='The key lookup, the ContextVar read that finds no override, and the cache read.',
            excluded='Declaration, freeze, and the construction of the singleton, all done in setup.',
            semantics='Singleton. The cache is warm before the first timed call, so nothing is constructed.',
            shape='One provider with no dependencies; its key is resolved.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The production case: `overrides.active` is on every resolution, and in a deployed process it '
                'always takes the empty branch.',
                'The control the override and generic-key workloads are read against. All three resolve one '
                'provider, so the difference between them is the feature and not the graph.',
            ),
            invalid=(
                'Not an isolated cost for the ContextVar read: the whole resolution is timed, and the read is '
                'a part of it.',
                'Not a different measurement from `resolve_cached_singleton` in kind — only in graph size, '
                'which the baseline measured flat within 3% over 1 to 300 nodes.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _resolve_through_an_active_override() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(_sole).freeze()
        stack = contextlib.ExitStack()
        _ = stack.enter_context(frozen.override(Sole, Substitute()))
        _ = frozen.resolve(Sole)
        return Session(
            call=lambda: frozen.resolve(Sole),
            observe=lambda: Observation(result=type(frozen.resolve(Sole)).__name__, constructed=(), closed=()),
            close=stack.close,
        )

    def direct_setup() -> Session:
        held = Indirect(Wired(Substitute()))
        return Session(
            call=lambda: held.inner.value,
            observe=lambda: Observation(result=type(held.inner.value).__name__, constructed=(), closed=()),
        )

    return Workload(
        name='resolve_through_an_active_override',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does a resolution cost while an override for that key is installed?',
            work='Return the replacement value for a key one active override substitutes.',
            included=(
                'The key lookup, the ContextVar read that finds the override, and the transient spec the '
                'override is wrapped in on every lookup.'
            ),
            excluded='Declaration, freeze, and entering the override, all done in setup.',
            semantics=(
                'The override is a value, not a factory, so nothing is constructed. The substituted spec is '
                'transient, so no cache is consulted and the registered singleton is never reached.'
            ),
            shape='One provider with no dependencies, with one override installed over its key.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'What using an override costs, read as the difference from `resolve_with_no_active_override`: '
                'the branch that fires against the branch that does not.',
                'The ratio to the direct implementation, which reaches a held object through one indirection.',
            ),
            invalid=(
                'Not a production figure. An override is a testing seam, and a deployed process installs none.',
                'Not the cost of installing or leaving an override, which happens once and is in setup.',
                'Not the cost of an override whose replacement is a factory, which is called per resolution.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _resolve_a_generic_key() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(_boxed).freeze()
        _ = frozen.resolve(Boxed[Repo])
        return Session(
            call=lambda: frozen.resolve(Boxed[Repo]),
            observe=lambda: Observation(result=type(frozen.resolve(Boxed[Repo])).__name__, constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Wired(Boxed(Repo()))
        return Session(
            call=lambda: held.value,
            observe=lambda: Observation(result=type(held.value).__name__, constructed=(), closed=()),
        )

    return Workload(
        name='resolve_a_generic_key',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does a parameterised generic key cost at resolution time?',
            work='Return a cached singleton bound under `Boxed[Repo]` rather than under a bare class.',
            included=(
                'The key lookup, which takes the `get_origin` branch of the key check because the key is not '
                'a class, then the override check and the cache read.'
            ),
            excluded='Declaration, freeze, and the construction of the singleton, all done in setup.',
            semantics='Singleton. The cache is warm before the first timed call, so nothing is constructed.',
            shape='One provider with no dependencies, keyed by a parameterised generic.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'What a generic key costs per resolution, read as the difference from '
                '`resolve_with_no_active_override`, which resolves one provider under a plain class key.',
            ),
            invalid=(
                'Not the freeze-time cost of a generic key, which `freeze_a_generic_key_chain_of_*` measures '
                'and which is a different code path with a different frequency.',
                'Not a statement about collections: `list[Element]` is also a generic key, but resolving one '
                'gathers members as well.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _construct_a_singleton_for_the_first_time() -> Workload:
    def recording(log: list[str]) -> Callable[[], Sole]:
        def provide() -> Sole:
            log.append(Sole.__name__)
            return Sole()

        return provide

    def depin_setup() -> Session:
        frozen = Container().bind(_sole).freeze()
        _ = frozen.resolve(Sole)

        def cold() -> object:
            frozen.reset()
            return frozen.resolve(Sole)

        log: list[str] = []
        observed = Container().bind(recording(log)).freeze()
        _ = observed.resolve(Sole)

        def observe() -> Observation:
            observed.reset()
            log.clear()
            value = observed.resolve(Sole)
            return Observation(result=type(value).__name__, constructed=tuple(log), closed=())

        return Session(call=cold, observe=observe)

    def direct_setup() -> Session:
        cache: dict[type[Sole], Sole] = {Sole: Sole()}

        def cold() -> object:
            cache.clear()
            cache[Sole] = Sole()
            return cache[Sole]

        def observe() -> Observation:
            cache.clear()
            log = [Sole.__name__]
            cache[Sole] = Sole()
            return Observation(result=type(cache[Sole]).__name__, constructed=tuple(log), closed=())

        return Session(call=cold, observe=observe)

    return Workload(
        name='construct_a_singleton_for_the_first_time',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does the first resolution of a singleton cost, before anything is cached?',
            work='Drop the singleton cache and resolve the key again, so the value is constructed.',
            included=(
                'The cache being dropped, the lookup, the construction, and the cache write. Dropping is '
                'inside the timed region because there is no other way to reach a cold cache repeatedly, and '
                'the direct implementation clears its own one-entry cache for the same reason.'
            ),
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Singleton. Every timed call constructs exactly one value, because the provider it drops has '
                'no dependencies and registers no teardown for the drop to run.'
            ),
            shape='One provider with no dependencies; its key is resolved from cold.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The cold path, read against `resolve_with_no_active_override`, which is the same lookup with '
                'the value already there.',
                'The ratio to the direct implementation, which clears and refills the same one-entry cache.',
            ),
            invalid=(
                'Not a startup figure for a real graph: one provider is constructed here, and a startup builds '
                'all of them in dependency order.',
                'Not the cost of `reset()` as an operation, which is measured here only over an empty teardown record.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _sync_resource() -> Callable[[], Iterator[Connection]]:
    def provide() -> Iterator[Connection]:
        yield Connection()

    return provide


def _recording_sync_resource(log: list[str]) -> Callable[[], Iterator[Connection]]:
    """`_sync_resource`, naming the resource in `log` as it opens and as it closes.

    A separate factory rather than a flag inside the provider, so the timed
    implementation carries no branch the observed one needs.
    """

    def provide() -> Iterator[Connection]:
        log.append(f'open {Connection.__name__}')
        yield Connection()
        log.append(f'close {Connection.__name__}')

    return provide


def _resolve_a_sync_resource_with_teardown() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(_sync_resource(), provides=Connection, scope=Scope.SCOPED).freeze()

        def cycle() -> object:
            with frozen.scope():
                return frozen.resolve(Connection)

        log: list[str] = []
        observed = Container().bind(_recording_sync_resource(log), provides=Connection, scope=Scope.SCOPED).freeze()

        def observe() -> Observation:
            log.clear()
            with observed.scope():
                value = observed.resolve(Connection)
            return Observation(
                result=type(value).__name__,
                constructed=tuple(event.removeprefix('open ') for event in log if event.startswith('open ')),
                closed=tuple(event.removeprefix('close ') for event in log if event.startswith('close ')),
            )

        return Session(call=cycle, observe=observe)

    def direct_setup() -> Session:
        @contextlib.contextmanager
        def hold() -> Generator[Connection]:
            yield Connection()

        def cycle() -> object:
            with hold() as connection:
                return connection

        def observe() -> Observation:
            log: list[str] = []

            @contextlib.contextmanager
            def recording() -> Generator[Connection]:
                log.append('open')
                yield Connection()
                log.append('close')

            with recording() as connection:
                value = connection
            return Observation(
                result=type(value).__name__,
                constructed=tuple(Connection.__name__ for event in log if event == 'open'),
                closed=tuple(Connection.__name__ for event in log if event == 'close'),
            )

        return Session(call=cycle, observe=observe)

    return Workload(
        name='resolve_a_sync_resource_with_teardown',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does one resource with a teardown cost, from open to drain?',
            work='Enter a scope, resolve one generator-backed resource, and leave the scope so it is closed.',
            included='Frame creation, one resolution, the generator entered, the teardown recorded, and the drain.',
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Scoped. The resource is constructed once per scope, its teardown registered on construction, '
                'and run when the scope closes.'
            ),
            shape='One scoped generator provider; the resource is resolved inside one scope.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'What teardown adds to a scope, read against `open_and_close_a_scope`, whose providers register none.',
                'The ratio to the direct implementation, a handwritten context manager doing the same work.',
            ),
            invalid=(
                'Not an async teardown, which runs on a different path and through an event loop.',
                'Not a per-resource cost transferable to a scope holding many: `scale_scope_teardown` is the '
                'curve for that.',
                'Not the teardown path after a failure, where the drain collects exceptions instead.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _call_through_an_inject_wrapper_with_explicit_arguments() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(Repo).freeze()

        @frozen.inject
        def handler(offset: int, repo: Repo = injected) -> int:
            return repo.count() + offset

        _ = handler(1)
        return Session(
            call=lambda: handler(1),
            observe=lambda: Observation(result=str(handler(1)), constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Repo()

        def handler(offset: int, repo: Repo = held) -> int:
            return repo.count() + offset

        return Session(
            call=lambda: handler(1),
            observe=lambda: Observation(result=str(handler(1)), constructed=(), closed=()),
        )

    return Workload(
        name='call_through_an_inject_wrapper_with_explicit_arguments',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does an argument the caller supplies add to an injected call?',
            work='Call a two-parameter function with one argument supplied and one injected.',
            included='The wrapper dispatch, the argument the caller passed, the resolution of the injected one.',
            excluded='Declaration, freeze, wrapping, and the construction of the dependency, all done in setup.',
            semantics='Singleton dependency, cached before the first timed call.',
            shape='One provider with no dependencies, injected into a function that also takes one argument.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'What a supplied argument costs the wrapper, read as the difference from '
                '`call_through_an_inject_wrapper`, which supplies none.',
                'The ratio to calling the same two-parameter function directly.',
            ),
            invalid=(
                'Not a per-argument cost: one argument is supplied, and the wrapper is entered once either way.',
                'Not an async call, which goes through a different wrapper.',
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
    _call_through_an_inject_wrapper_with_explicit_arguments(),
    _resolve_an_async_singleton(),
    _resolve_with_no_active_override(),
    _resolve_through_an_active_override(),
    _resolve_a_generic_key(),
    _construct_a_singleton_for_the_first_time(),
    _resolve_a_sync_resource_with_teardown(),
)
