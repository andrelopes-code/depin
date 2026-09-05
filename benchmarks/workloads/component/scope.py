"""Component workload for a request-shaped scope."""

from benchmarks.contracts import Claim, Metric, Observation, Tier, Workload
from benchmarks.workloads.component.primitives import (
    INCOMING,
    REQUEST,
    DatabaseSession,
    RequestHandler,
    request_observation,
)
from benchmarks.workloads.shell import CONCURRENCY, Session, implementation
from depin import Container, Scope


def open_a_request_shaped_scope() -> Workload:
    def depin_setup() -> Session:
        frozen = (
            Container()
            .scope_value(REQUEST)
            .bind(DatabaseSession, scope=Scope.SCOPED)
            .bind(RequestHandler, scope=Scope.SCOPED)
            .freeze()
        )

        def run() -> object:
            with frozen.scope() as frame:
                frame.provide(REQUEST, INCOMING)
                return frozen.resolve(RequestHandler)

        def observe() -> Observation:
            with frozen.scope() as frame:
                frame.provide(REQUEST, INCOMING)
                return request_observation(frozen.resolve(RequestHandler))

        return Session(call=run, observe=observe)

    def direct_setup() -> Session:
        def run() -> RequestHandler:
            seeded: dict[str, str] = {'request': INCOMING}
            built: dict[type[object], object] = {}
            session = DatabaseSession(seeded['request'])
            built[DatabaseSession] = session
            handler = RequestHandler(session, seeded['request'])
            built[RequestHandler] = handler
            built.clear()
            seeded.clear()
            return handler

        return Session(call=run, observe=lambda: request_observation(run()))

    return Workload(
        name='open_a_request_shaped_scope',
        tier=Tier.COMPONENT,
        claim=Claim(
            question='What does one request cost an integration that opens a scope, seeds it, and resolves?',
            work='Open a scope, seed one value into it, construct two scoped objects, and leave the scope.',
            included='Frame creation, the seed, two resolutions with their constructions, and the drain on exit.',
            excluded='Declaration and freeze, both done in setup.',
            semantics=(
                'Scoped. Both values are built once per scope and dropped on exit. The seeded token is provided '
                'into the frame rather than bound to a provider.'
            ),
            shape='One seeded token and two scoped providers, one of which depends on the other.',
            concurrency=CONCURRENCY,
            metric=Metric.LATENCY,
            unit='seconds per operation',
            valid=(
                'The per-request overhead of the scope shape every integration runs.',
                'The ratio to constructing the same two objects into a per-request map by hand.',
            ),
            invalid=(
                'Not an end-to-end request cost: no framework, routing, or transport is in the timed region.',
                'Not the cost of teardown: neither provider here registers one.',
            ),
        ),
        subject=implementation('depin', depin_setup),
        baseline=implementation('direct', direct_setup),
    )
