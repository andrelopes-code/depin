"""Validates the provider specs and orders them into a `ResolutionPlan`.

This is what `Container.freeze()` runs. Every check here happens before a single
value is constructed: duplicates, unsatisfied dependencies, cycles, captive
singletons, and which providers transitively need async resolution.
"""

import sys
from collections.abc import Iterable
from types import ModuleType
from typing import Final

from depin._core.markers import get_provides
from depin._core.providers import ASYNC_SHAPES, build_specs
from depin._core.scope import Scope
from depin._core.spec import BindRecord, Ident, ProviderKey, ProviderSpec, ResolutionPlan, fmt_chain, fmt_key
from depin.errors import (
    CaptiveDependencyError,
    CircularDependencyError,
    DuplicateProviderError,
    MissingProviderError,
)

type _Index = dict[Ident, ProviderSpec]

INACTIVE_NOTE: Final[str] = '; a conditional binding for this key is registered but inactive'


def build_plan(records: Iterable[BindRecord]) -> ResolutionPlan:
    """Validate the bindings and return the plan the frozen container resolves from.

    Raises:
        DuplicateProviderError: Two bindings share a key and tag.
        MissingProviderError: A required dependency has no provider.
        CircularDependencyError: The graph contains a cycle.
        CaptiveDependencyError: A singleton depends on a scoped provider.
        InvalidProviderError: A binding lacks the type information to infer a key,
            or carries a condition that is neither a bool nor a callable.
        InvalidScopeError: A lifecycle provider is bound as transient.
    """
    specs = build_specs(records)
    _check_duplicates(specs.providers)
    by_key = _index(specs.providers)
    _check_missing(specs.providers, by_key, specs.inactive)
    order = _toposort(specs.providers, by_key)
    _check_captive(order, by_key)
    resolved = tuple(_with_async_flags(order, by_key))
    return ResolutionPlan(order=resolved, by_key=_index(resolved), inactive=specs.inactive)


def _index(specs: Iterable[ProviderSpec]) -> _Index:
    return {(spec.key, spec.tag): spec for spec in specs}


def _check_duplicates(specs: Iterable[ProviderSpec]) -> None:
    seen: set[Ident] = set()
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


def _check_missing(specs: Iterable[ProviderSpec], by_key: _Index, inactive: frozenset[Ident] = frozenset()) -> None:
    all_specs = tuple(specs)
    if not _any_unsatisfied(all_specs, by_key):
        return
    missing: dict[Ident, tuple[tuple[ProviderSpec, ...], ProviderSpec, str]] = {}
    for root in all_specs:
        _collect_missing(root, by_key, (root,), missing)
    # Deepest chain first: the longest resolution path is the most informative
    # one to show when several providers are unsatisfied.
    ordered = sorted(missing.items(), key=lambda kv: len(kv[1][0]), reverse=True)
    lines = [
        format_missing(ident[0], tuple(spec.key for spec in chain), owner.key, param_name, inactive=ident in inactive)
        for ident, (chain, owner, param_name) in ordered
    ]
    if len(lines) == 1:
        raise MissingProviderError(lines[0])
    body = '\n  - '.join(lines)
    raise MissingProviderError(f'{len(lines)} missing providers:\n  - {body}')


def _any_unsatisfied(specs: Iterable[ProviderSpec], by_key: _Index) -> bool:
    """Whether some spec declares a required parameter that no binding provides.

    Exactly the condition `_collect_missing` ends up detecting, but answered in
    one pass over the specs instead of a walk from every root: a parameter is
    unsatisfied where it stands, independently of the chains that reach it, unless
    a default or an optional annotation excuses it. The walk then runs only to
    reconstruct the deepest chain for the error message. `_check_missing` skips
    that walk whenever this returns `False`, so the two must keep agreeing on
    what counts as missing, or a real gap goes unreported.
    """
    return any(
        not param.has_default and not param.optional and (param.key, param.tag) not in by_key
        for spec in specs
        for param in spec.params
    )


