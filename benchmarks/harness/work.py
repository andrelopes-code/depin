"""Python-level calls per operation: a cost proxy that carries no noise at all.

The latency gate cannot see a regression smaller than its workload's noise band —
between 5% and 28% on the measured suite. A cached resolution costs thirteen
Python calls, and a change that adds one dict copy to the resolution path adds
calls the moment it lands. Counting them catches that on the first run, exactly,
with no false alarm available to it.

It is a proxy for cost rather than cost itself, which is why it supplements the
latency gate rather than replacing it.
"""

import sys
from collections.abc import Callable
from types import FrameType

from benchmarks.harness import HarnessError


def calls_per_operation(call: Callable[[], object], *, operations: int) -> int:
    """Count the Python-level calls one invocation of `call` makes.

    `call` is invoked once before counting starts, so a lazily built cache or an
    import performed on first use is charged to the setup rather than to the
    first operation. The count includes the invocation of `call` itself, which is
    constant across revisions and therefore cancels in a comparison.

    Only `call` events are counted. C-level calls are excluded: they move with the
    interpreter build rather than with the code under measurement.

    Raises:
        HarnessError: `operations` is below one, or the total does not divide by
            it — a workload whose per-operation cost is not uniform is a finding,
            not something to average away. Measure it at `operations=1`, or fix
            the workload's setup.
    """
    if operations < 1:
        raise HarnessError(f'{operations} operations; at least one is needed to count calls')

    _ = call()
    counted = 0

    def count(frame: FrameType, event: str, argument: object) -> None:
        del frame, argument
        nonlocal counted
        if event == 'call':
            counted += 1

    previous = sys.getprofile()
    sys.setprofile(count)
    try:
        for _ in range(operations):
            _ = call()
    finally:
        sys.setprofile(previous)

    if counted % operations != 0:
        raise HarnessError(
            f'{counted} Python calls over {operations} operations does not divide evenly; '
            'the workload does not cost the same on every operation'
        )
    return counted // operations
