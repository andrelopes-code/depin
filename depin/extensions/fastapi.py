from typing import override

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from depin._internal.request_scope import RequestScopeService


class RequestScopeMiddleware(BaseHTTPMiddleware):
    @override
    async def dispatch(self, request: Request, call_next):
        async with RequestScopeService.request_scope_async():
            # adds the current request to the context var
            RequestScopeService.set_current_request(request)

            return await call_next(request)