def _collect_missing(
    root: ProviderSpec,
    by_key: _Index,
    chain: tuple[ProviderSpec, ...],
    missing: dict[Ident, tuple[tuple[ProviderSpec, ...], ProviderSpec, str]],
) -> None:
    # The walk decides on whether a binding exists, not on whether the parameter
    # also carries a default: a satisfied parameter is traversed either way, which
    # is what keeps this walk and `render._deepest_requirement` agreeing on one
    # chain. Iterative DFS over the dependency graph; each entry is the current
    # spec paired with the chain that led to it, and cycles are broken by the
    # ``id(dep) in chain_specs`` check below and reported by `_toposort`.
    stack: list[tuple[ProviderSpec, tuple[ProviderSpec, ...]]] = [(root, chain)]
    while stack:
        spec, current_chain = stack.pop()
        chain_specs = {id(c) for c in current_chain}
        for param in spec.params:
            dep = by_key.get((param.key, param.tag))
            if dep is None:
                if param.has_default or param.optional:
                    continue
                ident = (param.key, param.tag)
                if ident not in missing or len(current_chain) > len(missing[ident][0]):
                    missing[ident] = (current_chain, spec, param.name)
                continue
            if id(dep) in chain_specs:
                continue
            stack.append((dep, (*current_chain, dep)))


def format_missing(
    key: ProviderKey,
    chain: tuple[ProviderKey, ...],
    owner: ProviderKey,
    param_name: str,
    *,
    inactive: bool = False,
) -> str:
    """The message `build_plan` raises for an unsatisfied parameter.

    Also used by `depin._core.render` for a key that `explain()` is asked about
    and no binding provides, so the two paths report one chain in one wording —
    the note about an inactive conditional binding included.
    """
    suggestions = suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    note = INACTIVE_NOTE if inactive else ''
    return (
        f'no provider for {fmt_key(key)} '
        f'(required by {fmt_key(owner)}.{param_name}; '
        f'resolution chain: {fmt_chain((*chain, key))}){note}{extra}'
    )


_SUGGEST_RESULT_LIMIT = 5


def _loaded_modules() -> list[object]:
    """Snapshot of ``sys.modules``' values, typed as `object`, not `ModuleType`.

    The typeshed stub for ``sys.modules`` promises ``dict[str, ModuleType]``,
    but the runtime does not keep that promise: a failed import leaves `None`
    behind, on every version. On 3.12 only, `typing` also registers
    `typing.io`/`typing.re` as classes standing in for modules; CPython removed
    both in 3.13. Returning `object` keeps the `isinstance` guard in
    `suggest_candidates` meaningful instead of flagged as unreachable by a
    checker that trusts the narrower stub.
    """
    return list(sys.modules.values())


