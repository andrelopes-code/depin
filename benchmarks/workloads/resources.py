"""Memory: what a per-request path allocates, and what a container holds once it returns.

The rest of the inventory is timed. These workloads are counted instead, under
`benchmarks.harness.memory`, which reads `tracemalloc` in a process started with
`PYTHONHASHSEED=0`. A count carries no dispersion, so a single reading is a gate:
one extra object allocated per resolution shows up on the first run, where the
latency band would have hidden it.

The allocation half does not restate the paths tier 1 and tier 2 already declare.
It reuses their `Implementation` pairs by name, so the callable counted here is
byte-for-byte the callable timed there, and the equivalence their `Observation`
already proves is inherited rather than re-derived. Only the claim differs,
because only the question does.

The retention half has no counterpart in the timed tiers: it measures what is
still reachable after an operation returns, which is a property of the container
rather than of a call.
"""

import contextlib

from benchmarks.contracts import (
    Claim,
    Metric,
    Observation,
    Tier,
    Workload,
)
from benchmarks.graphs import build_chain, chain_types
from benchmarks.harness import HarnessError
from benchmarks.workloads.component import LARGE_GRAPH
from benchmarks.workloads.component import WORKLOADS as COMPONENT_WORKLOADS
from benchmarks.workloads.micro import CHAIN_DEPTH, HOT_GRAPH
from benchmarks.workloads.micro import WORKLOADS as MICRO_WORKLOADS
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation, recording_chain
from depin import ProviderKey, Scope

ALLOCATION_UNIT = 'tracemalloc blocks and bytes per operation'

RETENTION_UNIT = 'bytes reachable after the operation returns'

WARM_SETUP = (
    'The first invocation, which `memory.allocations_per_operation` performs before tracing starts, so a '
    'lazily built cache or an import performed on first use is charged to the setup.'
)

BLOCKS_ARE_NOT_BYTES = (
    'A block count is not a byte cost and not a latency. One block is one allocation the interpreter made; '
    'its size is reported separately, and how long it took follows from neither.'
)

NOT_RESIDENT_MEMORY = (
    'Not resident memory: `tracemalloc` counts Python-level blocks, and sees nothing the allocator, the '
    'interpreter, or a C extension holds outside them.'
)

SNAPSHOT_FLOOR = (
    'Not an absolute figure. `tracemalloc` counts what its own snapshots allocate, which on this host is a '
    'constant 8 blocks and 832 bytes for an allocation reading and roughly 670 bytes for a retention one. The '
    'floor is identical on both sides of a comparison and cancels there; it does not cancel in a number quoted '
    'on its own.'
)

RETENTION_IS_NOT_A_PEAK = (
    'Not a high-water mark: the reading is what survives a collection while the built object is still '
    'referenced, and constructing it can allocate far more than that on the way.'
)

NO_BASELINE_HOLDING = (
    'There is no direct baseline: hand-wiring declares no graph, so nothing in it holds a validated plan to '
    'compare the frozen container against.'
)

_SOURCES: dict[str, Workload] = {workload.name: workload for workload in (*MICRO_WORKLOADS, *COMPONENT_WORKLOADS)}


def key_name(key: ProviderKey) -> str:
    return key.__name__ if isinstance(key, type) else str(key)


def _source(name: str) -> Workload:
    """The timed workload whose implementations are counted here instead of timed.

    Raises:
        HarnessError: no workload of that name is declared, which means an
            allocation claim names a path that is no longer measured.
    """
    if name not in _SOURCES:
        raise HarnessError(f'{name}: no declared workload of that name to count allocations for')
    return _SOURCES[name]


def _allocation_claim(
    *,
    question: str,
    work: str,
    included: str,
    semantics: str,
    shape: str,
    valid: tuple[str, ...],
    invalid: tuple[str, ...],
) -> Claim:
    return Claim(
        question=question,
        work=work,
        included=included,
        excluded=f'Declaration, freeze, and every construction the setup performs. {WARM_SETUP}',
        semantics=semantics,
        shape=shape,
        concurrency=CONCURRENCY,
        metric=Metric.ALLOCATIONS,
        unit=ALLOCATION_UNIT,
        valid=valid,
        invalid=(BLOCKS_ARE_NOT_BYTES, NOT_RESIDENT_MEMORY, SNAPSHOT_FLOOR, *invalid),
    )


