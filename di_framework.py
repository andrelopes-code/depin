import contextlib
import inspect
from contextvars import ContextVar
from enum import Enum
from typing import Any, Callable, Dict, Type, cast, get_type_hints, overload, override

from fastapi import FastAPI

type ProviderFn[T] = Callable[..., T]
CONTEXT_MANAGERS_KEY = '__context_managers__'


class _Dependency[T]:
    def __init__(self, provider_fn: ProviderFn[T]) -> None:
        self.provider_fn = provider_fn


def Provide[T](provider_fn: Any) -> Any:
    return _Dependency(provider_fn)


class Scope(Enum):
    SINGLETON = 'singleton'
    TRANSIENT = 'transient'
    REQUEST = 'request'


_request_context: ContextVar[Dict[Any, Any]] = ContextVar(
    '_request_context',
    default={},
)


def enter_request_scope():
    token = _request_context.set({})
    return token


def exit_request_scope(token):
    print('cleaning request scope')
    store = _request_context.get(token)

    context_managers = store.get(CONTEXT_MANAGERS_KEY, [])

    for cm in reversed(context_managers):
        try:
            if hasattr(cm, '__exit__'):
                cm.__exit__(None, None, None)
            elif hasattr(cm, 'close'):
                cm.close()

        except Exception:
            pass

    _request_context.reset(token)


async def aexit_request_scope(token):
    print('cleaning request scope [async]')
    store = _request_context.get()

    context_managers = store.get(CONTEXT_MANAGERS_KEY, [])

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

    _request_context.reset(token)


def get_request_store():
    return _request_context.get()


def get_request_key(item):
    return item


def _wrap_sync_gen(gen_fn, params):
    @contextlib.contextmanager
    def _ctx():
        gen = gen_fn(**params)
        try:
            value = next(gen)
            yield value
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    return _ctx()


