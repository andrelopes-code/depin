"""Calls a provider according to its shape and registers whatever teardown it leaves.

Nine shapes, two entry points. `sync` handles everything that can run without an
event loop; `asynchronous` handles the three async shapes and delegates the rest
to `sync`, which is why an async scope can resolve a sync provider but never the
other way round.
"""

from collections.abc import Callable

from depin._core.spec import ProviderShape, ProviderSpec, fmt_key
from depin._core.teardown import (
    AsyncCMTeardown,
    AsyncGenTeardown,
    SyncCMTeardown,
    SyncGenTeardown,
    Teardown,
)
from depin._core.typeguards import (
    as_async_context_manager,
    as_async_iterator,
    as_awaitable,
    as_class,
    as_factory,
    as_sync_context_manager,
    as_sync_iterator,
)
from depin.errors import AsyncInSyncContextError, InvalidProviderError

type OnTeardown = Callable[[Teardown], None]
type ReadFrame = Callable[[ProviderSpec], object]


def sync(
    spec: ProviderSpec,
    kwargs: dict[str, object],
    on_teardown: OnTeardown,
    read_frame: ReadFrame,
) -> object:
    """Build a value for any non-async shape.

    Raises:
        AsyncInSyncContextError: ``spec`` is an async shape.
        InvalidProviderError: The provider did not return what its shape promises.
    """
    key = spec.key
    match spec.shape:
        case ProviderShape.VALUE:
            return spec.source
        case ProviderShape.FRAME:
            return read_frame(spec)
        case ProviderShape.CLASS:
            return as_class(spec.source, key)(**kwargs)
        case ProviderShape.FUNCTION:
            return as_factory(spec.source, key)(**kwargs)
        case ProviderShape.GENERATOR:
            gen = as_sync_iterator(as_factory(spec.source, key)(**kwargs), key)
            value = next(gen)
            on_teardown(SyncGenTeardown(gen))
            return value
        case ProviderShape.CONTEXT_MANAGER:
            cm = as_sync_context_manager(as_factory(spec.source, key)(**kwargs), key)
            value = cm.__enter__()
            on_teardown(SyncCMTeardown(cm))
            return value
        case ProviderShape.ASYNC_FUNCTION | ProviderShape.ASYNC_GENERATOR | ProviderShape.ASYNC_CONTEXT_MANAGER:
            # Unreachable through the public API: `resolve` rejects a spec whose
            # `needs_async` flag is set, long before construction. Kept so the
            # match stays exhaustive over ProviderShape if a shape is added.
            raise AsyncInSyncContextError(f'{fmt_key(key)} is an async provider; resolve it with aresolve()')
        case ProviderShape.ALIAS:
            # Unreachable through the public API: nothing yet binds a
            # ProviderShape.ALIAS spec. Kept so the match stays exhaustive.
            raise InvalidProviderError(f'{fmt_key(key)} is an alias, which construct.sync does not resolve yet')


async def asynchronous(
    spec: ProviderSpec,
    kwargs: dict[str, object],
    on_teardown: OnTeardown,
    read_frame: ReadFrame,
) -> object:
    """Build a value for an async shape, or hand a sync one to `sync`.

    Raises:
        InvalidProviderError: The provider did not return what its shape promises.
    """
    key = spec.key
    match spec.shape:
        case ProviderShape.ASYNC_FUNCTION:
            return await as_awaitable(as_factory(spec.source, key)(**kwargs), key)
        case ProviderShape.ASYNC_GENERATOR:
            agen = as_async_iterator(as_factory(spec.source, key)(**kwargs), key)
            value = await agen.__anext__()
            on_teardown(AsyncGenTeardown(agen))
            return value
        case ProviderShape.ASYNC_CONTEXT_MANAGER:
            acm = as_async_context_manager(as_factory(spec.source, key)(**kwargs), key)
            value = await acm.__aenter__()
            on_teardown(AsyncCMTeardown(acm))
            return value
        case _:
            return sync(spec, kwargs, on_teardown, read_frame)