def _retention_claim(
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
        concurrency=CONCURRENCY,
        metric=Metric.RETAINED,
        unit=RETENTION_UNIT,
        valid=valid,
        invalid=(RETENTION_IS_NOT_A_PEAK, NOT_RESIDENT_MEMORY, SNAPSHOT_FLOOR, *invalid),
    )


def _counted(name: str, timed: str, claim: Claim) -> Workload:
    """`name`, counting the implementations the workload `timed` is measured through.

    The subject and the baseline are the same objects the latency tier declares, so
    the two metrics cannot drift onto different code, and the pair's equivalence is
    the one `tests/integration/test_workload_equivalence.py` already proves there.
    """
    source = _source(timed)
    return Workload(name=name, tier=source.tier, claim=claim, subject=source.subject, baseline=source.baseline)


def _allocations_of_a_cached_singleton_resolution() -> Workload:
    return _counted(
        'allocations_of_a_cached_singleton_resolution',
        'resolve_cached_singleton',
        _allocation_claim(
            question='What does one resolution allocate once the value is already built?',
            work='Return the singleton at the deep end of a 100-provider chain, and count what that allocates.',
            included='The key lookup, the override check, and the cache read.',
            semantics='Singleton. The cache is warm before the counted call, so nothing is constructed.',
            shape=f'A linear chain of {HOT_GRAPH} providers; the leaf is resolved.',
            valid=(
                'A gate on the resolution path: an extra object built per resolution changes this by a whole '
                'block, which no latency band on this workload could resolve.',
                'The excess over the direct implementation, which is an attribute read and allocates nothing.',
            ),
            invalid=(
                'Not the allocation cost of building the object; nothing is constructed in the counted region.',
                'Not a function of graph size, for the reason `resolve_cached_singleton` states about latency.',
            ),
        ),
    )


def _allocations_of_a_transient_chain() -> Workload:
    return _counted(
        'allocations_of_a_transient_chain',
        'resolve_a_transient_chain',
        _allocation_claim(
            question='What does depin allocate on top of the objects a transient chain constructs?',
            work=f'Construct {CHAIN_DEPTH} objects, each depending on the one before it, and count what that '
            'allocates.',
            included='One resolution per node: lookup, override check, parameter resolution, and construction.',
            semantics='Transient. Nothing is cached, so every counted call constructs the whole chain.',
            shape=f'A linear chain of {CHAIN_DEPTH} transient providers; the leaf is resolved.',
            valid=(
                'The per-node allocation overhead, as the excess over the direct implementation, which '
                'constructs the same objects and allocates the argument frames for nothing else.',
            ),
            invalid=(
                'Not divisible into a per-node figure by inspection: the resolution of the first node holds the '
                'whole recursion, and the count is the total.',
                'Not applicable to singletons, which pay this once rather than per resolution.',
            ),
        ),
    )


def _allocations_of_a_scope_cycle() -> Workload:
    return _counted(
        'allocations_of_a_scope_cycle',
        'open_and_close_a_scope',
        _allocation_claim(
            question='What does one scope allocate, from entry through teardown?',
            work=f'Enter a scope, construct {CHAIN_DEPTH} scoped objects through one resolution, leave it, and '
            'count what that allocates.',
            included='Frame creation, one resolution per node, the scoped cache, and the drain on exit.',
            semantics=(
                'Scoped. Every value is built once per scope and dropped on exit. No provider here registers a '
                'teardown, so the drain runs over an empty record list.'
            ),
            shape=f'A linear chain of {CHAIN_DEPTH} scoped providers; the leaf is resolved inside one scope.',
            valid=(
                'A gate on the scope path that the latency workload cannot provide: the same operation was '
                'measured the noisiest in the suite, and this reading carries no dispersion at all.',
                'The fixed cost of the frame, as the excess over the direct implementation, which uses a plain '
                'dictionary for the same cache.',
            ),
            invalid=(
                'Not the allocation cost of teardown: no provider here has one to run.',
                'Not what an open scope holds: everything counted here is released on exit, which is what '
                '`retained_by_an_open_scope_of_20` measures instead.',
            ),
        ),
    )


def _allocations_of_an_inject_call() -> Workload:
    return _counted(
        'allocations_of_an_inject_call',
        'call_through_an_inject_wrapper',
        _allocation_claim(
            question='What does calling a function whose dependency depin supplies allocate?',
            work='Call a one-parameter function that returns a value read off its dependency, and count what '
            'that allocates.',
            included='The wrapper dispatch, the resolution of the one injected parameter, and the call itself.',
            semantics='Singleton dependency, cached before the counted call.',
            shape='One provider with no dependencies, injected into one function.',
            valid=(
                'The per-call allocation the wrapper adds, as the excess over calling the same function with the '
                'dependency in default-value position.',
            ),
            invalid=(
                'Not a per-parameter figure: one parameter is injected, and the wrapper is entered once either way.',
                'Not an async call, which goes through a different wrapper and an event loop.',
            ),
        ),
    )


