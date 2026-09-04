"""Regression coverage for frozen-container runtime invariants."""

import pytest

from depin._core.container import Container


def test_nested_scopes_remain_owned_by_their_frozen_containers() -> None:
    outer = Container().scope_value(str).freeze()
    inner = Container().scope_value(str).freeze()

    with outer.scope() as outer_frame:
        outer_frame.provide(str, 'outer')
        with inner.scope() as inner_frame:
            inner_frame.provide(str, 'inner')
            assert outer.resolve(str) == 'outer'
            assert inner.resolve(str) == 'inner'


@pytest.mark.asyncio
async def test_nested_async_scopes_remain_owned_by_their_frozen_containers() -> None:
    outer = Container().scope_value(str).freeze()
    inner = Container().scope_value(str).freeze()

    async with outer.ascope() as outer_frame:
        outer_frame.provide(str, 'outer')
        async with inner.ascope() as inner_frame:
            inner_frame.provide(str, 'inner')
            assert await outer.aresolve(str) == 'outer'
            assert await inner.aresolve(str) == 'inner'


def test_scope_seeds_are_distinguished_by_tag() -> None:
    frozen = Container().scope_value(str, tag='primary').scope_value(str, tag='secondary').freeze()

    with frozen.scope() as frame:
        frame.provide(str, 'one', tag='primary')
        frame.provide(str, 'two', tag='secondary')
        assert frozen.resolve(str, tag='primary') == 'one'
        assert frozen.resolve(str, tag='secondary') == 'two'
