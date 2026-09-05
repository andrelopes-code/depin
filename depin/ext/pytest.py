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

from depin import FrozenContainer, Host, ProviderKey, ScopeFrame
from depin.errors import ContainerNotBoundError

_CONTAINER_NOT_DEFINED = (
    'depin_container is not defined.\n'
    'Add a fixture to your conftest.py:\n\n'
    '    @pytest.fixture\n'
    '    def depin_container() -> FrozenContainer:\n'
    '        return build_container()\n'
)


class OverrideFactory(Protocol):
    """The callable `depin_override` returns.

    Named so a helper that takes `depin_override` as a parameter has something
    to annotate it with; the plugin exports no fixture importable this way,
    only this type.
    """

    def __call__(self, key: ProviderKey, /, *, tag: str | None = None) -> 'OverrideHandle': ...


class OverrideHandle(Protocol):
    """A selected pytest override that receives its replacement through `using()`."""

    def using(self, replacement: object, /) -> contextlib.AbstractContextManager[FrozenContainer]: ...


class AsyncOverrideFactory(Protocol):
    """The callable `depin_aoverride` returns; the async counterpart to `OverrideFactory`."""

    def __call__(self, key: ProviderKey, /, *, tag: str | None = None) -> 'AsyncOverrideHandle': ...


class AsyncOverrideHandle(Protocol):
    """A selected async pytest override that receives its replacement through `using()`."""

    def using(self, replacement: object, /) -> contextlib.AbstractAsyncContextManager[FrozenContainer]: ...


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
def depin_override(depin_container: FrozenContainer) -> OverrideFactory:
    """Factory for a context manager that overrides a provider and evicts cached consumers.

    Calls `FrozenContainer.reset()` before entering `FrozenContainer.override()`,
    so a singleton already built before the block is rebuilt inside it and sees
    the replacement, then calls `reset()` again on exit, so the real graph is
    back and no singleton built inside the block survives. Both calls reach the
    singletons in the root cache only: a scoped value already cached in an open
    `depin_scope` frame is untouched and keeps the dependency it was built
    with.

    Returns:
        A callable ``(key, *, tag=None)`` whose result accepts `using(replacement)`
        and yields `depin_container` inside its context manager.

    Raises:
        MissingProviderError: ``key`` is not a valid provider key type.
        ExceptionGroup: A teardown drained by `reset()` failed, or a singleton
            being evicted is an async provider — use `depin_aoverride` instead.

    Example:
        What the factory automates, spelled out with the plain `override()` /
        `reset()` calls it wraps:

        ```pycon
        >>> from depin import Container
        >>> class Clock:
        ...     def now(self) -> str:
        ...         return 'real'
        >>> class FakeClock:
        ...     def now(self) -> str:
        ...         return 'fake'
        >>> class Report:
        ...     def __init__(self, clock: Clock) -> None:
        ...         self.clock = clock
        >>> di = Container().bind(Clock).bind(Report).freeze()
        >>> _ = di[Report]
        >>> di.reset()
        >>> with di.override(Clock).using(FakeClock()):
        ...     di[Report].clock.now()
        'fake'
        >>> di.reset()
        >>> di[Report].clock.now()
        'real'

        ```
    """

    class Handle:
        def __init__(self, key: ProviderKey, tag: str | None) -> None:
            self._key = key
            self._tag = tag

        @contextlib.contextmanager
        def using(self, replacement: object, /) -> Generator[FrozenContainer]:
            depin_container.reset()
            try:
                with depin_container.override(self._key, tag=self._tag).using(replacement):
                    yield depin_container
            finally:
                depin_container.reset()

    def factory(key: ProviderKey, /, *, tag: str | None = None) -> OverrideHandle:
        return Handle(key, tag)

    return factory


@pytest.fixture
def depin_aoverride(depin_container: FrozenContainer) -> AsyncOverrideFactory:
    """The async counterpart to `depin_override`, using `FrozenContainer.areset()`.

    Needed instead of `depin_override` whenever a singleton on the path being
    overridden is built by an async provider: `reset()` raises for that case,
    while `areset()` drains it correctly.

    Returns:
        A callable ``(key, *, tag=None)`` whose result accepts `using(replacement)`
        and yields `depin_container` inside its async context manager.

    Raises:
        MissingProviderError: ``key`` is not a valid provider key type.
        ExceptionGroup: A teardown drained by `areset()` failed.
    """

    class Handle:
        def __init__(self, key: ProviderKey, tag: str | None) -> None:
            self._key = key
            self._tag = tag

        @contextlib.asynccontextmanager
        async def using(self, replacement: object, /) -> AsyncGenerator[FrozenContainer]:
            await depin_container.areset()
            try:
                with depin_container.override(self._key, tag=self._tag).using(replacement):
                    yield depin_container
            finally:
                await depin_container.areset()

    def factory(key: ProviderKey, /, *, tag: str | None = None) -> AsyncOverrideHandle:
        return Handle(key, tag)

    return factory


@pytest.fixture
def depin_scope(depin_container: FrozenContainer) -> Generator[ScopeFrame]:
    """Publish `depin_container` and open one synchronous scope around the test.

    Yields the `ScopeFrame`, so the test can seed a `Container.scope_value`
    key with `ScopeFrame.provide` before anything resolves through it.

    Raises:
        TeardownError: An async provider left a teardown in this sync scope,
            reported inside the raised `ExceptionGroup` rather than bare; use
            `depin_ascope` instead.
        ExceptionGroup: One or more teardowns failed when the scope closed.
    """
    with Host(depin_container).scope() as frame:
        yield frame


@pytest.fixture
async def depin_ascope(depin_container: FrozenContainer) -> AsyncGenerator[ScopeFrame]:
    """The async counterpart to `depin_scope`, using `Host.ascope()`.

    Raises:
        ExceptionGroup: One or more teardowns failed when the scope closed.
    """
    async with Host(depin_container).ascope() as frame:
        yield frame
