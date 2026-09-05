"""The shared WSGI middleware, driven by hand-written applications and no framework.

These tests install no web framework and import none. `depin.ext.wsgi` speaks
the WSGI protocol structurally, so a plain ``def app(environ, start_response)``
is a legitimate downstream peer — supplying one is not mocking depin, whose
real `FrozenContainer` performs every resolution asserted here.
"""

from collections.abc import Generator, Iterable

import pytest

from depin import Container, FrozenContainer, Scope, ScopeSeed, Token, hosted_container, optional_hosted_container
from depin.errors import ContainerNotBoundError, MissingProviderError
from depin.ext.wsgi import Environ, RequestScope

REQUEST_ID = Token[str]('request_id')

NO_CONTAINER = (
    'no container is hosted in this context; open a scope with Host.scope() or Host.ascope(), '
    'or publish one with Host.activated()'
)


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


def environ_of(path: str = '/') -> Environ:
    return {'REQUEST_METHOD': 'GET', 'PATH_INFO': path}


def start_response(status: str, headers: list[tuple[str, str]]) -> object:
    """Discard the status line: only the tests that assert on it record their own."""
    return (status, headers)


def seed_request_id(value: str) -> ScopeSeed:
    return ScopeSeed(REQUEST_ID, value)


def test_a_request_publishes_the_container() -> None:
    di = seeded_container()
    seen: list[FrozenContainer | None] = []

    def app(_environ: Environ, _start_response: object) -> Iterable[bytes]:
        seen.append(optional_hosted_container())
        return [b'ok']

    RequestScope(app, di)(environ_of(), start_response)

    assert seen == [di]


def test_a_request_applies_the_seed_before_the_downstream_app_runs() -> None:
    di = seeded_container()
    resolved: list[str] = []

    def app(_environ: Environ, _start_response: object) -> Iterable[bytes]:
        resolved.append(di.resolve(REQUEST_ID))
        return [b'ok']

    RequestScope(app, di, seed=lambda _: seed_request_id('r-1'))(environ_of(), start_response)

    assert resolved == ['r-1']


def test_a_seed_reads_the_environ_of_its_own_request() -> None:
    di = seeded_container()
    resolved: list[str] = []

    def seed(environ: Environ) -> ScopeSeed:
        return ScopeSeed(REQUEST_ID, str(environ['PATH_INFO']))

    def app(_environ: Environ, _start_response: object) -> Iterable[bytes]:
        resolved.append(di.resolve(REQUEST_ID))
        return [b'ok']

    middleware = RequestScope(app, di, seed=seed)
    middleware(environ_of('/first'), start_response)
    middleware(environ_of('/second'), start_response)

    assert resolved == ['/first', '/second']


def test_a_seed_returning_none_seeds_nothing() -> None:
    di = seeded_container()
    seen: list[FrozenContainer | None] = []

    def app(_environ: Environ, _start_response: object) -> Iterable[bytes]:
        seen.append(optional_hosted_container())
        with pytest.raises(MissingProviderError):
            di.resolve(REQUEST_ID)
        return [b'ok']

    RequestScope(app, di, seed=lambda _: None)(environ_of(), start_response)

    assert seen == [di]


def test_no_seed_at_all_behaves_like_a_seed_returning_none() -> None:
    di = seeded_container()
    seen: list[FrozenContainer | None] = []

    def app(_environ: Environ, _start_response: object) -> Iterable[bytes]:
        seen.append(optional_hosted_container())
        with pytest.raises(MissingProviderError):
            di.resolve(REQUEST_ID)
        return [b'ok']

    RequestScope(app, di)(environ_of(), start_response)

    assert seen == [di]


def test_the_response_reaches_the_caller_unchanged() -> None:
    di = seeded_container()
    body = [b'first ', b'second']
    calls: list[tuple[str, list[tuple[str, str]]]] = []

    def app(_environ: Environ, respond: object) -> Iterable[bytes]:
        assert callable(respond)
        respond('200 OK', [('Content-Type', 'text/plain')])
        return body

    def record(status: str, headers: list[tuple[str, str]]) -> object:
        calls.append((status, headers))
        return None

    returned = RequestScope(app, di)(environ_of(), record)

    assert returned is body
    assert list(returned) == [b'first ', b'second']
    assert calls == [('200 OK', [('Content-Type', 'text/plain')])]


def test_a_scoped_teardown_runs_once_per_request_and_the_next_request_is_fresh() -> None:
    torn: list[Resource] = []
    di = torn_down_container(torn)
    built: list[Resource] = []

    def app(_environ: Environ, _start_response: object) -> Iterable[bytes]:
        built.append(di.resolve(Resource))
        return [b'ok']

    middleware = RequestScope(app, di)

    middleware(environ_of(), start_response)
    after_first = list(torn)
    middleware(environ_of(), start_response)

    assert after_first == built[:1]
    assert torn == built
    assert built[0] is not built[1]


def test_a_downstream_exception_propagates_and_the_scope_still_drains() -> None:
    torn: list[Resource] = []
    di = torn_down_container(torn)

    def app(_environ: Environ, _start_response: object) -> Iterable[bytes]:
        di.resolve(Resource)
        raise DownstreamFailure

    with pytest.raises(DownstreamFailure):
        RequestScope(app, di)(environ_of(), start_response)

    assert len(torn) == 1
    assert optional_hosted_container() is None


def test_a_streaming_body_cannot_reach_the_container_after_the_application_returns() -> None:
    """The documented WSGI limitation, pinned so a refactor cannot lose it.

    WSGI gives the middleware no hook that outlives the return, so the scope
    has already drained by the time the server consumes the iterable. A
    generator that resolves while being consumed therefore fails, and it fails
    with the contract-level error `hosted_container()` raises when nothing is
    published.
    """
    di = seeded_container()

    def app(_environ: Environ, _start_response: object) -> Iterable[bytes]:
        def stream() -> Generator[bytes]:
            yield b'first '
            yield hosted_container().resolve(REQUEST_ID).encode()

        return stream()

    returned = RequestScope(app, di, seed=lambda _: seed_request_id('r-1'))(environ_of(), start_response)
    body = iter(returned)

    assert next(body) == b'first '
    with pytest.raises(ContainerNotBoundError) as failure:
        next(body)

    assert str(failure.value) == NO_CONTAINER
