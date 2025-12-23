from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import Request

_GLOBAL_REQUEST_STORE: ContextVar[dict[Any, Any]] = ContextVar(
    '_GLOBAL_REQUEST_STORE',
    default={},
)


class RequestScopeService:
    CONTEXT_MANAGERS_KEY = '__Context_Managers__'
    CURRENT_REQUEST_KEY = '__Current_Request__'

    @classmethod
    def get_request_store(cls):
        return _GLOBAL_REQUEST_STORE.get()

    @classmethod
    def get_request_key(cls, item):
        return item

    @classmethod
    def set_current_request(cls, request: Request):
        store = cls.get_request_store()
        store[cls.CURRENT_REQUEST_KEY] = request

    @classmethod
    def get_current_request(cls) -> Request:
        store = cls.get_request_store()

        request = store.get(cls.CURRENT_REQUEST_KEY)

        if request is None:
            raise RuntimeError(
                'No Request instance found in the current request scope. '
                'This indicates that the RequestScopeMiddleware did not run before '
                'dependency resolution.\n\n'
                'Most common causes:\n'
                '  • The middleware was not added: app.add_middleware(RequestScopeMiddleware)\n'
                '  • The container is resolving dependencies outside an HTTP request\n'
                '  • A background task is trying to access Request\n\n'
                'How to fix:\n'
                '  Ensure that RequestScopeMiddleware is registered before any routes and that '
                'all Request-dependent dependencies are only resolved inside an HTTP request.'
            )

        return request

    @classmethod
    @contextmanager
    def request_scope(cls):
        token = cls._start_request_scope()

        try:
            yield cls
        except Exception:
            import sys

            cls._exit_request_scope(token, sys.exc_info())
            raise
        else:
            cls._exit_request_scope(token)

    @classmethod
    @asynccontextmanager
    async def request_scope_async(cls):
        token = cls._start_request_scope()

        try:
            yield cls
        except Exception:
            import sys

            await cls._exit_request_scope_async(token, sys.exc_info())
            raise
        else:
            await cls._exit_request_scope_async(token)

    @classmethod
    def _start_request_scope(cls):
        token = _GLOBAL_REQUEST_STORE.set({})
        return token

    @classmethod
    def _exit_request_scope(cls, token, exc_info=None):
        store = _GLOBAL_REQUEST_STORE.get(token)

        context_managers = store.get(cls.CONTEXT_MANAGERS_KEY, [])

        if exc_info and exc_info[0] is not None:
            for cm in reversed(context_managers):
                try:
                    if hasattr(cm, '__exit__'):
                        cm.__exit__(*exc_info)
                    elif hasattr(cm, 'close'):
                        cm.close()

                except Exception:
                    pass
        else:
            for cm in reversed(context_managers):
                try:
                    if hasattr(cm, '__exit__'):
                        cm.__exit__(None, None, None)
                    elif hasattr(cm, 'close'):
                        cm.close()

                except Exception:
                    pass

        _GLOBAL_REQUEST_STORE.reset(token)

    @classmethod
    async def _exit_request_scope_async(cls, token, exc_info=None):
        store = _GLOBAL_REQUEST_STORE.get()
        context_managers = store.get(cls.CONTEXT_MANAGERS_KEY, [])

        if exc_info and exc_info[0] is not None:
            for cm in reversed(context_managers):
                try:
                    if hasattr(cm, '__aexit__'):
                        await cm.__aexit__(*exc_info)
                    elif hasattr(cm, '__exit__'):
                        cm.__exit__(*exc_info)
                    elif hasattr(cm, 'aclose'):
                        await cm.aclose()
                    elif hasattr(cm, 'close'):
                        cm.close()
                except Exception:
                    pass
        else:
            for cm in reversed(context_managers):
                try:
                    if hasattr(cm, '__aexit__'):
                        await cm.__aexit__(None, None, None)
                    elif hasattr(cm, '__exit__'):
                        cm.__exit__(None, None, None)
                    elif hasattr(cm, 'aclose'):
                        await cm.aclose()
                    elif hasattr(cm, 'close'):
                        cm.close()
                except Exception:
                    pass

        _GLOBAL_REQUEST_STORE.reset(token)
