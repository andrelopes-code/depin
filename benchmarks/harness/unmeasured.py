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
            '`tests/unit/test_longest_chain.py::test_failing_freeze_is_not_cubic_in_the_chain_length`, which '
            'asserts a complexity class over 400 providers on a budget two orders of magnitude above the '
            'constant, and the fixed-size latency workloads `freeze_a_chain_missing_a_provider_of_50` and '
            '`_of_100`.'
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
            '`tests/unit/test_longest_chain.py::test_explain_of_an_unbound_key_is_not_exponential_in_the_'
            'path_count`, over a 24-node fan-in-2 DAG, and the fixed-size latency workloads '
            '`explain_an_unbound_key_of_16` and `_of_20`.'
        ),
    ),
)

REFUSED: tuple[Refusal, ...] = (
    Refusal(
        case='Concurrent requests, active scopes, and singleton first-use contention.',
        reason=(
            'Timed sleeps are forbidden here, so contention has to be created with explicit '
            'synchronisation — a barrier, a reduced switch interval — and a benchmark built that way '
            'measures the synchronisation as much as it measures the lock. The invariants themselves are '
            'already tested for correctness under free-threading in `tests/unit/test_free_threading.py`, '
            'where the guarantee rather than the number is what matters.'
        ),
        needed=(
            'A design of its own, alongside the free-threading work that owns what the public surface '
            'commits to under concurrency. Routed to Step 8.'
        ),
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
