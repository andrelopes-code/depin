import inspect
from typing import Any, Callable


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


async def force_async(v) -> Any:
    if is_coroutine(v):
        return await v

    return v
