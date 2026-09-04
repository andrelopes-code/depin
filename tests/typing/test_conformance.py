"""Static conformance of the public API under both type checkers.

`assert_type` is a no-op at runtime; what this module buys is the diagnostic a
checker emits when an inferred type drifts. `pytest` collects the functions too,
so a change that breaks the import still fails the suite.

Every assertion here is positive. The one negative assertion this module used to
carry — a `check=` whose parameter did not match the binding — is
`conformance/negative/n02_check_parameter.py`, where the expected diagnostic is
data rather than an inline suppression. Written here it needed
``# type: ignore[arg-type]  # pyright: ignore[reportArgumentType]``, and mypy's
``warn_unused_ignores`` — implied by ``strict`` — turns that pair into a gate
failure the moment either checker stops reporting the error it guards, which is
the opposite of what a negative fixture should do.
"""

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from typing import Annotated, Protocol, assert_type

from depin import (
    CONTRACT_VERSION,
    Container,
    ContractVersion,
    DependencyGraph,
    FrozenContainer,
    GraphEdge,
    GraphNode,
    HealthCheck,
    HealthReport,
    Host,
    ProviderKey,
    ProviderShape,
    Scope,
    ScopeFrame,
    Token,
    TokenKey,
    Underlying,
    WarmupReport,
    hosted_container,
    injected,
    optional_hosted_container,
    provides,
)


class Config:
    value: int = 1


class Service:
    def __init__(self, config: Config) -> None:
        self.config = config


port = Token[int]('port')


def test_resolve_returns_the_requested_type() -> None:
    di = Container().bind(Config).bind(Service).value(port, 8080).freeze()
    assert_type(di, FrozenContainer)
    assert_type(di.resolve(Service), Service)
    assert_type(di[Service], Service)
    assert_type(di.resolve(port), int)
    assert_type(di[port], int)


def test_tagged_resolution_keeps_the_requested_type() -> None:
    di = Container().bind(Config, tag='primary').freeze()
    assert_type(di.resolve(Config, tag='primary'), Config)


def test_inject_preserves_the_wrapped_signature() -> None:
    di = Container().bind(Config).freeze()

    @di.inject
    def handler(label: str, config: Config = injected) -> str:
        return f'{label}={config.value}'

    assert_type(handler(label='n'), str)


def test_inject_preserves_an_async_signature() -> None:
    di = Container().bind(Config).freeze()

    @di.inject
    async def handler(label: str, config: Config = injected) -> str:
        return f'{label}={config.value}'

    # A typed witness rather than `assert_type`: both `inject` overloads match
    # an `async def`, four checkers pick the first and ty the second, and the
    # `CoroutineType[Any, Any, str]` that follows preserves every operation
    # `Awaitable[str]` promises. Exact equality would state a promise the
    # library does not make.
    #
    # Nested and never called: the witness is checked statically, and calling
    # the wrapper here would leave an un-awaited coroutine behind.
    def call_site() -> None:
        _pending: Awaitable[str] = handler(label='n')

    _ = call_site


def test_an_injected_parameter_keeps_its_declared_type() -> None:
    di = Container().bind(Config).value(port, 8080).freeze()

    @di.inject
    def handler(config: Config = injected, number: Annotated[int, port] = injected) -> str:
        assert_type(config, Config)
        assert_type(number, int)
        return f'{config.value}:{number}'

    assert_type(handler(), str)


def test_scope_yields_a_frame() -> None:
    di = Container().bind(Config).freeze()
    with di.scope() as frame:
        assert_type(frame, ScopeFrame)


async def test_aresolve_returns_the_requested_type() -> None:
    di = Container().bind(Config).bind(Service).value(port, 8080).freeze()
    assert_type(await di.aresolve(Service), Service)
    assert_type(await di.aresolve(port), int)


async def test_ascope_yields_a_frame() -> None:
    di = Container().bind(Config).freeze()
    async with di.ascope() as frame:
        assert_type(frame, ScopeFrame)


def test_override_yields_the_container() -> None:
    di = Container().bind(Config).freeze()
    with di.override(Config).using(Config()) as overridden:
        assert_type(overridden, FrozenContainer)


def test_the_builder_stays_a_container_through_chaining() -> None:
    di = Container()
    assert_type(di.bind(Config), Container)
    assert_type(di.value(port, 8080), Container)
    assert_type(di.bind(Service, scope=Scope.SCOPED), Container)


