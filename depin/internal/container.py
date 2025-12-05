import contextlib
import inspect
from enum import Enum
from typing import Any, Callable, Type, cast, get_type_hints, overload

from depin.internal.helpers import is_async_callable, is_async_generator_callable, is_generator_callable
from depin.internal.request_scope import RequestScopeService
from depin.internal.types import AsyncProviderFn, ProviderDependency, ProviderFn

INSPECT_EMPTY = inspect._empty  # pyright: ignore[reportPrivateUsage]


def Provide[T](provider_fn: Any) -> Any:
    return ProviderDependency(provider_fn)


class Scope(Enum):
    SINGLETON = 'singleton'
    TRANSIENT = 'transient'
    REQUEST = 'request'


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


class Container:
    def __init__(self):
        self._providers: dict[type[Any] | ProviderFn[Any], Callable[[], Any]] = {}
        self._registrations: dict[type[Any] | ProviderFn[Any], dict[str, Any]] = {}

    @property
    def registrations(self):
        return self._registrations

    def register[T](
        self,
        source: type[T] | ProviderFn[T],
        *,
        abstract: type[T] | None = None,
        scope: Scope,
    ):
        if scope != Scope.REQUEST:
            if is_async_generator_callable(source):
                raise ValueError('async generators are not supported in non-request scopes')
            elif is_generator_callable(source):
                raise ValueError('generators are not supported in non-request scopes')

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

        if provider_fn and implementation:
            raise ValueError('provider_fn and implementation cannot be both non-none')

        implementation = cast(type[T], implementation)
        abstract = cast(type[T], abstract)

        is_fn = bool(provider_fn)
        is_class = not is_fn
        needs_async = False
        provider = None

        if is_class:
            needs_async = self._class_needs_async_resolution(implementation)
        if is_fn and provider_fn is not None:
            needs_async = is_async_callable(provider_fn) or is_async_generator_callable(provider_fn)

        if scope == Scope.SINGLETON:
            instance_holder = {}

            if is_class:
                if needs_async:

                    async def provider_singleton_class_async():
                        if 'inst' not in instance_holder:
                            instance_holder['inst'] = await self._aconstruct(implementation)
                        return instance_holder['inst']

                    provider = provider_singleton_class_async
                else:
                    # Provider síncrono para classes sem deps async
                    def provider_singleton_class():
                        if 'inst' not in instance_holder:
                            instance_holder['inst'] = self._construct(implementation)
                        return instance_holder['inst']

                    provider = provider_singleton_class

            elif is_fn:
                if needs_async:

                    async def provider_singleton_callable_async():
                        assert provider_fn is not None

                        if 'inst' not in instance_holder:
                            params = await self._resolve_func_params_async(provider_fn)
                            instance_holder['inst'] = await provider_fn(**params)  # pyright: ignore[reportGeneralTypeIssues]
                        return instance_holder['inst']

                    provider = provider_singleton_callable_async
                else:

                    def provider_singleton_callable_sync():
                        assert provider_fn is not None

                        if 'inst' not in instance_holder:
                            params = self._resolve_func_params(provider_fn)
                            instance_holder['inst'] = provider_fn(**params)
                        return instance_holder['inst']

                    provider = provider_singleton_callable_sync

        elif scope == Scope.TRANSIENT:
            if is_class:
                if needs_async:

                    async def provider_transient_class_async():
                        return await self._aconstruct(implementation)

                    provider = provider_transient_class_async
                else:

                    def provider_transient_class():
                        return self._construct(implementation)

                    provider = provider_transient_class

            if is_fn:
                if needs_async:

                    async def provider_transient_callable_async():
                        assert provider_fn is not None

                        params = await self._resolve_func_params_async(provider_fn)
                        return await provider_fn(**params)  # pyright: ignore[reportGeneralTypeIssues]

                    provider = provider_transient_callable_async
                else:

                    def provider_transient_callable_sync():
                        assert provider_fn is not None

                        params = self._resolve_func_params(provider_fn)
                        return provider_fn(**params)

                    provider = provider_transient_callable_sync

        elif scope == Scope.REQUEST:
            if is_class:
                if needs_async:

                    async def provider_request_class_async():
                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(abstract)

                        if key not in store:
                            store[key] = await self._aconstruct(implementation)
                        return store[key]

                    provider = provider_request_class_async
                else:

                    def provider_request_class():
                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(abstract)

                        if key not in store:
                            store[key] = self._construct(implementation)
                        return store[key]

                    provider = provider_request_class

            if is_fn:
                assert provider_fn is not None

                if is_async_generator_callable(provider_fn):

                    async def provider_request_async_gen():
                        assert provider_fn is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(provider_fn)

                        if key not in store:
                            params = await self._resolve_func_params_async(provider_fn)
                            ctx = _wrap_async_gen(provider_fn, params)
                            store[key] = await ctx.__aenter__()

                            if RequestScopeService.CONTEXT_MANAGERS_KEY not in store:
                                store[RequestScopeService.CONTEXT_MANAGERS_KEY] = []

                            store[RequestScopeService.CONTEXT_MANAGERS_KEY].append(ctx)

                        return store[key]

                    provider = provider_request_async_gen

                elif is_generator_callable(provider_fn):

                    def provider_request_gen_sync():
                        assert provider_fn is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(provider_fn)

                        if key not in store:
                            params = self._resolve_func_params(provider_fn)
                            ctx = _wrap_sync_gen(provider_fn, params)
                            store[key] = ctx.__enter__()

                            if RequestScopeService.CONTEXT_MANAGERS_KEY not in store:
                                store[RequestScopeService.CONTEXT_MANAGERS_KEY] = []

                            store[RequestScopeService.CONTEXT_MANAGERS_KEY].append(ctx)

                        return store[key]

                    provider = provider_request_gen_sync

                elif needs_async:

                    async def provider_request_callable_async():
                        assert provider_fn is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(provider_fn)

                        if key not in store:
                            params = await self._resolve_func_params_async(provider_fn)
                            store[key] = await provider_fn(**params)  # pyright: ignore[reportGeneralTypeIssues]
                        return store[key]

                    provider = provider_request_callable_async

                else:

                    def provider_request_callable_sync():
                        assert provider_fn is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(provider_fn)

                        if key not in store:
                            params = self._resolve_func_params(provider_fn)
                            store[key] = provider_fn(**params)
                        return store[key]

                    provider = provider_request_callable_sync

        if provider is None:
            raise RuntimeError(f'Nao foi possivel registrar {abstract}')

        key = abstract or provider_fn
        impl = provider_fn if is_fn else implementation

        assert key is not None

        self._providers[key] = provider
        self._registrations[key] = {'implementation': impl, 'scope': scope}

    def _resolve_func_params[T](self, func: ProviderFn[T]) -> dict[str, Any]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)
        kwargs = {}

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = self.resolve(param.default.provider_fn)
                kwargs[name] = resolved

            elif param_type and self._has_provider_for(param_type):
                resolved = self.resolve(param_type)
                kwargs[name] = resolved

            else:
                if param.default is not inspect._empty:  # pyright: ignore[reportPrivateUsage]
                    pass
                else:
                    raise RuntimeError(
                        f"Não é possível resolver parâmetro '{name}' para {func}. Falta provider ou default."
                    )

        return kwargs

    async def _resolve_func_params_async[T](self, func: ProviderFn[T]) -> dict[str, Any]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)
        kwargs = {}

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = await self.aresolve(param.default.provider_fn)
                kwargs[name] = resolved

            elif param_type and self._has_provider_for(param_type):
                resolved = await self.aresolve(param_type)
                kwargs[name] = resolved

            else:
                if param.default is not inspect._empty:  # pyright: ignore[reportPrivateUsage]
                    pass
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

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = self.resolve(param.default.provider_fn)

                # 🔧 CORREÇÃO: Detecta corrotina não aguardada
                if inspect.iscoroutine(resolved):
                    raise RuntimeError(
                        f"Parâmetro '{name}' da classe {cls.__name__} depende de um provider assíncrono. "
                        f'Isso não é permitido em escopo SINGLETON/TRANSIENT com classes síncronas. '
                        f'Considere usar scope=Scope.REQUEST ou tornar todas as dependências síncronas.'
                    )

                kwargs[name] = resolved

            elif param_type and self._has_provider_for(param_type):
                resolved = self.resolve(param_type)

                # 🔧 CORREÇÃO: Detecta corrotina não aguardada
                if inspect.iscoroutine(resolved):
                    raise RuntimeError(
                        f"Parâmetro '{name}' (tipo {param_type.__name__}) da classe {cls.__name__} "
                        f'depende de um provider assíncrono. '
                        f'Isso não é permitido em escopo SINGLETON/TRANSIENT com classes síncronas. '
                        f'Considere usar scope=Scope.REQUEST ou tornar todas as dependências síncronas.'
                    )

                kwargs[name] = resolved
            else:
                if param.default is not inspect._empty:  # pyright: ignore[reportPrivateUsage]
                    pass
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

            if param.default and isinstance(param.default, ProviderDependency):
                kwargs[name] = await self.aresolve(param.default.provider_fn)

            elif param_type and self._has_provider_for(param_type):
                kwargs[name] = await self.aresolve(param_type)
            else:
                if param.default is not inspect._empty:  # pyright: ignore[reportPrivateUsage]
                    pass
                else:
                    raise RuntimeError(
                        f"Não é possível resolver parâmetro '{name}' para {cls}. Falta provider ou default."
                    )

        return cls(**kwargs)

    def _has_provider_for(self, t: type[Any] | ProviderFn[Any]) -> bool:
        return t in self._providers

    def _class_needs_async_resolution(self, cls: type[Any]) -> bool:
        """Verifica se alguma dependência da classe precisa de resolução async."""
        signature = inspect.signature(cls.__init__)
        type_hints = get_type_hints(cls.__init__)

        for name, param in signature.parameters.items():
            if name == 'self':
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                provider_fn = param.default.provider_fn
                if provider_fn in self._providers:
                    provider = self._providers[provider_fn]
                    if is_async_callable(provider):
                        return True

            elif param_type and param_type in self._providers:
                provider = self._providers[param_type]
                if is_async_callable(provider):
                    return True

        return False

    def resolve[T](self, abstract: Type[T] | ProviderFn[T]) -> T:
        provider = cast(Callable[[], T], self._providers.get(abstract))

        if provider is None:
            raise ValueError(f'provider for {abstract} not registered')

        return provider()

    async def aresolve[T](self, abstract: Type[T] | AsyncProviderFn[T]) -> T:
        provider = cast(Callable[[], T], self._providers.get(abstract))

        if provider is None:
            raise ValueError(f'Provider para {abstract} nao foi registrado')

        result = provider()

        if inspect.iscoroutine(result):
            return await result

        return result

    def inject[T, **K](self, func: Callable[K, T]) -> Callable[K, T]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)

        injectable_params = set()

        for name, param in signature.parameters.items():
            if name == 'self' or name == 'cls':
                continue

            param_type = type_hints.get(name, None)

            if (
                param.default
                and isinstance(param.default, ProviderDependency)
                and self._has_provider_for(param.default.provider_fn)
            ):
                injectable_params.add(name)

            elif param_type and self._has_provider_for(param_type):
                injectable_params.add(name)

        if not is_async_callable(func):

            def sync_wrapper(*args, **kwargs):
                bound = signature.bind_partial(*args, **kwargs)

                for param_name in injectable_params:
                    if param_name not in bound.arguments:
                        source = type_hints[param_name]

                        if self._is_Provide_param(signature.parameters[param_name]):
                            default: ProviderDependency[T] = signature.parameters[param_name].default
                            source = default.provider_fn

                        provider = self._providers[source]

                        if is_async_callable(provider):
                            raise RuntimeError(
                                f'async dependencies not supported in sync functions.'
                                ' The dependency probably has async arguments in its signature.'
                                f'{param_name=} {source=} {provider=}'
                            )

                        bound.arguments[param_name] = self.resolve(source)

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
                        source: Any = type_hints[param_name]

                        if self._is_Provide_param(signature.parameters[param_name]):
                            default: ProviderDependency[T] = signature.parameters[param_name].default
                            source = default.provider_fn

                        bound.arguments[param_name] = await self.aresolve(source)

                return await func(*bound.args, **bound.kwargs)  # pyright: ignore[reportGeneralTypeIssues]

            async_wrapper.__name__ = func.__name__
            async_wrapper.__doc__ = func.__doc__
            async_wrapper.__annotations__ = func.__annotations__
            return async_wrapper  # pyright: ignore[reportReturnType]

    def _is_Provide_param(self, param: inspect.Parameter):
        if param.default != INSPECT_EMPTY and isinstance(param.default, ProviderDependency):
            return True
        return False

    def provide(self, t: Any):
        async def _dep():
            return await self.aresolve(t)

        return _dep
