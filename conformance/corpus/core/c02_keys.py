"""Every spelling of a provider key, and every position that accepts one.

A key is a class, a `Protocol`, a `Token`, a string, a parameterised generic
alias, or an `Underlying`. `resolve` narrows only the first three shapes back to
a value type, so those carry `assert_type`; the rest are asserted where they are
accepted — in `ProviderKey` position, or through the binding they name.

`Named` and `Tag` are `Annotated` metadata rather than keys. They are exercised
through the parameter they annotate, because that is the only place a consumer
writes them.
"""

from typing import Annotated, Protocol, assert_type

from depin import (
    Container,
    FrozenContainer,
    Named,
    ProviderKey,
    ScopeSeed,
    ScopeSeeder,
    Tag,
    Token,
    Underlying,
    render_key,
)


class Config:
    def __init__(self, dsn: str = 'sqlite://') -> None:
        self.dsn = dsn


class Store(Protocol):
    def get(self) -> str: ...


class MemStore:
    def get(self) -> str:
        return 'memory'


class Loud:
    def __init__(self, inner: Store) -> None:
        self.inner = inner

    def get(self) -> str:
        return self.inner.get().upper()


class User: ...


class Repo[T]:
    def __init__(self) -> None:
        self.items: list[T] = []


port = Token[int]('port')
dsn = Token[str]('db.dsn')


def a_class_key_resolves_to_the_class() -> None:
    di = Container().bind(Config).freeze()
    assert_type(di.resolve(Config), Config)
    assert_type(di[Config], Config)


def a_protocol_key_resolves_to_the_protocol() -> None:
    di = Container().bind(MemStore, provides=Store).freeze()
    assert_type(di.resolve(Store), Store)
    assert_type(di[Store], Store)


def a_token_resolves_at_its_parameter() -> None:
    di = Container().value(port, 8080).value(dsn, 'sqlite://').freeze()
    assert_type(di.resolve(port), int)
    assert_type(di.resolve(dsn), str)


def a_class_a_protocol_and_a_string_are_provider_keys() -> None:
    _class_key: ProviderKey = Config
    _protocol_key: ProviderKey = Store
    _string_key: ProviderKey = 'http.port'


def a_provider_key_renders_with_an_optional_tag() -> None:
    assert_type(render_key(port), str)
    assert_type(render_key(port, tag='primary'), str)


def a_scope_seed_contract_is_structural() -> None:
    def seed(_context: object) -> ScopeSeed:
        return ScopeSeed(port, 8080)

    _seeder: ScopeSeeder[object] = seed


def a_parameterised_generic_alias_is_a_key() -> None:
    def make_repo() -> Repo[User]:
        return Repo()

    di = Container().bind(make_repo).freeze()
    assert_type(di.resolve(Repo[User]), Repo[User])
    assert_type(di[Repo[User]], Repo[User])


def a_parameterised_generic_alias_is_a_provider_key() -> None:
    _generic_key: ProviderKey = Repo[User]
    _collection_key: ProviderKey = list[Store]


def an_underlying_names_what_a_decorator_wraps() -> None:
    di = Container().bind(MemStore, provides=Store).decorate(Store, Loud).freeze()
    _key: ProviderKey = Underlying(Store, 0)
    assert_type(di.explain(Underlying(Store, 0)), str)
    assert_type(Underlying(Store, 0).applied, int)


def a_named_marker_selects_a_token_key() -> None:
    class Pool:
        def __init__(self, url: Annotated[str, Named(dsn)]) -> None:
            self.url = url

    di = Container().value(dsn, 'sqlite://').bind(Pool).freeze()
    assert_type(di.resolve(Pool).url, str)


def a_named_marker_selects_a_string_key() -> None:
    def make_port() -> int:
        return 8080

    class Listener:
        def __init__(self, number: Annotated[int, Named('http.port')]) -> None:
            self.number = number

    di = Container().bind(make_port, provides='http.port').bind(Listener).freeze()
    assert_type(di.resolve(Listener).number, int)


def a_tag_marker_selects_one_of_several_bindings_of_a_key() -> None:
    class Report:
        def __init__(self, store: Annotated[Store, Tag('primary')]) -> None:
            self.store = store

    di = Container().bind(MemStore, provides=Store, tag='primary').bind(Report).freeze()
    assert_type(di.resolve(Report).store, Store)
    assert_type(di.resolve(Store, tag='primary'), Store)


def a_key_is_accepted_wherever_the_alias_is_declared(di: FrozenContainer) -> None:
    def first(key: ProviderKey) -> ProviderKey:
        return key

    assert_type(first(Config), ProviderKey)
    assert_type(first(port), ProviderKey)
    assert_type(first('http.port'), ProviderKey)
    assert_type(first(Repo[User]), ProviderKey)
    assert_type(first(Underlying(Config, 0)), ProviderKey)
    assert_type(di.explain(first(Config)), str)
