import dataclasses
import typing
from collections.abc import Callable

import pytest

from depin._core.markers import Named, Tag, Token, TokenKey, get_provides, injected, is_inject_marker, provides
from depin.errors import DepinError, InvalidProviderError


def test_token_is_typed_key() -> None:
    db_url = Token[str]('db.url')
    assert db_url.name == 'db.url'


def test_tokens_with_same_name_are_equal() -> None:
    a = Token[str]('db.url')
    b = Token[str]('db.url')
    assert a is not b
    assert a == b
    assert hash(a) == hash(b)


def test_tokens_with_different_names_are_distinct() -> None:
    assert Token[str]('a') != Token[str]('b')
    assert hash(Token[str]('a')) != hash(Token[str]('b'))


def test_token_phantom_type_does_not_affect_equality() -> None:
    """Token's generic parameter is phantom — runtime equality is name-only."""
    assert Token[str]('x') == Token[int]('x')


def test_token_repr_includes_name() -> None:
    t = Token[int]('max.conn')
    assert 'max.conn' in repr(t)


def test_named_holds_key() -> None:
    tok = Token[str]('x')
    n = Named(tok)
    assert n.key == tok


def test_named_accepts_string_key() -> None:
    n = Named('legacy')
    assert n.key == 'legacy'


def test_tag_holds_name() -> None:
    t = Tag('primary')
    assert t.name == 'primary'


def test_provides_attaches_metadata_to_class() -> None:
    class Logger: ...

    @provides(Logger)
    class StdLogger(Logger): ...

    assert get_provides(StdLogger) is Logger


def test_provides_returns_decorated_class_unchanged() -> None:
    class Cache: ...

    @provides(Cache)
    class RedisCache(Cache):
        x = 1

    assert RedisCache.x == 1
    assert RedisCache.__name__ == 'RedisCache'


def test_get_provides_returns_none_when_absent() -> None:
    class Plain: ...

    assert get_provides(Plain) is None


def test_injected_returns_marker_with_class_key() -> None:
    class Svc: ...

    marker = injected(Svc)
    assert is_inject_marker(marker)
    assert marker.key is Svc
    assert marker.tag is None


def test_injected_carries_tag() -> None:
    class Svc: ...

    result = injected(Svc, tag='primary')
    assert is_inject_marker(result)
    assert result.tag == 'primary'


def test_injected_accepts_token_key() -> None:
    tok = Token[str]('db.url')
    result = injected(tok)
    assert is_inject_marker(result)
    assert result.key == tok


def test_is_inject_marker_false_for_other_values() -> None:
    assert not is_inject_marker(42)
    assert not is_inject_marker(object())


def test_inject_marker_leaked_value_raises_clear_error() -> None:
    marker = injected(object)
    assert is_inject_marker(marker)
    with pytest.raises(DepinError, match='injection marker'):
        _ = marker.connection


def test_inject_marker_dunder_access_falls_through() -> None:
    marker = injected(object)
    assert is_inject_marker(marker)
    with pytest.raises(AttributeError, match='__wrapped__'):
        _ = marker.__wrapped__


def test_injected_token_with_tag() -> None:
    tok = Token[int]('n')
    marker = injected(tok, tag='primary')
    assert is_inject_marker(marker)
    assert marker.key == tok
    assert marker.tag == 'primary'


def test_inject_marker_is_frozen() -> None:
    marker = injected(object)
    # Indirect attribute name: a direct `marker.tag = ...` is a static error on a
    # frozen dataclass, and setattr with a literal name trips ruff B010.
    field = 'tag'
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(marker, field, 'mutated')


def test_provides_returns_the_decorated_class_unchanged() -> None:
    class Store: ...

    class MemStore: ...

    assert provides(Store)(MemStore) is MemStore
    assert get_provides(MemStore) is Store


def test_provides_accepts_a_parameterised_generic() -> None:
    class User: ...

    class Repo[T]: ...

    @provides(Repo[User])
    class SqlRepo: ...

    assert get_provides(SqlRepo) == Repo[User]


@pytest.mark.parametrize('target', [42, 'Store', Token[str]('db.url')])
def test_provides_rejects_a_non_class_target(target: object) -> None:
    with pytest.raises(InvalidProviderError, match='expected a class'):
        _ = provides(target)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    ('target', 'fragment'),
    [
        (typing.List[int], 'deprecated typing alias'),  # noqa: UP006
        (Callable[[int], str], 'is not itself a provider key'),
        (int | None, 'and this is not one'),
        (int | str, 'names no single key'),
    ],
)
def test_provides_explains_a_key_shaped_target_in_its_own_terms(target: object, fragment: str) -> None:
    """A value that looks like a key but is not one gets the message freeze() would give, not 'expected a class'."""
    with pytest.raises(InvalidProviderError, match=fragment):
        _ = provides(target)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def test_a_token_is_a_token_key() -> None:
    assert isinstance(Token[str]('db.url'), TokenKey)


def test_tokens_with_the_same_name_are_equal_and_hash_equally_as_keys() -> None:
    a: TokenKey = Token[str]('db.url')
    b: TokenKey = Token[int]('db.url')
    assert a == b
    assert hash(a) == hash(b)


def test_a_token_instance_carries_no_dict() -> None:
    assert not hasattr(Token[str]('db.url'), '__dict__')


def test_token_repr_is_unchanged() -> None:
    assert repr(Token[int]('max.conn')) == "Token('max.conn')"
