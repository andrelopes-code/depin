"""Allocation and retention, counted with `tracemalloc` under a fixed hash seed.

`tracemalloc` counts Python-level blocks, which is what makes these numbers
deterministic where a resident-set reading would not be: they do not move with the
allocator's arena behaviour or with what the rest of the process is doing.

They are deterministic only under a fixed hash seed. Dictionary and set sizing
depends on the hashes of the keys stored in them, so the same operation can
allocate a different number of blocks in two processes that started with different
seeds. The seed cannot be changed after the interpreter is running, so the
measuring process has to be started with it — `HASH_SEED` is the value the harness
starts its children with, and the guard here refuses to produce a number the
caller would otherwise compare against one measured under a different seed.
"""

import gc
import sys
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass

from benchmarks.harness import HarnessError

HASH_SEED = '0'
GROUP_BY = 'filename'


@dataclass(frozen=True, slots=True)
class Allocation:
    """What one operation allocated, and what the whole measurement peaked at.

    `blocks` and `size` are per operation. `peak` is the traced maximum over the
    entire measurement: a high-water mark is a property of a run rather than of one
    operation, and dividing it would state something no operation ever did.
    """

    blocks: int
    size: int
    peak: int


def hashing_is_deterministic() -> bool:
    """Whether this interpreter was started with hash randomisation off."""
    return sys.flags.hash_randomization == 0


def _require_deterministic_hashing() -> None:
    if not hashing_is_deterministic():
        raise HarnessError(
            f'allocation measurement needs PYTHONHASHSEED={HASH_SEED}; this interpreter randomises hashing and the '
            'seed cannot be changed after start, so re-run the measuring process with the variable set'
        )


def _require_idle_tracing() -> None:
    if tracemalloc.is_tracing():
        raise HarnessError('tracemalloc is already tracing; a nested measurement would count the outer one')


def _difference(before: tracemalloc.Snapshot, after: tracemalloc.Snapshot) -> tuple[int, int]:
    deltas = after.compare_to(before, GROUP_BY)
    return sum(delta.count_diff for delta in deltas), sum(delta.size_diff for delta in deltas)


def _live(before: tracemalloc.Snapshot, after: tracemalloc.Snapshot, held: object) -> int:
    """The bytes `after` holds that `before` did not, measured while `held` is alive.

    `held` is a parameter rather than an unused local because keeping the built
    object referenced past the snapshot is the whole measurement: retained memory
    is what survives while something points at it.
    """
    del held
    return _difference(before, after)[1]


def allocations_per_operation(call: Callable[[], object], *, operations: int) -> Allocation:
    """Measure what one invocation of `call` allocates.

    `call` is invoked once before tracing starts, so first-use caches are charged
    to the setup. Garbage is collected before the baseline snapshot, so the number
    is what the operations allocated rather than what a previous test left behind.

    Raises:
        HarnessError: the interpreter randomises hashing; `tracemalloc` is already
            tracing; `operations` is below one; or a total does not divide by
            `operations`, for the reason `work.calls_per_operation` states.
    """
    _require_deterministic_hashing()
    _require_idle_tracing()
    if operations < 1:
        raise HarnessError(f'{operations} operations; at least one is needed to count allocations')

    _ = call()
    _ = gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.take_snapshot()
        tracemalloc.reset_peak()
        for _ in range(operations):
            _ = call()
        after = tracemalloc.take_snapshot()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    blocks, size = _difference(before, after)
    if blocks % operations != 0 or size % operations != 0:
        raise HarnessError(
            f'{blocks} blocks and {size} bytes over {operations} operations do not divide evenly; '
            'the workload does not allocate the same on every operation'
        )
    return Allocation(blocks=blocks // operations, size=size // operations, peak=peak)


def retained(build: Callable[[], object]) -> int:
    """Measure the bytes the object `build` returns keeps alive.

    Garbage is collected before the closing snapshot, so what is reported is what
    the object holds rather than what constructing it discarded.

    Raises:
        HarnessError: the interpreter randomises hashing, or `tracemalloc` is
            already tracing.
    """
    _require_deterministic_hashing()
    _require_idle_tracing()

    _ = gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.take_snapshot()
        held = build()
        _ = gc.collect()
        after = tracemalloc.take_snapshot()
        return _live(before, after, held)
    finally:
        tracemalloc.stop()
