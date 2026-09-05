"""Scoped and injection workload definitions."""

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.graphs import build_chain, chain_types
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation, recording_chain
from depin import Container, Scope, injected

from .core import CHAIN_DEPTH, Repo


def open_and_close_a_scope() -> Workload:
    def depin_setup() -> Session:
        container, leaf = build_chain(CHAIN_DEPTH, scope=Scope.SCOPED)
        frozen = container.freeze()
        log: list[str] = []
        observed, observed_leaf = recording_chain(CHAIN_DEPTH, Scope.SCOPED, log)
        observed_frozen = observed.freeze()

        def cycle() -> object:
            with frozen.scope():
                return frozen.resolve(leaf)

        def observe() -> Observation:
            log.clear()
            with observed_frozen.scope():
                value = observed_frozen.resolve(observed_leaf)
            return Observation(result=type(value).__name__, constructed=tuple(log), closed=())

        return Session(call=cycle, observe=observe)

    def direct_setup() -> Session:
        nodes = chain_types(CHAIN_DEPTH)

        def cycle() -> object:
            cache: dict[type[object], object] = {}
            for node in nodes:
                cache[node] = node()
            made = cache[nodes[-1]]
            cache.clear()
            return made

        def observe() -> Observation:
            log: list[str] = []
            cache: dict[type[object], object] = {}
            for node in nodes:
                log.append(node.__name__)
                cache[node] = node()
            made = cache[nodes[-1]]
            cache.clear()
            return Observation(result=type(made).__name__, constructed=tuple(log), closed=())

        return Session(call=cycle, observe=observe)

    return Workload(
        name='open_and_close_a_scope',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does one scope cost, from entry to teardown?',
            work=f'Enter a scope, construct {CHAIN_DEPTH} scoped objects through one resolution, and leave it.',
            included='Frame creation, one resolution per node, the scoped cache, and the drain on exit.',
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Scoped. Every value is built once per scope and dropped on exit. No provider here registers a '
                'teardown, so the drain runs over an empty record list.'
            ),
            shape=f'A linear chain of {CHAIN_DEPTH} scoped providers; the leaf is resolved inside one scope.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=('A regression alarm on the scope path, against its own measured band.',),
            invalid=(
                'Not an absolute figure worth publishing: the baseline measured this the noisiest case in the '
                'suite, 7.0% run to run and 13.8% under the paired protocol, and both mitigations tried on it '
                'were rejected on their own data.',
                'Not the cost of teardown: no provider here has one to run.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def call_through_an_inject_wrapper() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(Repo).freeze()

        @frozen.inject
        def handler(repo: Repo = injected) -> int:
            return repo.count()

        _ = handler()
        return Session(
            call=handler,
            observe=lambda: Observation(result=str(handler()), constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Repo()

        def handler(repo: Repo = held) -> int:
            return repo.count()

        return Session(
            call=handler,
            observe=lambda: Observation(result=str(handler()), constructed=(), closed=()),
        )

    return Workload(
        name='call_through_an_inject_wrapper',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does calling a function whose dependency depin supplies cost?',
            work='Call a one-parameter function that returns a value read off its dependency.',
            included='The wrapper dispatch, the resolution of the one injected parameter, and the call itself.',
            excluded='Declaration, freeze, wrapping, and the construction of the dependency, all done in setup.',
            semantics='Singleton dependency, cached before the first timed call.',
            shape='One provider with no dependencies, injected into one function.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=('The dispatch overhead of `@inject`, as the ratio to calling the same function directly.',),
            invalid=(
                'Not a per-parameter cost: one parameter is injected, and the wrapper is entered once either way.',
                'Not an async call, which goes through a different wrapper.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )


def call_through_an_inject_wrapper_with_explicit_arguments() -> Workload:
    def depin_setup() -> Session:
        frozen = Container().bind(Repo).freeze()

        @frozen.inject
        def handler(offset: int, repo: Repo = injected) -> int:
            return repo.count() + offset

        _ = handler(1)
        return Session(
            call=lambda: handler(1),
            observe=lambda: Observation(result=str(handler(1)), constructed=(), closed=()),
        )

    def direct_setup() -> Session:
        held = Repo()

        def handler(offset: int, repo: Repo = held) -> int:
            return repo.count() + offset

        return Session(
            call=lambda: handler(1),
            observe=lambda: Observation(result=str(handler(1)), constructed=(), closed=()),
        )

    return Workload(
        name='call_through_an_inject_wrapper_with_explicit_arguments',
        tier=Tier.ISOLATED,
        claim=Claim(
            question='What does an argument the caller supplies add to an injected call?',
            work='Call a two-parameter function with one argument supplied and one injected.',
            included='The wrapper dispatch, the argument the caller passed, the resolution of the injected one.',
            excluded='Declaration, freeze, wrapping, and the construction of the dependency, all done in setup.',
            semantics='Singleton dependency, cached before the first timed call.',
            shape='One provider with no dependencies, injected into a function that also takes one argument.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'What a supplied argument costs the wrapper, read as the difference from '
                '`call_through_an_inject_wrapper`, which supplies none.',
                'The ratio to calling the same two-parameter function directly.',
            ),
            invalid=(
                'Not a per-argument cost: one argument is supplied, and the wrapper is entered once either way.',
                'Not an async call, which goes through a different wrapper.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )
