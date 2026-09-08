"""Context-local provider substitution, the seam tests use to swap a dependency."""

import contextlib
from collections.abc import Generator
from contextvars import ContextVar

from depin._core.scope import Scope
from depin._core.spec import ProviderKey, ProviderShape, ProviderSpec

type _Frame = dict[tuple[ProviderKey, str | None], object]

_stack: ContextVar[tuple[_Frame, ...]] = ContextVar('depin_overrides', default=())


@contextlib.contextmanager
def pushed(key: ProviderKey, tag: str | None, replacement: object) -> Generator[None]:
    """Make ``(key, tag)`` resolve to ``replacement`` for the duration of the block.

    Bound to the current `contextvars.Context`, so concurrent contexts are
    unaffected. Frames nest; the innermost wins.
    """
    frame: _Frame = {(key, tag): replacement}
    token = _stack.set((*_stack.get(), frame))
    try:
        yield
    finally:
        _stack.reset(token)


def active(key: ProviderKey, tag: str | None) -> ProviderSpec | None:
    """Return the spec for an active override of ``(key, tag)``, innermost first."""
    for frame in reversed(_stack.get()):
        if (key, tag) in frame:
            return _spec_for(key, tag, frame[(key, tag)])
    return None


def _spec_for(key: ProviderKey, tag: str | None, replacement: object) -> ProviderSpec:
    """Wrap a replacement in a transient spec: a callable becomes a factory, anything else a value."""
    is_factory = callable(replacement) and not isinstance(replacement, type)
    shape = ProviderShape.FUNCTION if is_factory else ProviderShape.VALUE
    return ProviderSpec(
        key=key,
        tag=tag,
        source=replacement,
        scope=Scope.TRANSIENT,
        shape=shape,
        needs_async=False,
        params=(),
    )
