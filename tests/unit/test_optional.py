"""A `T | None` parameter resolves to the bound provider, or to None when unbound."""

from typing import Annotated, Optional

import pytest

from depin import Container, Named, Scope, Tag, Token
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


def test_an_unbound_optional_dependency_resolves_to_none() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Service).freeze()
    assert di[Service].cache is None


def test_a_bound_optional_dependency_resolves_to_the_provider() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Cache).bind(Service).freeze()
    assert di[Service].cache is di[Cache]


def test_the_typing_optional_spelling_behaves_the_same() -> None:
    class Service:
        def __init__(self, cache: Optional[Cache]) -> None:  # noqa: UP045
            self.cache = cache

    assert Container().bind(Service).freeze()[Service].cache is None


def test_an_explicit_default_wins_over_optionality() -> None:
    fallback = Cache()

    class Service:
        def __init__(self, cache: Cache | None = fallback) -> None:
            self.cache = cache

    assert Container().bind(Service).freeze()[Service].cache is fallback


def test_an_optional_token_dependency_resolves_to_none_when_unbound() -> None:
    url = Token[str]('db.url')

    class Service:
        def __init__(self, dsn: Annotated[str | None, Named(url)]) -> None:
            self.dsn = dsn

    assert Container().bind(Service).freeze()[Service].dsn is None


def test_an_optional_tagged_dependency_resolves_to_none_when_that_tag_is_unbound() -> None:
    class Service:
        def __init__(self, cache: Annotated[Cache | None, Tag('primary')]) -> None:
            self.cache = cache

    di = Container().bind(Cache).bind(Service).freeze()
    assert di[Service].cache is None


def test_an_optional_dependency_of_a_scoped_provider_resolves_to_none() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Service, scope=Scope.SCOPED).freeze()
    with di.scope():
        assert di[Service].cache is None


@pytest.mark.asyncio
async def test_an_unbound_optional_resolves_to_none_in_an_async_provider() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    async def make() -> Service:
        return Service(None)

    class Wrapper:
        def __init__(self, service: Service, cache: Cache | None) -> None:
            self.service = service
            self.cache = cache

    di = Container().bind(make, provides=Service).bind(Wrapper).freeze()
    resolved = await di.aresolve(Wrapper)
    assert resolved.cache is None
