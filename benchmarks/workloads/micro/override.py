"""Provider override workload definitions."""

import contextlib

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation
from depin import Container

from .core import Indirect, Sole, Substitute, Wired, _sole


def _resolve_with_no_active_override() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(_sole).freeze()
        _ = frozen.resolve(Sole)
        return Session(
            call=lambda: frozen.resolve(Sole),
            observe=lambda: Observation(result=type(frozen.resolve(Sole)).__name__, constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Wired(Sole())
        return Session(
            call=lambda: held.value,
            observe=lambda: Observation(result=type(held.value).__name__, constructed=(), closed=()),
        )

    return Workload(
        name='resolve_with_no_active_override',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does the override check cost on a resolution nothing has overridden?',
            work='Return a cached singleton from a one-provider graph with the override stack empty.',
            included='The key lookup, the ContextVar read that finds no override, and the cache read.',
            excluded='Declaration, freeze, and the construction of the singleton, all done in setup.',
            semantics='Singleton. The cache is warm before the first timed call, so nothing is constructed.',
            shape='One provider with no dependencies; its key is resolved.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The production case: `overrides.active` is on every resolution, and in a deployed process it '
                'always takes the empty branch.',
                'The control the override and generic-key workloads are read against. All three resolve one '
                'provider, so the difference between them is the feature and not the graph.',
            ),
            invalid=(
                'Not an isolated cost for the ContextVar read: the whole resolution is timed, and the read is '
                'a part of it.',
                'Not a different measurement from `resolve_cached_singleton` in kind — only in graph size, '
                'which the baseline measured flat within 3% over 1 to 300 nodes.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _resolve_through_an_active_override() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(_sole).freeze()
        stack = contextlib.ExitStack()
        _ = stack.enter_context(frozen.override(Sole, Substitute()))
        _ = frozen.resolve(Sole)
        return Session(
            call=lambda: frozen.resolve(Sole),
            observe=lambda: Observation(result=type(frozen.resolve(Sole)).__name__, constructed=(), closed=()),
            close=stack.close,
        )

    def direct_setup() -> Session:
        held = Indirect(Wired(Substitute()))
        return Session(
            call=lambda: held.inner.value,
            observe=lambda: Observation(result=type(held.inner.value).__name__, constructed=(), closed=()),
        )

    return Workload(
        name='resolve_through_an_active_override',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does a resolution cost while an override for that key is installed?',
            work='Return the replacement value for a key one active override substitutes.',
            included=(
                'The key lookup, the ContextVar read that finds the override, and the transient spec the '
                'override is wrapped in on every lookup.'
            ),
            excluded='Declaration, freeze, and entering the override, all done in setup.',
            semantics=(
                'The override is a value, not a factory, so nothing is constructed. The substituted spec is '
                'transient, so no cache is consulted and the registered singleton is never reached.'
            ),
            shape='One provider with no dependencies, with one override installed over its key.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'What using an override costs, read as the difference from `resolve_with_no_active_override`: '
                'the branch that fires against the branch that does not.',
                'The ratio to the direct implementation, which reaches a held object through one indirection.',
            ),
            invalid=(
                'Not a production figure. An override is a testing seam, and a deployed process installs none.',
                'Not the cost of installing or leaving an override, which happens once and is in setup.',
                'Not the cost of an override whose replacement is a factory, which is called per resolution.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )
