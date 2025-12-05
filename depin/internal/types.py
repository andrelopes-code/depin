from collections.abc import Callable
from typing import Awaitable

type ProviderFn[T] = Callable[..., T]
type AsyncProviderFn[T] = Callable[..., Awaitable[T]]


class ProviderDependency[T]:
    def __init__(self, provider_fn: ProviderFn[T]) -> None:
        self.provider_fn = provider_fn
