"""`depin.ext.flask`: the WSGI specialisation, installed the way Flask asks for it.

Flask writes its signatures against `wsgiref.types`, whose response starter
takes a third ``exc_info`` argument and returns a writer — neither of which
`depin.ext.wsgi.StartResponse` states. The middleware is generic over the
environment and the response starter precisely so it adopts Flask's pair
instead, and the assignment back to ``app.wsgi_app`` is where that has to hold:
the value sits in both an argument and a parameter position, so its type must
match Flask's exactly.

The installation written here reads ``app.wsgi_app`` and serves the middleware
directly, which is the form `depin.ext.flask.RequestScope` documents. Flask
declares ``wsgi_app`` as a method, so rebinding it draws mypy's
``method-assign`` and a ty ``invalid-assignment`` for every Flask user; that is
Flask's typing, not a promise this corpus is entitled to assert.

Requires the `flask` extra, so this file is checked in all-extras mode only.
"""

from collections.abc import Callable
from wsgiref.types import StartResponse, WSGIApplication, WSGIEnvironment

from flask import Flask

from depin import Container, FrozenContainer, ScopeSeed
from depin.ext.flask import RequestScope, seed_request
from depin.ext.wsgi import RequestScope as BaseRequestScope
from depin.ext.wsgi import WSGIApp


class Settings:
    def __init__(self) -> None:
        self.page_size = 25


def build() -> FrozenContainer:
    return Container().bind(Settings).freeze()


def the_middleware_wraps_the_application_flask_exposes() -> None:
    app = Flask(__name__)
    _served: WSGIApplication = RequestScope(app.wsgi_app, build())


def the_middleware_is_a_wsgi_application(app: WSGIApplication) -> None:
    _installed: WSGIApplication = RequestScope(app, build())


def the_middleware_specialises_the_generic_base(app: WSGIApplication) -> None:
    _base: BaseRequestScope[WSGIEnvironment, StartResponse] = RequestScope(app, build())
    _protocol: WSGIApp[WSGIEnvironment, StartResponse] = RequestScope(app, build())


def the_seed_maps_the_environment_to_a_key_and_a_value() -> None:
    _seed: Callable[[WSGIEnvironment], ScopeSeed] = seed_request
