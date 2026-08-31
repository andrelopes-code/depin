"""A `check=` declaration reaches the plan intact, through every rebuild of a spec."""

import pytest

from depin import Container, Token, Underlying
from depin._core.graph import build_plan
from depin._core.spec import ProviderKey, ProviderSpec
from depin.errors import InvalidProviderError


def _spec(container: Container, key: ProviderKey, tag: str | None = None) -> ProviderSpec:
    plan = build_plan(container.records())
    return plan.by_key[(key, tag)]


def test_a_bind_check_reaches_the_plan() -> None:
    class Database: ...

    def ping(db: Database) -> None: ...

    spec = _spec(Container().bind(Database, check=ping), Database)
    assert spec.check is ping


def test_a_value_check_reaches_the_plan() -> None:
    port = Token[int]('port')

    def positive(value: int) -> bool:
        return value > 0

    spec = _spec(Container().value(port, 8080, check=positive), port)
    assert spec.check is positive


def test_a_check_survives_the_async_flag_pass() -> None:
    class Database: ...

    class Service:
        def __init__(self, db: Database) -> None: ...

    async def build() -> Service:
        return Service(Database())

    def ping(db: Database) -> None: ...

    container = Container().bind(Database, check=ping).bind(build)
    spec = _spec(container, Database)
    assert spec.check is ping


def test_a_check_follows_a_decorated_binding_to_its_undecorated_node() -> None:
    class Database: ...

    class Loud(Database):
        def __init__(self, inner: Database) -> None: ...

    def ping(db: Database) -> None: ...

    container = Container().bind(Database, check=ping).decorate(Database, Loud)
    assert _spec(container, Underlying(Database, 0)).check is ping
    assert _spec(container, Database).check is None


def test_a_binding_without_a_check_carries_none() -> None:
    class Database: ...

    assert _spec(Container().bind(Database), Database).check is None


def test_a_non_callable_check_is_rejected_at_freeze() -> None:
    class Database: ...

    container = Container().bind(Database, check=3)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidProviderError, match='as a health check'):
        _ = container.freeze()
