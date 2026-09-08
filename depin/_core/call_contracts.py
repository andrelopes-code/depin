"""Safe call contracts shared by private executable representations."""

import inspect
from collections.abc import Callable
from types import FunctionType

from depin._core.spec import ProviderShape, ProviderSpec
from depin._core.typeguards import as_factory


def sync_positional_factory(spec: ProviderSpec) -> Callable[..., object] | None:
    if spec.shape is not ProviderShape.FUNCTION or spec.needs_async:
        return None
    if any(param.has_default or param.optional for param in spec.params):
        return None
    if any(not param.call_positionally for param in spec.params):
        return None

    factory = as_factory(spec.source, spec.key)
    if not isinstance(factory, FunctionType):
        return factory if not spec.params else None

    code = factory.__code__
    expected_names = tuple(param.name for param in spec.params)
    actual_names = code.co_varnames[: code.co_argcount]
    exact = (
        not code.co_posonlyargcount
        and not code.co_kwonlyargcount
        and not code.co_flags & inspect.CO_VARARGS
        and code.co_argcount == len(expected_names)
        and actual_names == expected_names
    )
    return factory if exact else None
