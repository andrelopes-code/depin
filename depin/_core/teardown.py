"""Records for provider cleanup and the drains that run them.

A provider that owns a resource — a generator, an ``@contextmanager`` — leaves
a teardown record on the scope frame that cached it. Draining a frame runs its
records in reverse order of construction, so a dependency is always torn down
after the value that used it. Failures never short-circuit the drain: they are
collected and re-raised together as an ``ExceptionGroup``.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from depin.errors import TeardownError

if TYPE_CHECKING:
    from depin._core.scope import ScopeFrame


@dataclass(frozen=True, slots=True)
class SyncGenTeardown:
    gen: Iterator[object]


@dataclass(frozen=True, slots=True)
class AsyncGenTeardown:
    gen: AsyncIterator[object]


@dataclass(frozen=True, slots=True)
class SyncCMTeardown:
    cm: AbstractContextManager[object]


@dataclass(frozen=True, slots=True)
class AsyncCMTeardown:
    cm: AbstractAsyncContextManager[object]


type Teardown = SyncGenTeardown | AsyncGenTeardown | SyncCMTeardown | AsyncCMTeardown


def run_sync(record: Teardown) -> None:
    """Run one teardown record without an event loop.

    Raises:
        TeardownError: The record is async, or a generator provider yielded
            twice.
    """
    match record:
        case SyncGenTeardown(gen):
            _exhaust_sync(gen)
        case SyncCMTeardown(cm):
            _ = cm.__exit__(None, None, None)
        case AsyncGenTeardown() | AsyncCMTeardown():
            raise TeardownError(
                'an async provider registered a teardown in a synchronous scope; '
                'open the scope with ascope() and drain it with aclose()/ascope() instead'
            )


async def run_async(record: Teardown) -> None:
    """Run one teardown record inside an event loop; handles sync records too.

    Raises:
        TeardownError: A generator provider yielded twice.
    """
    match record:
        case SyncGenTeardown(gen):
            _exhaust_sync(gen)
        case AsyncGenTeardown(gen):
            try:
                _ = await gen.__anext__()
            except StopAsyncIteration:
                return
            raise TeardownError('async generator provider yielded more than once; it must yield exactly once')
        case SyncCMTeardown(cm):
            _ = cm.__exit__(None, None, None)
        case AsyncCMTeardown(cm):
            _ = await cm.__aexit__(None, None, None)


def _exhaust_sync(gen: Iterator[object]) -> None:
    try:
        _ = next(gen)
    except StopIteration:
        return
    raise TeardownError('generator provider yielded more than once; it must yield exactly once')


def drain_sync(frame: 'ScopeFrame') -> None:
    """Run every pending teardown on ``frame``, newest first, without an event loop.

    Raises:
        ExceptionGroup: One or more teardowns failed. Every failure is reported;
            none is allowed to hide another.
    """
    errors: list[Exception] = []
    for record in frame.take_teardowns():
        try:
            run_sync(record)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup('depin teardown errors', errors)


async def drain_async(frame: 'ScopeFrame') -> None:
    """Run every pending teardown on ``frame``, newest first, inside an event loop.

    Raises:
        ExceptionGroup: One or more teardowns failed.
    """
    errors: list[Exception] = []
    for record in frame.take_teardowns():
        try:
            await run_async(record)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup('depin teardown errors', errors)
