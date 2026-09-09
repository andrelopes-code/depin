"""FastAPI endpoint compilation behind the public integration surface."""

from collections.abc import Callable
from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Annotated, Final, TypeGuard

import fastapi
from fastapi import FastAPI, Request
from fastapi.dependencies.models import Dependant
from fastapi.params import Depends
from fastapi.routing import APIRoute, request_response
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from depin import FrozenContainer, Token, optional_hosted_container
from depin._integration import LazyScopeSeed, _lazy_host, _provide_active_eager_seed, _provide_lazy_seed
from depin.errors import ContainerNotBoundError, FastAPIIntegrationError

__all__: list[str] = []

_REQUEST_ARGUMENT = '__depin_request__'
_INSTALLATION_MARKER: Final[object] = object()


@dataclass(frozen=True, slots=True)
class _InjectResolver[T]:
    key: type[T] | Token[T]

    async def __call__(self, request: Request) -> T:
        _provide_lazy_seed(LazyScopeSeed(Request, lambda: request))
        container = optional_hosted_container()
        if container is None:
            raise ContainerNotBoundError(
                'Inject[...] resolved outside a hosted FastAPI request; call install(app, container) '
                'after route registration or install RequestScope compatibility middleware.'
            )
        _provide_active_eager_seed(container, Request, request)
        return await container.aresolve(self.key)


@dataclass(frozen=True, slots=True)
class _EndpointProgram:
    container: FrozenContainer
    entries: tuple[tuple[str, type[object] | Token[object]], ...]

    async def resolve(self, request: Request) -> dict[str, object]:
        _provide_lazy_seed(LazyScopeSeed(Request, lambda: request))
        return {name: await self.container.aresolve(key) for name, key in self.entries}


class Inject:
    """FastAPI parameter annotation that resolves a dependency from depin."""

    def __class_getitem__[T](cls, key: type[T] | Token[T]) -> object:
        return Annotated[object, Depends(dependency=_InjectResolver(key))]


@dataclass(frozen=True, slots=True)
class _RoutePlan:
    route: APIRoute
    program: _EndpointProgram
    dependencies: list[Dependant]
    endpoint: Callable[..., object]
    request_argument: str
    passes_request: bool


@dataclass(frozen=True, slots=True)
class _AppliedRoute:
    route: APIRoute
    call: Callable[..., object] | None
    dependencies: list[Dependant]
    request_argument: str | None
    app: ASGIApp


class _LazyRequestScope:
    __slots__ = ('_app', '_container')

    def __init__(self, app: ASGIApp, container: FrozenContainer, marker: object) -> None:
        del marker
        self._app = app
        self._container = container

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self._app(scope, receive, send)
            return
        async with _lazy_host(self._container):
            await self._app(scope, receive, send)


def install(app: FastAPI, container: FrozenContainer) -> None:
    """Compile direct `Inject` parameters after all application routes are registered.

    The compiled route resolves all direct injections once per request while
    preserving FastAPI's native dependency graph. Call this before application
    startup; repeat calls with the same container compile newly added routes.
    `RequestScope` remains the eager compatibility path. HTTP scopes are opened
    only for scoped values, request seeds, or request-owned resources; streaming,
    background, and WebSocket cleanup retains the same lifetime as `RequestScope`.

    Args:
        app: Application whose existing path operation routes to compile.
        container: Frozen container hosted for installed HTTP and WebSocket work.

    Raises:
        FastAPIIntegrationError: The application has already started, was
            installed with another container, or exposes an unsupported route
            shape. Upgrade FastAPI or use `RequestScope` compatibility middleware.

    Example:
        >>> from fastapi import FastAPI
        >>> from depin import Container
        >>> from depin.ext.fastapi import Inject, install
        >>> class Service:
        ...     value = 'ready'
        >>> app = FastAPI()
        >>> @app.get('/')
        ... async def endpoint(service: Inject[Service]) -> str:
        ...     return service.value
        >>> install(app, Container().bind(Service).freeze())
    """
    user_middleware = _require_application_shape(app)
    if app.middleware_stack is not None:
        raise _setup_error('the application middleware stack has already been built; call install before startup')

    installed = [middleware for middleware in user_middleware if _is_installed_middleware(_middleware_args(middleware))]
    if len(installed) > 1:
        raise _setup_error('the application has multiple depin lazy request middleware entries')
    if installed and _middleware_container(_middleware_args(installed[0])) is not container:
        raise _setup_error('the application was already installed with a different FrozenContainer')

    plans = tuple(
        plan
        for route in app.routes
        if isinstance(route, APIRoute)
        if (plan := _plan_route(route, container)) is not None
    )
    applied: list[_AppliedRoute] = []
    original_middleware = tuple(user_middleware)
    try:
        for plan in plans:
            applied.append(_apply_plan(plan))
        if not installed:
            app.add_middleware(_LazyRequestScope, container, _INSTALLATION_MARKER)
    except Exception as error:
        for route in reversed(applied):
            _restore_route(route)
        user_middleware[:] = original_middleware
        if isinstance(error, FastAPIIntegrationError):
            raise
        raise _setup_error(f'application installation failed: {error}') from error


