"""Construction contracts that are only reachable after provider-shape detection."""

import pytest

from depin._core.construct import asynchronous, sync
from depin._core.scope import Scope
from depin._core.spec import ProviderShape, ProviderSpec
from depin._core.teardown import Teardown
from depin.errors import AsyncInSyncContextError, InvalidProviderError


class _Result: ...


def _spec(shape: ProviderShape, source: object) -> ProviderSpec:
    return ProviderSpec(
        key=_Result,
        tag=None,
        source=source,
        scope=Scope.TRANSIENT,
        shape=shape,
        needs_async=shape
        in {ProviderShape.ASYNC_FUNCTION, ProviderShape.ASYNC_GENERATOR, ProviderShape.ASYNC_CONTEXT_MANAGER},
        params=(),
    )


def _read_frame(spec: ProviderSpec) -> object:
    raise AssertionError(f'unexpected frame read for {spec.key!r}')


def _returns_value() -> object:
    return 42


def _record_teardown(record: Teardown) -> None:
    del record


@pytest.mark.parametrize(
    ('shape', 'source', 'contract'),
    [
        (ProviderShape.CLASS, 42, 'provider for _Result is bound as a class, but 42 is not a class'),
        (ProviderShape.FUNCTION, 42, 'provider for _Result is bound as a factory, but 42 is not callable'),
        (
            ProviderShape.GENERATOR,
            _returns_value,
            'generator provider for _Result returned 42, which is not an iterator',
        ),
        (
            ProviderShape.CONTEXT_MANAGER,
            _returns_value,
            'context-manager provider for _Result returned 42, which is not a context manager',
        ),
    ],
)
def test_sync_construction_reports_the_bound_key_for_invalid_provider_shapes(
    shape: ProviderShape, source: object, contract: str
) -> None:
    with pytest.raises(InvalidProviderError) as exc:
        _ = sync(_spec(shape, source), {}, _record_teardown, _read_frame)

    assert str(exc.value) == contract


def test_sync_construction_rejects_an_async_shape_with_resolution_guidance() -> None:
    with pytest.raises(AsyncInSyncContextError) as exc:
        _ = sync(_spec(ProviderShape.ASYNC_FUNCTION, _returns_value), {}, _record_teardown, _read_frame)

    assert str(exc.value) == '_Result is an async provider; resolve it with aresolve()'


@pytest.mark.parametrize(
    'shape',
    [ProviderShape.GENERATOR, ProviderShape.CONTEXT_MANAGER],
)
def test_sync_factory_shapes_report_the_key_when_the_source_is_not_callable(shape: ProviderShape) -> None:
    with pytest.raises(InvalidProviderError) as exc:
        _ = sync(_spec(shape, 42), {}, _record_teardown, _read_frame)

    assert str(exc.value) == 'provider for _Result is bound as a factory, but 42 is not callable'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('shape', 'contract'),
    [
        (ProviderShape.ASYNC_FUNCTION, 'async provider for _Result returned 42, which is not awaitable'),
        (
            ProviderShape.ASYNC_GENERATOR,
            'async generator provider for _Result returned 42, which is not an async iterator',
        ),
        (
            ProviderShape.ASYNC_CONTEXT_MANAGER,
            'async context-manager provider for _Result returned 42, which is not an async context manager',
        ),
    ],
)
async def test_async_construction_reports_the_bound_key_for_invalid_provider_shapes(
    shape: ProviderShape, contract: str
) -> None:
    with pytest.raises(InvalidProviderError) as exc:
        _ = await asynchronous(_spec(shape, _returns_value), {}, _record_teardown, _read_frame)

    assert str(exc.value) == contract


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'shape',
    [ProviderShape.ASYNC_FUNCTION, ProviderShape.ASYNC_GENERATOR, ProviderShape.ASYNC_CONTEXT_MANAGER],
)
async def test_async_factory_shapes_report_the_key_when_the_source_is_not_callable(shape: ProviderShape) -> None:
    with pytest.raises(InvalidProviderError) as exc:
        _ = await asynchronous(_spec(shape, 42), {}, _record_teardown, _read_frame)

    assert str(exc.value) == 'provider for _Result is bound as a factory, but 42 is not callable'
