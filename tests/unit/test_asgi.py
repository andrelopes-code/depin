"""The shared ASGI middleware, driven by hand-written applications and no framework.

These tests install no web framework and import none. `depin.ext.asgi` speaks
the ASGI protocol structurally, so a plain ``async def app(scope, receive,
send)`` is a legitimate downstream peer — supplying one is not mocking depin,
whose real `FrozenContainer` performs every resolution asserted here.
"""

import asyncio
from collections.abc import Generator

import pytest

from depin import Container, FrozenContainer, Scope, ScopeSeed, Token, optional_hosted_container
from depin.errors import MissingProviderError
from depin.ext.asgi import ASGIScope, Message, RequestScope

REQUEST_ID = Token[str]('request_id')


class Resource:
    """A scoped dependency whose teardown the tests count."""


class DownstreamFailure(Exception):
    """Raised by a downstream application to prove the scope still drains."""


def seeded_container() -> FrozenContainer:
    return Container().scope_value(REQUEST_ID).freeze()


def torn_down_container(torn: list[Resource]) -> FrozenContainer:
    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(item)

    return Container().bind(make, scope=Scope.SCOPED, provides=Resource).freeze()


def scope_of(kind: str, path: str = '/') -> ASGIScope:
    return {'type': kind, 'path': path}


async def receive() -> Message:
    return {'type': 'http.request'}


async def send(message: Message) -> None:
    """Discard the message: nothing here asserts on the response stream."""


def seed_request_id(value: str) -> ScopeSeed:
    return ScopeSeed(REQUEST_ID, value)


async def test_a_lifespan_scope_is_forwarded_with_no_scope_opened() -> None:
    di = seeded_container()
    lifespan = scope_of('lifespan')
    seen: list[tuple[object, object, object, FrozenContainer | None]] = []

    async def app(scope: ASGIScope, recv: object, snd: object) -> None:
        seen.append((scope, recv, snd, optional_hosted_container()))

    await RequestScope(app, di, seed=lambda _: seed_request_id('r-1'))(lifespan, receive, send)

    assert seen == [(lifespan, receive, send, None)]


async def test_an_http_scope_publishes_the_container() -> None:
    di = seeded_container()
    seen: list[FrozenContainer | None] = []

    async def app(_scope: ASGIScope, _receive: object, _send: object) -> None:
        seen.append(optional_hosted_container())

    await RequestScope(app, di)(scope_of('http'), receive, send)

    assert seen == [di]


async def test_an_http_scope_applies_the_seed() -> None:
    di = seeded_container()
    resolved: list[str] = []

    async def app(_scope: ASGIScope, _receive: object, _send: object) -> None:
        resolved.append(await di.aresolve(REQUEST_ID))

    await RequestScope(app, di, seed=lambda _: seed_request_id('r-1'))(scope_of('http'), receive, send)

    assert resolved == ['r-1']


async def test_a_websocket_scope_publishes_the_container_but_applies_no_seed() -> None:
    di = seeded_container()
    seen: list[FrozenContainer | None] = []

    async def app(_scope: ASGIScope, _receive: object, _send: object) -> None:
        seen.append(optional_hosted_container())
        with pytest.raises(MissingProviderError):
            await di.aresolve(REQUEST_ID)

    await RequestScope(app, di, seed=lambda _: seed_request_id('r-1'))(scope_of('websocket'), receive, send)

    assert seen == [di]


async def test_a_seed_returning_none_seeds_nothing() -> None:
    di = seeded_container()
    seen: list[FrozenContainer | None] = []

    async def app(_scope: ASGIScope, _receive: object, _send: object) -> None:
        seen.append(optional_hosted_container())
        with pytest.raises(MissingProviderError):
            await di.aresolve(REQUEST_ID)

    await RequestScope(app, di, seed=lambda _: None)(scope_of('http'), receive, send)

    assert seen == [di]


async def test_no_seed_at_all_behaves_like_a_seed_returning_none() -> None:
    di = seeded_container()
    seen: list[FrozenContainer | None] = []

    async def app(_scope: ASGIScope, _receive: object, _send: object) -> None:
        seen.append(optional_hosted_container())
        with pytest.raises(MissingProviderError):
            await di.aresolve(REQUEST_ID)

    await RequestScope(app, di)(scope_of('http'), receive, send)

    assert seen == [di]


async def test_a_scoped_teardown_runs_once_per_request_and_the_next_request_is_fresh() -> None:
    torn: list[Resource] = []
    di = torn_down_container(torn)
    built: list[Resource] = []

    async def app(_scope: ASGIScope, _receive: object, _send: object) -> None:
        built.append(await di.aresolve(Resource))

    middleware = RequestScope(app, di)

    await middleware(scope_of('http'), receive, send)
    after_first = list(torn)
    await middleware(scope_of('http'), receive, send)

    assert after_first == built[:1]
    assert torn == built
    assert built[0] is not built[1]


async def test_a_downstream_exception_propagates_and_the_scope_still_drains() -> None:
    torn: list[Resource] = []
    di = torn_down_container(torn)

    async def app(_scope: ASGIScope, _receive: object, _send: object) -> None:
        await di.aresolve(Resource)
        raise DownstreamFailure

    with pytest.raises(DownstreamFailure):
        await RequestScope(app, di)(scope_of('http'), receive, send)

    assert len(torn) == 1
    assert optional_hosted_container() is None


async def test_two_concurrent_requests_each_see_their_own_seed() -> None:
    di = seeded_container()
    entered = asyncio.Event()
    released = asyncio.Event()
    seen: dict[object, str] = {}

    def seed(scope: ASGIScope) -> ScopeSeed:
        return ScopeSeed(REQUEST_ID, scope['path'])

    async def app(scope: ASGIScope, _receive: object, _send: object) -> None:
        path = scope['path']
        if path == '/first':
            entered.set()
            await released.wait()
        else:
            await entered.wait()
        seen[path] = await di.aresolve(REQUEST_ID)
        released.set()

    middleware = RequestScope(app, di, seed=seed)

    await asyncio.gather(
        middleware(scope_of('http', '/first'), receive, send),
        middleware(scope_of('http', '/second'), receive, send),
    )

    assert seen == {'/first': '/first', '/second': '/second'}
