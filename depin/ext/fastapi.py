"""FastAPI integration: per-request scoping and type-level injection.

Importing this module requires the ``fastapi`` extra (``pip install
'pydepin[fastapi]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract —
`depin.optional_hosted_container` — plus the Starlette middleware, which is
itself `depin.ext.asgi.RequestScope` with one seed applied. That shared
middleware is what holds the `Host` and opens the per-request scope; this
module adds `Inject` on top of it.
"""

from typing import TYPE_CHECKING

from depin.ext._fastapi import Inject as _RuntimeInject
from depin.ext._fastapi import install

# `fastapi.Request` is `starlette.requests.Request` — FastAPI re-exports the
# class rather than subclassing it — so the Starlette middleware seeds exactly
# the key a FastAPI provider asks for, and one middleware serves both.
from depin.ext.starlette import RequestScope

__all__ = ['Inject', 'RequestScope', 'install']


if TYPE_CHECKING:
    # `Inject[T]` is a PEP 695 type alias so the parameter's static type is `T` —
    # `svc: Inject[UserService]` is read by basedpyright as `svc: UserService`.
    # At runtime (else-branch) `Inject[T]` is a class whose `__class_getitem__`
    # returns `Annotated[T, Depends(resolver)]`, which FastAPI picks up via the
    # usual dependency-injection plumbing. The two views must stay in sync.
    type Inject[T] = T
else:
    Inject = _RuntimeInject