def test_the_scope_decorator_preserves_a_class_target() -> None:
    di = Container()

    @di.singleton()
    class Pool:
        def __init__(self) -> None:
            self.size = 1

    assert_type(Pool(), Pool)


def test_the_scope_decorator_preserves_a_factory_target() -> None:
    di = Container()

    @di.singleton()
    def make_service(config: Config) -> Service:
        return Service(config)

    assert_type(make_service(Config()), Service)


def test_a_protocol_key_keeps_its_type_through_subscript() -> None:
    class Store(Protocol):
        def get(self) -> str: ...

    @provides(Store)
    class MemStore:
        def get(self) -> str:
            return 'v'

    di = Container().bind(MemStore).freeze()
    assert_type(di[Store], Store)
    assert_type(di.resolve(Store), Store)


def test_graph_diagnostics_keep_their_types() -> None:
    di = Container().bind(Config).bind(Service).freeze()
    assert_type(di.graph(), DependencyGraph)
    assert_type(di.graph().nodes, tuple[GraphNode, ...])
    assert_type(di.graph().roots, tuple[GraphNode, ...])
    assert_type(di.graph().node(Service), GraphNode)
    assert_type(di.graph().find(Service), GraphNode | None)
    assert_type(di.graph().node(Service).dependencies, tuple[GraphEdge, ...])
    assert_type(di.graph().node(Service).shape, ProviderShape)
    assert_type(di.graph().dot(), str)
    assert_type(di.graph().mermaid(), str)
    assert_type(di.explain(Service), str)
    assert_type(di.explain(Service, tag='primary'), str)


def test_alias_keeps_the_builder_type_and_the_resolved_type() -> None:
    class Store(Protocol):
        def get(self) -> str: ...

    class MemStore:
        def get(self) -> str:
            return 'v'

    builder = Container().bind(MemStore)
    assert_type(builder.alias(Store, to=MemStore), Container)
    di = builder.freeze()
    assert_type(di.resolve(Store), Store)
    assert_type(di[Store], Store)


def test_a_collection_key_keeps_its_element_type() -> None:
    class Handler(Protocol):
        def run(self) -> str: ...

    class Email:
        def run(self) -> str:
            return 'email'

    builder = Container().bind(Email)
    assert_type(builder.collect(Handler, [Email]), Container)
    di = builder.freeze()
    assert_type(di.resolve(list[Handler]), list[Handler])
    assert_type(di[list[Handler]], list[Handler])

    @di.inject
    def handler(handlers: list[Handler] = injected) -> int:
        assert_type(handlers, list[Handler])
        return len(handlers)

    assert_type(handler(), int)


def test_a_generic_key_keeps_its_parameterisation() -> None:
    class User: ...

    class Repo[T]: ...

    class Reader[T](Protocol):
        def read(self) -> str: ...

    def make() -> Repo[User]:
        return Repo()

    class MemReader:
        def read(self) -> str:
            return 'mem'

    di = Container().bind(make).bind(MemReader, provides=Reader[User]).collect(Repo[User], [Repo[User]]).freeze()
    assert_type(di.resolve(Repo[User]), Repo[User])
    assert_type(di[Repo[User]], Repo[User])
    assert_type(di.resolve(Reader[User]), Reader[User])
    assert_type(di.resolve(list[Repo[User]]), list[Repo[User]])


def test_decorate_returns_the_same_builder() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    assert_type(Container().bind(Store).decorate(Store, Loud), Container)


def test_a_protocol_is_a_decoration_key() -> None:
    class Store(Protocol):
        def get(self) -> str: ...

    class Impl:
        def get(self) -> str:
            return 'x'

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    assert_type(Container().bind(Impl, provides=Store).decorate(Store, Loud), Container)


def test_a_condition_takes_both_spellings() -> None:
    class Cache: ...

    assert_type(Container().bind(Cache, when=True), Container)
    assert_type(Container().bind(Cache, when=lambda: True), Container)


def test_an_underlying_key_is_an_explain_argument() -> None:
    class Store: ...

    class Loud:
        def __init__(self, inner: Store) -> None: ...

    di = Container().bind(Store).decorate(Store, Loud).freeze()
    assert_type(di.explain(Underlying(Store, 0)), str)


