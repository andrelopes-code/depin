from functools import wraps
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec('P')
R = TypeVar('R')


def inject(fn: Callable[P, R]) -> Callable[P, R]:
    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # aqui você injeta dependências
        return fn(*args, **kwargs)

    return wrapper


@inject
def myfun(a: int):
    return a


print(myfun)
