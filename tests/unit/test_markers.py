import dataclasses

import pytest

from depin._core.markers import Named, Tag, Token, get_provides, injected, is_inject_marker, provides
from depin.errors import DepinError


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
