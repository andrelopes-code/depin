from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Generator

type Resolvable[T] = (
    Callable[..., T]
    | Callable[..., Awaitable[T]]
    | Callable[..., AsyncGenerator[T, Any]]
    | Callable[..., Generator[T, Any, Any]]
)

type Provider[T] = Callable[[], T] | Callable[[], Awaitable[T]]
type ProviderSource[T = Any] = type[T] | Resolvable[T]


class Request[T]: ...


class Singleton[T]: ...


class Transient[T]: ...


class Scope(Enum):
    SINGLETON = 'singleton'
    TRANSIENT = 'transient'
    REQUEST = 'request'


@dataclass
class Token:
    name: str


@dataclass
class ProviderInfo[T = Any]:
    provider: Provider[T]
    source: ProviderSource[T]
    needs_async: bool
    scope: Scope


class ProviderDependency:
    def __init__(self, provider_source: ProviderSource[Any]) -> None:
        self.provider_source = provider_source
