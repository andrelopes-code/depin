"""Tier 2: representative graphs, the startup path, the diagnostics, and the error paths.

The error paths are new here. The baseline found both unrepaired algorithmic
costs on them — a cubic failing `freeze()` and an exponential missing-key walk —
and found no benchmark covering either.
"""

from collections.abc import Callable
from typing import Annotated

from benchmarks.contracts import (
    Claim,
    Metric,
    Observation,
    Tier,
    Workload,
)
from benchmarks.graphs import (
    Unbound,
    build_chain,
    build_chain_missing_a_provider,
    build_decorated_chain,
    build_generic_chain,
    build_layered_dag,
    chain_types,
)
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation
from depin import Container, ProviderKey, Scope, Token, WarmupReport
from depin.errors import MissingProviderError

LARGE_GRAPH = 1000
"""The size the diagnostics and the warmup have always used, and the largest the suite declares."""

LAYERED_GRAPH = 500
"""The layered DAG the elision guard is exercised over.

Chosen so its rendered tree — 998 lines — is the size `explain_a_deep_chain`
renders, which makes the two readable against each other. The chain elides
nothing; this shape elides 498 subtrees.
"""

FAILING_FREEZE_SIZES = (50, 100)
"""The sizes the failing-freeze workload declares.

The baseline measured the pre-repair walk at 9 ms, 32 ms, 193 ms and 1380 ms over
50, 100, 200 and 400 nodes. The two smallest keep the workload well inside a
second even against the cubic implementation.
"""

UNBOUND_EXPLAIN_SIZES = (16, 20)
"""The sizes the missing-key workload declares.

The baseline measured the pre-repair walk at 12 ms, 28 ms, 70 ms, 186 ms and
503 ms over 16, 18, 20, 22 and 24 nodes, the count of simple paths being
Fibonacci in the size. Sixteen and twenty stay well inside a second.
"""

NO_BASELINE_VALIDATION = (
    'There is no direct baseline: hand-wiring declares no graph, so it has no validation step to compare against.'
)

NO_BASELINE_DIAGNOSTIC = (
    'There is no direct baseline: hand-wiring declares no graph, so there is nothing for it to describe.'
)

REQUEST = Token[str]('request')

INCOMING = 'r-1'


class DatabaseSession:
    """A per-request value built from the seeded token."""

    def __init__(self, incoming: Annotated[str, REQUEST]) -> None:
        self.incoming = incoming


class RequestHandler:
    """The per-request consumer, reached by one resolution."""

    def __init__(self, session: DatabaseSession, incoming: Annotated[str, REQUEST]) -> None:
        self.session = session
        self.incoming = incoming


def _key_name(key: ProviderKey) -> str:
    return key.__name__ if isinstance(key, type) else str(key)


def _plan_size(container: Container) -> str:
    return f'{len(container.freeze().graph().nodes)} providers'


def _tree_shape(tree: str) -> str:
    return f'lines={len(tree.splitlines())} elided={tree.count("(shown above)")}'


def _request_observation(handler: RequestHandler) -> Observation:
    return Observation(
        result=type(handler).__name__,
        constructed=(type(handler.session).__name__, type(handler).__name__),
        closed=(),
    )


def _freeze_claim(*, work: str, shape: str, valid: tuple[str, ...], invalid: tuple[str, ...]) -> Claim:
    return Claim(
        question='What does validating a declared graph cost at freeze time?',
        work=work,
        included=(
            'Key canonicalisation, the duplicate and missing checks, the decoration fold, the topological '
            'order, and the captive-dependency check.'
        ),
        excluded='Declaration of the providers, done in setup, and construction, which freeze never performs.',
        semantics='Startup. Freeze constructs nothing and caches nothing; it returns a frozen container.',
        shape=shape,
        concurrency=CONCURRENCY,
        metric=Metric.LATENCY,
        unit='seconds per operation',
        valid=valid,
        invalid=(NO_BASELINE_VALIDATION, *invalid),
    )