@contextlib.asynccontextmanager
async def _wrap_async_gen(gen_fn, params):
    """Wrapper para async generators."""
    gen = gen_fn(**params)
    try:
        value = await gen.__anext__()
        yield value
    finally:
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass


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
        self._providers: Dict[type[Any] | ProviderFn[Any], Callable[[], Any]] = {}
        self._registrations: Dict[type[Any] | ProviderFn[Any], Dict[str, Any]] = {}

    @property
    def registrations(self):
        return self._registrations

    @property
    def request_store(self):
        return get_request_store()

    def register[T](
        self,
        *,
        source: type[T] | ProviderFn[T] | None,
        abstract: type[T] | None = None,
        scope: Scope = Scope.SINGLETON,
    ):
        if isinstance(source, type):
            self._register(abstract=abstract, implementation=source, provider_fn=None, scope=scope)
        elif callable(source):
            self._register(abstract=abstract, implementation=None, provider_fn=source, scope=scope)
        else:
            raise ValueError(f'failed to register {source=}')

    def _register[T](
        self,
        *,
        scope: Scope = Scope.SINGLETON,
        abstract: type[T] | None,
        implementation: type[T] | None,
        provider_fn: ProviderFn[T] | None,
    ):

        abstract = abstract or implementation

        if abstract is None and implementation is None and provider_fn is None:
            raise ValueError('abstract, implementation or provider_fn must be provided')

        if abstract is None and provider_fn is None:
            raise ValueError('abstract and provider_fn cannot both be None')

        if implementation is None and provider_fn is None:
            raise ValueError('implementation and provider_fn cannot both be None')

        if provider_fn and (implementation or abstract):
            raise ValueError('Não é possível registrar uma função e uma classe, Informe apenas um provider.')

        implementation = cast(type[T], implementation)
        abstract = cast(type[T], abstract)

        is_fn = bool(provider_fn)
        is_class = not is_fn
        provider = None
        is_async = False

        if is_fn and provider_fn is not None:
            is_async = _is_async_callable(provider_fn) or _is_async_gen_callable(provider_fn)

        if scope == Scope.SINGLETON:
            instance_holder = {}

            if is_class:

                def provider_singleton_class():
                    if 'inst' not in instance_holder:
                        instance_holder['inst'] = self._construct(implementation)
                    return instance_holder['inst']

                provider = provider_singleton_class

            elif is_fn:
                if is_async:

                    async def provider_singleton_callable_async():
                        assert provider_fn is not None

                        if 'inst' not in instance_holder:
                            params = await self._resolve_func_params_async(provider_fn)
                            instance_holder['inst'] = await provider_fn(**params)  # pyright: ignore[reportGeneralTypeIssues]
                        return instance_holder['inst']

                    provider = provider_singleton_callable_async
                else:
                    # Provider síncrono
                    def provider_singleton_callable_sync():
                        assert provider_fn is not None

                        if 'inst' not in instance_holder:
                            params = self._resolve_func_params(provider_fn)
                            instance_holder['inst'] = provider_fn(**params)
                        return instance_holder['inst']

                    provider = provider_singleton_callable_sync

        elif scope == Scope.TRANSIENT:
            if is_class:

                def provider_transient_class():
                    return self._construct(implementation)

                provider = provider_transient_class

            if is_fn:
                if is_async:
                    # Provider assíncrono
                    async def provider_transient_callable_async():
                        assert provider_fn is not None

                        params = await self._resolve_func_params_async(provider_fn)
                        return await provider_fn(**params)  # pyright: ignore[reportGeneralTypeIssues]

                    provider = provider_transient_callable_async
                else:
                    # Provider síncrono
                    def provider_transient_callable_sync():
                        assert provider_fn is not None

                        params = self._resolve_func_params(provider_fn)
                        return provider_fn(**params)

                    provider = provider_transient_callable_sync

        elif scope == Scope.REQUEST:
            if is_class:
                # Provider síncrono
                def provider_request_class():
                    store = get_request_store()
                    key = get_request_key(abstract)

                    if key not in store:
                        store[key] = self._construct(implementation)
                    return store[key]

                # Provider assíncrono
                async def provider_request_class_async():
                    store = get_request_store()
                    key = get_request_key(abstract)

                    if key not in store:
                        store[key] = await self._aconstruct(implementation)
                    return store[key]

                # Escolhe qual usar baseado nas dependências
                # Se ALGUMA dependência do __init__ for async, usa o async
                needs_async = self._class_needs_async_resolution(implementation)
                provider = provider_request_class_async if needs_async else provider_request_class

            if is_fn:
                assert provider_fn is not None

                if _is_async_gen_callable(provider_fn):
                    # Async generator para REQUEST scope
                    async def provider_request_async_gen():
                        assert provider_fn is not None

                        store = get_request_store()
                        key = get_request_key(provider_fn)

                        if key not in store:
                            params = await self._resolve_func_params_async(provider_fn)
                            ctx = _wrap_async_gen(provider_fn, params)
                            store[key] = await ctx.__aenter__()

                            if CONTEXT_MANAGERS_KEY not in store:
                                store[CONTEXT_MANAGERS_KEY] = []

                            store[CONTEXT_MANAGERS_KEY].append(ctx)

                        return store[key]

                    provider = provider_request_async_gen

                elif _is_gen_callable(provider_fn):
                    # Sync generator para REQUEST scope
                    def provider_request_gen_sync():
                        assert provider_fn is not None

                        store = get_request_store()
                        key = get_request_key(provider_fn)

                        if key not in store:
                            params = self._resolve_func_params(provider_fn)
                            ctx = _wrap_sync_gen(provider_fn, params)
                            store[key] = ctx.__enter__()

                            if CONTEXT_MANAGERS_KEY not in store:
                                store[CONTEXT_MANAGERS_KEY] = []

                            store[CONTEXT_MANAGERS_KEY].append(ctx)

                        return store[key]

                    provider = provider_request_gen_sync

                elif is_async:

                    async def provider_request_callable_async():
                        assert provider_fn is not None

                        store = get_request_store()
                        key = get_request_key(provider_fn)

                        if key not in store:
                            params = await self._resolve_func_params_async(provider_fn)
                            store[key] = await provider_fn(**params)  # pyright: ignore[reportGeneralTypeIssues]
                        return store[key]

                    provider = provider_request_callable_async

                else:
                    # Sync callable simples para REQUEST scope
                    def provider_request_callable_sync():
                        assert provider_fn is not None

                        store = get_request_store()
                        key = get_request_key(provider_fn)

                        if key not in store:
                            params = self._resolve_func_params(provider_fn)
                            store[key] = provider_fn(**params)
                        return store[key]

                    provider = provider_request_callable_sync

        if provider is None:
            raise RuntimeError(f'Nao foi possivel registrar {abstract}')

        key = provider_fn if is_fn else abstract
        impl = provider_fn if is_fn else implementation

        assert key is not None

        self._providers[key] = provider
        self._registrations[key] = {'implementation': impl, 'scope': scope}

    def _resolve_func_params[T](self, func: ProviderFn[T]) -> Dict[str, Any]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)
        kwargs = {}

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, _Dependency):
                resolved = self.resolve(param.default.provider_fn)
                kwargs[name] = resolved

            elif param_type and self._has_provider_for(param_type):
                resolved = self.resolve(param_type)
                kwargs[name] = resolved

            else:
                if param.default is not inspect._empty:  # pyright: ignore[reportPrivateUsage]
                    pass  # Usar default
                else:
                    raise RuntimeError(
                        f"Não é possível resolver parâmetro '{name}' para {func}. Falta provider ou default."
                    )

        return kwargs

    async def _resolve_func_params_async[T](self, func: ProviderFn[T]) -> Dict[str, Any]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)
        kwargs = {}

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, _Dependency):
                resolved = await self.aresolve(param.default.provider_fn)
                kwargs[name] = resolved

            elif param_type and self._has_provider_for(param_type):
                resolved = await self.aresolve(param_type)
                kwargs[name] = resolved

            else:
                if param.default is not inspect._empty:  # pyright: ignore[reportPrivateUsage]
                    pass  # Usar default
                else:
                    raise RuntimeError(
                        f"Não é possível resolver parâmetro '{name}' para {func}. Falta provider ou default."
                    )

        return kwargs

    def _construct(self, cls: type[Any]):
        signature = inspect.signature(cls.__init__)
        type_hints = get_type_hints(cls.__init__)
        kwargs = {}

        for name, param in signature.parameters.items():
            if name == 'self':
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, _Dependency):
                kwargs[name] = self.resolve(param.default.provider_fn)

            elif param_type and self._has_provider_for(param_type):
                kwargs[name] = self.resolve(param_type)
            else:
                if param.default is not inspect._empty:  # pyright: ignore[reportPrivateUsage]
                    pass  # usar default
                else:
                    raise RuntimeError(
                        f"Não é possível resolver parâmetro '{name}' para {cls}. Falta provider ou default."
                    )

        return cls(**kwargs)

    async def _aconstruct(self, cls: type[Any]):
        signature = inspect.signature(cls.__init__)
        type_hints = get_type_hints(cls.__init__)
        kwargs = {}

        for name, param in signature.parameters.items():
            if name == 'self':
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, _Dependency):
                kwargs[name] = await self.aresolve(param.default.provider_fn)  # ✅ aresolve

            elif param_type and self._has_provider_for(param_type):
                kwargs[name] = await self.aresolve(param_type)  # ✅ aresolve
            else:
                if param.default is not inspect._empty:  # pyright: ignore
                    pass
                else:
                    raise RuntimeError(
                        f"Não é possível resolver parâmetro '{name}' para {cls}. Falta provider ou default."
                    )

        return cls(**kwargs)

    def _has_provider_for(self, t: type[Any]) -> bool:
        return t in self._providers

    def _class_needs_async_resolution(self, cls: type[Any]) -> bool:
        """Verifica se alguma dependência da classe precisa de resolução async."""
        signature = inspect.signature(cls.__init__)
        type_hints = get_type_hints(cls.__init__)

        for name, param in signature.parameters.items():
            if name == 'self':
                continue

            param_type = type_hints.get(name, None)

            # Verifica se é um Provide com função async
            if param.default and isinstance(param.default, _Dependency):
                provider_fn = param.default.provider_fn
                if provider_fn in self._providers:
                    provider = self._providers[provider_fn]
                    if _is_async_callable(provider):
                        return True

            # Verifica se o tipo registrado tem provider async
            elif param_type and param_type in self._providers:
                provider = self._providers[param_type]
                if _is_async_callable(provider):
                    return True

        return False

    def resolve[T](self, abstract: Type[T] | ProviderFn[T]) -> T:
        provider = cast(Callable[[], T], self._providers.get(abstract))

        if provider is None:
            raise ValueError(f'Provider para {abstract} nao foi registrado')

        return provider()

    async def aresolve[T](self, abstract: Type[T] | ProviderFn[T]) -> T:
        provider = cast(Callable[[], T], self._providers.get(abstract))

        if provider is None:
            raise ValueError(f'Provider para {abstract} nao foi registrado')

        result = provider()

        if inspect.iscoroutine(result):
            return await result

        return result

    def inject[T](self, func: Callable[..., T]) -> Callable[..., T]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)

        injectable_params = set()

        for name, _param in signature.parameters.items():
            if name == 'self' or name == 'cls':
                continue

            param_type = type_hints.get(name, None)

            if param_type and self._has_provider_for(param_type):
                injectable_params.add(name)

        if not _is_async_callable(func):

            def sync_wrapper(*args, **kwargs):
                bound = signature.bind_partial(*args, **kwargs)

                for param_name in injectable_params:
                    if param_name not in bound.arguments:
                        param_type = type_hints[param_name]
                        bound.arguments[param_name] = self.resolve(param_type)

                return func(*bound.args, **bound.kwargs)

            sync_wrapper.__name__ = func.__name__
            sync_wrapper.__doc__ = func.__doc__
            sync_wrapper.__annotations__ = func.__annotations__
            return sync_wrapper

        else:

            async def async_wrapper(*args, **kwargs):
                bound = signature.bind_partial(*args, **kwargs)

                for param_name in injectable_params:
                    if param_name not in bound.arguments:
                        param_type = type_hints[param_name]
                        bound.arguments[param_name] = await self.aresolve(param_type)

                return await func(*bound.args, **bound.kwargs)  # pyright: ignore[reportGeneralTypeIssues]

            async_wrapper.__name__ = func.__name__
            async_wrapper.__doc__ = func.__doc__
            async_wrapper.__annotations__ = func.__annotations__
            return async_wrapper  # pyright: ignore[reportReturnType]

    def provide(self, t: Any):
        async def _dep():
            return await self.aresolve(t)

        return _dep

    def wire_fastapi(self, app: FastAPI):
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request

        class _RequestScopeMiddleware(BaseHTTPMiddleware):
            @override
            async def dispatch(self, request: Request, call_next):
                token = enter_request_scope()
                print('[RequestScopeMiddleware] entered request scope')
                try:
                    response = await call_next(request)
                    return response
                finally:
                    # Usa versão async do exit para limpar context managers async
                    await aexit_request_scope(token)
                    print('[RequestScopeMiddleware] exited request scope')

        app.add_middleware(_RequestScopeMiddleware)
