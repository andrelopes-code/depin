"""Measurement setup and observation for application deployments."""

import asyncio
import time

from httpx import ASGITransport, AsyncClient, Response
from starlette.routing import Route

from benchmarks.contracts import Cost, Implementation, Observation, Prepared

from .model import Builder, NullSink, TraceSink, WorkloadError


def prepare_request(build: Builder, path: str) -> Prepared:
    """Open the loop, the transport and the client, prime the route, and hand back one request.

    Everything a request does not pay for on the steady path is done here: the
    loop, the ASGI transport, the client, the singleton warmup, and one primed
    request that absorbs route-matching and first-scope costs.
    """
    deployment = build(NullSink())
    loop = asyncio.new_event_loop()
    client = AsyncClient(transport=ASGITransport(app=deployment.app), base_url='http://bench')

    def close() -> None:
        loop.run_until_complete(client.aclose())
        loop.close()

    try:
        loop.run_until_complete(deployment.warm())
        primed = loop.run_until_complete(client.get(path))
        if primed.status_code != 200:
            raise WorkloadError(f'{path} answered {primed.status_code}: {primed.text}')
    except BaseException:
        close()
        raise

    def call() -> object:
        started = time.process_time_ns()
        _: Response = loop.run_until_complete(client.get(path))
        return Cost(cpu_nanoseconds=time.process_time_ns() - started)

    return Prepared(call=call, close=close)


def observe_request(build: Builder, path: str) -> Observation:
    """Run one request with a recording sink, after warmup, and report what it built and closed."""
    sink = TraceSink()
    deployment = build(sink)
    loop = asyncio.new_event_loop()
    client = AsyncClient(transport=ASGITransport(app=deployment.app), base_url='http://bench')
    try:
        loop.run_until_complete(deployment.warm())
        sink.reset()
        response = loop.run_until_complete(client.get(path))
        loop.run_until_complete(client.aclose())
    finally:
        loop.close()
    return Observation(
        result=f'{response.status_code} {response.text}', constructed=sink.constructed, closed=sink.disposed
    )


def prepare_startup(build: Builder) -> Prepared:
    def call() -> object:
        started = time.process_time_ns()
        _ = build(NullSink())
        return Cost(cpu_nanoseconds=time.process_time_ns() - started)

    return Prepared(call=call)


def observe_startup(build: Builder) -> Observation:
    sink = TraceSink()
    deployment = build(sink)
    paths = sorted(route.path for route in deployment.app.routes if isinstance(route, Route))
    return Observation(result=' '.join(paths), constructed=sink.constructed, closed=sink.disposed)


def request_implementations(label: str, build: Builder, path: str) -> Implementation:
    return Implementation(
        label=label, prepare=lambda: prepare_request(build, path), observe=lambda: observe_request(build, path)
    )
