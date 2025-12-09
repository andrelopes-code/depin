from typing import override

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from depin._internal.request_scope import RequestScopeService


class RequestScopeMiddleware(BaseHTTPMiddleware):
    @override
    async def dispatch(self, request: Request, call_next):
        token = RequestScopeService.enter_request_scope()

        RequestScopeService.set_current_request(request)

        try:
            return await call_next(request)

        finally:
            await RequestScopeService.aexit_request_scope(token)
