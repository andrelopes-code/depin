"""Resolution of provider chains beyond Python's call-stack limit."""

from collections.abc import Callable

import pytest

from depin._core.container import Container
from depin._core.markers import Token
from depin._core.scope import Scope

DEPTH = 1_000


def _sync_chain(scope: Scope, *, failure_at: int | None = None) -> tuple[Container, Token[object], object]:
    tokens = [Token[object](f'node-{index}') for index in range(DEPTH)]
    terminal = object()
    container = Container()

    def leaf() -> object:
        return terminal

    container.bind(leaf, provides=tokens[0], scope=scope)
    for index, token in enumerate(tokens[1:], start=1):
        make = _sync_step(index, failure_at)
        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=scope)
    return container, tokens[-1], terminal


def _sync_step(index: int, failure_at: int | None) -> Callable[[object], object]:
    def make(value: object) -> object:
        if index == failure_at:
            raise RuntimeError('mid-chain failure')
        return value

    return make


def test_sync_transient_chain_of_one_thousand_resolves_without_recursion() -> None:
    container, key, terminal = _sync_chain(Scope.TRANSIENT)
    assert container.freeze().resolve(key) is terminal


def test_sync_singleton_cold_chain_of_one_thousand_resolves_without_recursion() -> None:
    container, key, terminal = _sync_chain(Scope.SINGLETON)
    frozen = container.freeze()
    assert frozen.resolve(key) is terminal
    assert frozen.resolve(key) is terminal


@pytest.mark.asyncio
async def test_async_chain_of_one_thousand_resolves_without_recursion() -> None:
    tokens = [Token[object](f'async-node-{index}') for index in range(DEPTH)]
    terminal = object()
    container = Container()

    async def leaf() -> object:
        return terminal

    container.bind(leaf, provides=tokens[0], scope=Scope.TRANSIENT)
    for index, token in enumerate(tokens[1:], start=1):

        async def make(value: object) -> object:
            return value

        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.TRANSIENT)

    assert await container.freeze().aresolve(tokens[-1]) is terminal


def test_sync_chain_propagates_a_mid_chain_provider_failure() -> None:
    container, key, _ = _sync_chain(Scope.TRANSIENT, failure_at=DEPTH // 2)
    with pytest.raises(RuntimeError, match='mid-chain failure'):
        _ = container.freeze().resolve(key)