def suggest_candidates(target: object) -> list[str]:
    """Scan loaded modules for `@provides(target)` hints. Used only at error time.

    Candidates are found by walking every module in ``sys.modules`` and every
    attribute in each module's namespace, rather than by scanning the garbage
    collector's object graph: on free-threaded builds, ``gc.get_objects()``
    stops enumerating heap types entirely once any thread has run, so it
    misses classes it previously found and never recovers them. A module scan
    has no such gap. The scan is unbounded and always runs to completion: it
    only happens on a path that is already raising and aborting `freeze()`, so
    walking every loaded module is negligible next to a startup that has
    already failed. Collecting every match and sorting before truncating to
    ``_SUGGEST_RESULT_LIMIT`` is what keeps the reported candidates independent
    of module and attribute iteration order, which is otherwise unspecified.
    """
    if not isinstance(target, type):
        return []

    # Deduped on the emitted string, not `id(obj)`: two distinct classes can
    # share a `__module__` and `__qualname__` (a module reload, a class
    # factory), and an identity-keyed set would let both through, repeating
    # the same name in the reported candidates.
    out: set[str] = set()
    seen: set[int] = set()
    for module in _loaded_modules():
        if not isinstance(module, ModuleType):
            # `sys.modules` entries are conventionally modules, but nothing
            # enforces it: a failed import leaves `None` behind, on every
            # version. On 3.12 only, `typing` also registers `typing.io`/
            # `typing.re` as classes standing in for modules. Neither is a
            # namespace this scan means to walk.
            continue
        for name in list(vars(module)):
            try:
                obj = getattr(module, name)
            except Exception:
                # Best-effort scan: a hostile module `__getattr__`, a lazy-import
                # shim, or a partially initialised module mid circular-import can
                # raise anything on attribute access; none of that may break the
                # error path that is already reporting a different, real failure.
                # This also swallows a `DepinError` raised from the read, which
                # this file's own rule forbids everywhere else — relaxed here on
                # purpose because depin installs no module-level `__getattr__`,
                # making the case practically unreachable.
                continue
            if not isinstance(obj, type) or id(obj) in seen:
                continue
            seen.add(id(obj))
            try:
                found = get_provides(obj)
            except Exception:
                # Same rationale as the module attribute read above: `get_provides`
                # is itself an attribute read (a class whose metaclass defines
                # `__getattr__` can raise anything from it), and it must be no
                # less forgiving than the read that produced `obj`.
                continue
            if found is target:
                out.add(f'{obj.__module__}.{obj.__qualname__}')
    return sorted(out)[:_SUGGEST_RESULT_LIMIT]


def _toposort(specs: Iterable[ProviderSpec], by_key: _Index) -> tuple[ProviderSpec, ...]:
    """Iterative post-order DFS. Frames are ``(spec, next_param_index)``."""
    ordered: list[ProviderSpec] = []
    visited: set[Ident] = set()
    visiting: set[Ident] = set()

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
                chain = fmt_chain(k for k, _ in cycle_path)
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
        reached_from: dict[Ident, ProviderSpec] = {}
        stack: list[ProviderSpec] = [root]
        while stack:
            spec = stack.pop()
            for param in spec.params:
                dep = by_key.get((param.key, param.tag))
                if dep is None:
                    continue
                if dep.scope is Scope.SCOPED:
                    chain = (*_captive_chain(root, spec, reached_from), dep)
                    raise CaptiveDependencyError(_format_captive(root, dep, chain))
                if dep.scope is Scope.TRANSIENT:
                    ident = (dep.key, dep.tag)
                    if ident in reached_from:
                        continue
                    reached_from[ident] = spec
                    stack.append(dep)


def _captive_chain(
    root: ProviderSpec,
    spec: ProviderSpec,
    reached_from: dict[Ident, ProviderSpec],
) -> tuple[ProviderSpec, ...]:
    """Rebuild the ``root -> ... -> spec`` path from the walk's parent links.

    `reached_from` records one parent per transient, because the walk pushes each
    at most once, so following it back from `spec` yields the single path the
    walk took to reach it.
    """
    chain = [spec]
    node = spec
    while (node.key, node.tag) != (root.key, root.tag):
        node = reached_from[(node.key, node.tag)]
        chain.append(node)
    chain.reverse()
    return tuple(chain)


def _format_captive(root: ProviderSpec, dep: ProviderSpec, chain: tuple[ProviderSpec, ...]) -> str:
    path = fmt_chain(s.key for s in chain)
    return (
        f'captive dependency: singleton {fmt_key(root.key)} depends on scoped {fmt_key(dep.key)} '
        f'(chain: {path}). A singleton outlives every scope, so it would capture one '
        f"scope's {fmt_key(dep.key)} and reuse it across all later scopes. "
        f'Make {fmt_key(root.key)} scoped, or {fmt_key(dep.key)} a singleton.'
    )


def _with_async_flags(order: Iterable[ProviderSpec], by_key: _Index) -> Iterable[ProviderSpec]:
    """Mark every spec that is async itself or depends on one, in dependency order."""
    needs: dict[Ident, bool] = {}
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
