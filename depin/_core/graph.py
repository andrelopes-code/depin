"""Validates the provider specs and orders them into a `ResolutionPlan`.

This is what `Container.freeze()` runs. Every check here happens before a single
value is constructed: duplicates, unsatisfied dependencies, cycles, captive
singletons, and which providers transitively need async resolution.
"""

from collections.abc import Iterable

from depin._core.markers import get_provides
from depin._core.providers import ASYNC_SHAPES, build_specs
from depin._core.scope import Scope
from depin._core.spec import BindRecord, ProviderKey, ProviderSpec, ResolutionPlan, fmt_key
from depin.errors import (
    CaptiveDependencyError,
    CircularDependencyError,
    DuplicateProviderError,
    MissingProviderError,
)

type _Index = dict[tuple[ProviderKey, str | None], ProviderSpec]
type _Ident = tuple[ProviderKey, str | None]


def build_plan(records: Iterable[BindRecord]) -> ResolutionPlan:
    """Validate the bindings and return the plan the frozen container resolves from.

    Raises:
        DuplicateProviderError: Two bindings share a key and tag.
        MissingProviderError: A required dependency has no provider.
        CircularDependencyError: The graph contains a cycle.
        CaptiveDependencyError: A singleton depends on a scoped provider.
        InvalidProviderError: A binding lacks the type information to infer a key.
        InvalidScopeError: A lifecycle provider is bound as transient.
    """
    specs = build_specs(records)
    _check_duplicates(specs)
    by_key = _index(specs)
    _check_missing(specs, by_key)
    order = _toposort(specs, by_key)
    _check_captive(order, by_key)
    resolved = tuple(_with_async_flags(order, by_key))
    return ResolutionPlan(order=resolved, by_key=_index(resolved))


def _index(specs: Iterable[ProviderSpec]) -> _Index:
    return {(spec.key, spec.tag): spec for spec in specs}


def _check_duplicates(specs: Iterable[ProviderSpec]) -> None:
    seen: set[_Ident] = set()
    for spec in specs:
        ident = (spec.key, spec.tag)
        if ident in seen:
            key, tag = ident
            raise DuplicateProviderError(
                f'duplicate provider for {fmt_key(key)} (tag={tag!r}): '
                'two bindings resolve to the same key. Remove one, or give them '
                'distinct tags to register multiple implementations.'
            )
        seen.add(ident)


def _check_missing(specs: Iterable[ProviderSpec], by_key: _Index) -> None:
    missing: dict[_Ident, tuple[tuple[ProviderSpec, ...], ProviderSpec, str]] = {}
    for root in specs:
        _collect_missing(root, by_key, (root,), missing)
    if not missing:
        return
    # Deepest chain first: the longest resolution path is the most informative
    # one to show when several providers are unsatisfied.
    ordered = sorted(missing.items(), key=lambda kv: len(kv[1][0]), reverse=True)
    lines = [_format_missing(ident, chain, owner, param_name) for ident, (chain, owner, param_name) in ordered]
    if len(lines) == 1:
        raise MissingProviderError(lines[0])
    body = '\n  - '.join(lines)
    raise MissingProviderError(f'{len(lines)} missing providers:\n  - {body}')


def _collect_missing(
    root: ProviderSpec,
    by_key: _Index,
    chain: tuple[ProviderSpec, ...],
    missing: dict[_Ident, tuple[tuple[ProviderSpec, ...], ProviderSpec, str]],
) -> None:
    # Iterative DFS over the dependency graph. Each entry is the current spec
    # paired with the chain that led to it; cycles are broken by the
    # ``id(dep) in chain_specs`` check below and reported by `_toposort`.
    stack: list[tuple[ProviderSpec, tuple[ProviderSpec, ...]]] = [(root, chain)]
    while stack:
        spec, current_chain = stack.pop()
        chain_specs = {id(c) for c in current_chain}
        for param in spec.params:
            if param.has_default:
                continue
            dep = by_key.get((param.key, param.tag))
            if dep is None:
                ident = (param.key, param.tag)
                if ident not in missing or len(current_chain) > len(missing[ident][0]):
                    missing[ident] = (current_chain, spec, param.name)
                continue
            if id(dep) in chain_specs:
                continue
            stack.append((dep, (*current_chain, dep)))


def _format_missing(
    ident: _Ident,
    chain: tuple[ProviderSpec, ...],
    owner: ProviderSpec,
    param_name: str,
) -> str:
    key, _tag = ident
    path = ' -> '.join(fmt_key(s.key) for s in chain)
    suggestions = _suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    return (
        f'no provider for {fmt_key(key)} '
        f'(required by {fmt_key(owner.key)}.{param_name}; '
        f'resolution chain: {path} -> {fmt_key(key)}){extra}'
    )


_SUGGEST_SCAN_LIMIT = 50_000
_SUGGEST_RESULT_LIMIT = 5


