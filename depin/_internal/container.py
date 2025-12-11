import inspect
from typing import Any, Callable, cast

from fastapi import Depends

from depin._internal.exceptions import CircularDependencyError, MissingProviderError, UnexpectedCoroutineError
from depin._internal.helpers import (
    get_cached_signature,
    get_cached_type_hints,
    is_async_callable,
    is_async_generator_callable,
    is_generator_callable,
)
from depin._internal.request_scope import RequestScopeService
from depin._internal.types import Provider, ProviderDependency, ProviderInfo, ProviderSource, Resolvable, Scope
from depin._internal.wraps import wrap_async_gen, wrap_sync_gen

INSPECT_EMPTY = inspect._empty  # pyright: ignore[reportPrivateUsage]


def Inject[T](dependency: ProviderSource[T]) -> T:
    return ProviderDependency(dependency)  # type: ignore[return-value]


class Container:
    """Dependency injection container"""

    Scope = Scope

    def __init__(self):
        self._providers: dict[ProviderSource, ProviderInfo] = {}

    def register[T](
        self,
        scope: Scope,
        *,
        abstract: type[T] | None = None,
        aliases: list[type] | None = None,
    ):
        """Decorator that registers a class or function as a provider in the container.

        ### Example:
            ```py
            @container.register(Scope.REQUEST)
            def get_session():
                with Session() as session:
                    yield session

            @container.register(Scope.REQUEST)
            class SomeRepository:
                def __init__(self, session: Session = Inject(get_session)):
                    self._session = session
            ```
        """

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
        source: ProviderSource[T],
        abstract: type[T] | None = None,
        aliases: list[type] | None = None,
    ):
        """Function used to register a class or function as a provider in the container.

        ### Example:
            ```py
            def get_session():
                with Session() as session:
                    yield session

            class SomeRepository:
                def __init__(self, session: Session = Inject(get_session)):
                    self._session = session

            container.bind(source=get_session, scope=Scope.REQUEST)
            container.bind(source=SomeRepository, scope=Scope.REQUEST)
            ```
        """

        if scope != Scope.REQUEST:
            if is_async_generator_callable(source):
                raise RuntimeError('Async generators are not supported in non-request scopes')
            elif is_generator_callable(source):
                raise RuntimeError('Generators are not supported in non-request scopes')

        if isinstance(source, type):
            return self._register(
                abstract=abstract,
                implementation=source,
                callable_source=None,
                scope=scope,
                aliases=aliases,
            )

        elif callable(source):
            return self._register(
                abstract=abstract,
                implementation=None,
                callable_source=source,
                scope=scope,
                aliases=aliases,
            )

        raise ValueError(f'failed to register {source=}; source must be a type or callable')

    def _register[T](
        self,
        *,
        scope: Scope = Scope.SINGLETON,
        abstract: type[T] | None,
        implementation: type[T] | None,
        callable_source: Resolvable[T] | None,
        aliases: list[type] | None = None,
    ):

        abstract = abstract or implementation

        if abstract is None and implementation is None and callable_source is None:
            raise ValueError('abstract, implementation or callable_source must be provided')

        if implementation is None and callable_source is None:
            raise ValueError('implementation and callable_source cannot both be None')

        if callable_source and implementation:
            raise ValueError('callable_source and implementation cannot be both non-none')

        implementation = cast(type[T], implementation)
        abstract = cast(type[T], abstract)

        is_callable = bool(callable_source)
        is_class = not is_callable
        needs_async = False
        provider = None

        if is_class:
            needs_async = self._class_needs_async_resolution(implementation)

        if is_callable and callable_source is not None:
            needs_async = self._callable_needs_async_resolution(callable_source)

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
                        assert callable_source is not None

                        if 'inst' not in instance_holder:
                            params = await self._resolve_func_params_async(callable_source)

                            if is_async_callable(callable_source):
                                instance_holder['inst'] = await callable_source(**params)  # pyright: ignore[reportGeneralTypeIssues]
                            else:
                                instance_holder['inst'] = callable_source(**params)

                        return instance_holder['inst']

                    provider = provider_singleton_callable_async
                else:

                    def provider_singleton_callable_sync():
                        assert callable_source is not None

                        if 'inst' not in instance_holder:
                            params = self._resolve_func_params(callable_source)
                            instance_holder['inst'] = callable_source(**params)
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
                        assert callable_source is not None

                        params = await self._resolve_func_params_async(callable_source)

                        if is_async_callable(callable_source):
                            return await callable_source(**params)  # pyright: ignore[reportGeneralTypeIssues]
                        else:
                            return callable_source(**params)

                    provider = provider_transient_callable_async
                else:

                    def provider_transient_callable_sync():
                        assert callable_source is not None

                        params = self._resolve_func_params(callable_source)
                        return callable_source(**params)

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
                assert callable_source is not None

                if is_async_generator_callable(callable_source):

                    async def provider_request_async_gen():
                        assert callable_source is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(callable_source)

                        if key not in store:
                            params = await self._resolve_func_params_async(callable_source)
                            ctx = wrap_async_gen(callable_source, params)
                            store[key] = await ctx.__aenter__()

                            if RequestScopeService.CONTEXT_MANAGERS_KEY not in store:
                                store[RequestScopeService.CONTEXT_MANAGERS_KEY] = []

                            store[RequestScopeService.CONTEXT_MANAGERS_KEY].append(ctx)

                        return store[key]

                    provider = provider_request_async_gen

                elif is_generator_callable(callable_source):

                    def provider_request_gen_sync():
                        assert callable_source is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(callable_source)

                        if key not in store:
                            params = self._resolve_func_params(callable_source)
                            ctx = wrap_sync_gen(callable_source, params)
                            store[key] = ctx.__enter__()

                            if RequestScopeService.CONTEXT_MANAGERS_KEY not in store:
                                store[RequestScopeService.CONTEXT_MANAGERS_KEY] = []

                            store[RequestScopeService.CONTEXT_MANAGERS_KEY].append(ctx)

                        return store[key]

                    provider = provider_request_gen_sync

                elif needs_async:

                    async def provider_request_callable_async():
                        assert callable_source is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(callable_source)

                        if key not in store:
                            params = await self._resolve_func_params_async(callable_source)

                            if is_async_callable(callable_source):
                                store[key] = await callable_source(**params)  # pyright: ignore[reportGeneralTypeIssues]
                            else:
                                store[key] = callable_source(**params)

                        return store[key]

                    provider = provider_request_callable_async

                else:

                    def provider_request_callable_sync():
                        assert callable_source is not None

                        store = RequestScopeService.get_request_store()
                        key = RequestScopeService.get_request_key(callable_source)

                        if key not in store:
                            params = self._resolve_func_params(callable_source)
                            store[key] = callable_source(**params)
                        return store[key]

                    provider = provider_request_callable_sync

        key = abstract or callable_source
        impl = callable_source if is_callable else implementation

        if provider is None:
            raise RuntimeError(f'Cannot register {key=}, {impl=}: no provider found')

        assert key is not None

        for item in [key, *(aliases or [])]:
            self._providers[item] = ProviderInfo(
                provider=provider,
                source=impl,
                scope=scope,
                needs_async=needs_async,
            )

    def get[T](self, abstract: ProviderSource[T]) -> T:
        """Function used to resolve some dependency manually.

        ### Example:
            ```python
            user_service = container.get(UserService)
            ```
        """

        provider = self._get_provider(abstract)

        if is_async_callable(provider):
            raise UnexpectedCoroutineError(f'Provider for {abstract} is asynchronous, use get_async instead.')

        sync_provider = cast(Callable[[], T], provider)

        return sync_provider()

    async def get_async[T](self, abstract: ProviderSource[T]) -> T:
        """Function used to resolve some asynchronous dependency manually.

        ### Example:
            ```python
            user_service = await container.get_async(UserService)
            ```
        """

        provider = cast(Callable[[], T], self._get_provider(abstract))

        result = provider()

        if inspect.iscoroutine(result):
            return await result

        return result

    def inject[T, **K](self, func: Callable[K, T]) -> Callable[K, T]:
        """Decorator used to inject dependencies into function/method parameters.

        ### Example:
            ```python
            @container.inject
            def get_user(user_service: UserService = Inject(UserService)):
                return user_service.get_user()
            ```
        """

        signature = get_cached_signature(func)
        type_hints = get_cached_type_hints(func)

        injectable_params = set()

        for name, param in signature.parameters.items():
            if name == 'self' or name == 'cls':
                continue

            param_type = type_hints.get(name)

            if (
                param.default
                and isinstance(param.default, ProviderDependency)
                and self._has_provider_for(param.default.provider_source)
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

                        if self._is_Inject_param(signature.parameters[param_name]):
                            default: ProviderDependency = signature.parameters[param_name].default
                            source = default.provider_source

                        provider = self._get_provider(source)

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

                        if self._is_Inject_param(signature.parameters[param_name]):
                            default: ProviderDependency = signature.parameters[param_name].default
                            source = default.provider_source

                        bound.arguments[param_name] = await self.get_async(source)

                return await func(*bound.args, **bound.kwargs)  # pyright: ignore[reportGeneralTypeIssues]

            async_wrapper.__name__ = func.__name__
            async_wrapper.__doc__ = func.__doc__
            async_wrapper.__annotations__ = func.__annotations__
            return async_wrapper  # pyright: ignore[reportReturnType]

    def Depends(self, t: ProviderSource):
        """Wrapper used to convert some dependency to be used in FastAPI.

        Args:
            t: Dependency to be used in FastAPI.

        ### Example:
            ```python
            @app.get('/user')
            def get_user(user_service: UserService = container.Depends(UserService)):
                return user_service.get_user()
            ```
        """

        async def _dep():
            return await self.get_async(t)

        return Depends(_dep)

    def _resolve_func_params[T](self, func: Resolvable[T]) -> dict[str, Any]:
        signature = get_cached_signature(func)
        type_hints = get_cached_type_hints(func)
        kwargs = {}

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name)

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = self.get(param.default.provider_source)
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

    async def _resolve_func_params_async[T](self, func: Resolvable[T]) -> dict[str, Any]:
        signature = get_cached_signature(func)
        type_hints = get_cached_type_hints(func)
        kwargs = {}

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = type_hints.get(name)

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = await self.get_async(param.default.provider_source)
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

            param_type = type_hints.get(name)

            if param.default and isinstance(param.default, ProviderDependency):
                resolved = self.get(param.default.provider_source)

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

            param_type = type_hints.get(name)

            if param.default and isinstance(param.default, ProviderDependency):
                kwargs[name] = await self.get_async(param.default.provider_source)

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

    def _class_needs_async_resolution[T](self, cls: type[T]) -> bool:
        return self._class_needs_async_resolution_recursive(cls, set())

    def _callable_needs_async_resolution[T](self, func: Resolvable[T]) -> bool:
        if is_async_callable(func) or is_async_generator_callable(func):
            return True

        return self._callable_needs_async_resolution_recursive(func, set())

    def _source_needs_async_recursive(self, source: ProviderSource, visited: set[Any]) -> bool:
        source_id = id(source)

        if source_id in visited:
            raise CircularDependencyError(f'Circular dependency detected: {source}')

        visited.add(source_id)

        try:
            if self._has_provider_for(source):
                provider_info = self._providers[source]

                if provider_info.needs_async:
                    return True

                if is_async_callable(provider_info.provider):
                    return True

            if isinstance(source, type):
                return self._class_needs_async_resolution_recursive(source, visited)

            elif callable(source):
                if is_async_callable(source) or is_async_generator_callable(source):
                    return True

                return self._callable_needs_async_resolution_recursive(source, visited)

        finally:
            visited.remove(source_id)

    def _callable_needs_async_resolution_recursive(self, func: Resolvable[Any], visited: set[Any]) -> bool:
        signature = get_cached_signature(func)
        type_hints = get_cached_type_hints(func)

        for name, param in signature.parameters.items():
            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                dep = param.default.provider_source
                if self._source_needs_async_recursive(dep, visited):
                    return True

            elif param_type:
                if self._source_needs_async_recursive(param_type, visited):
                    return True

        return False

    def _class_needs_async_resolution_recursive(self, cls: type, visited: set[Any]) -> bool:
        signature = get_cached_signature(cls.__init__)
        type_hints = get_cached_type_hints(cls.__init__)

        for name, param in signature.parameters.items():
            if name == 'self':
                continue

            param_type = type_hints.get(name, None)

            if param.default and isinstance(param.default, ProviderDependency):
                dep = param.default.provider_source
                if self._source_needs_async_recursive(dep, visited):
                    return True

            elif param_type:
                if self._source_needs_async_recursive(param_type, visited):
                    return True

        return False

    def _has_provider_for(self, t: ProviderSource) -> bool:
        return t in self._providers

    def _is_Inject_param(self, param: inspect.Parameter):
        if param.default != INSPECT_EMPTY and isinstance(param.default, ProviderDependency):
            return True
        return False

    def _get_provider[T](self, t: ProviderSource[T]) -> Provider[T]:
        provider_info = self._providers.get(t)

        if not provider_info:
            raise MissingProviderError(f'Provider for {t} not registered')

        return provider_info.provider  # pyright: ignore[reportReturnType]