def _diagnostic_claim(
    *,
    question: str,
    work: str,
    shape: str,
    valid: tuple[str, ...],
    invalid: tuple[str, ...],
) -> Claim:
    return Claim(
        question=question,
        work=work,
        included='The walk over the validated plan and the string it builds.',
        excluded='Declaration and freeze, both done in setup.',
        semantics='Read-only over a frozen container. Nothing is constructed, cached, or torn down.',
        shape=shape,
        concurrency=CONCURRENCY,
        metric=Metric.LATENCY,
        unit='seconds per operation',
        valid=valid,
        invalid=(NO_BASELINE_DIAGNOSTIC, *invalid),
    )


def _freeze_workload(name: str, build: Callable[[], Container], claim: Claim) -> Workload:
    def setup() -> Session:
        container = build()
        return Session(
            call=container.freeze,
            observe=lambda: Observation(result=_plan_size(container), constructed=(), closed=()),
        )

    return Workload(name=name, tier=Tier.COMPONENT, claim=claim, subject=implementation('depin', setup))


def _explain_workload(name: str, build: Callable[[], tuple[Container, ProviderKey]], claim: Claim) -> Workload:
    def setup() -> Session:
        container, key = build()
        frozen = container.freeze()
        return Session(
            call=lambda: frozen.explain(key),
            observe=lambda: Observation(result=_tree_shape(frozen.explain(key)), constructed=(), closed=()),
        )

    return Workload(name=name, tier=Tier.COMPONENT, claim=claim, subject=implementation('depin', setup))


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


