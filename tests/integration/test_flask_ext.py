"""The Flask integration, driven by a real `Flask` app over a real WSGI client.

`depin.ext.flask.RequestScope` is the shared WSGI middleware with one seed
applied, so what these tests exercise is the seed and the wiring: the request
object reaches providers, the scope is per request, and it drains when the
request ends. The last test pins the drain against a real Flask streaming
response, so the boundary the guide warns about is anchored to the framework
and not only to the hand-written application in ``tests/unit/test_wsgi.py``.

Flask's documented installation is ``app.wsgi_app = RequestScope(app.wsgi_app,
di)``: a middleware instance, not a class, unlike the ASGI frameworks. That
assignment cannot be written here, because Flask declares ``wsgi_app`` as a
method and mypy rejects rebinding one (``method-assign``); a `typing.Protocol`
naming ``wsgi_app`` as a settable attribute does not help either, since the
method is read-only to a protocol. The suite therefore wraps ``app.wsgi_app``
— reading it is fine — and drives the wrapper through `werkzeug.test.Client`,
which is the class Flask's own ``app.test_client()`` derives from, so the
responses asserted on are real Flask responses.
"""

from collections.abc import Generator, Iterator

from flask import Flask, Request, Response
from werkzeug.test import Client

from depin import Container, FrozenContainer, Scope, hosted_container, optional_hosted_container
from depin.ext.flask import RequestScope


class Counter:
    """A scoped dependency whose identity distinguishes one request from the next."""

    def __init__(self) -> None:
        self.value = 0

    def tick(self) -> int:
        self.value += 1
        return self.value


class Resource:
    """A scoped dependency whose teardown the tests count."""


class HeaderProbe:
    """A provider whose only input is the seeded request."""

    def __init__(self, request: Request) -> None:
        self.probe = request.headers.get('x-probe', 'none')
        self.path = request.path


def hosted(container: FrozenContainer, app: Flask) -> Client:
    return Client(RequestScope(app.wsgi_app, container))


def test_a_scoped_provider_is_resolved_once_per_request() -> None:
    app = Flask(__name__)

    def endpoint() -> dict[str, int]:
        counter = hosted_container().resolve(Counter)
        again = hosted_container().resolve(Counter)
        return {'n': counter.tick(), 'again': again.tick()}

    app.add_url_rule('/tick', view_func=endpoint)

    di = Container().bind(Counter, scope=Scope.SCOPED).freeze()

    assert hosted(di, app).get('/tick').get_json() == {'n': 1, 'again': 2}


def test_two_requests_get_independent_scoped_instances() -> None:
    seen: list[int] = []
    app = Flask(__name__)

    def endpoint() -> dict[str, int]:
        counter = hosted_container().resolve(Counter)
        seen.append(id(counter))
        return {'n': counter.tick()}

    app.add_url_rule('/tick', view_func=endpoint)

    di = Container().bind(Counter, scope=Scope.SCOPED).freeze()
    client = hosted(di, app)

    first = client.get('/tick').get_json()
    second = client.get('/tick').get_json()

    assert (first, second) == ({'n': 1}, {'n': 1})
    assert seen[0] != seen[1]


def test_the_request_scope_drains_its_teardowns_when_the_request_ends() -> None:
    torn: list[Resource] = []
    torn_while_serving: list[int] = []
    app = Flask(__name__)

    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(item)

    def endpoint() -> dict[str, bool]:
        _ = hosted_container().resolve(Resource)
        torn_while_serving.append(len(torn))
        return {'ok': True}

    app.add_url_rule('/res', view_func=endpoint)

    di = Container().bind(make, scope=Scope.SCOPED, provides=Resource).freeze()
    client = hosted(di, app)

    assert client.get('/res').get_json() == {'ok': True}
    assert len(torn) == 1
    _ = client.get('/res')
    assert len(torn) == 2
    assert torn_while_serving == [0, 1]


def test_the_hosted_container_is_reachable_from_a_view() -> None:
    di = Container().freeze()
    app = Flask(__name__)

    def endpoint() -> dict[str, bool]:
        return {'same': hosted_container() is di}

    app.add_url_rule('/host', view_func=endpoint)

    assert hosted(di, app).get('/host').get_json() == {'same': True}


def test_a_provider_reads_headers_off_the_seeded_request() -> None:
    app = Flask(__name__)

    def endpoint(x: str) -> dict[str, str]:
        found = hosted_container().resolve(HeaderProbe)
        return {'probe': found.probe, 'path': found.path}

    app.add_url_rule('/probe/<x>', view_func=endpoint)

    di = Container().scope_value(Request).bind(HeaderProbe, scope=Scope.SCOPED).freeze()

    payload = hosted(di, app).get('/probe/abc', headers={'x-probe': 'yes'}).get_json()

    assert payload == {'probe': 'yes', 'path': '/probe/abc'}


def test_a_streaming_flask_response_is_produced_after_the_scope_has_drained() -> None:
    """The WSGI boundary, against a real `flask.Response` rather than a hand-written app.

    A streamed body is pulled by the server after the application has
    returned, which is after `depin.ext.wsgi.RequestScope` has drained the
    scope and unpublished the container. Anything the generator needs has to
    be resolved — and closed over — before the response is returned.
    """
    hosted_inside_body: list[object] = []
    served: list[Resource] = []
    torn: list[Resource] = []
    app = Flask(__name__)

    def make() -> Generator[Resource]:
        item = Resource()
        yield item
        torn.append(item)

    def endpoint() -> Response:
        resource = hosted_container().resolve(Resource)
        served.append(resource)

        def chunks() -> Iterator[bytes]:
            hosted_inside_body.append(optional_hosted_container())
            yield f'{id(resource):x}'.encode()

        return Response(chunks(), mimetype='text/plain')

    app.add_url_rule('/stream', view_func=endpoint)

    di = Container().bind(make, scope=Scope.SCOPED, provides=Resource).freeze()
    response = hosted(di, app).get('/stream')

    assert response.get_data() == f'{id(served[0]):x}'.encode()
    assert hosted_inside_body == [None]
    assert torn == served
