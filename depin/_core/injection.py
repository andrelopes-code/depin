"""Wraps a function so parameters defaulting to `injected` are filled on call."""

import functools
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import get_type_hints

from depin._core.introspect import extract_annotated_meta
from depin._core.markers import is_inject_marker
from depin._core.providers import param_key_from_meta
from depin._core.spec import ProviderKey, fmt_key
from depin._core.typeguards import as_awaitable
from depin.errors import InvalidProviderError, MissingProviderError


@dataclass(frozen=True, slots=True)
class Injectable:
    """A marked parameter, and whether a provider was found for its key.

    ``registered`` is false only for a parameter whose annotation admits
    ``None``: every other unregistered key is refused at decoration time.
    """

    key: ProviderKey
    tag: str | None
    registered: bool


type Injectables = dict[str, Injectable]
type SyncResolver = Callable[[ProviderKey, str | None], object]
type AsyncResolver = Callable[[ProviderKey, str | None], Awaitable[object]]


def collect(
    fn: Callable[..., object],
    sig: inspect.Signature,
    is_registered: Callable[[ProviderKey, str | None], bool],
) -> Injectables:
    """Read the key of every parameter defaulting to `injected` off its annotation.

    Raises:
        InvalidProviderError: A marked parameter carries no annotation, or one
            whose names do not resolve.
        MissingProviderError: A marked parameter names an unregistered key and
            its annotation does not admit ``None``.
    """
    marked = tuple(name for name, param in sig.parameters.items() if is_inject_marker(param.default))
    if not marked:
        return {}

    hints = _annotations(fn)
    out: Injectables = {}
    for name in marked:
        annotation = hints.get(name)
        if annotation is None:
            raise InvalidProviderError(
                f"@inject: parameter '{name}' of {fn!r} defaults to injected but carries no type "
                'annotation, so depin cannot tell what to resolve. Annotate it with the key to inject.'
            )
        meta = extract_annotated_meta(annotation)
        key = param_key_from_meta(meta)
        registered = is_registered(key, meta.tag)
        if not registered and not meta.optional:
            tag_note = f', tag={meta.tag!r}' if meta.tag is not None else ''
            raise MissingProviderError(
                f"@inject: parameter '{name}' requests {fmt_key(key)}{tag_note} "
                'but no provider is registered for that key. '
                'Bind it on the Container before calling .freeze(), or remove the injected default.'
            )
        out[name] = Injectable(key=key, tag=meta.tag, registered=registered)
    return out


def _annotations(fn: Callable[..., object]) -> dict[str, object]:
    try:
        return dict(get_type_hints(fn, include_extras=True))
    except (NameError, TypeError) as exc:
        raise InvalidProviderError(
            f'@inject: the annotations of {fn!r} could not be resolved ({exc}). '
            'Import the names they use at module level, so depin can resolve the reference.'
        ) from exc


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
            for name, injectable in injectables.items():
                if name not in bound.arguments:
                    bound.arguments[name] = (
                        await aresolve(injectable.key, injectable.tag) if injectable.registered else None
                    )
            return await as_awaitable(fn(*bound.args, **bound.kwargs), fn)

        return wrapper_async

    @functools.wraps(fn)
    def wrapper_sync(*args: object, **kwargs: object) -> object:
        bound = sig.bind_partial(*args, **kwargs)
        for name, injectable in injectables.items():
            if name not in bound.arguments:
                bound.arguments[name] = resolve(injectable.key, injectable.tag) if injectable.registered else None
        return fn(*bound.args, **bound.kwargs)

    return wrapper_sync