def _suggest_candidates(target: object) -> list[str]:
    """Scan live classes for `@provides(target)` hints. Used only at error time.

    Bounded by ``_SUGGEST_SCAN_LIMIT`` to keep error-path latency predictable in
    large processes where ``gc.get_objects()`` returns hundreds of thousands of
    references.
    """
    if not isinstance(target, type):
        return []
    import gc

    out: list[str] = []
    for i, obj in enumerate(gc.get_objects()):
        if i >= _SUGGEST_SCAN_LIMIT:
            break
        if not isinstance(obj, type):
            continue
        if get_provides(obj) is target:
            out.append(f'{obj.__module__}.{obj.__qualname__}')
            if len(out) >= _SUGGEST_RESULT_LIMIT:
                break
    return out


def _toposort(specs: Iterable[ProviderSpec], by_key: _Index) -> tuple[ProviderSpec, ...]:
    """Iterative post-order DFS. Frames are ``(spec, next_param_index)``."""
    ordered: list[ProviderSpec] = []
    visited: set[_Ident] = set()
    visiting: set[_Ident] = set()

    for root in specs:
        if (root.key, root.tag) in visited:
            continue
        stack: list[tuple[ProviderSpec, int]] = [(root, 0)]
        visiting.add((root.key, root.tag))
        while stack:
            spec, i = stack[-1]
            if i >= len(spec.params):
                ident = (spec.key, spec.tag)
                visiting.remove(ident)
                visited.add(ident)
                ordered.append(spec)
                _ = stack.pop()
                continue
            stack[-1] = (spec, i + 1)
            param = spec.params[i]
            dep = by_key.get((param.key, param.tag))
            if dep is None:
                continue
            dep_ident = (dep.key, dep.tag)
            if dep_ident in visited:
                continue
            if dep_ident in visiting:
                cycle_path = [(s.key, s.tag) for s, _ in stack]
                cycle_path.append(dep_ident)
                chain = ' -> '.join(fmt_key(k) for k, _ in cycle_path)
                raise CircularDependencyError(f'cycle detected: {chain}')
            visiting.add(dep_ident)
            stack.append((dep, 0))
    return tuple(ordered)


def _check_captive(order: Iterable[ProviderSpec], by_key: _Index) -> None:
    """Reject singletons that would capture a scoped provider for their lifetime.

    A singleton is built once and lives forever; a scoped provider lives only for
    the duration of a ``scope()``. If a singleton depended on a scoped provider it
    would cache the first scope's instance and silently reuse it across every
    later scope. Transient providers are inlined into their consumer, so a scoped
    provider reached through a chain of transients is captured just the same —
    the walk below looks through transients but stops at singleton boundaries
    (each singleton is validated as its own root).
    """
    for root in order:
        if root.scope is not Scope.SINGLETON:
            continue
        seen: set[_Ident] = set()
        stack: list[tuple[ProviderSpec, tuple[ProviderSpec, ...]]] = [(root, (root,))]
        while stack:
            spec, chain = stack.pop()
            for param in spec.params:
                dep = by_key.get((param.key, param.tag))
                if dep is None:
                    continue
                if dep.scope is Scope.SCOPED:
                    raise CaptiveDependencyError(_format_captive(root, dep, (*chain, dep)))
                if dep.scope is Scope.TRANSIENT:
                    ident = (dep.key, dep.tag)
                    if ident in seen:
                        continue
                    seen.add(ident)
                    stack.append((dep, (*chain, dep)))


def _format_captive(root: ProviderSpec, dep: ProviderSpec, chain: tuple[ProviderSpec, ...]) -> str:
    path = ' -> '.join(fmt_key(s.key) for s in chain)
    return (
        f'captive dependency: singleton {fmt_key(root.key)} depends on scoped {fmt_key(dep.key)} '
        f'(chain: {path}). A singleton outlives every scope, so it would capture one '
        f"scope's {fmt_key(dep.key)} and reuse it across all later scopes. "
        f'Make {fmt_key(root.key)} scoped, or {fmt_key(dep.key)} a singleton.'
    )


def _with_async_flags(order: Iterable[ProviderSpec], by_key: _Index) -> Iterable[ProviderSpec]:
    """Mark every spec that is async itself or depends on one, in dependency order."""
    needs: dict[_Ident, bool] = {}
    for spec in order:
        own = spec.shape in ASYNC_SHAPES
        for param in spec.params:
            dep = by_key.get((param.key, param.tag))
            if dep is not None and needs.get((dep.key, dep.tag), False):
                own = True
                break
        needs[(spec.key, spec.tag)] = own
        yield ProviderSpec(
            key=spec.key,
            tag=spec.tag,
            source=spec.source,
            scope=spec.scope,
            shape=spec.shape,
            needs_async=own,
            params=spec.params,
        )