def _open_a_request_shaped_scope() -> Workload:
    def depin_setup() -> Session:
        frozen = (
            Container()
            .scope_value(REQUEST)
            .bind(DatabaseSession, scope=Scope.SCOPED)
            .bind(RequestHandler, scope=Scope.SCOPED)
            .freeze()
        )

        def run() -> object:
            with frozen.scope() as frame:
                frame.provide(REQUEST, INCOMING)
                return frozen.resolve(RequestHandler)

        def observe() -> Observation:
            with frozen.scope() as frame:
                frame.provide(REQUEST, INCOMING)
                return _request_observation(frozen.resolve(RequestHandler))

        return Session(call=run, observe=observe)

    def direct_setup() -> Session:
        def run() -> RequestHandler:
            seeded: dict[str, str] = {'request': INCOMING}
            built: dict[type[object], object] = {}
            session = DatabaseSession(seeded['request'])
            built[DatabaseSession] = session
            handler = RequestHandler(session, seeded['request'])
            built[RequestHandler] = handler
            built.clear()
            seeded.clear()
            return handler

        return Session(call=run, observe=lambda: _request_observation(run()))

    return Workload(
        name='open_a_request_shaped_scope',
        tier=Tier.COMPONENT,
        claim=Claim(
            question='What does one request cost an integration that opens a scope, seeds it, and resolves?',
            work='Open a scope, seed one value into it, construct two scoped objects, and leave the scope.',
            included='Frame creation, the seed, two resolutions with their constructions, and the drain on exit.',
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Scoped. Both values are built once per scope and dropped on exit. The seeded token is provided '
                'into the frame rather than bound to a provider.'
            ),
            shape='One seeded token and two scoped providers, one of which depends on the other.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The per-request overhead of the scope shape every integration runs.',
                'The ratio to constructing the same two objects into a per-request map by hand.',
            ),
            invalid=(
                'Not an end-to-end request cost: no framework, routing, or transport is in the timed region.',
                'Not the cost of teardown: neither provider here registers one.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _build_the_graph_view() -> Workload:
    def setup() -> Session:
        container, _ = build_chain(LARGE_GRAPH)
        frozen = container.freeze()

        def observe() -> Observation:
            view = frozen.graph()
            edges = sum(len(node.dependencies) for node in view.nodes)
            return Observation(result=f'{len(view.nodes)} nodes, {edges} edges', constructed=(), closed=())

        return Session(call=frozen.graph, observe=observe)

    return Workload(
        name='build_the_graph_view',
        tier=Tier.COMPONENT,
        claim=_diagnostic_claim(
            question='What does the public graph view over a validated plan cost?',
            work=f'Build the node and edge view of a {LARGE_GRAPH}-provider graph.',
            shape=f'A linear chain of {LARGE_GRAPH} providers.',
            valid=('The diagnostic cost of the graph view, published apart from resolution.',),
            invalid=('Not a cost any resolution pays: the view is built only when it is asked for.',),
        ),
        subject=implementation('depin', setup),
    )


def _explain_a_deep_chain() -> Workload:
    return _explain_workload(
        'explain_a_deep_chain',
        lambda: build_chain(LARGE_GRAPH),
        _diagnostic_claim(
            question='What does rendering a resolution tree cost over a chain nothing is reached twice in?',
            work=f'Render the resolution tree below the leaf of a {LARGE_GRAPH}-provider chain.',
            shape=f'A linear chain of {LARGE_GRAPH} providers, so every node is reached exactly once.',
            valid=('The cost of rendering a tree with one line per node and no repeated subtree.',),
            invalid=(
                'Not evidence about the subtree-elision guard: the baseline counted 0 occurrences of '
                '"(shown above)" over this shape, so removing the guard could not change this result. '
                '`explain_a_layered_dag` is the workload that covers it.',
            ),
        ),
    )


def _explain_a_deep_chain_with_every_node_decorated() -> Workload:
    return _explain_workload(
        'explain_a_deep_chain_with_every_node_decorated',
        lambda: build_decorated_chain(LARGE_GRAPH),
        _diagnostic_claim(
            question='What does a decorator over every node add to rendering a resolution tree?',
            work=f'Render the resolution tree below the leaf of a decorated {LARGE_GRAPH}-provider chain.',
            shape='`explain_a_deep_chain`, with one pass-through decorator over every node.',
            valid=('The cost of rendering a decoration chain, read against `explain_a_deep_chain`.',),
            invalid=('Not evidence about the elision guard: this shape reaches no node twice either.',),
        ),
    )


def _explain_a_layered_dag() -> Workload:
    return _explain_workload(
        'explain_a_layered_dag',
        lambda: build_layered_dag(LAYERED_GRAPH),
        _diagnostic_claim(
            question='What does rendering a resolution tree cost when subtrees repeat?',
            work=f'Render the resolution tree below the deepest node of a {LAYERED_GRAPH}-node layered DAG.',
            shape=(
                f'{LAYERED_GRAPH} providers where node i depends on both i-1 and i-2, so all but two nodes are '
                'reached twice and the second visit is elided.'
            ),
            valid=(
                'The cost of rendering a tree whose subtrees repeat, and the only coverage the subtree-elision '
                'guard has: this shape elides 498 subtrees where `explain_a_deep_chain` elides none, so '
                'removing the guard is detectable here and nowhere else.',
            ),
            invalid=(
                'Not comparable with `explain_a_deep_chain` as a size-for-size pair: the two render a similar '
                'number of lines from a different number of nodes.',
            ),
        ),
    )


def _export_a_large_graph_as_dot() -> Workload:
    def setup() -> Session:
        container, _ = build_chain(LARGE_GRAPH)
        graph = container.freeze().graph()
        return Session(
            call=graph.dot,
            observe=lambda: Observation(
                result=f'lines={len(graph.dot().splitlines())}',
                constructed=(),
                closed=(),
            ),
        )

    return Workload(
        name='export_a_large_graph_as_dot',
        tier=Tier.COMPONENT,
        claim=_diagnostic_claim(
            question='What does exporting a graph to Graphviz cost?',
            work=f'Render a {LARGE_GRAPH}-provider graph as a dot document.',
            shape=f'A linear chain of {LARGE_GRAPH} providers.',
            valid=('The export cost, and the quietest workload in the suite to gate against.',),
            invalid=('Not a cost any resolution pays: the export runs only when it is asked for.',),
        ),
        subject=implementation('depin', setup),
    )


def _freeze_a_chain_missing_a_provider(size: int) -> Workload:
    def setup() -> Session:
        container, _ = build_chain_missing_a_provider(size)

        def attempt() -> object:
            try:
                return container.freeze()
            except MissingProviderError as failure:
                return failure

        def observe() -> Observation:
            outcome = attempt()
            if not isinstance(outcome, MissingProviderError):
                return Observation(result='froze without raising', constructed=(), closed=())
            message = str(outcome)
            return Observation(
                result=f'{message.count(" -> ") + 1} chain steps',
                constructed=(),
                closed=(),
                error=type(outcome).__name__,
            )

        return Session(call=attempt, observe=observe)

    return Workload(
        name=f'freeze_a_chain_missing_a_provider_of_{size}',
        tier=Tier.COMPONENT,
        claim=Claim(
            question='What does rejecting a graph with an unsatisfied parameter cost?',
            work=(
                f'Freeze a chain of {size} providers whose deepest node requires an unbound key, and format the '
                'chain that reaches it.'
            ),
            included=(
                'Validation, the walk that finds the longest chain reaching the unsatisfied parameter, the scan '
                'over loaded modules that suggests candidate keys, the message it formats, and the `except` '
                'that keeps the timed callable from propagating.'
            ),
            excluded='Declaration of the providers, done in setup.',
            semantics='Startup, on the failing path. Nothing is constructed and no container is returned.',
            shape=f'A linear chain of {size} providers; the deepest requires a key nothing binds.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The cost of the actionable error path, which no benchmark covered before this one.',
                'The complexity class of the missing-provider walk, read across the two sizes: the baseline '
                'measured the pre-repair implementation cubic, at 9 ms and 32 ms over these sizes.',
            ),
            invalid=(
                NO_BASELINE_VALIDATION,
                'Not a cost a correct application pays: this path runs once, and only on a graph that is wrong.',
                'Not the cost of the missing-provider walk alone: the timed region also carries the validation '
                'of a chain of this size and a candidate scan measured at about 3 ms on the reference host. '
                'The difference between the two sizes is the part the walk moves.',
            ),
        ),
        subject=implementation('depin', setup),
    )


