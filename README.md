# depin — Small Dependency Injection container for Python

> Simple, lightweight dependency injection for synchronous and asynchronous code, with request-scoped context useful for web frameworks such as FastAPI.

## Features

- Register classes and factories as `SINGLETON`, `TRANSIENT` or `REQUEST` scope.
- Support for synchronous and asynchronous providers (functions / async functions).
- `Inject(...)` helper for explicit provider parameters.
- `Container.inject` decorator to auto-inject parameters into callables.
- FastAPI integration: `Container.Depends(...)` and `RequestScopeMiddleware`.

## Installation

Or install from a distribution package (if published):

```bash
# PIP
python -m pip install pydepin
# UV
uv add pydepin
```

Requirements: Python 3.9+.

## Quickstart

Create a `Container`, register providers and resolve dependencies.

```python
from depin import Container, Inject, Scope

DI = Container()

class Config:
    def __init__(self):
        self.value = 100


def config_provider():
    return Config()


def service(config: Config):
    return config.value * 2

# register providers
DI.bind(source=config_provider, scope=Scope.SINGLETON)
DI.bind(source=service, scope=Scope.SINGLETON)

result = DI.get(service)  # -> 200
```

## Concepts

- `Container` — main entry point. Use it to register providers and resolve values.
- `Scope` — enumeration with `SINGLETON`, `TRANSIENT` and `REQUEST`.
  - `SINGLETON`: one instance shared during container lifetime.
  - `TRANSIENT`: a new instance produced on each resolution.
  - `REQUEST`: request-scoped lifecycle (requires `RequestScopeService` context).
- `Inject(provider)` — used as a default value for function/constructor parameters
  to explicitly point to a provider.
- `Container.inject` — decorator that wraps a function and automatically fills
  injectable parameters (by type-hint or `Inject(...)`). Works for sync and async.

## Registration styles

You can register providers in a few different ways:

- Using `bind(...)` with a class or function literal:

```python
DI.bind(source=MyClass, scope=DI.Scope.SINGLETON)
DI.bind(source=my_factory_fn, scope=DI.Scope.SINGLETON)
```

- Using the `@register(...)` decorator (convenient for modules):

```python
@DI.register(DI.Scope.TRANSIENT)
def random_id():
    import uuid
    return uuid.uuid4().hex


@DI.register(DI.Scope.REQUEST)
class UserService:
    def __init__(self, repo: UserRepo, request: Request):
        ...
```

## Explicit `Inject` parameter

Use `Inject(provider)` when you want to override the type hint and point to
another provider directly:

```python
from depin import Inject

def get_string():
    return 'from_provider'

class Service:
    def __init__(self, value: int = Inject(get_string)):
        self.value = value

DI.bind(source=get_string, scope=DI.Scope.SINGLETON)
DI.bind(source=Service, scope=DI.Scope.SINGLETON)

s = DI.get(Service)
assert s.value == 'from_provider'
```

## Async providers and request-scoped resources

Request scope supports generator / async-generator providers which are entered
when first resolved during a request and cleaned up when the request scope ends.

Example (from `example/dependencies/database.py`):

```python
from contextlib import asynccontextmanager
from depin import Inject, Scope

@DI.register(Scope.SINGLETON)
async def db_engine():
    return Engine()


@DI.register(Scope.REQUEST)
async def db_session(engine: Engine = Inject(db_engine), session_id: str = Inject(random_id)):
    async with db_session_ctx(engine, session_id) as session:
        yield session

@asynccontextmanager
async def db_session_ctx(engine: Engine, session_id: str):
    session = Session(engine, session_id)
    try:
        yield session
    finally:
        # cleanup
        pass
```

The container will call `__aenter__` / `__enter__` for request-scoped
generator providers and store the created resource in the current request store.

## FastAPI integration

To use request scope with FastAPI, add the `RequestScopeMiddleware` from
`depin.extensions.fastapi` before defining routes and use `Container.Depends`
to get FastAPI-compatible dependencies that call into the container.

```python
from fastapi import FastAPI
from depin import Container
from depin.extensions.fastapi import RequestScopeMiddleware

DI = Container()

app = FastAPI()
app.add_middleware(RequestScopeMiddleware)

@DI.register(DI.Scope.REQUEST)
class UserService:
    def __init__(self, request: Request):
        self.request = request

@app.get('/')
async def index(s: UserService = DI.Depends(UserService)):
    # `s` is resolved from the container using the request-scoped store
    return {'message': 'ok'}
```

Alternatively you can call `RequestScopeService` directly from providers to
access the currently active `Request` instance.

## Container helpers

- `Container.get(t)` — synchronous resolution (raises when provider is async).
- `Container.get_async(t)` — asynchronous resolution that awaits async providers.
- `Container.inject(func)` — returns a wrapped callable that auto-injects
  dependencies by type hints and `Inject(...)` defaults.
- `Container.Depends(type_or_provider)` — returns a FastAPI `Depends` wrapper.

## Examples

- See the `example` folder for a complete FastAPI example integrating request
  scope, async database sessions, and services.
- See `tests/` for unit tests showing usage patterns (provider functions,
  `Inject` param, decorators and scopes).

## Running the example

From the repository root run:

```bash
python example/app.py
```

Open `http://localhost:8001` to exercise the sample endpoints.
