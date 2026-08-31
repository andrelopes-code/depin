"""pytest integration: fixtures for the container, its overrides, and its scopes.

Registered on the ``pytest11`` entry point, so installing ``pydepin`` makes
these fixtures available with no ``conftest.py`` import. The plugin adds
fixtures only — no hooks, no autouse, no change to collection or reporting.

Define `depin_container` in your own ``conftest.py`` to hand the plugin the
container your suite tests; everything else builds on it.
"""

import contextlib
from collections.abc import AsyncGenerator, Generator
from typing import Protocol

import pytest

from depin import FrozenContainer, Host, ScopeFrame, Token
from depin.errors import ContainerNotBoundError

_CONTAINER_NOT_DEFINED = (
    'depin_container is not defined.\n'
    'Add a fixture to your conftest.py:\n\n'
    '    @pytest.fixture\n'
    '    def depin_container() -> FrozenContainer:\n'
    '        return build_container()\n'
)


class _OverrideFactory(Protocol):
    """The callable `depin_override` returns."""

    def __call__[T](
        self,
        key: type[T] | Token[T],
        replacement: T,
        *,
        tag: str | None = None,
    ) -> contextlib.AbstractContextManager[FrozenContainer]: ...


class _AsyncOverrideFactory(Protocol):
    """The callable `depin_aoverride` returns."""

    def __call__[T](
        self,
        key: type[T] | Token[T],
        replacement: T,
        *,
        tag: str | None = None,
    ) -> contextlib.AbstractAsyncContextManager[FrozenContainer]: ...


@pytest.fixture
def depin_container() -> FrozenContainer:
    """The `FrozenContainer` under test.

    This fixture always raises. Override it by defining a fixture of the same
    name in your own ``conftest.py``; every other fixture in this plugin is
    built on top of whatever that fixture returns.

    Raises:
        ContainerNotBoundError: No ``depin_container`` fixture was defined for
            this suite. The message names the fixture and shows the shape to
            write.
    """
    raise ContainerNotBoundError(_CONTAINER_NOT_DEFINED)


@pytest.fixture
def depin_override(depin_container: FrozenContainer) -> _OverrideFactory:
    """Factory for a context manager that overrides a provider and evicts cached consumers.

    Calls `FrozenContainer.reset()` before entering `FrozenContainer.override()`,
    so a singleton already built before the block is rebuilt inside it and sees
    the replacement, then calls `reset()` again on exit, so the block leaves no
    trace: the real graph is back and nothing built inside it survives.

    Returns:
        A callable ``(key, replacement, *, tag=None)`` whose result is a
        context manager yielding `depin_container`.

    Example:
        ```python
        def test_uses_fake_clock(depin_container, depin_override):
            real_report = depin_container[Report]
            with depin_override(Clock, FakeClock()) as di:
                assert di[Report].rendered_at == 'fake'
        ```
    """

    @contextlib.contextmanager
    def factory[T](
        key: type[T] | Token[T],
        replacement: T,
        *,
        tag: str | None = None,
    ) -> Generator[FrozenContainer]:
        depin_container.reset()
        try:
            with depin_container.override(key, replacement, tag=tag):
                yield depin_container
        finally:
            depin_container.reset()

    return factory


@pytest.fixture
def depin_aoverride(depin_container: FrozenContainer) -> _AsyncOverrideFactory:
    """The async counterpart to `depin_override`, using `FrozenContainer.areset()`.

    Needed instead of `depin_override` whenever a singleton on the path being
    overridden is built by an async provider: `reset()` raises for that case,
    while `areset()` drains it correctly.

    Returns:
        A callable ``(key, replacement, *, tag=None)`` whose result is an
        async context manager yielding `depin_container`.
    """

    @contextlib.asynccontextmanager
    async def factory[T](
        key: type[T] | Token[T],
        replacement: T,
        *,
        tag: str | None = None,
    ) -> AsyncGenerator[FrozenContainer]:
        await depin_container.areset()
        try:
            with depin_container.override(key, replacement, tag=tag):
                yield depin_container
        finally:
            await depin_container.areset()

    return factory


@pytest.fixture
def depin_scope(depin_container: FrozenContainer) -> Generator[ScopeFrame]:
    """Publish `depin_container` and open one synchronous scope around the test.

    Yields the `ScopeFrame`, so the test can seed a `Container.scope_value`
    key with `ScopeFrame.provide` before anything resolves through it.
    """
    with Host(depin_container).scope() as frame:
        yield frame


@pytest.fixture
async def depin_ascope(depin_container: FrozenContainer) -> AsyncGenerator[ScopeFrame]:
    """The async counterpart to `depin_scope`, using `Host.ascope()`."""
    async with Host(depin_container).ascope() as frame:
        yield frame
