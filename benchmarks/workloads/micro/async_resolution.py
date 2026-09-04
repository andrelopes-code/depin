"""Asynchronous resolution workload definitions."""

import asyncio

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.workloads.shell import Session, implementation
from depin import Container, Scope

from .core import Pool, ready


def resolve_an_async_singleton() -> Workload:
    def depin_setup() -> Session:
        async def make() -> Pool:
            return Pool()

        frozen = Container().bind(make, provides=Pool, scope=Scope.SINGLETON).freeze()
        loop = asyncio.new_event_loop()
        _ = loop.run_until_complete(frozen.aresolve(Pool))
        return Session(
            call=lambda: loop.run_until_complete(frozen.aresolve(Pool)),
            observe=lambda: Observation(
                result=type(loop.run_until_complete(frozen.aresolve(Pool))).__name__,
                constructed=(),
                closed=(),
            ),
            close=loop.close,
        )

    def direct_setup() -> Session:
        held = Pool()
        loop = asyncio.new_event_loop()
        _ = loop.run_until_complete(ready(held))
        return Session(
            call=lambda: loop.run_until_complete(ready(held)),
            observe=lambda: Observation(
                result=type(loop.run_until_complete(ready(held))).__name__,
                constructed=(),
                closed=(),
            ),
            close=loop.close,
        )

    return Workload(
        name='resolve_an_async_singleton',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does depin add to driving one coroutine through an event loop?',
            work='Await a cached singleton whose provider is a coroutine function, and return it.',
            included=(
                'The event loop boundary. The baseline measured 19.614 µs for this against 16.093 µs for the '
                'bare coroutine, so 82% of the timed region is asyncio.'
            ),
            excluded='Loop creation, declaration, freeze, and the construction of the singleton, all done in setup.',
            semantics='Singleton. The cache is warm before the first timed call, so nothing is constructed.',
            shape='One provider with no dependencies, bound from a coroutine function.',
            concurrency='Single-threaded; one event loop for the whole measurement, driven by run_until_complete.',
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The difference from the direct implementation, which drives a bare coroutine through the same '
                'loop boundary. That difference — about 3.5 µs when the baseline measured it — is depin.',
            ),
            invalid=(
                'Not the cost of an async resolution: most of the timed region is asyncio, which is why the '
                'direct implementation is the same loop call around a coroutine that does nothing.',
                'Not the cost of constructing an async provider, which happens once, in setup.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )
