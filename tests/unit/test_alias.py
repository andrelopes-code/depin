"""`Container.alias`: a second name for a binding, with no second instance."""

from collections.abc import Generator
from typing import Annotated, Protocol

import pytest

from depin import Container, Named, ProviderShape, Registry, Scope, Token
from depin.errors import MissingProviderError, OutsideScopeError


class Store(Protocol):
    def get(self) -> str: ...


class PostgresStore:
    def get(self) -> str:
        return 'pg'


def test_an_alias_resolves_to_the_same_singleton_instance() -> None:
    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
    assert di.resolve(Store) is di[PostgresStore]


def test_an_alias_does_not_add_a_second_construction() -> None:
    built: list[int] = []

    class Counted:
        def __init__(self) -> None:
            built.append(1)

    di = Container().bind(Counted).alias(Store, to=Counted).freeze()
    _ = di.resolve(Store)
    _ = di[Counted]
    _ = di.resolve(Store)
    assert len(built) == 1


def test_an_alias_reaches_the_same_instance_as_a_nested_dependency() -> None:
    class Service:
        def __init__(self, store: Store) -> None:
            self.store = store

    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).bind(Service).freeze()
    assert di[Service].store is di[PostgresStore]


def test_an_alias_to_a_scoped_target_shares_the_scope_instance() -> None:
    di = Container().bind(PostgresStore, scope=Scope.SCOPED).alias(Store, to=PostgresStore).freeze()
    with di.scope():
        assert di.resolve(Store) is di[PostgresStore]


def test_an_alias_to_a_scoped_target_needs_a_scope() -> None:
    di = Container().bind(PostgresStore, scope=Scope.SCOPED).alias(Store, to=PostgresStore).freeze()
    with pytest.raises(OutsideScopeError):
        _ = di.resolve(Store)


def test_an_alias_to_a_transient_target_builds_each_time() -> None:
    di = Container().bind(PostgresStore, scope=Scope.TRANSIENT).alias(Store, to=PostgresStore).freeze()
    assert di.resolve(Store) is not di.resolve(Store)


def test_an_alias_selects_a_tagged_target() -> None:
    def primary() -> PostgresStore:
        return PostgresStore()

    def backup() -> PostgresStore:
        return PostgresStore()

    di = (
        Container()
        .bind(primary, provides=PostgresStore, tag='primary')
        .bind(backup, provides=PostgresStore, tag='backup')
        .alias(Store, to=PostgresStore, to_tag='backup')
        .freeze()
    )
    assert di.resolve(Store) is di.resolve(PostgresStore, tag='backup')
    assert di.resolve(Store) is not di.resolve(PostgresStore, tag='primary')


def test_an_alias_can_carry_its_own_tag() -> None:
    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore, tag='main').freeze()
    assert di.resolve(Store, tag='main') is di[PostgresStore]
    with pytest.raises(MissingProviderError):
        _ = di.resolve(Store)


def test_an_alias_may_target_another_alias() -> None:
    class Middle(Protocol):
        def get(self) -> str: ...

    di = Container().bind(PostgresStore).alias(Middle, to=PostgresStore).alias(Store, to=Middle).freeze()
    assert di.resolve(Store) is di[PostgresStore]


def test_an_alias_binds_a_token_key() -> None:
    store = Token[PostgresStore]('store')
    di = Container().bind(PostgresStore).alias(store, to=PostgresStore).freeze()
    assert di[store] is di[PostgresStore]


def test_an_alias_binds_a_string_key() -> None:
    class Consumer:
        def __init__(self, store: Annotated[PostgresStore, Named('store')]) -> None:
            self.store = store

    di = Container().bind(PostgresStore).alias('store', to=PostgresStore).bind(Consumer).freeze()
    assert di.graph().node('store').shape is ProviderShape.ALIAS
    assert di[Consumer].store is di[PostgresStore]


def test_an_alias_leaves_teardown_with_the_target() -> None:
    events: list[str] = []

    class Pool: ...

    def pool() -> Generator[Pool]:
        events.append('open')
        yield Pool()
        events.append('close')

    di = Container().bind(pool).alias(Store, to=Pool).freeze()
    _ = di.resolve(Store)
    _ = di[Pool]
    di.close()
    assert events == ['open', 'close']


def test_an_alias_reads_a_scope_value_target() -> None:
    class Principal:
        def __init__(self, name: str) -> None:
            self.name = name

    class Actor(Protocol):
        name: str

    di = Container().scope_value(Principal).alias(Actor, to=Principal).freeze()
    with di.scope() as frame:
        frame.provide(Principal, Principal('ana'))
        assert di.resolve(Actor).name == 'ana'


def test_an_alias_is_a_transient_node_in_the_graph() -> None:
    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
    node = di.graph().node(Store)
    assert node.shape is ProviderShape.ALIAS
    assert node.scope is Scope.TRANSIENT
    assert [edge.parameter for edge in node.dependencies] == ['target']


def test_a_registry_carries_aliases_into_a_container() -> None:
    registry = Registry('stores').bind(PostgresStore).alias(Store, to=PostgresStore)
    di = Container(registry).freeze()
    assert di.resolve(Store) is di[PostgresStore]
