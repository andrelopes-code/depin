import inspect
from functools import lru_cache
from typing import Any, Callable, get_type_hints


class ClassProperty:
    def __init__(self, fget):
        self.fget = fget

    def __get__(self, instance, owner):
        return self.fget(owner)


def is_async_generator_callable(func: Callable[..., Any]) -> bool:
    return inspect.isasyncgenfunction(func)


def is_generator_callable(func: Callable[..., Any]) -> bool:
    return inspect.isgeneratorfunction(func)


def is_async_callable(func: Callable[..., Any]) -> bool:
    return inspect.iscoroutinefunction(func) or inspect.iscoroutine(func)


def is_coroutine(obj: Any) -> bool:
    return inspect.iscoroutine(obj)


@lru_cache(None)
def get_cached_signature(func: Callable[..., Any]) -> inspect.Signature:
    return inspect.signature(func)


@lru_cache(None)
def get_cached_type_hints(func: Callable[..., Any]) -> dict[str, Any]:
    return get_type_hints(func)
