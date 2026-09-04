"""Cached singleton workload definitions."""

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.graphs import build_chain, chain_types
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation

from .core import HOT_GRAPH, Aliased, Middle, Outer, Wired, _construct_chain, _decoration


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
