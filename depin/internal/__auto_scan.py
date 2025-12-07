import importlib
import inspect
import pkgutil
from contextvars import ContextVar
from enum import Enum
from typing import Any, Callable, Dict, Optional, Type, TypeVar, cast, get_type_hints, overload, override


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


CLASS = TypeVar('CLASS', bound=type)


@overload
def injectable(_cls: CLASS, /, *, scope: Scope = Scope.SINGLETON) -> CLASS: ...
@overload
def injectable(*, scope: Scope = Scope.SINGLETON) -> Callable[[CLASS], CLASS]: ...


def injectable(
    _cls: CLASS | None = None,
    *,
    scope: Scope = Scope.SINGLETON,
) -> CLASS | Callable[[CLASS], CLASS]:
    def wrap(cls: CLASS) -> CLASS:
        setattr(cls, '__di_component__', True)
        setattr(cls, '__di_scope__', scope)
        return cls

    if _cls is None:
        return wrap

    return wrap(_cls)


class Container:
    def __init__(self):
        self._providers: Dict[type[Any], Callable[[], Any]] = {}
        self._registrations: Dict[type[Any], Dict[str, Any]] = {}

    def auto_scan(self, package_names: list[str]):
        for package_name in package_names:
            self._scan_package(package_name)

    def _scan_package(self, package_name: str):
        try:
            package_or_module = importlib.import_module(package_name)

        except Exception as e:
            raise RuntimeError(f'Erro importando package {package_name}: {e}') from e

        is_single_module = not hasattr(package_or_module, '__path__')

        if is_single_module:
            self._scan_module(package_or_module)
            return

        for _finder, name, _is_package in pkgutil.walk_packages(
            package_or_module.__path__, prefix=package_or_module.__name__ + '.'
        ):
            try:
                module = importlib.import_module(name)

            except Exception:
                # ignora módulos que falham ao importar
                continue

            self._scan_module(module)

    def _scan_module(self, module):
        for _, obj in inspect.getmembers(module, inspect.isclass):
            # considerar apenas classes definidas naquele módulo (evitar importar builtins)
            if obj.__module__ != module.__name__:
                continue

            is_di_injectable = getattr(obj, '__di_component__', False)

            if is_di_injectable:
                scope = getattr(obj, '__di_scope__', Scope.SINGLETON)
                self.register(obj, implementation=obj, scope=scope)
            else:
                # se for concreta e não-abc, registra por convenção? não registrar automaticamente
                # registramos também classes concretas para possibilidade de autowire
                pass

    def register(self, abstract: type[Any], implementation: Optional[type[Any]] = None, scope: Scope = Scope.SINGLETON):
        """
        Registra um tipo (abstract/interface) mapeado para uma implementação.
        Se implementation is None, assume-se abstract é instanciável.
        """

        impl = implementation or abstract
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

        sig = inspect.signature(cls.__init__)
        kwargs = {}
        hints = get_type_hints(cls.__init__)
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            # se existe hint de tipo, tenta resolver
            param_type = hints.get(name, None)
            if param_type and self._has_provider_for(param_type):
                kwargs[name] = self.resolve(param_type)
            else:
                # sem provider conhecido => se parametro tem default, deixa
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
            # se o tipo é instanciável concreto, tenta registrar automaticamente
            if inspect.isclass(abstract) and not inspect.isabstract(abstract):
                self.register(abstract, implementation=abstract, scope=Scope.TRANSIENT)

                provider = cast(Callable[[], T], self._providers.get(abstract))
            else:
                raise RuntimeError(f'Nenhum provider registrado para {abstract}')

        if provider is None:
            raise ValueError('Provider não pode ser None')

        return provider()

    def provide(self, t: type[Any]):
        """Retorna um callável pronto para usar em Depends: Depends(container.provide(Cls))"""

        def _dep():
            return self.resolve(t)

        return _dep

    def wire_fastapi(self, app):
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

    def registrations(self):
        return dict(self._registrations)
