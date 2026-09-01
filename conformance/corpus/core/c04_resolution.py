"""Resolution: `resolve`, `aresolve`, `__getitem__`, and what survives a scope.

Every promise here is exact inference over a nominal class, a `Protocol`, a
builtin, or a parameterised generic of a consumer type, so `assert_type` is the
honest form throughout. The one construct that is not — the context manager
`scope()` returns — is asserted on the value the `with` statement binds, which
is a nominal `ScopeFrame`.

The generic cases are the point of the file: a key parameterised at `User` must
resolve at `User` and not at the bare origin, because the erasure this suite
exists to detect looks exactly like a lost type argument.
"""

from typing import Protocol, assert_type

from depin import Container, FrozenContainer, Scope, ScopeFrame, Token


class Config:
    def __init__(self) -> None:
        self.dsn = 'sqlite://'


class Repository:
    def __init__(self, config: Config) -> None:
        self.config = config


class Service:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository


class Session:
    def __init__(self) -> None:
        self.open = True


class User: ...


class Order: ...


class Repo[T]:
    def __init__(self) -> None:
        self.items: list[T] = []


class Reader[T](Protocol):
    def read(self) -> str: ...


class UserReader:
    def read(self) -> str:
        return 'user'


port = Token[int]('port')


def build() -> FrozenContainer:
    return Container().bind(Config).bind(Repository).bind(Service).value(port, 8080).freeze()


def resolve_returns_the_requested_type() -> None:
    di = build()
    assert_type(di.resolve(Service), Service)
    assert_type(di.resolve(Repository), Repository)
    assert_type(di.resolve(port), int)


def the_subscript_form_agrees_with_resolve() -> None:
    di = build()
    assert_type(di[Service], Service)
    assert_type(di[port], int)


def resolution_reaches_the_members_of_what_it_returns() -> None:
    di = build()
    assert_type(di.resolve(Service).repository.config.dsn, str)
    assert_type(di[Service].repository.config.dsn, str)


def a_tag_does_not_change_the_resolved_type() -> None:
    di = Container().bind(Config, tag='primary').freeze()
    assert_type(di.resolve(Config, tag='primary'), Config)


async def aresolve_returns_the_requested_type() -> None:
    di = build()
    assert_type(await di.aresolve(Service), Service)
    assert_type(await di.aresolve(port), int)


def a_scoped_provider_resolves_inside_a_scope() -> None:
    di = Container().bind(Session, scope=Scope.SCOPED).freeze()
    with di.scope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(di.resolve(Session), Session)
        assert_type(di[Session], Session)


async def a_scoped_provider_resolves_inside_an_async_scope() -> None:
    di = Container().bind(Session, scope=Scope.SCOPED).freeze()
    async with di.ascope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(await di.aresolve(Session), Session)


def a_transient_provider_resolves_at_its_own_type() -> None:
    di = Container().bind(Session, scope=Scope.TRANSIENT).freeze()
    assert_type(di.resolve(Session), Session)


def a_generic_key_keeps_its_type_argument() -> None:
    def make_users() -> Repo[User]:
        return Repo()

    def make_orders() -> Repo[Order]:
        return Repo()

    di = Container().bind(make_users).bind(make_orders).freeze()
    assert_type(di.resolve(Repo[User]), Repo[User])
    assert_type(di.resolve(Repo[Order]), Repo[Order])
    assert_type(di[Repo[User]], Repo[User])


def a_generic_key_reaches_the_members_its_argument_gives_it() -> None:
    def make_users() -> Repo[User]:
        return Repo()

    di = Container().bind(make_users).freeze()
    assert_type(di.resolve(Repo[User]).items, list[User])


def a_generic_protocol_key_keeps_its_type_argument() -> None:
    di = Container().bind(UserReader, provides=Reader[User]).freeze()
    assert_type(di.resolve(Reader[User]), Reader[User])
    assert_type(di.resolve(Reader[User]).read(), str)