def _allocations_of_a_request_shaped_scope() -> Workload:
    return _counted(
        'allocations_of_a_request_shaped_scope',
        'open_a_request_shaped_scope',
        _allocation_claim(
            question='What does one request allocate in an integration that opens a scope, seeds it, and resolves?',
            work='Open a scope, seed one value into it, construct two scoped objects, leave the scope, and count '
            'what that allocates.',
            included='Frame creation, the seed, two resolutions with their constructions, and the drain on exit.',
            semantics=(
                'Scoped. Both values are built once per scope and dropped on exit. The seeded token is provided '
                'into the frame rather than bound to a provider.'
            ),
            shape='One seeded token and two scoped providers, one of which depends on the other.',
            valid=(
                'The per-request allocation budget of the scope shape every integration runs.',
                'The excess over constructing the same two objects into a per-request map by hand.',
            ),
            invalid=(
                'Not an end-to-end request figure: no framework, routing, or transport is in the counted region.',
                'Not the cost of teardown: neither provider here registers one.',
            ),
        ),
    )


def _retained_by_a_frozen_container(size: int) -> Workload:
    def setup() -> Session:
        container, _ = build_chain(size)
        _ = container.freeze()

        def observe() -> Observation:
            view = container.freeze().graph()
            edges = sum(len(node.dependencies) for node in view.nodes)
            return Observation(result=f'{len(view.nodes)} nodes, {edges} edges', constructed=(), closed=())

        return Session(call=container.freeze, observe=observe)

    return Workload(
        name=f'retained_by_a_frozen_container_of_{size}',
        tier=Tier.COMPONENT,
        claim=_retention_claim(
            question='How much memory does a frozen container hold for a graph of this size?',
            work=f'Freeze a declared chain of {size} providers and hold the frozen container.',
            included='Everything `freeze()` allocates and the frozen container keeps: the canonical keys, the '
            'provider specs, the resolution plan, and the topological order.',
            excluded=(
                'The declarations themselves. The node classes, the provider callables, and the unfrozen '
                'container are all built in setup, before tracing starts, so the reading is what validation '
                'adds on top of code the user wrote anyway.'
            ),
            semantics='Startup. Freeze constructs no dependency and caches no value; it returns a frozen container.',
            shape=f'A linear chain of {size} providers, each depending on the one before it.',
            valid=(
                'The resident cost of declaring a graph of this size, per provider once divided by the count.',
                'The growth class of that cost, read against the other size this family declares.',
            ),
            invalid=(
                NO_BASELINE_HOLDING,
                'Not what a running application holds: no singleton has been constructed, which is what '
                f'`retained_by_a_warm_singleton_cache_of_{LARGE_GRAPH}` measures.',
            ),
        ),
        subject=implementation('depin', setup),
    )


