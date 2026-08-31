"""Rewrites a decorated binding into the chain of nodes that resolves it.

A decorator is not a shape of its own. `Container.decorate` leaves the wrapper
on the public key and moves what it wraps to an `Underlying` key one layer
below, so every node in the chain is an ordinary provider whose parameters are
what it depends on. Nothing downstream of here — validation, ordering, caching,
construction, teardown, or rendering — needs to know a decoration happened.
"""

from collections.abc import Iterable, Sequence

from depin._core.providers import LIFECYCLE_SHAPES
from depin._core.scope import Scope
from depin._core.spec import (
    DecorationSpec,
    Ident,
    ParamSpec,
    ProviderKey,
    ProviderShape,
    ProviderSpec,
    Underlying,
    fmt_key,
)
from depin.errors import InvalidProviderError, InvalidScopeError, MissingProviderError


def apply(
    providers: tuple[ProviderSpec, ...],
    decorations: tuple[DecorationSpec, ...],
    inactive: frozenset[Ident],
) -> tuple[ProviderSpec, ...]:
    """Return the specs with every decorated binding replaced by its chain.

    ``inactive`` is the identities `Container.freeze()` dropped because their
    condition did not hold, used only to tell that case apart from a key that
    was never bound at all.

    Raises:
        MissingProviderError: A decorator names a key that nothing binds, or
            that a condition dropped from the plan.
        InvalidProviderError: The decorated binding is a `Container.scope_value`.
        InvalidScopeError: A lifecycle decorator wraps a transient binding.
    """
    if not decorations:
        return providers
    grouped = _group(decorations)
    _check_targets(grouped, {(spec.key, spec.tag): spec for spec in providers}, inactive)
    out: list[ProviderSpec] = []
    for spec in providers:
        layers = grouped.get((spec.key, spec.tag))
        if layers is None:
            out.append(spec)
            continue
        out.extend(_chain(spec, layers))
    return tuple(out)


def _group(decorations: Iterable[DecorationSpec]) -> dict[Ident, list[DecorationSpec]]:
    """Decorations by the binding they target, each list in registration order."""
    grouped: dict[Ident, list[DecorationSpec]] = {}
    for decoration in decorations:
        grouped.setdefault((decoration.key, decoration.tag), []).append(decoration)
    return grouped


def _check_targets(
    grouped: dict[Ident, list[DecorationSpec]],
    index: dict[Ident, ProviderSpec],
    inactive: frozenset[Ident],
) -> None:
    for ident, layers in grouped.items():
        key, tag = ident
        spec = index.get(ident)
        if spec is None:
            if ident in inactive:
                raise MissingProviderError(
                    f'cannot decorate {fmt_key(key)} (tag={tag!r}): its binding is registered under a '
                    'condition that did not hold, so nothing was bound for it in this configuration. '
                    'Give the decorator the same condition as the binding it wraps.'
                )
            raise MissingProviderError(
                f'cannot decorate {fmt_key(key)} (tag={tag!r}): no binding is registered for it. A '
                'decorator wraps an existing binding, so bind the key, drop the decorator, or give '
                'the decorator the same condition as the binding it wraps.'
            )
        if spec.shape is ProviderShape.FRAME:
            raise InvalidProviderError(
                f'cannot decorate {fmt_key(key)} (tag={tag!r}): it is declared with scope_value(), '
                'and a value supplied by whoever opens the scope is read from the active frame '
                'before the plan is consulted, so a parameter would receive the undecorated value. '
                'Wrap the value where the scope is opened instead.'
            )
        for layer in layers:
            if layer.shape in LIFECYCLE_SHAPES and spec.scope is Scope.TRANSIENT:
                raise InvalidScopeError(
                    f'cannot decorate transient {fmt_key(key)} with {layer.source!r}: a generator or '
                    'context-manager decorator owns a teardown, and a transient value is never '
                    'cached, so nothing would drain it. Bind the key as singleton or scoped.'
                )


def _chain(spec: ProviderSpec, layers: Sequence[DecorationSpec]) -> Iterable[ProviderSpec]:
    """The registered binding one layer down, then one node per wrapper above it.

    Every yielded spec carries ``needs_async=False``: `graph._with_async_flags`
    recomputes it for the whole plan after the fold, from each node's own shape
    and its dependencies, so a value written here is never read.

    A check verifies the value the binding it was declared on produces, so it
    stays with that binding rather than moving to the key the wrapper occupies.
    """
    key = spec.key
    tag = spec.tag
    yield ProviderSpec(
        key=Underlying(key, 0),
        tag=tag,
        source=spec.source,
        scope=spec.scope,
        shape=spec.shape,
        needs_async=False,
        params=spec.params,
        check=spec.check,
    )
    outermost = len(layers) - 1
    for depth, layer in enumerate(layers):
        yield ProviderSpec(
            key=key if depth == outermost else Underlying(key, depth + 1),
            tag=tag,
            source=layer.source,
            scope=spec.scope,
            shape=layer.shape,
            needs_async=False,
            params=tuple(_rewrite(param, layer.inner, Underlying(key, depth), tag) for param in layer.params),
        )


def _rewrite(param: ParamSpec, inner: str, key: ProviderKey, tag: str | None) -> ParamSpec:
    """Point a decorator's designated parameter one layer down.

    The rewritten parameter is required and not optional whatever it was
    written as: the node below it always exists, so a default or a `T | None`
    on it could only hide a defect in the fold.
    """
    if param.name != inner:
        return param
    return ParamSpec(name=param.name, key=key, tag=tag, has_default=False, default=None, optional=False)
