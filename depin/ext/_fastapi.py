"""FastAPI endpoint compilation behind the public integration surface."""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Annotated, Final, Protocol, TypeGuard, override, runtime_checkable

import fastapi
import fastapi.dependencies.models as fastapi_models
from fastapi import FastAPI, Request
from fastapi.dependencies.models import Dependant
from fastapi.dependencies.utils import get_dependant
from fastapi.params import Depends
from fastapi.routing import APIRoute
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from depin import FrozenContainer, Token, optional_hosted_container
from depin._integration import (
    LazyScopeSeed,
    _begin_lazy_host,
    _finish_lazy_host,
    _provide_active_eager_seed,
    _provide_lazy_seed,
)
from depin.errors import ContainerNotBoundError, FastAPIIntegrationError

__all__: list[str] = []

_REQUEST_ARGUMENT_PREFIX = '__depin_request__'
_INSTALLATION_MARKER: Final[object] = object()


@runtime_checkable
class _CoroutineShape(Protocol):
    def __call__(self, call: Callable[..., object]) -> bool: ...


@runtime_checkable
class _AwaitableObject(Protocol):
    def __await__(self) -> Generator[object, None, object]: ...


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


@dataclass(slots=True)
class FastAPIObservation:
    frames: int = 0
    programs: int = 0

    def frame_opened(self, frame: object) -> None:
        del frame
        self.frames += 1

    def program_resolved(self) -> None:
        self.programs += 1


@dataclass(frozen=True, slots=True)
class _ObservedEndpointProgram(_EndpointProgram):
    observation: FastAPIObservation

    @override
    async def resolve(self, request: Request) -> dict[str, object]:
        self.observation.program_resolved()
        return await _EndpointProgram.resolve(self, request)


class Inject:
    """FastAPI parameter annotation that resolves a dependency from depin."""

    def __class_getitem__[T](cls, key: type[T] | Token[T]) -> object:
        return Annotated[object, Depends(dependency=_InjectResolver(key))]


@dataclass(frozen=True, slots=True)
class _RoutePlan:
    route: APIRoute
    dependant: Dependant
    program: _EndpointProgram
    dependencies: list[Dependant]
    endpoint: Callable[..., object]
    request_argument: str
    passes_request: bool
    is_async: bool
    program_argument: str | None


@dataclass(frozen=True, slots=True)
class _AppliedRoute:
    dependant: Dependant
    call: Callable[..., object] | None
    dependencies: list[Dependant]
    request_argument: str | None


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
        state, publication = _begin_lazy_host(self._container)
        try:
            await self._app(scope, receive, send)
        except BaseException as error:
            await _finish_lazy_host(state, publication, error)
            raise
        else:
            await _finish_lazy_host(state, publication, None)


class _ObservedLazyRequestScope(_LazyRequestScope):
    __slots__ = ('_observation',)

    def __init__(
        self, app: ASGIApp, container: FrozenContainer, marker: object, observation: FastAPIObservation
    ) -> None:
        super().__init__(app, container, marker)
        self._observation = observation

    @override
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self._app(scope, receive, send)
            return
        state, publication = _begin_lazy_host(self._container, on_open=self._observation.frame_opened)
        try:
            await self._app(scope, receive, send)
        except BaseException as error:
            await _finish_lazy_host(state, publication, error)
            raise
        else:
            await _finish_lazy_host(state, publication, None)


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
    _install(app, container, None)


def install_for_observation(app: FastAPI, container: FrozenContainer, observation: FastAPIObservation) -> None:
    _install(app, container, observation)


def _install(app: FastAPI, container: FrozenContainer, observation: FastAPIObservation | None) -> None:
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
        if (plan := _plan_route(route, container, observation)) is not None
    )
    applied: list[_AppliedRoute] = []
    original_middleware = tuple(user_middleware)
    try:
        for plan in plans:
            applied.append(_apply_plan(plan))
        if not installed:
            if observation is None:
                app.add_middleware(_LazyRequestScope, container, _INSTALLATION_MARKER)
            else:
                app.add_middleware(_ObservedLazyRequestScope, container, _INSTALLATION_MARKER, observation)
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


def _plan_route(
    route: APIRoute, container: FrozenContainer, observation: FastAPIObservation | None = None
) -> _RoutePlan | None:
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
    entries = tuple((name, resolver.key) for name, resolver in resolvers if isinstance(name, str))
    program: _EndpointProgram
    if observation is None:
        program = _EndpointProgram(container, entries)
    else:
        program = _ObservedEndpointProgram(container, entries, observation)
    replacement = [dependency for dependency in dependencies if not _is_resolver(dependency.call)]
    endpoint = route.dependant.call
    if endpoint is None:
        raise _setup_error(f'route {route.path!r} has no callable endpoint')
    request_argument = route.dependant.request_param_name
    passes_request = request_argument is not None
    is_async = _coroutine_shape()(endpoint)
    program_argument: str | None = None
    if not is_async:
        program_argument = _request_argument_name(route.dependant)
        replacement.append(_program_dependant(route, program, program_argument))
    return _RoutePlan(
        route,
        route.dependant,
        program,
        replacement,
        endpoint,
        request_argument or _request_argument_name(route.dependant),
        passes_request,
        is_async,
        program_argument,
    )