def _explain_an_unbound_key(size: int) -> Workload:
    def setup() -> Session:
        container, _ = build_layered_dag(size)
        frozen = container.freeze()
        return Session(
            call=lambda: frozen.explain(Unbound),
            observe=lambda: Observation(result=frozen.explain(Unbound), constructed=(), closed=()),
        )

    return Workload(
        name=f'explain_an_unbound_key_of_{size}',
        tier=Tier.COMPONENT,
        claim=Claim(
            question='What does explaining a key the graph does not bind cost?',
            work=(
                f'Ask a frozen {size}-node layered DAG to explain a key nothing binds, and return the line it produces.'
            ),
            included=(
                'The walk for the longest chain reaching the key, the scan over loaded modules that suggests '
                'candidate keys, and the line it formats when neither finds anything.'
            ),
            excluded='Declaration and freeze, both done in setup.',
            semantics='Read-only over a frozen container. Nothing is constructed, cached, or torn down.',
            shape=(
                f'{size} providers where node i depends on both i-1 and i-2, so the count of simple paths '
                'through the graph is Fibonacci in the size. No edge points at the key being explained.'
            ),
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The cost of the missing-key path, which no benchmark covered before this one.',
                'The complexity class of the walk, read across the two sizes: the baseline measured the '
                'pre-repair implementation exponential, at 12 ms and 70 ms over these sizes.',
            ),
            invalid=(
                NO_BASELINE_DIAGNOSTIC,
                'Not a cost that depends on the key being reachable: the walk runs for any key the graph does '
                'not bind, whether or not an edge points at it.',
                'Not the cost of the walk alone: the candidate scan over loaded modules is the larger part, '
                'measured at 2.97 ms of 3.41 ms at 16 nodes on the reference host. Read the two sizes against '
                'each other rather than either in isolation.',
            ),
        ),
        subject=implementation('depin', setup),
    )


WORKLOADS: tuple[Workload, ...] = (
    *(_freeze_a_chain(size) for size in (10, 100, LARGE_GRAPH)),
    *(_freeze_a_generic_key_chain(size) for size in (10, 100, LARGE_GRAPH)),
    *(_freeze_a_decorated_chain(size) for size in (10, 100, LARGE_GRAPH)),
    _warmup_a_cold_singleton_graph(),
    _open_a_request_shaped_scope(),
    _build_the_graph_view(),
    _explain_a_deep_chain(),
    _explain_a_deep_chain_with_every_node_decorated(),
    _explain_a_layered_dag(),
    _export_a_large_graph_as_dot(),
    *(_freeze_a_chain_missing_a_provider(size) for size in FAILING_FREEZE_SIZES),
    *(_explain_an_unbound_key(size) for size in UNBOUND_EXPLAIN_SIZES),
)
