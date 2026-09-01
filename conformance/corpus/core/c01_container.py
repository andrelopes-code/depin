"""Container construction and resolution, written the way a consumer writes it.

Every promise here is exact inference over a nominal class, a builtin, or a
parameterised generic of a depin type, so `assert_type` is the honest form.
Nothing in this file is decorator-returned, awaitable, a context manager, or an
enum member; those categories take a typed-assignment witness instead, and the
witnesses below carry a leading underscore so `ruff`'s F841 does not reject an
unused annotated local.
"""

from typing import assert_type

from depin import Container, FrozenContainer, ProviderKey, Token, TokenKey


class Config:
    def __init__(self) -> None:
        self.dsn = 'sqlite://'


class Repository:
    def __init__(self, config: Config) -> None:
        self.config = config


class Service:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository


port = Token[int]('port')


def build() -> FrozenContainer:
    return Container().bind(Config).bind(Repository).bind(Service).value(port, 8080).freeze()


def freeze_returns_a_frozen_container() -> None:
    assert_type(Container().bind(Config).freeze(), FrozenContainer)


def resolution_keeps_the_requested_type() -> None:
    di = build()
    assert_type(di.resolve(Service), Service)
    assert_type(di.resolve(Repository), Repository)
    assert_type(di[Service], Service)


def resolution_reaches_the_members_of_what_it_returns() -> None:
    di = build()
    assert_type(di.resolve(Service).repository.config.dsn, str)


def a_token_resolves_at_its_own_type() -> None:
    di = build()
    assert_type(di.resolve(port), int)
    assert_type(di[port], int)


def a_token_is_accepted_where_a_key_is_expected() -> None:
    _key: ProviderKey = port
    _base: TokenKey = port


def provides_accepts_a_token() -> None:
    def make_config() -> Config:
        return Config()

    config_key = Token[Config]('config')
    di = Container().bind(make_config, provides=config_key).freeze()
    assert_type(di.resolve(config_key), Config)


def provides_accepts_a_string() -> None:
    def make_config() -> Config:
        return Config()

    di = Container().bind(make_config, provides='config').freeze()
    assert_type(di, FrozenContainer)