def _apply_plan(plan: _RoutePlan) -> _AppliedRoute:
    route = plan.route
    original = plan.endpoint
    endpoint: Callable[..., object]
    applied = _AppliedRoute(
        plan.dependant,
        plan.dependant.call,
        plan.dependant.dependencies,
        plan.dependant.request_param_name,
    )

    if plan.is_async:

        async def async_endpoint(**arguments: object) -> object:
            request = _compiled_request(route, plan, arguments)
            arguments.update(await plan.program.resolve(request))
            return await _await_endpoint(route, original, arguments)

        endpoint = async_endpoint

    else:

        if plan.program_argument is None:
            raise _setup_error(f'route {route.path!r} has no compiled program argument')

        program_argument = plan.program_argument

        def sync_endpoint(**arguments: object) -> object:
            values = arguments.pop(program_argument)
            if not _is_program_values(values):
                raise _setup_error(f'route {route.path!r} did not provide compiled dependency values')
            arguments.update(values)
            return original(**arguments)

        endpoint = sync_endpoint

    try:
        plan.dependant.dependencies = plan.dependencies
        if plan.is_async:
            plan.dependant.request_param_name = plan.request_argument
        plan.dependant.call = endpoint
    except Exception as error:
        _restore_route(applied)
        raise _setup_error(f'route {route.path!r} could not apply its compiled call: {error}') from error
    return applied


def _restore_route(applied: _AppliedRoute) -> None:
    applied.dependant.dependencies = applied.dependencies
    applied.dependant.request_param_name = applied.request_argument
    applied.dependant.call = applied.call


def _require_route_shape(route: APIRoute) -> None:
    for name in ('dependant', 'path', 'path_format', 'app'):
        if not hasattr(route, name):
            raise _setup_error(f'route {route!r} does not provide required attribute {name!r}')
    _require_dependant_shape(route, route.dependant)


def _require_dependant_shape(route: APIRoute, dependant: Dependant) -> None:
    if type(dependant) is not Dependant:
        raise _setup_error(f"route {route.path!r} root dependant is not FastAPI's mutable Dependant type")
    for name in (
        'call',
        'dependencies',
        'name',
        'request_param_name',
        'websocket_param_name',
        'http_connection_param_name',
        'response_param_name',
        'background_tasks_param_name',
        'security_scopes_param_name',
        'path_params',
        'query_params',
        'header_params',
        'cookie_params',
        'body_params',
    ):
        if not hasattr(dependant, name):
            raise _setup_error(f'route {route.path!r} dependant does not provide required attribute {name!r}')
    if type(dependant.dependencies) is not list:
        raise _setup_error(f'route {route.path!r} dependant dependencies are not a mutable list')
    for dependency in dependant.dependencies:
        _require_dependant_shape(route, dependency)


def _compiled_request(route: APIRoute, plan: _RoutePlan, arguments: dict[str, object]) -> Request:
    request = arguments[plan.request_argument] if plan.passes_request else arguments.pop(plan.request_argument)
    if not _is_fastapi_request(request):
        raise _setup_error(f'route {route.path!r} did not provide a FastAPI Request to its compiled call')
    return request


async def _await_endpoint(route: APIRoute, endpoint: Callable[..., object], arguments: dict[str, object]) -> object:
    result = endpoint(**arguments)
    if not isinstance(result, _AwaitableObject):
        raise _setup_error(f'route {route.path!r} has an asynchronous FastAPI call that returned a non-awaitable')
    return await result


def _program_dependant(route: APIRoute, program: _EndpointProgram, name: str) -> Dependant:
    async def resolve_program(request: Request) -> dict[str, object]:
        return await program.resolve(request)

    try:
        dependency = get_dependant(path=route.path_format, call=resolve_program, name=name)
    except Exception as error:
        raise _setup_error(f'route {route.path!r} could not build its compiled program dependency: {error}') from error
    _require_dependant_shape(route, dependency)
    return dependency


def _coroutine_shape() -> _CoroutineShape:
    candidate = vars(fastapi_models).get('_is_coroutine_callable')
    if not isinstance(candidate, _CoroutineShape):
        raise _setup_error('FastAPI does not expose a callable coroutine-shape detector')
    return candidate


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


def _is_fastapi_request(value: object) -> TypeGuard[Request]:
    return isinstance(value, Request)


def _is_program_values(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _request_argument_name(dependant: Dependant) -> str:
    reserved = _dependency_value_names(dependant)
    candidate = _REQUEST_ARGUMENT_PREFIX
    while candidate in reserved:
        candidate = f'{candidate}_'
    return candidate


def _dependency_value_names(dependant: Dependant) -> set[str]:
    names = {
        name
        for name in (
            dependant.name,
            dependant.request_param_name,
            dependant.websocket_param_name,
            dependant.http_connection_param_name,
            dependant.response_param_name,
            dependant.background_tasks_param_name,
            dependant.security_scopes_param_name,
        )
        if name is not None
    }
    for fields in (
        dependant.path_params,
        dependant.query_params,
        dependant.header_params,
        dependant.cookie_params,
        dependant.body_params,
    ):
        names.update(field.name for field in fields)
    for dependency in dependant.dependencies:
        names.update(_dependency_value_names(dependency))
    return names


def _is_installed_middleware(args: tuple[object, ...]) -> bool:
    return len(args) == 2 and args[1] is _INSTALLATION_MARKER


def _middleware_container(args: tuple[object, ...]) -> object:
    return args[0]


def _middleware_args(middleware: Middleware) -> tuple[object, ...]:
    args: tuple[object, ...] = middleware.args
    return args
