"""`depin.ext.starlette` and `depin.ext.litestar`: the two ASGI specialisations.

Both are `depin.ext.asgi.RequestScope` closed over one framework's own
connection triple and one seed, so what a consumer needs from them is that the
middleware is still an ASGI application *of that framework's own types* — the
property `corpus/ext_core/e01_asgi.py` proves for a consumer's own triple, and
the property a non-generic middleware would lose.

The two frameworks are in one file because they make the same promise through
two mutually incompatible spellings of the same protocol: Starlette writes its
scope as ``MutableMapping[str, Any]`` and Litestar writes its as a
``TypedDict``. Checking them side by side is what shows the generic seam
carrying both.

Requires the `starlette` and `litestar` extras, so this file is checked in
all-extras mode only.
"""

from collections.abc import Callable

from litestar.types import ASGIApp as LitestarASGIApp
from litestar.types import Receive as LitestarReceive
from litestar.types import Scope as LitestarScope
from litestar.types import Send as LitestarSend
from starlette.types import ASGIApp as StarletteASGIApp
from starlette.types import Receive as StarletteReceive
from starlette.types import Scope as StarletteScope
from starlette.types import Send as StarletteSend

from depin import Container, FrozenContainer, ScopeSeed
from depin.ext.asgi import RequestScope as BaseRequestScope
from depin.ext.litestar import RequestScope as LitestarRequestScope
from depin.ext.litestar import seed_request as litestar_seed
from depin.ext.starlette import RequestScope as StarletteRequestScope
from depin.ext.starlette import seed_request as starlette_seed


class Settings:
    def __init__(self) -> None:
        self.page_size = 25


def build() -> FrozenContainer:
    return Container().bind(Settings).freeze()


def the_starlette_middleware_is_a_starlette_asgi_app(app: StarletteASGIApp) -> None:
    _middleware: StarletteASGIApp = StarletteRequestScope(app, build())


def the_starlette_middleware_specialises_the_generic_base(app: StarletteASGIApp) -> None:
    _base: BaseRequestScope[StarletteScope, StarletteReceive, StarletteSend] = StarletteRequestScope(app, build())


def the_starlette_seed_maps_a_scope_to_a_key_and_a_value() -> None:
    _seed: Callable[[StarletteScope], ScopeSeed] = starlette_seed


def the_litestar_middleware_is_a_litestar_asgi_app(app: LitestarASGIApp) -> None:
    _middleware: LitestarASGIApp = LitestarRequestScope(app, build())


def the_litestar_middleware_specialises_the_generic_base(app: LitestarASGIApp) -> None:
    _base: BaseRequestScope[LitestarScope, LitestarReceive, LitestarSend] = LitestarRequestScope(app, build())


def the_litestar_seed_maps_a_scope_to_a_key_and_a_value() -> None:
    _seed: Callable[[LitestarScope], ScopeSeed] = litestar_seed
