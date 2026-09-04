"""Shared declarations and factories for component workloads."""

from collections.abc import Callable
from typing import Annotated

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation
from depin import Container, ProviderKey, Token

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


def key_name(key: ProviderKey) -> str:
    return key.__name__ if isinstance(key, type) else str(key)


def _plan_size(container: Container) -> str:
    return f'{len(container.freeze().graph().nodes)} providers'


def _tree_shape(tree: str) -> str:
    return f'lines={len(tree.splitlines())} elided={tree.count("(shown above)")}'


def request_observation(handler: RequestHandler) -> Observation:
    return Observation(
        result=type(handler).__name__,
        constructed=(type(handler.session).__name__, type(handler).__name__),
        closed=(),
    )


def freeze_claim(*, work: str, shape: str, valid: tuple[str, ...], invalid: tuple[str, ...]) -> Claim:
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


def diagnostic_claim(
    *, question: str, work: str, shape: str, valid: tuple[str, ...], invalid: tuple[str, ...]
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


def freeze_workload(name: str, build: Callable[[], Container], claim: Claim) -> Workload:
    def setup() -> Session:
        container = build()
        return Session(
            call=container.freeze,
            observe=lambda: Observation(result=_plan_size(container), constructed=(), closed=()),
        )

    return Workload(name=name, tier=Tier.COMPONENT, claim=claim, subject=implementation('depin', setup))


def explain_workload(name: str, build: Callable[[], tuple[Container, ProviderKey]], claim: Claim) -> Workload:
    def setup() -> Session:
        container, key = build()
        frozen = container.freeze()
        return Session(
            call=lambda: frozen.explain(key),
            observe=lambda: Observation(result=_tree_shape(frozen.explain(key)), constructed=(), closed=()),
        )

    return Workload(name=name, tier=Tier.COMPONENT, claim=claim, subject=implementation('depin', setup))
