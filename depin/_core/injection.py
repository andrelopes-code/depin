"""Wraps a function so parameters marked with `injected()` are filled on call."""

import functools
import inspect
from collections.abc import Awaitable, Callable

from depin._core.markers import is_inject_marker
from depin._core.spec import ProviderKey, fmt_key
from depin._core.typeguards import as_awaitable
from depin.errors import MissingProviderError

type Injectables = dict[str, tuple[ProviderKey, str | None]]
type SyncResolver = Callable[[ProviderKey, str | None], object]
type AsyncResolver = Callable[[ProviderKey, str | None], Awaitable[object]]


def collect(sig: inspect.Signature, is_registered: Callable[[ProviderKey, str | None], bool]) -> Injectables:
    """Find the parameters defaulting to `injected()` and validate their keys.

    Raises:
        MissingProviderError: A marked parameter names an unregistered key.
    """
    out: Injectables = {}
    for name, param in sig.parameters.items():
        marker = param.default
        if not is_inject_marker(marker):
            continue
        if not is_registered(marker.key, marker.tag):
            tag_note = f', tag={marker.tag!r}' if marker.tag is not None else ''
            raise MissingProviderError(
                f"@inject: parameter '{name}' requests "
                f'injected({fmt_key(marker.key)}{tag_note}) '
                'but no provider is registered for that key. '
                'Bind it on the Container before calling .freeze(), or remove the injected() default.'
            )
        out[name] = (marker.key, marker.tag)
    return out


def wrap(
    fn: Callable[..., object],
    sig: inspect.Signature,
    injectables: Injectables,
    resolve: SyncResolver,
    aresolve: AsyncResolver,
) -> Callable[..., object]:
    """Return a wrapper that fills the injectable parameters the caller left out.

    The wrapper preserves the sync or async nature of ``fn``. Arguments the
    caller supplies are never overridden, so an injected parameter can still be
    passed explicitly.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def wrapper_async(*args: object, **kwargs: object) -> object:
            bound = sig.bind_partial(*args, **kwargs)
            for name, (key, tag) in injectables.items():
                if name not in bound.arguments:
                    bound.arguments[name] = await aresolve(key, tag)
            return await as_awaitable(fn(*bound.args, **bound.kwargs), fn)

        return wrapper_async

    @functools.wraps(fn)
    def wrapper_sync(*args: object, **kwargs: object) -> object:
        bound = sig.bind_partial(*args, **kwargs)
        for name, (key, tag) in injectables.items():
            if name not in bound.arguments:
                bound.arguments[name] = resolve(key, tag)
        return fn(*bound.args, **bound.kwargs)

    return wrapper_sync
