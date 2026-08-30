import contextlib
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from typing import Annotated

from depin._core.introspect import detect_shape, extract_annotated_meta
from depin._core.markers import Named, Tag, Token
from depin._core.spec import ProviderShape


def test_detect_shape_class() -> None:
    class A: ...

    assert detect_shape(A) is ProviderShape.CLASS


def test_detect_shape_sync_function() -> None:
    def f() -> int:
        return 0

    assert detect_shape(f) is ProviderShape.FUNCTION


def test_detect_shape_async_function() -> None:
    async def f() -> int:
        return 0

    assert detect_shape(f) is ProviderShape.ASYNC_FUNCTION


def test_detect_shape_sync_generator() -> None:
    def gen() -> Iterator[int]:
        yield 0

    assert detect_shape(gen) is ProviderShape.GENERATOR


def test_detect_shape_async_generator() -> None:
    async def gen() -> AsyncIterator[int]:
        yield 0

    assert detect_shape(gen) is ProviderShape.ASYNC_GENERATOR


def test_detect_shape_context_manager_factory() -> None:
    @contextlib.contextmanager
    def cm() -> Generator[int]:
        yield 1

    assert detect_shape(cm) is ProviderShape.CONTEXT_MANAGER


def test_detect_shape_async_context_manager_factory() -> None:
    @contextlib.asynccontextmanager
    async def cm() -> AsyncGenerator[int]:
        yield 1

    assert detect_shape(cm) is ProviderShape.ASYNC_CONTEXT_MANAGER


def test_detect_shape_non_callable_raises() -> None:
    import pytest

    with pytest.raises(TypeError) as exc:
        detect_shape(42)
    assert str(exc.value).endswith('bind a class, a function, a generator function, or a context-manager factory')


def test_extract_meta_returns_empty_for_bare_annotation() -> None:
    meta = extract_annotated_meta(int)
    assert meta.token is None
    assert meta.named is None
    assert meta.tag is None
    assert meta.base is int


def test_extract_meta_picks_token() -> None:
    tok = Token[str]('db.url')
    meta = extract_annotated_meta(Annotated[str, tok])
    assert meta.token == tok
    assert meta.base is str


def test_extract_meta_picks_tag() -> None:
    meta = extract_annotated_meta(Annotated[str, Tag('primary')])
    assert meta.tag == 'primary'


def test_extract_meta_picks_named_string() -> None:
    meta = extract_annotated_meta(Annotated[str, Named('legacy')])
    assert meta.named == 'legacy'


def test_extract_meta_token_wins_over_named() -> None:
    tok = Token[int]('x')
    meta = extract_annotated_meta(Annotated[int, tok, Named('legacy')])
    assert meta.token == tok
    assert meta.named is None
