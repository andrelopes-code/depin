"""Component workloads for graph validation and singleton warmup."""

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.graphs import build_chain, build_decorated_chain, build_generic_chain, chain_types
from benchmarks.workloads.component.primitives import LARGE_GRAPH, _freeze_claim, _freeze_workload, _key_name
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation
from depin import WarmupReport


def _freeze_a_chain(size: int) -> Workload:
    return _freeze_workload(
        f'freeze_a_chain_of_{size}',
        lambda: build_chain(size)[0],
        _freeze_claim(
            work=f'Validate and order a linear chain of {size} providers.',
            shape=f'A linear chain of {size} providers, each depending on the one before it.',
            valid=(
                'The absolute startup cost of validating a graph of this size.',
                'The complexity class of validation, read across the three sizes.',
            ),
            invalid=('Not the cost of starting an application, which also constructs its singletons.',),
        ),
    )


def _freeze_a_generic_key_chain(size: int) -> Workload:
    return _freeze_workload(
        f'freeze_a_generic_key_chain_of_{size}',
        lambda: build_generic_chain(size)[0],
        _freeze_claim(
            work=f'Validate and order a chain of {size} providers whose every key is a parameterised generic.',
            shape=f'`freeze_a_chain_of_{size}`, with every key a parameterised generic instead of a bare class.',
            valid=(
                'The incremental cost of a parameterised key, read against `freeze_a_chain_of_'
                f'{size}` at the same size.',
            ),
            invalid=('Not a statement about resolution: the canonical-form check this exercises runs at freeze time.',),
        ),
    )


def _freeze_a_decorated_chain(size: int) -> Workload:
    return _freeze_workload(
        f'freeze_a_decorated_chain_of_{size}',
        lambda: build_decorated_chain(size)[0],
        _freeze_claim(
            work=f'Validate and order a chain of {size} providers with one decorator over every node.',
            shape=f'`freeze_a_chain_of_{size}`, with one pass-through decorator over every node.',
            valid=(f'The cost of the decoration fold, read against `freeze_a_chain_of_{size}` at the same size.',),
            invalid=(
                'Not the cost of resolving through a decorator, which '
                '`resolve_singleton_through_a_two_deep_decoration_chain` measures.',
            ),
        ),
    )


def _warmup_a_cold_singleton_graph() -> Workload:
    def depin_setup() -> Session:
        container, _ = build_chain(LARGE_GRAPH)
        frozen = container.freeze()

        def cycle() -> object:
            frozen.reset()
            return frozen.warmup()

        def observe() -> Observation:
            frozen.reset()
            report: WarmupReport = frozen.warmup()
            return Observation(
                result=f'{len(report.constructed)} constructed',
                constructed=tuple(_key_name(node.key) for node in report.constructed),
                closed=(),
            )

        return Session(call=cycle, observe=observe)

    def direct_setup() -> Session:
        nodes = chain_types(LARGE_GRAPH)
        cache: dict[type[object], object] = {}

        def cycle() -> object:
            cache.clear()
            for node in nodes:
                cache[node] = node()
            return cache

        def observe() -> Observation:
            built: list[str] = []
            cache.clear()
            for node in nodes:
                built.append(node.__name__)
                cache[node] = node()
            return Observation(result=f'{len(built)} constructed', constructed=tuple(built), closed=())

        return Session(call=cycle, observe=observe)

    return Workload(
        name='warmup_a_cold_singleton_graph',
        tier=Tier.COMPONENT,
        claim=Claim(
            question='What does building every singleton in a graph cost at startup?',
            work=f'Drop the singleton cache and construct all {LARGE_GRAPH} singletons in topological order.',
            included=(
                'The reset that re-cools the container, because a cold warmup needs one that has cached '
                'nothing, and one construction per provider.'
            ),
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Singleton. Warmup constructs in topological order, so every provider finds its dependency '
                'already cached and none is built twice.'
            ),
            shape=f'A linear chain of {LARGE_GRAPH} singleton providers.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The absolute startup cost of constructing a graph of this size.',
                'The ratio to constructing the same objects by hand, which is what warmup replaces.',
            ),
            invalid=(
                'Not the cost of a resolution: warmup pays the whole graph once, and the reset it needs is '
                'inside the timed region.',
                'Not the depth cost of a cold resolve: warmup constructs in order and never recurses, which is '
                'why it succeeds on a graph the baseline measured cold resolution failing beyond 332 nodes.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )
