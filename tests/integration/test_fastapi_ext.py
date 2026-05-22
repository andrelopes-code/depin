import pytest
from fastapi import FastAPI, Request as FastAPIRequest
from httpx import ASGITransport, AsyncClient

from depin import Container, Scope
from depin.ext.fastapi import Inject, RequestScope


@pytest.mark.asyncio
async def test_request_scope_middleware_opens_scope_per_request() -> None:
    class Counter:
        def __init__(self) -> None:
            self.value = 0

        def tick(self) -> int:
            self.value += 1
            return self.value

    frozen = Container().bind(Counter, scope=Scope.SCOPED).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    # FastAPI consumes the route via @app.get; the function binding looks unused statically.
    @app.get('/tick')
    async def _tick(c: Counter = Inject(Counter)) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {'n': c.tick(), 'again': c.tick()}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r1 = await client.get('/tick')
        r2 = await client.get('/tick')
    assert r1.json() == {'n': 1, 'again': 2}
    assert r2.json() == {'n': 1, 'again': 2}


@pytest.mark.asyncio
async def test_request_is_available_as_scoped_dependency() -> None:
    class Probe:
        def __init__(self, request: FastAPIRequest) -> None:
            self.path = request.url.path

    frozen = (
        Container()
        .frame_provides(FastAPIRequest)
        .bind(Probe, scope=Scope.SCOPED)
        .freeze()
    )

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    # FastAPI consumes the route via @app.get; the function binding looks unused statically.
    @app.get('/probe/{x}')
    async def _probe(p: Probe = Inject(Probe)) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {'p': p.path}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        r = await client.get('/probe/abc')
    assert r.json() == {'p': '/probe/abc'}
