"""Scaling workload for lookup through nested override frames."""

import contextlib
from collections.abc import Callable
from functools import partial

from benchmarks.contracts import Observation, Prepared
from depin import Scope

from .builders import OVERRIDE_GRAPH, Trace, _chain


def _override_nesting_session(size: int) -> tuple[Callable[[], object], Callable[[], None]]:
    """A warm singleton behind `size` nested override frames, none of which name its key.

    The frames are entered in setup and left standing for the whole measurement,
    because entering and leaving them is a different operation from resolving
    through them. Each names a key of its own that nothing binds, so the lookup
    walks the whole stack and then reads the plan — the shape a resolution takes
    inside a test that has overridden something else.
    """
    container, leaf = _chain(OVERRIDE_GRAPH, Scope.SINGLETON, Trace(recording=False))
    frozen = container.freeze()
    _ = frozen.resolve(leaf)
    stack = contextlib.ExitStack()
    try:
        for index in range(size):
            _ = stack.enter_context(frozen.override(type(f'Unrelated{index}', (), {}), object()))
    except BaseException:
        stack.close()
        raise
    return partial(frozen.resolve, leaf), stack.close


def _override_nesting_prepare(size: int) -> Prepared:
    call, close = _override_nesting_session(size)
    return Prepared(call=call, close=close)


def _override_nesting_observe(size: int) -> Observation:
    call, close = _override_nesting_session(size)
    try:
        return Observation(result=type(call()).__name__, constructed=(), closed=())
    finally:
        close()