def test_warmup_returns_a_warmup_report() -> None:
    di = Container().bind(Config).freeze()
    assert_type(di.warmup(), WarmupReport)


def test_checks_returns_a_tuple_of_health_checks() -> None:
    class Database: ...

    def ping(db: Database) -> None: ...

    di = Container().bind(Database, check=ping).freeze()
    assert_type(di.checks(), tuple[HealthCheck, ...])


def test_health_returns_a_health_report() -> None:
    class Database: ...

    def ping(db: Database) -> None: ...

    di = Container().bind(Database, check=ping).freeze()
    assert_type(di.health(), HealthReport)


def test_bind_infers_the_check_parameter_from_the_bound_type() -> None:
    class Database: ...

    def ping(db: Database) -> None: ...

    assert_type(Container().bind(Database, check=ping), Container)


def test_bind_infers_the_check_parameter_for_a_generator_factory() -> None:
    class Pool: ...

    def pool() -> Generator[Pool]:
        yield Pool()

    def ping(p: Pool) -> None: ...

    assert_type(Container().bind(pool, check=ping), Container)


def test_bind_infers_the_check_parameter_for_an_async_generator_factory() -> None:
    class Pool: ...

    async def pool() -> AsyncGenerator[Pool]:
        yield Pool()

    def ping(p: Pool) -> None: ...

    assert_type(Container().bind(pool, check=ping), Container)


def test_bind_infers_the_check_parameter_for_an_async_def_factory() -> None:
    class Pool: ...

    async def make_pool() -> Pool:
        return Pool()

    def ping(p: Pool) -> None: ...

    assert_type(Container().bind(make_pool, check=ping), Container)


def test_bind_infers_the_check_parameter_for_a_contextmanager_factory() -> None:
    class Pool: ...

    @contextlib.contextmanager
    def pool() -> Generator[Pool]:
        yield Pool()

    def ping(p: Pool) -> None: ...

    assert_type(Container().bind(pool, check=ping), Container)


def test_bind_infers_the_check_parameter_for_an_asynccontextmanager_factory() -> None:
    class Pool: ...

    @contextlib.asynccontextmanager
    async def pool() -> AsyncGenerator[Pool]:
        yield Pool()

    def ping(p: Pool) -> None: ...

    assert_type(Container().bind(pool, check=ping), Container)


def test_bind_infers_the_check_parameter_for_a_plain_factory() -> None:
    class Pool: ...

    def make_pool() -> Pool:
        return Pool()

    def ping(p: Pool) -> None: ...

    assert_type(Container().bind(make_pool, check=ping), Container)


def test_the_integration_contract_keeps_its_types() -> None:
    di = Container().bind(Config).freeze()
    host = Host(di)
    assert_type(host.container, FrozenContainer)
    assert_type(CONTRACT_VERSION, ContractVersion)
    assert_type(CONTRACT_VERSION.major, int)
    with host.scope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(hosted_container(), FrozenContainer)
        assert_type(hosted_container().resolve(Config), Config)
    assert_type(optional_hosted_container(), FrozenContainer | None)


async def test_the_async_integration_contract_keeps_its_types() -> None:
    di = Container().bind(Config).freeze()
    async with Host(di).ascope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(await hosted_container().aresolve(Config), Config)


def test_reset_returns_none() -> None:
    di = Container().bind(Config).freeze()
    assert_type(di.reset(), None)


async def test_areset_returns_none() -> None:
    di = Container().bind(Config).freeze()
    assert_type(await di.areset(), None)


def _first_key(key: ProviderKey) -> ProviderKey:
    return key


def test_a_token_is_accepted_where_a_provider_key_is_expected() -> None:
    assert_type(_first_key(port), ProviderKey)
    key: TokenKey = port
    assert_type(_first_key(key), ProviderKey)


def test_a_token_is_an_alias_and_an_explain_argument() -> None:
    other = Token[int]('other')
    di = Container().value(port, 8080).alias(other, to=port).freeze()
    assert_type(di.resolve(other), int)
    assert_type(di.explain(port), str)


def test_provides_accepts_a_token() -> None:
    def make() -> int:
        return 8080

    assert_type(Container().bind(make, provides=port), Container)
    assert_type(Container().singleton(provides=port)(make), Callable[[], int])


def test_provides_accepts_a_name() -> None:
    def make() -> int:
        return 8080

    assert_type(Container().bind(make, provides='http.port'), Container)
