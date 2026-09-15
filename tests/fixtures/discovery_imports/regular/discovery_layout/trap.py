"""Provider module that records unexpected attribute probing."""

from depin import Catalog, provider

_getattr_calls = 0


class Trapped: ...


trapped_catalog = Catalog(__name__, provider(Trapped))


def getattr_calls() -> int:
    return _getattr_calls


def __getattr__(name: str) -> object:
    global _getattr_calls
    _getattr_calls += 1
    raise AttributeError(name)
