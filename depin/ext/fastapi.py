"""FastAPI integration: per-request scoping and type-level injection.

Importing this module requires the ``fastapi`` extra (``pip install
'pydepin[fastapi]'``); the depin core itself has no third-party dependencies.

Written entirely against depin's public integration contract —
`depin.optional_hosted_container` — plus the Starlette middleware, which is
itself `depin.ext.asgi.RequestScope` with one seed applied. That shared
middleware is what holds the `Host` and opens the per-request scope; this
module adds `Inject` on top of it.
"""

from typing import TYPE_CHECKING, Annotated

from fastapi.params import Depends

from depin import optional_hosted_container
from depin.errors import ContainerNotBoundError

# `fastapi.Request` is `starlette.requests.Request` — FastAPI re-exports the
# class rather than subclassing it — so the Starlette middleware seeds exactly
# the key a FastAPI provider asks for, and one middleware serves both.
from depin.ext.starlette import RequestScope

__all__ = ['Inject', 'RequestScope']


if TYPE_CHECKING:
    # `Inject[T]` is a PEP 695 type alias so the parameter's static type is `T` —
    # `svc: Inject[UserService]` is read by basedpyright as `svc: UserService`.
    # At runtime (else-branch) `Inject[T]` is a class whose `__class_getitem__`
    # returns `Annotated[T, Depends(resolver)]`, which FastAPI picks up via the
    # usual dependency-injection plumbing. The two views must stay in sync.
    type Inject[T] = T
else:

    class Inject:
        """FastAPI parameter annotation that resolves a dependency from depin.

        Write ``svc: Inject[UserService]`` on a route handler: to the type checker
        the parameter is plain ``UserService``, while at runtime ``Inject[T]``
        expands to ``Annotated[T, Depends(...)]`` so FastAPI resolves it through the
        active `RequestScope`. No default-value markers and no
        ``# noqa: B008`` waivers at the call site.

        Raises:
            ContainerNotBoundError: No container is hosted in this context.
                Usually because the `RequestScope` middleware was never
                installed with ``app.add_middleware(RequestScope,
                container=...)``; also raised for a route reached outside any
                active `Host` — for instance while it is being resolved from
                an ASGI lifespan hook with no `Host.activated()` in effect.
        """

        def __class_getitem__(cls, key: object) -> object:
            async def resolver() -> object:
                container = optional_hosted_container()
                if container is None:
                    raise ContainerNotBoundError(
                        'Inject[...] resolved outside a RequestScope; install the middleware with '
                        'app.add_middleware(RequestScope, container=...).'
                    )
                return await container.aresolve(key)

            return Annotated[key, Depends(dependency=resolver)]