def _retained_by_a_warm_singleton_cache() -> Workload:
    def depin_setup() -> Session:
        container, _ = build_chain(LARGE_GRAPH)
        frozen = container.freeze()
        _ = frozen.warmup()
        frozen.reset()

        def build() -> object:
            _ = frozen.warmup()
            return frozen

        def observe() -> Observation:
            frozen.reset()
            built = tuple(key_name(node.key) for node in frozen.warmup().constructed)
            return Observation(result=f'{len(built)} constructed', constructed=built, closed=())

        return Session(call=build, observe=observe)

    def direct_setup() -> Session:
        nodes = chain_types(LARGE_GRAPH)
        cache: dict[type[object], object] = {}
        for node in nodes:
            cache[node] = node()
        cache.clear()

        def build() -> object:
            for node in nodes:
                cache[node] = node()
            return cache

        def observe() -> Observation:
            cache.clear()
            for node in nodes:
                cache[node] = node()
            built = tuple(node.__name__ for node in cache)
            return Observation(result=f'{len(built)} constructed', constructed=built, closed=())

        return Session(call=build, observe=observe)

    return Workload(
        name=f'retained_by_a_warm_singleton_cache_of_{LARGE_GRAPH}',
        tier=Tier.COMPONENT,
        claim=_retention_claim(
            question='How much does the singleton cache hold once every provider has been constructed?',
            work=f'Warm a cold container of {LARGE_GRAPH} singleton providers and hold it.',
            included='The constructed singletons and the cache entries pointing at them.',
            excluded=(
                'The container, its plan, and one earlier warmup, all done in setup — the container is reset '
                'rather than rebuilt, so the reading is the cache the second warmup fills. The direct '
                'implementation fills and clears its dictionary in setup for the same reason.'
            ),
            semantics=(
                'Singleton. Warmup constructs in topological order, so every provider finds its dependency '
                'already cached and none is built twice. Nothing is dropped until the container is reset.'
            ),
            shape=f'A linear chain of {LARGE_GRAPH} singleton providers.',
            valid=(
                'The per-singleton bookkeeping depin holds, as the excess over the direct implementation, which '
                'holds the same objects in a plain dictionary.',
                'The steady-state footprint of an application of this size, once the plan is added.',
            ),
            invalid=(
                'Not the allocation cost of warmup: what construction discarded on the way is collected before '
                'the reading is taken.',
                'Not the footprint of the objects themselves in a real application, whose values carry state '
                'these empty node classes do not.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _retained_by_an_open_scope() -> Workload:
    def depin_setup() -> Session:
        container, leaf = build_chain(CHAIN_DEPTH, scope=Scope.SCOPED)
        frozen = container.freeze()
        with frozen.scope():
            _ = frozen.resolve(leaf)
        stack = contextlib.ExitStack()

        def build() -> object:
            frame = stack.enter_context(frozen.scope())
            return frame, frozen.resolve(leaf)

        def observe() -> Observation:
            log: list[str] = []
            declared, observed_leaf = recording_chain(CHAIN_DEPTH, Scope.SCOPED, log)
            observed = declared.freeze()
            with observed.scope():
                value = observed.resolve(observed_leaf)
            return Observation(result=type(value).__name__, constructed=tuple(log), closed=())

        return Session(call=build, observe=observe, close=stack.close)

    def direct_setup() -> Session:
        nodes = chain_types(CHAIN_DEPTH)
        held: list[dict[type[object], object]] = []

        def build() -> object:
            cache: dict[type[object], object] = {}
            for node in nodes:
                cache[node] = node()
            held.append(cache)
            return cache, cache[nodes[-1]]

        def observe() -> Observation:
            cache: dict[type[object], object] = {}
            for node in nodes:
                cache[node] = node()
            return Observation(
                result=type(cache[nodes[-1]]).__name__,
                constructed=tuple(node.__name__ for node in cache),
                closed=(),
            )

        return Session(call=build, observe=observe, close=held.clear)

    return Workload(
        name=f'retained_by_an_open_scope_of_{CHAIN_DEPTH}',
        tier=Tier.ISOLATED,
        claim=_retention_claim(
            question='How much does a scope hold while it is open?',
            work=f'Enter a scope, construct {CHAIN_DEPTH} scoped objects through one resolution, and leave the '
            'scope open.',
            included='The scope frame, its cache, its teardown record list, and the scoped values themselves.',
            excluded='Declaration, freeze, and one earlier scope cycle, all done in setup.',
            semantics=(
                'Scoped. The values live as long as the frame, which the measurement deliberately does not '
                'close; the harness releases it afterwards, through the close hook the preparation returns.'
            ),
            shape=f'A linear chain of {CHAIN_DEPTH} scoped providers; the leaf is resolved inside one open scope.',
            valid=(
                'The memory one concurrent request holds, and therefore what a given concurrency level costs.',
                'The frame overhead, as the excess over the direct implementation, which holds the same objects '
                'in a per-request dictionary.',
            ),
            invalid=(
                'Not what a request costs to serve: nothing here is allocated and released, which is what '
                '`allocations_of_a_scope_cycle` counts.',
                'Not additive across nested scopes: a scoped value built in an outer scope is reused rather '
                'than rebuilt, so a nested frame holds less than this.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


WORKLOADS: tuple[Workload, ...] = (
    _allocations_of_a_cached_singleton_resolution(),
    _allocations_of_a_transient_chain(),
    _allocations_of_a_scope_cycle(),
    _allocations_of_an_inject_call(),
    _allocations_of_a_request_shaped_scope(),
    _retained_by_a_frozen_container(HOT_GRAPH),
    _retained_by_a_frozen_container(LARGE_GRAPH),
    _retained_by_a_warm_singleton_cache(),
    _retained_by_an_open_scope(),
)
