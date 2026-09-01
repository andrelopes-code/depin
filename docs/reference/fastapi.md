# FastAPI integration

`depin.ext.fastapi.RequestScope` is `depin.ext.starlette.RequestScope`,
re-exported unchanged — `fastapi.Request` is `starlette.requests.Request`, so
one middleware serves both. It is documented on the
[Starlette](starlette.md) page.

::: depin.ext.fastapi.Inject