def compile_route(route: APIRoute, container: FrozenContainer) -> bool:
    """Compile one compatible route; kept private to the FastAPI boundary."""
    plan = _plan_route(route, container)
    if plan is None:
        return False
    _apply_plan(plan)
    return True


def _plan_route(route: APIRoute, container: FrozenContainer) -> _RoutePlan | None:
    _require_route_shape(route)
    dependencies = route.dependant.dependencies
    resolvers: list[tuple[str | None, _InjectResolver[object]]] = []
    for dependency in dependencies:
        call: object = dependency.call
        if _is_resolver(call):
            resolvers.append((dependency.name, call))
    if not resolvers:
        return None
    if any(not isinstance(name, str) for name, _ in resolvers):
        raise _setup_error(f'route {route.path!r} has a direct Inject dependency with no parameter name')
    names = tuple(name for name, _ in resolvers)
    entries = tuple((name, resolver.key) for name, resolver in resolvers if isinstance(name, str))
    program = _EndpointProgram(container, entries)
    replacement = [dependency for dependency in dependencies if not _is_resolver(dependency.call)]
    endpoint = route.dependant.call
    if endpoint is None:
        raise _setup_error(f'route {route.path!r} has no callable endpoint')
    request_argument = route.dependant.request_param_name
    passes_request = request_argument is not None
    return _RoutePlan(route, program, replacement, endpoint, request_argument or _REQUEST_ARGUMENT, passes_request)


def _apply_plan(plan: _RoutePlan) -> _AppliedRoute:
    route = plan.route
    original = plan.endpoint
    applied = _AppliedRoute(
        route,
        route.dependant.call,
        route.dependant.dependencies,
        route.dependant.request_param_name,
        route.app,
    )

    async def endpoint(**arguments: object) -> object:
        request = arguments[plan.request_argument] if plan.passes_request else arguments.pop(plan.request_argument)
        if not isinstance(request, Request):
            raise _setup_error(f'route {route.path!r} did not provide a FastAPI Request to its compiled call')
        arguments.update(await plan.program.resolve(request))
        if iscoroutinefunction(original):
            return await original(**arguments)
        return await run_in_threadpool(original, **arguments)

    try:
        route.dependant.dependencies = plan.dependencies
        route.dependant.request_param_name = plan.request_argument
        route.dependant.call = endpoint
        route.app = request_response(route.get_route_handler())
    except Exception as error:
        _restore_route(applied)
        raise _setup_error(f'route {route.path!r} could not rebuild: {error}') from error
    return applied


def _restore_route(applied: _AppliedRoute) -> None:
    applied.route.dependant.dependencies = applied.dependencies
    applied.route.dependant.request_param_name = applied.request_argument
    applied.route.dependant.call = applied.call
    applied.route.app = applied.app


def _require_route_shape(route: APIRoute) -> None:
    for name in ('dependant', 'path', 'path_format', 'get_route_handler', 'app'):
        if not hasattr(route, name):
            raise _setup_error(f'route {route!r} does not provide required attribute {name!r}')
    dependant = route.dependant
    for name in ('call', 'dependencies', 'request_param_name'):
        if not hasattr(dependant, name):
            raise _setup_error(f'route {route.path!r} dependant does not provide required attribute {name!r}')
    if type(dependant.dependencies) is not list:
        raise _setup_error(f'route {route.path!r} dependant dependencies are not a mutable list')
    for dependency in dependant.dependencies:
        for name in ('call', 'name'):
            if not hasattr(dependency, name):
                raise _setup_error(f'route {route.path!r} dependency does not provide required attribute {name!r}')


def _require_application_shape(app: FastAPI) -> list[Middleware]:
    try:
        middleware_stack = app.middleware_stack
        user_middleware = app.user_middleware
        routes = app.routes
        add_middleware = app.add_middleware
    except (AttributeError, TypeError) as error:
        raise _setup_error(f'application does not expose the required FastAPI installation shape: {error}') from error
    if middleware_stack is not None and not callable(middleware_stack):
        raise _setup_error('application middleware stack is not callable')
    if type(user_middleware) is not list:
        raise _setup_error('application user_middleware is not a mutable list')
    if type(routes) is not list:
        raise _setup_error('application routes is not a mutable list')
    if not callable(add_middleware):
        raise _setup_error('application does not expose a callable add_middleware')
    return user_middleware


def _setup_error(reason: str) -> FastAPIIntegrationError:
    return FastAPIIntegrationError(
        f'FastAPI integration setup failed: {reason}. Detected FastAPI {fastapi.__version__}. '
        'Upgrade to a tested FastAPI version or use RequestScope compatibility middleware.'
    )


def _is_resolver(call: object) -> TypeGuard[_InjectResolver[object]]:
    return isinstance(call, _InjectResolver)


def _is_installed_middleware(args: tuple[object, ...]) -> bool:
    return len(args) == 2 and args[1] is _INSTALLATION_MARKER


def _middleware_container(args: tuple[object, ...]) -> object:
    return args[0]


def _middleware_args(middleware: Middleware) -> tuple[object, ...]:
    args: tuple[object, ...] = middleware.args
    return args
