"""Collection, transient, and generic-key workload definitions."""

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.graphs import build_chain, chain_types
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation, recording_chain
from depin import Container, Scope

from .core import (
    CHAIN_DEPTH,
    Boxed,
    Element,
    Repo,
    Wired,
    _boxed,
    _build_collection,
    _collection_result,
    _construct_chain,
    _construct_recorded,
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
