"""What the suite does not measure, and why — retired workloads and refused cases.

A workload that disappears from the inventory and a case that was never added
look identical to a later reader. Both are recorded here so the published page
carries the absence rather than only the presence, and so a reader can tell a
decision from an oversight.

`Retirement` is a workload that was measured and stopped being measured, because
what it claimed to detect it no longer detects. `Refusal` is a case the
performance proposal asked for and this suite declines to measure, with the thing
that would be needed instead named rather than implied.

The module carries no import of `benchmarks.workloads`, so
`benchmarks.harness.report` stays free of the framework dependency the inventory
pulls in. `tests/integration/test_workload_contracts.py` closes the loop from the
other side: a retired name may not reappear in the inventory.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Retirement:
    """A workload that was published, then withdrawn, and what still covers its path.

    ``covered_by`` is not optional. A path whose measurement is withdrawn and
    whose protection is not named has been silently dropped, which is the outcome
    this record exists to prevent.
    """

    workload: str
    claimed: str
    reason: str
    covered_by: str


@dataclass(frozen=True, slots=True)
class Refusal:
    """A measurement the proposal asked for and this suite declines to produce.

    ``needed`` names what an honest measurement would require, so the refusal is
    a specification of the missing work rather than a statement that it will
    never happen.
    """

    case: str
    reason: str
    needed: str


RETIRED: tuple[Retirement, ...] = (
    Retirement(
        workload='scale_failing_freeze',
        claimed='The complexity class of the failing-freeze path, as the growth ratio between graph sizes.',
        reason=(
            'The path is dominated by a constant that does not depend on graph size: `suggest_candidates` '
            'scans `sys.modules` when the error is built. Measured on the pull-request runner with both '
            'sides on identical code, the curve read 7.095, 7.021 and 7.026 ms at sizes 25, 50 and 100 — '
            'flat across a fourfold range — and the difference between the two identical revisions reached '
            '+23.61% against a 15% budget. The scan also depends on how many modules each process loaded, '
            'which is not a property of the revision under test. The curve was valid before the walk it '
            'watched was repaired; the repair is what left the constant in charge.'
        ),
        covered_by=(
            '`tests/unit/test_longest_chain.py::test_failing_freeze_does_not_grow_cubically_with_the_chain_'
            'length`, which compares 200 providers against 400 — the sizes at which the walk overtakes the '
            'constant — and reads 1.80 repaired against 5.91 with the cubic walk restored. It replaced a '
            'half-second wall-clock budget that the same seeded walk passed at 0.42 s, on a host faster than '
            'the one that budget was written on. The fixed-size latency workloads '
            '`freeze_a_chain_missing_a_provider_of_50` and `_of_100` cover the path as well.'
        ),
    ),
    Retirement(
        workload='scale_explain_missing_key',
        claimed='The complexity class of the missing-key walk, as the growth ratio between graph sizes.',
        reason=(
            'The same constant, reached through `render`. The published reference-host dataset already '
            'recorded the curve as flat — 5.479, 5.503 and 5.444 ms at sizes 10, 12 and 14, growth 1.00x '
            'and 0.99x — while the number of simple paths through those graphs grows Fibonacci in the size. '
            'A curve that does not move where the quantity it claims to track quadruples is not measuring '
            'that quantity.'
        ),
        covered_by=(
            '`tests/unit/test_longest_chain.py::test_explain_of_an_unbound_key_does_not_grow_with_the_path_'
            'count`, which compares a 16-node fan-in-2 DAG against a 24-node one — eighteen times the simple '
            'paths — and reads 1.00 repaired against 24.94 with the enumerating walk restored. The '
            'fixed-size latency workloads `explain_an_unbound_key_of_16` and `_of_20` cover the path as '
            'well.'
        ),
    ),
)

REFUSED: tuple[Refusal, ...] = (
    Refusal(
        case='fastapi_no_injection',
        reason=(
            'The installed no-injection route exists only in the FastAPI optimization head; the accepted '
            'dataset predates it, so an archived baseline cannot supply a paired observation. It remains a '
            'head-only diagnostic and is reported separately rather than silently treated as paired evidence.'
        ),
        needed='A five-repetition head-only diagnostic collection alongside the next accepted paired FastAPI run.',
    ),
    Refusal(
        case='fastapi_lazy_host_publication',
        reason='The accepted dataset predates the lazy FastAPI host-publication component diagnostic.',
        needed='A dedicated component collection in a new accepted FastAPI evidence dataset.',
    ),
    Refusal(
        case='fastapi_lazy_frame_activation_and_drain',
        reason='The accepted dataset predates the lazy FastAPI frame-activation component diagnostic.',
        needed='A dedicated component collection in a new accepted FastAPI evidence dataset.',
    ),
    Refusal(
        case='fastapi_endpoint_program_one_key',
        reason='The accepted dataset predates the one-key compiled FastAPI endpoint-program diagnostic.',
        needed='A dedicated component collection in a new accepted FastAPI evidence dataset.',
    ),
    Refusal(
        case='fastapi_endpoint_program_many_keys',
        reason='The accepted dataset predates the multi-key compiled FastAPI endpoint-program diagnostic.',
        needed='A dedicated component collection in a new accepted FastAPI evidence dataset.',
    ),
    Refusal(
        case='fastapi_request_seed_read',
        reason='The accepted dataset predates the lazy FastAPI request-seed component diagnostic.',
        needed='A dedicated component collection in a new accepted FastAPI evidence dataset.',
    ),
    Refusal(
        case='fastapi_async_resource_close',
        reason='The accepted dataset predates the async FastAPI resource-close component diagnostic.',
        needed='A dedicated component collection in a new accepted FastAPI evidence dataset.',
    ),
    Refusal(
        case='Long-running allocation and retention drift.',
        reason=(
            'Retention here is a point-in-time reading. Drift is only visible over a soak, and how much '
            'runner time a soak may consume in a blocking pull-request gate is a budget decision rather '
            'than a methodological one.'
        ),
        needed='A scheduled job with its own time budget, not a check on the pull-request path.',
    ),
)
