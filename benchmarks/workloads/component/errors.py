"""Component workloads for error paths."""

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.graphs import Unbound, build_chain_missing_a_provider, build_layered_dag
from benchmarks.workloads.component.primitives import (
    NO_BASELINE_DIAGNOSTIC,
    NO_BASELINE_VALIDATION,
)
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation
from depin.errors import MissingProviderError


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
