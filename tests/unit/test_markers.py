from depin._core.markers import Named, Tag, Token, get_provides, provides


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
