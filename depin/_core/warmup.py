"""Constructing every singleton at boot, and the report over what was built.

The walk itself belongs to `FrozenContainer`, which owns resolution; this module
owns the rule for which providers a warmup touches, the rule that refuses to
drive an async one without a loop, and the shape of the report.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import final

from depin._core.diagnostics import DependencyGraph, GraphNode
from depin._core.scope import Scope
from depin._core.spec import ProviderSpec, ResolutionPlan, fmt_key
from depin.errors import AsyncInSyncContextError


@final
@dataclass(frozen=True, slots=True)
class WarmupReport:
    """What a `FrozenContainer.warmup` call did, node by node.

    Both tuples are in resolution order, and both hold the same `GraphNode` the
    dependency graph exposes, so a caller reads a warmed provider's key, scope,
    shape, and dependencies off the node it already has.

    Attributes:
        constructed: Singletons this call built.
        cached: Singletons that were already built when the call began.

    Example:
        ```pycon
        >>> from depin import Container
        >>> class Config: ...
        >>> di = Container().bind(Config).freeze()
        >>> report = di.warmup()
        >>> [node.key.__qualname__ for node in report.constructed]
        ['Config']
        >>> di.warmup().cached == report.constructed
        True

        ```
    """

    constructed: tuple[GraphNode, ...]
    cached: tuple[GraphNode, ...]


def singleton_specs(plan: ResolutionPlan) -> tuple[ProviderSpec, ...]:
    """The providers a warmup builds: the singletons, in resolution order.

    A scoped value belongs to a scope and a transient one is never cached, so
    neither has a boot-time instance to build.
    """
    return tuple(spec for spec in plan.order if spec.scope is Scope.SINGLETON)


def reject_async_singletons(specs: Iterable[ProviderSpec]) -> None:
    """Refuse a synchronous warmup over singletons that need an event loop.

    Raised before anything is constructed, so a refusal leaves the container as
    it was rather than half warm.

    Raises:
        AsyncInSyncContextError: Some singleton needs async resolution.
    """
    pending = tuple(spec.key for spec in specs if spec.needs_async)
    if not pending:
        return
    names = ', '.join(fmt_key(key) for key in pending)
    raise AsyncInSyncContextError(
        f'warmup() cannot construct {names}: they require async resolution. Call awarmup() instead.'
    )


def warmup_report(
    graph: DependencyGraph,
    constructed: Sequence[ProviderSpec],
    cached: Sequence[ProviderSpec],
) -> WarmupReport:
    return WarmupReport(
        constructed=tuple(graph.node(spec.key, tag=spec.tag) for spec in constructed),
        cached=tuple(graph.node(spec.key, tag=spec.tag) for spec in cached),
    )
