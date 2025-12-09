import inspect
from typing import Any, Callable, Type, cast

from depin._internal.exceptions import MissingProviderError, UnexpectedCoroutineError
from depin._internal.helpers import (
    get_cached_signature,
    get_cached_type_hints,
    is_async_callable,
    is_async_generator_callable,
    is_generator_callable,
)
from depin._internal.request_scope import RequestScopeService
from depin._internal.types import CallableProvider, ProviderDependency, ProviderInfo, ProviderType, Scope
from depin._internal.wraps import wrap_async_gen, wrap_sync_gen

INSPECT_EMPTY = inspect._empty  # pyright: ignore[reportPrivateUsage]


def Inject[T](dependency: ProviderType[T]) -> T:
    return ProviderDependency(dependency)  # type: ignore[return-value]


class Container:
    Scope = Scope

    def __init__(self):
        self._providers: dict[type[Any] | CallableProvider[Any], Callable[[], Any]] = {}
        self._registrations: dict[type[Any] | CallableProvider[Any], ProviderInfo] = {}

    @property
    def registrations(self):
        return self._registrations

    def register[T](
        self,
        scope: Scope,
        *,
        abstract: type[T] | None = None,
        aliases: list[type[T]] | None = None,
    ):
        def decorator[U](source: U) -> U:

            self.bind(
                abstract=abstract,
                source=source,  # type: ignore[arg-type]
                scope=scope,
                aliases=aliases,
            )

            return source

        return decorator

    def bind[T](
        self,
        *,
        scope: Scope,
        source: type[T] | CallableProvider[T],
        abstract: type[T] | None = None,
        aliases: list[type[T]] | None = None,
    ):
        if scope != Scope.REQUEST:
            if is_async_generator_callable(source):
                raise ValueError('Async generators are not supported in non-request scopes')
            elif is_generator_callable(source):
                raise ValueError('Generators are not supported in non-request scopes')

        if isinstance(source, type):
            self._register(
                abstract=abstract,
                implementation=source,
                callable_provider=None,
                scope=scope,
                aliases=aliases,
            )
        elif callable(source):
            self._register(
                abstract=abstract,
                implementation=None,
                callable_provider=source,
                scope=scope,
                aliases=aliases,
            )
        else:
            raise ValueError(f'failed to register {source=}')

    def _register[T](
        self,
        *,
        scope: Scope = Scope.SINGLETON,
        abstract: type[T] | None,
        implementation: type[T] | None,
        callable_provider: CallableProvider[T] | None,
        aliases: list[type[T]] | None = None,
    ):

        abstract = abstract or implementation

        if abstract is None and implementation is None and callable_provider is None:
            raise ValueError('abstract, implementation or callable_provider must be provided')

        if implementation is None and callable_provider is None:
            raise ValueError('implementation and callable_provider cannot both be None')

        if callable_provider and implementation:
            raise ValueError('callable_provider and implementation cannot be both non-none')

        implementation = cast(type[T], implementation)
        abstract = cast(type[T], abstract)

        is_callable = bool(callable_provider)
        is_class = not is_callable
        needs_async = False
        provider = None

        if is_class:
            needs_async = self._class_needs_async_resolution(implementation)

        if is_callable and callable_provider is not None:
            # TODO: VERIFICAR OS PARAMETROS DO CALLABLE PRA VER SE ELE DEPENDE DE ASYNC
            needs_async = self._callable_needs_async_resolution(callable_provider)

        if scope == Scope.SINGLETON:
            instance_holder = {}

            if is_class:
                if needs_async:

                    async def provider_singleton_class_async():
                        if 'inst' not in instance_holder:
                            instance_holder['inst'] = await self._construct_async(implementation)
                        return instance_holder['inst']

                    provider = provider_singleton_class_async
                else:

                    def provider_singleton_class():
                        if 'inst' not in instance_holder:
                            instance_holder['inst'] = self._construct(implementation)
                        return instance_holder['inst']

                    provider = provider_singleton_class

            elif is_callable:
                if needs_async:

                    async def provider_singleton_callable_async():
                        assert callable_provider is not None

                        if 'inst' not in instance_holder:
                            params = await self._resolve_func_params_async(callable_provider)

                            if is_async_callable(callable_provider):
                                instance_holder['inst'] = await callable_provider(**params)  # pyright: ignore[reportGeneralTypeIssues]
                            else:
                                instance_holder['inst'] = callable_provider(**params)

                        return instance_holder['inst']

                    provider = provider_singleton_callable_async
                else:

                    def provider_singleton_callable_sync():
                        assert callable_provider is not None

                        if 'inst' not in instance_holder:
                            params = self._resolve_func_params(callable_provider)
                            instance_holder['inst'] = callable_provider(**params)
                        return instance_holder['inst']

                    provider = provider_singleton_callable_sync

        elif scope == Scope.TRANSIENT:
            if is_class:
                if needs_async:

                    async def provider_transient_class_async():
                        return await self._construct_async(implementation)

                    provider = provider_transient_class_async
                else:

                    def provider_transient_class():
                        return self._construct(implementation)

                    provider = provider_transient_class

            if is_callable:
                if needs_async:

                    async def provider_transient_callable_async():
                        assert callable_provider is not None

                        params = await self._resolve_func_params_async(callable_provider)

                        if is_async_callable(callable_provider):
                            return await callable_provider(**params)  # pyright: ignore[reportGeneralTypeIssues]
                        else:
                            return callable_provider(**params)

                    provider = provider_transient_callable_async
                else:

                    def provider_transient_callable_sync():
                        assert callable_provider is not None

                        params = self._resolve_func_params(callable_provider)
                        return callable_provider(**params)

                    provider = provider_transient_callable_sync

        elif scope == Scope.REQUEST:
            if is_class:
                if needs_async:

                    async def provider_request_class_async():
                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(abstract)

                        if key not in store:
                            store[key] = await self._construct_async(implementation)
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

            if is_callable:
                assert callable_provider is not None

                if is_async_generator_callable(callable_provider):

                    async def provider_request_async_gen():
                        assert callable_provider is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(callable_provider)

                        if key not in store:
                            params = await self._resolve_func_params_async(callable_provider)
                            ctx = wrap_async_gen(callable_provider, params)
                            store[key] = await ctx.__aenter__()

                            if RequestScopeService.CONTEXT_MANAGERS_KEY not in store:
                                store[RequestScopeService.CONTEXT_MANAGERS_KEY] = []

                            store[RequestScopeService.CONTEXT_MANAGERS_KEY].append(ctx)

                        return store[key]

                    provider = provider_request_async_gen

                elif is_generator_callable(callable_provider):

                    def provider_request_gen_sync():
                        assert callable_provider is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(callable_provider)

                        if key not in store:
                            params = self._resolve_func_params(callable_provider)
                            ctx = wrap_sync_gen(callable_provider, params)
                            store[key] = ctx.__enter__()

                            if RequestScopeService.CONTEXT_MANAGERS_KEY not in store:
                                store[RequestScopeService.CONTEXT_MANAGERS_KEY] = []

                            store[RequestScopeService.CONTEXT_MANAGERS_KEY].append(ctx)

                        return store[key]

                    provider = provider_request_gen_sync

                elif needs_async:

                    async def provider_request_callable_async():
                        assert callable_provider is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(callable_provider)

                        if key not in store:
                            params = await self._resolve_func_params_async(callable_provider)

                            if is_async_callable(callable_provider):
                                store[key] = await callable_provider(**params)  # pyright: ignore[reportGeneralTypeIssues]
                            else:
                                store[key] = callable_provider(**params)

                        return store[key]

                    provider = provider_request_callable_async

                else:

                    def provider_request_callable_sync():
                        assert callable_provider is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(callable_provider)

                        if key not in store:
                            params = self._resolve_func_params(callable_provider)
                            store[key] = callable_provider(**params)
                        return store[key]

                    provider = provider_request_callable_sync

        key = abstract or callable_provider
        impl = callable_provider if is_callable else implementation

        if provider is None:
            raise RuntimeError(f'Cannot register {key=}, {impl=}: no provider found')

        assert key is not None

        for item in [key, *(aliases or [])]:
            self._providers[item] = provider
            self._registrations[item] = ProviderInfo(
                implementation=impl,
                scope=scope,
            )

    def _resolve_func_params[T](self, func: CallableProvider[T]) -> dict[str, Any]:
        signature = get_cached_signature(func)
        type_hints = get_cached_type_hints(func)
        kwargs = {}

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = self.get(param.default.dependency)
                kwargs[name] = resolved

            elif param_type and self._has_provider_for(param_type):
                resolved = self.get(param_type)
                kwargs[name] = resolved

            else:
                if param.default is not INSPECT_EMPTY:
                    pass
                else:
                    raise MissingProviderError(
                        f"Cannot resolve parameter '{name}' (type: {param_type}) for {func}. "
                        'Missing provider or default value.'
                    )

        return kwargs

    async def _resolve_func_params_async[T](self, func: CallableProvider[T]) -> dict[str, Any]:
        signature = get_cached_signature(func)
        type_hints = get_cached_type_hints(func)
        kwargs = {}

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = await self.get_async(param.default.dependency)
                kwargs[name] = resolved

            elif param_type and self._has_provider_for(param_type):
                resolved = await self.get_async(param_type)
                kwargs[name] = resolved

            else:
                if param.default is not INSPECT_EMPTY:
                    pass
                else:
                    raise MissingProviderError(
                        f"Cannot resolve parameter '{name}' (type: {param_type}) for {func}. "
                        'Missing provider or default value.'
                    )

        return kwargs

    def _construct[T](self, cls: type[T]):
        signature = get_cached_signature(cls.__init__)
        type_hints = get_cached_type_hints(cls.__init__)
        kwargs = {}

        for name, param in signature.parameters.items():
            if name == 'self':
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = self.get(param.default.dependency)

                if inspect.iscoroutine(resolved):
                    raise UnexpectedCoroutineError(
                        f"Parameter '{name}' of class {cls.__name__} depends on an asynchronous provider. "
                        f'This is not allowed in SINGLETON/TRANSIENT scope with synchronous classes. '
                        f'Consider using scope=Scope.REQUEST or making all dependencies synchronous.'
                    )

                kwargs[name] = resolved

            elif param_type and self._has_provider_for(param_type):
                resolved = self.get(param_type)

                if inspect.iscoroutine(resolved):
                    raise UnexpectedCoroutineError(
                        f"Parameter '{name}' (type {param_type.__name__}) of class {cls.__name__} "
                        f'depends on an asynchronous provider. '
                        f'This is not allowed in SINGLETON/TRANSIENT scope with synchronous classes. '
                        f'Consider using scope=Scope.REQUEST or making all dependencies synchronous.'
                    )

                kwargs[name] = resolved
            else:
                if param.default is not INSPECT_EMPTY:
                    pass
                else:
                    raise MissingProviderError(
                        f"Cannot resolve parameter '{name}' (type: {param_type}) for {cls}. "
                        'Missing provider or default value.'
                    )

        return cls(**kwargs)

    async def _construct_async[T](self, cls: type[T]):
        signature = get_cached_signature(cls.__init__)
        type_hints = get_cached_type_hints(cls.__init__)
        kwargs = {}

        for name, param in signature.parameters.items():
            if name == 'self':
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                kwargs[name] = await self.get_async(param.default.dependency)

            elif param_type and self._has_provider_for(param_type):
                kwargs[name] = await self.get_async(param_type)
            else:
                if param.default is not INSPECT_EMPTY:
                    pass
                else:
                    raise MissingProviderError(
                        f"Cannot resolve parameter '{name}' (type: {param_type}) for {cls}. "
                        'Missing provider or default value.'
                    )

        return cls(**kwargs)

    def get[T](self, abstract: Type[T] | CallableProvider[T]) -> T:
        provider = cast(Callable[[], T], self._providers.get(abstract))

        if provider is None:
            raise MissingProviderError(f'Provider for {abstract} not registered')

        return provider()

    async def get_async[T](self, abstract: Type[T] | CallableProvider[T]) -> T:
        provider = cast(Callable[[], T], self._providers.get(abstract))

        if provider is None:
            raise MissingProviderError(f'Provider for {abstract} not registered')

        result = provider()

        if inspect.iscoroutine(result):
            return await result

        return result

    def inject[T, **K](self, func: Callable[K, T]) -> Callable[K, T]:
        signature = get_cached_signature(func)
        type_hints = get_cached_type_hints(func)

        injectable_params = set()

        for name, param in signature.parameters.items():
            if name == 'self' or name == 'cls':
                continue

            param_type = type_hints.get(name, None)

            if (
                param.default
                and isinstance(param.default, ProviderDependency)
                and self._has_provider_for(param.default.dependency)
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
                            default: ProviderDependency = signature.parameters[param_name].default
                            source = default.dependency

                        provider = self._providers[source]

                        if is_async_callable(provider):
                            raise RuntimeError(
                                f'Async dependencies not supported in sync functions.'
                                ' The dependency probably has async arguments in its signature.'
                                f'{param_name=} {source=} {provider=}'
                            )

                        bound.arguments[param_name] = self.get(source)

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
                            default: ProviderDependency = signature.parameters[param_name].default
                            source = default.dependency

                        bound.arguments[param_name] = await self.get_async(source)

                return await func(*bound.args, **bound.kwargs)  # pyright: ignore[reportGeneralTypeIssues]

            async_wrapper.__name__ = func.__name__
            async_wrapper.__doc__ = func.__doc__
            async_wrapper.__annotations__ = func.__annotations__
            return async_wrapper  # pyright: ignore[reportReturnType]

    def Depends(self, t: type[Any] | CallableProvider[Any]):
        from fastapi import Depends

        async def _dep():
            return await self.get_async(t)

        return Depends(_dep)

    def _class_needs_async_resolution[T](self, cls: type[T]) -> bool:
        signature = get_cached_signature(cls.__init__)
        type_hints = get_cached_type_hints(cls.__init__)

        for name, param in signature.parameters.items():
            if name == 'self':
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                callable_provider = param.default.dependency

                if callable_provider in self._providers:
                    if is_async_callable(self._providers[callable_provider]):
                        return True

            elif param_type and param_type in self._providers:
                if is_async_callable(self._providers[param_type]):
                    return True

        return False

    def _callable_needs_async_resolution[T](self, func: CallableProvider[T]) -> bool:
        if is_async_callable(func) or is_async_generator_callable(func):
            return True

        signature = get_cached_signature(func)
        type_hints = get_cached_type_hints(func)

        for name, param in signature.parameters.items():
            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                callable_provider = param.default.dependency

                if callable_provider in self._providers:
                    if is_async_callable(self._providers[callable_provider]):
                        return True

            elif param_type and param_type in self._providers:
                if is_async_callable(self._providers[param_type]):
                    return True

        return False

    def _has_provider_for(self, t: type[Any] | CallableProvider[Any]) -> bool:
        return t in self._providers

    def _is_Provide_param(self, param: inspect.Parameter):
        if param.default != INSPECT_EMPTY and isinstance(param.default, ProviderDependency):
            return True
        return False
