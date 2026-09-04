"""Construction and resource-teardown workload definitions."""

import contextlib
from collections.abc import Callable, Generator, Iterator

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation
from depin import Container, Scope

from .core import Connection, Sole, sole


def construct_a_singleton_for_the_first_time() -> Workload:
    def recording(log: list[str]) -> Callable[[], Sole]:
        def provide() -> Sole:
            log.append(Sole.__name__)
            return Sole()

        return provide

    def depin_setup() -> Session:
        frozen = Container().bind(sole).freeze()
        _ = frozen.resolve(Sole)

        def cold() -> object:
            frozen.reset()
            return frozen.resolve(Sole)

        log: list[str] = []
        observed = Container().bind(recording(log)).freeze()
        _ = observed.resolve(Sole)

        def observe() -> Observation:
            observed.reset()
            log.clear()
            value = observed.resolve(Sole)
            return Observation(result=type(value).__name__, constructed=tuple(log), closed=())

        return Session(call=cold, observe=observe)

    def direct_setup() -> Session:
        cache: dict[type[Sole], Sole] = {Sole: Sole()}

        def cold() -> object:
            cache.clear()
            cache[Sole] = Sole()
            return cache[Sole]

        def observe() -> Observation:
            cache.clear()
            log = [Sole.__name__]
            cache[Sole] = Sole()
            return Observation(result=type(cache[Sole]).__name__, constructed=tuple(log), closed=())

        return Session(call=cold, observe=observe)

    return Workload(
        name='construct_a_singleton_for_the_first_time',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does the first resolution of a singleton cost, before anything is cached?',
            work='Drop the singleton cache and resolve the key again, so the value is constructed.',
            included=(
                'The cache being dropped, the lookup, the construction, and the cache write. Dropping is '
                'inside the timed region because there is no other way to reach a cold cache repeatedly, and '
                'the direct implementation clears its own one-entry cache for the same reason.'
            ),
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Singleton. Every timed call constructs exactly one value, because the provider it drops has '
                'no dependencies and registers no teardown for the drop to run.'
            ),
            shape='One provider with no dependencies; its key is resolved from cold.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The cold path, read against `resolve_with_no_active_override`, which is the same lookup with '
                'the value already there.',
                'The ratio to the direct implementation, which clears and refills the same one-entry cache.',
            ),
            invalid=(
                'Not a startup figure for a real graph: one provider is constructed here, and a startup builds '
                'all of them in dependency order.',
                'Not the cost of `reset()` as an operation, which is measured here only over an empty teardown record.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def _sync_resource() -> Callable[[], Iterator[Connection]]:
    def provide() -> Iterator[Connection]:
        yield Connection()

    return provide


def _recording_sync_resource(log: list[str]) -> Callable[[], Iterator[Connection]]:
    """`_sync_resource`, naming the resource in `log` as it opens and as it closes.

    A separate factory rather than a flag inside the provider, so the timed
    implementation carries no branch the observed one needs.
    """

    def provide() -> Iterator[Connection]:
        log.append(f'open {Connection.__name__}')
        yield Connection()
        log.append(f'close {Connection.__name__}')

    return provide


def resolve_a_sync_resource_with_teardown() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(_sync_resource(), provides=Connection, scope=Scope.SCOPED).freeze()

        def cycle() -> object:
            with frozen.scope():
                return frozen.resolve(Connection)

        log: list[str] = []
        observed = Container().bind(_recording_sync_resource(log), provides=Connection, scope=Scope.SCOPED).freeze()

        def observe() -> Observation:
            log.clear()
            with observed.scope():
                value = observed.resolve(Connection)
            return Observation(
                result=type(value).__name__,
                constructed=tuple(event.removeprefix('open ') for event in log if event.startswith('open ')),
                closed=tuple(event.removeprefix('close ') for event in log if event.startswith('close ')),
            )

        return Session(call=cycle, observe=observe)

    def direct_setup() -> Session:
        @contextlib.contextmanager
        def hold() -> Generator[Connection]:
            yield Connection()

        def cycle() -> object:
            with hold() as connection:
                return connection

        def observe() -> Observation:
            log: list[str] = []

            @contextlib.contextmanager
            def recording() -> Generator[Connection]:
                log.append('open')
                yield Connection()
                log.append('close')

            with recording() as connection:
                value = connection
            return Observation(
                result=type(value).__name__,
                constructed=tuple(Connection.__name__ for event in log if event == 'open'),
                closed=tuple(Connection.__name__ for event in log if event == 'close'),
            )

        return Session(call=cycle, observe=observe)

    return Workload(
        name='resolve_a_sync_resource_with_teardown',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does one resource with a teardown cost, from open to drain?',
            work='Enter a scope, resolve one generator-backed resource, and leave the scope so it is closed.',
            included='Frame creation, one resolution, the generator entered, the teardown recorded, and the drain.',
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Scoped. The resource is constructed once per scope, its teardown registered on construction, '
                'and run when the scope closes.'
            ),
            shape='One scoped generator provider; the resource is resolved inside one scope.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'What teardown adds to a scope, read against `open_and_close_a_scope`, whose providers register none.',
                'The ratio to the direct implementation, a handwritten context manager doing the same work.',
            ),
            invalid=(
                'Not an async teardown, which runs on a different path and through an event loop.',
                'Not a per-resource cost transferable to a scope holding many: `scale_scope_teardown` is the '
                'curve for that.',
                'Not the teardown path after a failure, where the drain collects exceptions instead.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )
