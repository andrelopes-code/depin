from collections.abc import Callable
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


class ProviderDependency:
    def __init__(self, dependency: CallableProvider[Any]) -> None:
        self.dependency = dependency
