"""What happens when a provider does not behave like the shape it was bound as.

These are the runtime contracts that used to be bare ``assert`` statements: under
``python -O`` an assert vanishes and the mismatch surfaces much later, somewhere
unrelated. They are errors now, and every one of them names the offending
provider.
"""

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator, Iterator

import pytest

from depin._core.container import Container
from depin._core.markers import Token
from depin._core.scope import Scope
from depin._core.typeguards import (
    as_async_context_manager,
    as_async_iterator,
    as_awaitable,
    as_class,
    as_factory,
    as_sync_context_manager,
    as_sync_iterator,
    is_provider_key,
)
from depin.errors import InvalidProviderError


class _Widget: ...


def _disguised_as_context_manager(returns: object) -> Callable[[], object]:
    """A callable that shape detection reads as an ``@contextmanager`` factory.

    ``detect_shape`` classifies a wrapper by its ``__wrapped__`` attribute, which
    is how it recognises ``contextlib.contextmanager``. Setting it by hand is the
    only way to build a provider that claims a shape it does not honour.
    """

    def real() -> Generator[int]:
        yield 1

    def impostor() -> object:
        return returns

    impostor.__wrapped__ = real  # type: ignore[attr-defined]  # pyright: ignore[reportFunctionMemberAccess]
    return impostor


def test_a_context_manager_factory_that_returns_a_plain_value_is_rejected() -> None:
    frozen = (
        Container()
        .bind(
            _disguised_as_context_manager(42),
            scope=Scope.SINGLETON,
            provides=int,
        )
        .freeze()
    )
    with pytest.raises(InvalidProviderError, match='not a context manager'):
        _ = frozen[int]


def test_a_context_manager_provider_that_honours_the_shape_still_works() -> None:
    events: list[str] = []

    @contextlib.contextmanager
    def make() -> Generator[int]:
        yield 5
        events.append('closed')

    frozen = Container().bind(make, scope=Scope.SCOPED, provides=int).freeze()
    with frozen.scope():
        assert frozen[int] == 5
    assert events == ['closed']


@pytest.mark.parametrize('key', [int, 'legacy', Token[int]('k')])
def test_is_provider_key_accepts_classes_strings_and_tokens(key: object) -> None:
    assert is_provider_key(key)


@pytest.mark.parametrize('value', [42, None, 3.5])
def test_is_provider_key_rejects_anything_else(value: object) -> None:
    assert not is_provider_key(value)


def test_as_class_accepts_a_class_and_rejects_an_instance() -> None:
    assert as_class(_Widget, _Widget) is _Widget
    with pytest.raises(InvalidProviderError, match='is not a class'):
        _ = as_class(_Widget(), _Widget)


def test_as_factory_accepts_a_callable_and_rejects_a_value() -> None:
    assert as_factory(_Widget, _Widget) is _Widget
    with pytest.raises(InvalidProviderError, match='is not callable'):
        _ = as_factory(42, _Widget)


@pytest.mark.asyncio
async def test_as_awaitable_accepts_a_coroutine_and_rejects_a_value() -> None:
    async def coro() -> int:
        return 1

    awaitable: Awaitable[object] = as_awaitable(coro(), int)
    assert await awaitable == 1
    with pytest.raises(InvalidProviderError, match='not awaitable'):
        _ = as_awaitable(1, int)


def test_as_sync_iterator_accepts_a_generator_and_rejects_a_list() -> None:
    def gen() -> Iterator[int]:
        yield 1

    assert next(as_sync_iterator(gen(), int)) == 1
    with pytest.raises(InvalidProviderError, match='not an iterator'):
        _ = as_sync_iterator([1], int)


@pytest.mark.asyncio
async def test_as_async_iterator_accepts_an_async_generator_and_rejects_a_value() -> None:
    async def agen() -> AsyncGenerator[int]:
        yield 1

    assert await as_async_iterator(agen(), int).__anext__() == 1
    with pytest.raises(InvalidProviderError, match='not an async iterator'):
        _ = as_async_iterator([1], int)


def test_as_sync_context_manager_accepts_a_context_manager_and_rejects_a_value() -> None:
    assert as_sync_context_manager(contextlib.nullcontext(), int) is not None
    with pytest.raises(InvalidProviderError, match='not a context manager'):
        _ = as_sync_context_manager(1, int)


def test_as_async_context_manager_accepts_an_async_context_manager_and_rejects_a_value() -> None:
    assert as_async_context_manager(contextlib.AsyncExitStack(), int) is not None
    with pytest.raises(InvalidProviderError, match='not an async context manager'):
        _ = as_async_context_manager(1, int)
