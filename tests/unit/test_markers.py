from collections.abc import Callable

from depin._core.markers import Inject, Named, Tag, Token, get_provides, provides


def test_token_is_typed_key() -> None:
    db_url = Token[str]('db.url')
    assert db_url.name == 'db.url'


def test_tokens_are_distinct_by_identity() -> None:
    a = Token[str]('db.url')
    b = Token[str]('db.url')
    assert a is not b
    assert a != b
    assert hash(a) != hash(b)


def test_token_repr_includes_name() -> None:
    t = Token[int]('max.conn')
    assert 'max.conn' in repr(t)


def test_inject_holds_factory() -> None:
    def factory() -> int:
        return 1

    marker = Inject(factory)
    assert marker.factory is factory


def test_named_holds_key() -> None:
    tok = Token[str]('x')
    n = Named(tok)
    assert n.key is tok


def test_named_accepts_string_key() -> None:
    n = Named('legacy')
    assert n.key == 'legacy'


def test_tag_holds_name() -> None:
    t = Tag('primary')
    assert t.name == 'primary'


def test_inject_factory_is_callable_only() -> None:
    inj = Inject(lambda: 0)
    assert isinstance(inj.factory, Callable)


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
