from typing import override

from fastapi import FastAPI

from depin.internal.request_scope import RequestScopeService


def wire_fastapi(app: FastAPI):
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware

    class _RequestScopeMiddleware(BaseHTTPMiddleware):
        @override
        async def dispatch(self, request: Request, call_next):
            token = RequestScopeService.enter_request_scope()
            print('[RequestScopeMiddleware] entered request scope')

            RequestScopeService.set_current_request(request)

            try:
                response = await call_next(request)
                return response
            finally:
                await RequestScopeService.aexit_request_scope(token)
                print('[RequestScopeMiddleware] exited request scope')

    app.add_middleware(_RequestScopeMiddleware)
