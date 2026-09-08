"""Safe call contracts shared by private executable representations."""

import inspect
from collections.abc import Callable
from types import FunctionType

from depin._core.spec import ProviderShape, ProviderSpec
from depin._core.typeguards import as_factory


def sync_positional_factory(spec: ProviderSpec) -> Callable[..., object] | None:
    if spec.shape is not ProviderShape.FUNCTION or spec.needs_async:
        return None
    params = spec.params
    param_count = len(params)
    if param_count == 1:
        only = params[0]
        if only.has_default or only.optional or not only.call_positionally:
            return None
    elif param_count > 1:
        for param in params:
            if param.has_default or param.optional or not param.call_positionally:
                return None

    source = spec.source
    if not isinstance(source, FunctionType):
        factory = as_factory(source, spec.key)
        return factory if not params else None

    code = source.__code__
    if (
        code.co_posonlyargcount
        or code.co_kwonlyargcount
        or code.co_flags & inspect.CO_VARARGS
        or code.co_argcount != param_count
    ):
        return None
    if param_count == 1:
        return source if code.co_varnames[0] == params[0].name else None
    for index, param in enumerate(params):
        if code.co_varnames[index] != param.name:
            return None
    return source
