from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Generator

type CallableProvider[T] = (
    Callable[..., T]
    | Callable[..., Awaitable[T]]
    | Callable[..., AsyncGenerator[T, Any]]
    | Callable[..., Generator[T, Any, Any]]
)

type AsyncProviderFn[T] = Callable[..., Awaitable[T]]


type ProviderType[T] = (
    type[T]
    | Callable[..., T]
    | Callable[..., Awaitable[T]]
    | Callable[..., AsyncGenerator[T, Any]]
    | Callable[..., Generator[T, Any, Any]]
)


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
class ProviderInfo:
    implementation: type[Any] | CallableProvider[Any]
    scope: Scope


class ProviderDependency:
    def __init__(self, dependency: CallableProvider[Any]) -> None:
        self.dependency = dependency
