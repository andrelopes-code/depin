"""Resolution of provider chains beyond Python's call-stack limit."""

import asyncio
import threading
from collections.abc import AsyncGenerator, Callable

import pytest

from depin._core.container import Container
from depin._core.markers import Token
from depin._core.scope import Scope
from depin.errors import AsyncInSyncContextError

DEPTH = 1_000
CONCURRENCY_DEPTH = 400


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


@pytest.mark.asyncio
async def test_iterative_resolution_handles_optional_default_and_provided_parameters() -> None:
    class Result:
        def __init__(self, value: str | None, count: int = 7) -> None:
            self.value = value
            self.count = count

    container = Container()
    for index in range(CONCURRENCY_DEPTH):
        container.value(Token[int](f'padding-{index}'), index)
    frozen = container.bind(Result, scope=Scope.TRANSIENT).freeze()

    assert vars(frozen.resolve(Result)) == {'value': None, 'count': 7}
    assert vars(await frozen.aresolve(Result)) == {'value': None, 'count': 7}

    with frozen.scope() as frame:
        frame.provide(str, 'sync')
        assert vars(frozen.resolve(Result)) == {'value': 'sync', 'count': 7}
    async with frozen.ascope() as frame:
        frame.provide(str, 'async')
        assert vars(await frozen.aresolve(Result)) == {'value': 'async', 'count': 7}


def test_sync_chain_propagates_a_mid_chain_provider_failure() -> None:
    container, key, _ = _sync_chain(Scope.TRANSIENT, failure_at=DEPTH // 2)
    with pytest.raises(RuntimeError, match='mid-chain failure'):
        _ = container.freeze().resolve(key)


@pytest.mark.asyncio
async def test_async_singleton_chain_retries_after_cancelled_leader() -> None:
    tokens = [Token[object](f'cancel-node-{index}') for index in range(CONCURRENCY_DEPTH)]
    started = asyncio.Event()
    attempts = 0
    terminal = object()
    container = Container()

    async def leaf() -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            await asyncio.Event().wait()
        return terminal

    container.bind(leaf, provides=tokens[0], scope=Scope.SINGLETON)
    for index, token in enumerate(tokens[1:], start=1):

        async def make(value: object) -> object:
            return value

        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.SINGLETON)

    frozen = container.freeze()
    leader = asyncio.create_task(frozen.aresolve(tokens[-1]))
    await started.wait()
    follower = asyncio.create_task(frozen.aresolve(tokens[-1]))
    leader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leader
    resolved = await follower
    assert resolved is terminal
    assert await frozen.aresolve(tokens[-1]) is terminal
    assert attempts == 2


def test_sync_singleton_chain_retries_once_after_mid_chain_failure() -> None:
    tokens = [Token[object](f'flight-node-{index}') for index in range(CONCURRENCY_DEPTH)]
    barrier = threading.Barrier(3)
    failure_started = threading.Event()
    release_failure = threading.Event()
    attempts = [0] * CONCURRENCY_DEPTH
    terminal = object()
    failure_at = CONCURRENCY_DEPTH // 2
    container = Container()

    def leaf() -> object:
        attempts[0] += 1
        return terminal

    container.bind(leaf, provides=tokens[0], scope=Scope.SINGLETON)
    for index, token in enumerate(tokens[1:], start=1):
        make = _sync_singleton_step(index, failure_at, attempts, failure_started, release_failure)
        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.SINGLETON)

    frozen = container.freeze()
    failures: list[BaseException] = []
    resolved: list[object] = []

    def resolve() -> None:
        barrier.wait()
        try:
            resolved.append(frozen.resolve(tokens[-1]))
        except BaseException as exc:
            failures.append(exc)

    first = threading.Thread(target=resolve)
    second = threading.Thread(target=resolve)
    first.start()
    second.start()
    barrier.wait()
    failure_started.wait()
    release_failure.set()
    first.join()
    second.join()

    assert len(failures) == 1
    assert str(failures[0]) == 'mid-chain failure'
    assert resolved == [terminal]
    assert attempts == [1 if index != failure_at else 2 for index in range(CONCURRENCY_DEPTH)]


def _sync_singleton_step(
    index: int,
    failure_at: int,
    attempts: list[int],
    failure_started: threading.Event,
    release_failure: threading.Event,
) -> Callable[[object], object]:
    def make(value: object) -> object:
        attempts[index] += 1
        if index == failure_at and attempts[index] == 1:
            failure_started.set()
            release_failure.wait()
            raise RuntimeError('mid-chain failure')
        return value

    return make


@pytest.mark.asyncio
async def test_aclose_waits_for_cancelled_deep_resolution_and_drains_resources_lifo() -> None:
    resource_tokens = [Token[object](f'resource-node-{index}') for index in range(CONCURRENCY_DEPTH)]
    second = Token[object]('second-resource')
    blocked = Token[object]('blocked-resource')
    root = Token[object]('resource-root')
    events: list[str] = []
    blocked_started = asyncio.Event()
    release_blocked = asyncio.Event()
    first_value = object()
    second_value = object()
    container = Container()

    async def first_resource() -> AsyncGenerator[object]:
        events.append('first-open')
        yield first_value
        events.append('first-close')

    async def second_resource() -> AsyncGenerator[object]:
        events.append('second-open')
        yield second_value
        events.append('second-close')

    async def wait_for_close() -> object:
        blocked_started.set()
        await release_blocked.wait()
        return object()

    async def combine(first: object, second: object, blocker: object) -> object:
        return first, second, blocker

    container.bind(first_resource, provides=resource_tokens[0], scope=Scope.SINGLETON)
    for index, token in enumerate(resource_tokens[1:], start=1):

        async def make(value: object) -> object:
            return value

        make.__annotations__['value'] = resource_tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.SINGLETON)
    combine.__annotations__['first'] = resource_tokens[-1]
    combine.__annotations__['second'] = second
    combine.__annotations__['blocker'] = blocked
    container.bind(second_resource, provides=second, scope=Scope.SINGLETON)
    container.bind(wait_for_close, provides=blocked, scope=Scope.SINGLETON)
    container.bind(combine, provides=root, scope=Scope.SINGLETON)

    frozen = container.freeze()
    resolving = asyncio.create_task(frozen.aresolve(root))
    await blocked_started.wait()
    closing = asyncio.create_task(frozen.aclose())
    checkpoint = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(checkpoint.set_result, None)
    await checkpoint
    assert not closing.done()
    resolving.cancel()
    with pytest.raises(asyncio.CancelledError):
        await resolving
    await closing
    assert events == ['first-open', 'second-open', 'second-close', 'first-close']


@pytest.mark.asyncio
async def test_sync_async_preflight_leaves_deep_singleton_chain_resolvable() -> None:
    tokens = [Token[object](f'async-preflight-node-{index}') for index in range(CONCURRENCY_DEPTH)]
    terminal = object()
    container = Container()

    async def leaf() -> object:
        return terminal

    container.bind(leaf, provides=tokens[0], scope=Scope.SINGLETON)
    for index, token in enumerate(tokens[1:], start=1):

        def make(value: object) -> object:
            return value

        make.__annotations__['value'] = tokens[index - 1]
        container.bind(make, provides=token, scope=Scope.SINGLETON)

    frozen = container.freeze()
    with pytest.raises(AsyncInSyncContextError):
        _ = frozen.resolve(tokens[-1])
    assert await frozen.aresolve(tokens[-1]) is terminal
