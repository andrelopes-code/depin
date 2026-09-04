"""Scaling workloads for synchronous and asynchronous scope teardown."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Callable, Generator

from benchmarks.contracts import Observation, Prepared

from .builders import COLLECTION_KEY, Trace, async_resources, members, node, resources, split_events


def _teardown_call(size: int, trace: Trace) -> Callable[[], str]:
    frozen = resources(size, trace).freeze()

    def run() -> str:
        with frozen.scope():
            return members(frozen.resolve(COLLECTION_KEY))

    return run


def teardown_prepare(size: int) -> Prepared:
    return Prepared(call=_teardown_call(size, Trace(recording=False)))


def teardown_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    result = _teardown_call(size, trace)()
    opened, closed = split_events(trace)
    return Observation(result=result, constructed=opened, closed=closed)


def _direct_teardown(size: int, trace: Trace) -> Callable[[], str]:
    member_types = tuple(node(index) for index in range(size))

    @contextlib.contextmanager
    def hold(member: type[object]) -> Generator[object]:
        trace.record(member.__name__)
        yield member()
        trace.record(f'close {member.__name__}')

    def run() -> str:
        with contextlib.ExitStack() as stack:
            return members([stack.enter_context(hold(member)) for member in member_types])

    return run


def direct_teardown_prepare(size: int) -> Prepared:
    return Prepared(call=_direct_teardown(size, Trace(recording=False)))


def direct_teardown_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    result = _direct_teardown(size, trace)()
    opened, closed = split_events(trace)
    return Observation(result=result, constructed=opened, closed=closed)


def _async_teardown_session(size: int, trace: Trace) -> tuple[Callable[[], str], Callable[[], None]]:
    """One async scope cycle, and the loop release that has to happen outside the timed region."""
    frozen = async_resources(size, trace).freeze()
    loop = asyncio.new_event_loop()

    async def cycle() -> str:
        async with frozen.ascope():
            return members(await frozen.aresolve(COLLECTION_KEY))

    return lambda: loop.run_until_complete(cycle()), loop.close


def async_teardown_prepare(size: int) -> Prepared:
    call, close = _async_teardown_session(size, Trace(recording=False))
    return Prepared(call=call, close=close)


def async_teardown_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    call, close = _async_teardown_session(size, trace)
    try:
        result = call()
    finally:
        close()
    opened, closed = split_events(trace)
    return Observation(result=result, constructed=opened, closed=closed)


def _direct_async_teardown_session(size: int, trace: Trace) -> tuple[Callable[[], str], Callable[[], None]]:
    member_types = tuple(node(index) for index in range(size))
    loop = asyncio.new_event_loop()

    @contextlib.asynccontextmanager
    async def hold(member: type[object]) -> AsyncGenerator[object]:
        trace.record(member.__name__)
        yield member()
        trace.record(f'close {member.__name__}')

    async def cycle() -> str:
        async with contextlib.AsyncExitStack() as stack:
            return members([await stack.enter_async_context(hold(member)) for member in member_types])

    return lambda: loop.run_until_complete(cycle()), loop.close


def direct_async_teardown_prepare(size: int) -> Prepared:
    call, close = _direct_async_teardown_session(size, Trace(recording=False))
    return Prepared(call=call, close=close)


def direct_async_teardown_observe(size: int) -> Observation:
    trace = Trace(recording=True)
    call, close = _direct_async_teardown_session(size, trace)
    try:
        result = call()
    finally:
        close()
    opened, closed = split_events(trace)
    return Observation(result=result, constructed=opened, closed=closed)
