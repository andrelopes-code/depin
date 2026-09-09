"""Component measurements for the FastAPI lazy integration path."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient, Response

from benchmarks.contracts import Claim, Implementation, Metric, Observation, Prepared, Tier, Workload
from benchmarks.workloads.shell import CONCURRENCY, Session
from depin import Container, FrozenContainer, Scope
from depin.ext._fastapi import FastAPIObservation, install_for_observation
from depin.ext.fastapi import Inject, install


@dataclass(slots=True)
class _Trace:
    constructed: list[str]
    closed: list[str]
    frames: int
    programs: int

    def __init__(self) -> None:
        self.constructed = []
        self.closed = []
        self.frames = 0
        self.programs = 0


class _Singleton:
    def __init__(self, value: str) -> None:
        self.value = value


class _ScopedValue:
    def __init__(self, trace: _Trace) -> None:
        self.value = 'scoped'
        trace.constructed.append('ScopedValue')


class _AsyncResource:
    def __init__(self, trace: _Trace) -> None:
        self.value = 'resource'
        self._trace = trace
        trace.constructed.append('AsyncResource')

    def close(self) -> None:
        self._trace.closed.append('AsyncResource')


def _claim(question: str, work: str, semantics: str) -> Claim:
    return Claim(
        question=question,
        work=work,
        included='One installed FastAPI route invocation through the in-process ASGI transport.',
        excluded='Application construction, container freeze, client construction, and route priming.',
        semantics=semantics,
        shape='One FastAPI route and the smallest dependency graph needed for this integration transition.',
        concurrency=CONCURRENCY,
        metric=Metric.LATENCY,
        unit='seconds per operation',
        valid=('The isolated contribution of this named FastAPI integration transition.',),
        invalid=('Not a served-application throughput or network-latency measurement.',),
    )


def _workload(
    name: str,
    claim: Claim,
    build: Callable[[_Trace, Callable[[FastAPI, FrozenContainer], None]], FastAPI],
    *,
    path: str = '/',
) -> Workload:
    def setup(observation: FastAPIObservation | None) -> Session:
        trace = _Trace()

        def install_route(app: FastAPI, container: FrozenContainer) -> None:
            if observation is None:
                install(app, container)
            else:
                install_for_observation(app, container, observation)

        app = build(trace, install_route)
        loop = asyncio.new_event_loop()
        client = AsyncClient(transport=ASGITransport(app=app), base_url='http://bench')

        def request() -> Response:
            return loop.run_until_complete(client.get(path))

        def observe() -> Observation:
            response = request()
            if observation is not None:
                trace.frames = observation.frames
                trace.programs = observation.programs
            return Observation(
                result=f'{response.status_code} {response.text}; frames={trace.frames}; programs={trace.programs}',
                constructed=tuple(trace.constructed),
                closed=tuple(trace.closed),
            )

        def close() -> None:
            loop.run_until_complete(client.aclose())
            loop.close()

        return Session(call=request, observe=observe, close=close)

    def prepare() -> Prepared:
        session = setup(None)
        return Prepared(call=session.call, close=session.close)

    def observe() -> Observation:
        session = setup(FastAPIObservation())
        try:
            return session.observe()
        finally:
            if session.close is not None:
                session.close()

    return Workload(name=name, tier=Tier.COMPONENT, claim=claim, subject=Implementation('depin', prepare, observe))


def _lazy_host_publication(trace: _Trace, install_route: Callable[[FastAPI, FrozenContainer], None]) -> FastAPI:
    app = FastAPI()

    async def endpoint() -> dict[str, str]:
        return {'value': 'plain'}

    app.add_api_route('/', endpoint, methods=['GET'])
    install_route(app, Container().freeze())
    return app


def _lazy_frame_activation(trace: _Trace, install_route: Callable[[FastAPI, FrozenContainer], None]) -> FastAPI:
    def provide_scoped_value() -> _ScopedValue:
        return _ScopedValue(trace)

    app = FastAPI()

    async def endpoint(value: Inject[_ScopedValue]) -> dict[str, str]:
        return {'value': value.value}

    app.add_api_route('/', endpoint, methods=['GET'])
    install_route(app, Container().bind(provide_scoped_value, scope=Scope.SCOPED).freeze())
    return app


def _one_key_program(trace: _Trace, install_route: Callable[[FastAPI, FrozenContainer], None]) -> FastAPI:
    def provide_value() -> _Singleton:
        return _Singleton('singleton')

    app = FastAPI()

    async def endpoint(value: Inject[_Singleton]) -> dict[str, str]:
        return {'value': value.value}

    app.add_api_route('/', endpoint, methods=['GET'])
    install_route(app, Container().bind(provide_value).freeze())
    return app


def _many_key_program(trace: _Trace, install_route: Callable[[FastAPI, FrozenContainer], None]) -> FastAPI:
    class Left(_Singleton):
        pass

    class Right(_Singleton):
        pass

    def provide_left() -> Left:
        return Left('one')

    def provide_right() -> Right:
        return Right('two')

    app = FastAPI()

    async def endpoint(left: Inject[Left], right: Inject[Right]) -> dict[str, str]:
        return {'left': left.value, 'right': right.value}

    app.add_api_route('/', endpoint, methods=['GET'])
    install_route(app, Container().bind(provide_left).bind(provide_right).freeze())
    return app


def _request_seed_read(trace: _Trace, install_route: Callable[[FastAPI, FrozenContainer], None]) -> FastAPI:
    app = FastAPI()

    async def endpoint(request: Inject[Request]) -> dict[str, str]:
        trace.constructed.append('RequestSeed')
        return {'path': request.url.path}

    app.add_api_route('/seed', endpoint, methods=['GET'])
    install_route(app, Container().scope_value(Request).freeze())
    return app


def _async_resource_close(trace: _Trace, install_route: Callable[[FastAPI, FrozenContainer], None]) -> FastAPI:
    async def provide_resource() -> AsyncGenerator[_AsyncResource]:
        resource = _AsyncResource(trace)
        try:
            yield resource
        finally:
            resource.close()

    app = FastAPI()

    async def endpoint(resource: Inject[_AsyncResource]) -> dict[str, str]:
        return {'value': resource.value}

    app.add_api_route('/', endpoint, methods=['GET'])
    install_route(app, Container().bind(provide_resource, scope=Scope.SCOPED).freeze())
    return app


WORKLOADS: tuple[Workload, ...] = (
    _workload(
        'fastapi_lazy_host_publication',
        _claim(
            'What does lazy FastAPI host publication cost without injection?',
            'Serve one plain route.',
            'No frame opens.',
        ),
        _lazy_host_publication,
    ),
    _workload(
        'fastapi_lazy_frame_activation_and_drain',
        _claim(
            'What does first lazy frame activation and drain cost?',
            'Resolve one scoped route value.',
            'One frame opens.',
        ),
        _lazy_frame_activation,
    ),
    _workload(
        'fastapi_endpoint_program_one_key',
        _claim(
            'What does one compiled endpoint program with one key cost?',
            'Resolve one singleton route value.',
            'No frame opens.',
        ),
        _one_key_program,
    ),
    _workload(
        'fastapi_endpoint_program_many_keys',
        _claim(
            'What does one compiled endpoint program with multiple keys cost?',
            'Resolve two singleton route values.',
            'No frame opens.',
        ),
        _many_key_program,
    ),
    _workload(
        'fastapi_request_seed_read',
        _claim(
            'What does reading the lazy FastAPI request seed cost?',
            'Resolve the FastAPI Request route value.',
            'One frame opens.',
        ),
        _request_seed_read,
        path='/seed',
    ),
    _workload(
        'fastapi_async_resource_close',
        _claim(
            'What does async resource close cost after activation?',
            'Resolve and close one scoped async resource.',
            'One frame opens and drains.',
        ),
        _async_resource_close,
    ),
)
