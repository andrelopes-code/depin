"""A `T | None` parameter resolves to the bound provider, or to None when unbound."""

import pytest

from depin import Container
from depin.errors import InvalidProviderError


class Cache:
    def get(self) -> str:
        return 'cached'


def test_an_unbound_optional_dependency_freezes() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Service).freeze()
    assert di.graph().node(Service).dependencies[0].key is Cache


def test_a_union_of_two_providers_is_still_rejected() -> None:
    class Logger: ...

    class Service:
        def __init__(self, dep: Cache | Logger) -> None:
            del dep

    with pytest.raises(InvalidProviderError, match='names no single key'):
        _ = Container().bind(Service).freeze()


def test_a_union_of_two_providers_and_none_is_still_rejected() -> None:
    class Logger: ...

    class Service:
        def __init__(self, dep: Cache | Logger | None) -> None:
            del dep

    with pytest.raises(InvalidProviderError, match='names no single key'):
        _ = Container().bind(Service).freeze()
