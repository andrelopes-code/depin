import inspect
from contextvars import ContextVar
from enum import Enum
from typing import Any, Callable, Dict, Type, cast, get_type_hints, overload, override

from fastapi import FastAPI


class Scope(Enum):
    SINGLETON = 'singleton'
    TRANSIENT = 'transient'
    REQUEST = 'request'


_request_context: ContextVar[Dict[str, Any]] = ContextVar('_request_context', default={})


def enter_request_scope():
    token = _request_context.set({})
    return token


def exit_request_scope(token):
    _request_context.reset(token)


def get_request_store():
    return _request_context.get()


@overload
def injectable[T: type](_cls: T, /, *, scope: Scope = Scope.SINGLETON) -> T: ...
@overload
def injectable[T: type](*, scope: Scope = Scope.SINGLETON) -> Callable[[T], T]: ...


def injectable[T: type](
    _cls: T | None = None,
    *,
    scope: Scope = Scope.SINGLETON,
) -> T | Callable[[T], T]:
    def wrap(cls: T) -> T:
        setattr(cls, '__di_component__', True)
        setattr(cls, '__di_scope__', scope)
        return cls

    if _cls is None:
        return wrap

    return wrap(_cls)


def _is_async_gen_callable(func: Callable[..., Any]) -> bool:
    """Verifica se é um async generator function."""
    return inspect.isasyncgenfunction(func)


def _is_gen_callable(func: Callable[..., Any]) -> bool:
    """Verifica se é um generator function."""
    return inspect.isgeneratorfunction(func)


def _is_async_callable(func: Callable[..., Any]) -> bool:
    """Verifica se é uma função async."""
    return inspect.iscoroutinefunction(func)


class Container:
    def __init__(self):
        self._providers: Dict[type[Any], Callable[[], Any]] = {}
        self._registrations: Dict[type[Any], Dict[str, Any]] = {}

    def register[T](
        self,
        *,
        scope: Scope = Scope.SINGLETON,
        implementation: type[T] | None = None,
        abstract: type[T] | None = None,
    ):
        abstract = abstract or implementation
        impl = implementation or abstract

        if abstract is None:
            raise ValueError('abstract nao pode ser None')

        if impl is None:
            raise ValueError('abstract nao pode ser None')

        provider = None

        if scope == Scope.SINGLETON:
            instance_holder = {}

            def provider_singleton():
                if 'inst' not in instance_holder:
                    instance_holder['inst'] = self._construct(impl)
                return instance_holder['inst']

            provider = provider_singleton

        elif scope == Scope.TRANSIENT:

            def provider_transient():
                return self._construct(impl)

            provider = provider_transient

        elif scope == Scope.REQUEST:

            def provider_request():
                store = get_request_store()
                key = f'req::{abstract.__qualname__}'
                if key not in store:
                    store[key] = self._construct(impl)
                return store[key]

            provider = provider_request

        if provider is None:
            raise RuntimeError(f'Nao foi possivel registrar {abstract}')

        self._providers[abstract] = provider
        self._registrations[abstract] = {'implementation': impl, 'scope': scope}

    def _construct(self, cls: type[Any]):
        """Instancia uma classe resolvendo suas dependências via type hints do __init__."""

        signature = inspect.signature(cls.__init__)
        kwargs = {}
        type_hints = get_type_hints(cls.__init__)

        for name, param in signature.parameters.items():
            if name == 'self':
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            # se existe hint de tipo, tenta resolver
            param_type = type_hints.get(name, None)
            if param_type and self._has_provider_for(param_type):
                kwargs[name] = self.resolve(param_type)
            else:
                if param.default is not inspect._empty:  # pyright: ignore[reportPrivateUsage]
                    # usar default
                    pass
                else:
                    raise RuntimeError(
                        f"Não é possível resolver parâmetro '{name}' para {cls}. Falta provider ou default."
                    )

        return cls(**kwargs)

    def _has_provider_for(self, t: type[Any]) -> bool:
        return t in self._providers

    def resolve[T](self, abstract: Type[T]) -> T:
        """Obtém instância para um tipo registrado."""

        provider = cast(Callable[[], T], self._providers.get(abstract))

        if provider is None:
            raise ValueError(f'Provider para {abstract} nao foi registrado')

        return provider()

    def provide(self, t: type[Any]):
        def _dep():
            return self.resolve(t)

        return _dep

    def wire_fastapi(self, app: FastAPI):
        """
        Integracao básica: adiciona um middleware que cria/descarta request scope
        e fornece utilitarios.
        Use app.include_router normalmente. Para endpoints, use:
            def endpoint(svc: MyService = Depends(container.provide(MyService))): ...
        """

        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request

        class _RequestScopeMiddleware(BaseHTTPMiddleware):
            @override
            async def dispatch(self, request: Request, call_next):
                token = enter_request_scope()
                try:
                    response = await call_next(request)
                    return response
                finally:
                    exit_request_scope(token)

        app.add_middleware(_RequestScopeMiddleware)
