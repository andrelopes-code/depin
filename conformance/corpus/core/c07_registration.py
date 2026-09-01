"""Registration: `provides`, `alias`, `decorate`, `collect`, conditions, registries.

Two public symbols are spelled `provides` and both are here. The decorator
`provides(Store)` marks a class with the abstract key it satisfies; the
`provides=` keyword names the key one binding registers under, and it accepts a
class, a `TokenKey` and a string.

The scope decorators are the file's only assignability promises. A decorator's
return type is a category `assert_type` cannot state honestly — ty infers the
class-literal ``<class 'Pool'>`` for a decorated class, and distinguishes a
function type from the `Callable` protocol for a decorated function, printing
both sides identically — so each takes a typed witness. `ScopeDecorator` itself
is nominal and takes `assert_type`.
"""

from collections.abc import Callable
from typing import Protocol, assert_type

from depin import (
    Bindings,
    Condition,
    Container,
    FrozenContainer,
    Registry,
    Scope,
    ScopeDecorator,
    Token,
    provides,
)


class Config:
    def __init__(self) -> None:
        self.dsn = 'sqlite://'


class Store(Protocol):
    def get(self) -> str: ...


class Handler(Protocol):
    def run(self) -> str: ...


class Email:
    def run(self) -> str:
        return 'email'


class Sms:
    def run(self) -> str:
        return 'sms'


class Cache:
    def __init__(self) -> None:
        self.entries = 0


port = Token[int]('port')


@provides(Store)
class MemStore:
    def get(self) -> str:
        return 'memory'


class Loud:
    def __init__(self, inner: Store) -> None:
        self.inner = inner

    def get(self) -> str:
        return self.inner.get().upper()


def the_provides_decorator_returns_the_decorated_class() -> None:
    assert_type(MemStore().get(), str)
    di = Container().bind(MemStore).freeze()
    assert_type(di.resolve(Store), Store)
    assert_type(di[Store], Store)


def the_provides_keyword_takes_a_class() -> None:
    di = Container().bind(MemStore, provides=MemStore).freeze()
    assert_type(di.resolve(MemStore), MemStore)


def the_provides_keyword_takes_a_protocol() -> None:
    di = Container().bind(MemStore, provides=Store).freeze()
    assert_type(di.resolve(Store), Store)


def the_provides_keyword_takes_a_token() -> None:
    def make_port() -> int:
        return 8080

    di = Container().bind(make_port, provides=port).freeze()
    assert_type(di.resolve(port), int)


def the_provides_keyword_takes_a_string() -> None:
    def make_port() -> int:
        return 8080

    assert_type(Container().bind(make_port, provides='http.port'), Container)


def a_scope_decorator_is_a_nominal_object() -> None:
    di = Container()
    assert_type(di.singleton(), ScopeDecorator)
    assert_type(di.scoped(), ScopeDecorator)
    assert_type(di.transient(), ScopeDecorator)
    assert_type(di.singleton(provides=port, tag='primary', when=True), ScopeDecorator)


def a_scope_decorator_gives_back_the_class_it_decorated() -> None:
    di = Container()

    @di.singleton()
    class Pool:
        def __init__(self) -> None:
            self.size = 1

    _key: type[Pool] = Pool
    assert_type(Pool().size, int)


def a_scope_decorator_gives_back_the_function_it_decorated() -> None:
    di = Container()

    @di.scoped()
    def make_cache() -> Cache:
        return Cache()

    _factory: Callable[[], Cache] = make_cache
    assert_type(make_cache().entries, int)


def a_transient_decorator_keeps_the_wrapped_parameters() -> None:
    di = Container()

    @di.transient()
    def make_store(config: Config) -> MemStore:
        _ = config.dsn
        return MemStore()

    _factory: Callable[[Config], MemStore] = make_store


def alias_gives_one_binding_a_second_key() -> None:
    builder = Container().bind(MemStore)
    assert_type(builder.alias(Store, to=MemStore), Container)
    di = builder.freeze()
    assert_type(di.resolve(Store), Store)


def alias_gives_a_token_a_second_key() -> None:
    other = Token[int]('other.port')
    di = Container().value(port, 8080).alias(other, to=port).freeze()
    assert_type(di.resolve(other), int)


def decorate_wraps_a_binding_under_the_same_key() -> None:
    assert_type(Container().bind(MemStore, provides=Store).decorate(Store, Loud), Container)
    di = Container().bind(MemStore, provides=Store).decorate(Store, Loud).freeze()
    assert_type(di.resolve(Store), Store)


def collect_makes_a_list_key_out_of_its_members() -> None:
    builder = Container().bind(Email).bind(Sms)
    assert_type(builder.collect(Handler, [Email, Sms]), Container)
    di = builder.freeze()
    assert_type(di.resolve(list[Handler]), list[Handler])
    assert_type(di[list[Handler]], list[Handler])


def a_condition_takes_both_of_its_spellings() -> None:
    _literal: Condition = True

    def enabled() -> bool:
        return True

    _predicate: Condition = enabled
    assert_type(Container().bind(Cache, when=True), Container)
    assert_type(Container().bind(Cache, when=enabled), Container)
    assert_type(Container().alias(Store, to=MemStore, when=enabled), Container)


def an_unbound_optional_dependency_stays_optional() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Service).freeze()
    assert_type(di.resolve(Service).cache, Cache | None)


def a_bound_optional_dependency_keeps_the_same_declared_type() -> None:
    class Service:
        def __init__(self, cache: Cache | None) -> None:
            self.cache = cache

    di = Container().bind(Cache).bind(Service).freeze()
    assert_type(di.resolve(Service).cache, Cache | None)


def a_registry_is_a_binding_source() -> None:
    registry = Registry('infra')
    assert_type(registry, Registry)
    assert_type(registry.bind(Config), Registry)
    assert_type(registry.value(port, 8080), Registry)
    _source: Bindings = registry


def two_registries_compose_with_the_or_operator() -> None:
    infra = Registry('infra').bind(Config)
    app = Registry('app').bind(MemStore)
    assert_type(infra | app, Registry)
    _source: Bindings = infra | app


def a_container_is_built_from_registries() -> None:
    infra = Registry('infra').bind(Config)
    app = Registry('app').bind(MemStore)
    assert_type(Container(infra, app), Container)
    assert_type(Container(infra | app), Container)
    assert_type(Container().include(infra, app), Container)


def a_composed_container_resolves_what_its_registries_bound() -> None:
    infra = Registry('infra').bind(Config)
    app = Registry('app').bind(MemStore, provides=Store, scope=Scope.SINGLETON)
    di: FrozenContainer = Container(infra, app).freeze()
    assert_type(di.resolve(Config), Config)
    assert_type(di.resolve(Store), Store)
