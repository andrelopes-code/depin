"""Construction diagnostics exposed through a frozen container."""

import functools
from collections.abc import AsyncGenerator, Generator

import pytest

from depin._core.construct import asynchronous, sync
from depin._core.container import Container
from depin._core.scope import Scope
from depin._core.spec import ProviderShape, ProviderSpec
from depin.errors import AsyncInSyncContextError, InvalidProviderError


class _Result: ...


def _spec(shape: ProviderShape, source: object = 42) -> ProviderSpec:
    return ProviderSpec(
        key='wanted',
        tag=None,
        source=source,
        scope=Scope.TRANSIENT,
        shape=shape,
        needs_async=shape
        in {
            ProviderShape.ASYNC_FUNCTION,
            ProviderShape.ASYNC_GENERATOR,
            ProviderShape.ASYNC_CONTEXT_MANAGER,
        },
        params=(),
    )


def _no_teardown(value: object) -> None:
    del value


def _no_frame(spec: ProviderSpec) -> object:
    del spec
    return None


@pytest.mark.parametrize(
    ('shape', 'message'),
    [
        (ProviderShape.CLASS, "provider for 'wanted' is bound as a class, but 42 is not a class"),
        (ProviderShape.FUNCTION, "provider for 'wanted' is bound as a factory, but 42 is not callable"),
        (ProviderShape.GENERATOR, "provider for 'wanted' is bound as a factory, but 42 is not callable"),
        (ProviderShape.CONTEXT_MANAGER, "provider for 'wanted' is bound as a factory, but 42 is not callable"),
    ],
)
def test_sync_construct_reports_the_bound_key_for_each_factory_shape(shape: ProviderShape, message: str) -> None:
    with pytest.raises(InvalidProviderError, match='^' + message + '$'):
        sync(_spec(shape), {}, _no_teardown, _no_frame)


@pytest.mark.parametrize(
    'shape',
    [ProviderShape.ASYNC_FUNCTION, ProviderShape.ASYNC_GENERATOR, ProviderShape.ASYNC_CONTEXT_MANAGER],
)
def test_sync_construct_rejects_async_shapes_with_the_bound_key(shape: ProviderShape) -> None:
    with pytest.raises(AsyncInSyncContextError, match=r"^'wanted' is an async provider; resolve it with aresolve\(\)$"):
        sync(_spec(shape), {}, _no_teardown, _no_frame)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('shape', 'message'),
    [
        (ProviderShape.ASYNC_FUNCTION, "provider for 'wanted' is bound as a factory, but 42 is not callable"),
        (ProviderShape.ASYNC_GENERATOR, "provider for 'wanted' is bound as a factory, but 42 is not callable"),
        (ProviderShape.ASYNC_CONTEXT_MANAGER, "provider for 'wanted' is bound as a factory, but 42 is not callable"),
    ],
)
async def test_async_construct_reports_the_bound_key_for_async_factory_shapes(
    shape: ProviderShape, message: str
) -> None:
    with pytest.raises(InvalidProviderError, match='^' + message + '$'):
        await asynchronous(_spec(shape), {}, _no_teardown, _no_frame)


def test_sync_construct_reports_the_bound_key_when_a_generator_returns_a_non_iterator() -> None:
    with pytest.raises(
        InvalidProviderError,
        match=r"^generator provider for 'wanted' returned 42, which is not an iterator$",
    ):
        sync(_spec(ProviderShape.GENERATOR, lambda: 42), {}, _no_teardown, _no_frame)


@pytest.mark.asyncio
@pytest.mark.parametrize('shape', [ProviderShape.ASYNC_FUNCTION, ProviderShape.ASYNC_GENERATOR])
async def test_async_construct_reports_the_bound_key_when_async_results_have_the_wrong_shape(
    shape: ProviderShape,
) -> None:
    message = (
        "async provider for 'wanted' returned 42, which is not awaitable"
        if shape is ProviderShape.ASYNC_FUNCTION
        else "async generator provider for 'wanted' returned 42, which is not an async iterator"
    )
    with pytest.raises(InvalidProviderError, match='^' + message + '$'):
        await asynchronous(_spec(shape, lambda: 42), {}, _no_teardown, _no_frame)


def test_context_manager_contract_failure_names_the_bound_key() -> None:
    def declared_shape() -> Generator[_Result]:
        yield _Result()

    @functools.wraps(declared_shape)
    def provider() -> object:
        return 42

    frozen = Container().bind(provider, scope=Scope.SINGLETON, provides=_Result).freeze()

    with pytest.raises(InvalidProviderError) as exc:
        _ = frozen[_Result]

    assert str(exc.value) == 'context-manager provider for _Result returned 42, which is not a context manager'


@pytest.mark.asyncio
async def test_async_context_manager_contract_failure_names_the_bound_key() -> None:
    async def declared_shape() -> AsyncGenerator[_Result]:
        yield _Result()

    @functools.wraps(declared_shape)
    def provider() -> object:
        return 42

    frozen = Container().bind(provider, scope=Scope.SINGLETON, provides=_Result).freeze()

    with pytest.raises(InvalidProviderError) as exc:
        _ = await frozen.aresolve(_Result)

    assert (
        str(exc.value)
        == 'async context-manager provider for _Result returned 42, which is not an async context manager'
    )


def test_an_alias_spec_with_no_resolved_target_names_the_provider() -> None:
    class Store: ...

    spec = ProviderSpec(
        key=Store,
        tag=None,
        source=None,
        scope=Scope.TRANSIENT,
        shape=ProviderShape.ALIAS,
        needs_async=False,
        params=(),
    )
    with pytest.raises(InvalidProviderError, match='Store'):
        _ = sync(spec, {}, _no_teardown, _no_frame)
