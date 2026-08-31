"""The public seam an integration uses to host a container inside a framework."""

import contextlib
from collections.abc import AsyncGenerator, Generator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, final, override

from depin._core.frozen import FrozenContainer
from depin._core.scope import ScopeFrame
from depin.errors import ContainerNotBoundError


@final
@dataclass(frozen=True, slots=True, order=True)
class ContractVersion:
    """The version of the integration contract a release of depin implements.

    The minor number rises when an operation is added and every existing one
    keeps its meaning; the major number rises when an operation changes meaning
    or is removed. An integration that needs an operation added in ``1.2``
    guards on ``depin.CONTRACT_VERSION >= ContractVersion(1, 2)``.

    Attributes:
        major: Rises on a breaking change to an existing operation.
        minor: Rises when an operation is added.

    Example:
        ```pycon
        >>> from depin import CONTRACT_VERSION, ContractVersion
        >>> CONTRACT_VERSION >= ContractVersion(1, 0)
        True
        >>> str(CONTRACT_VERSION)
        '1.0'

        ```
    """

    major: int
    minor: int

    @override
    def __str__(self) -> str:
        return f'{self.major}.{self.minor}'


CONTRACT_VERSION: Final = ContractVersion(1, 0)
"""The contract version this release of depin implements."""

_hosted: ContextVar[FrozenContainer | None] = ContextVar('depin_hosted_container', default=None)


@final
class Host:
    """A `FrozenContainer` hosted inside a framework.

    An integration builds one `Host` when the application is wired, then opens
    a scope per unit of work — an HTTP request, a CLI invocation, a queue
    message. Inside that scope the container is published to the current
    `contextvars.Context`, so code that carries only an annotation reaches it
    through `hosted_container()`.

    The publication is context-local, so concurrent requests and concurrent
    tasks never see each other's container, and two hosts in one process nest
    the published container: the innermost wins and the enclosing one is
    restored on exit.

    Scopes do not nest that way. The scope frame stack is process-wide and
    shared by every container, so a scope opened inside another host's scope
    becomes a child of that frame, and a key already cached there is what the
    inner scope resolves — the inner container's own binding never runs. Two
    different containers must not nest their scopes.

    Example:
        ```pycon
        >>> from depin import Container, Host, Token, hosted_container
        >>> request_id = Token[str]('request_id')
        >>> di = Container().scope_value(request_id).freeze()
        >>> host = Host(di)
        >>> with host.scope() as frame:
        ...     frame.provide(request_id, 'r-1')
        ...     hosted_container().resolve(request_id)
        'r-1'

        ```
    """

    __slots__ = ('_container',)

    def __init__(self, container: FrozenContainer) -> None:
        self._container = container

    @property
    def container(self) -> FrozenContainer:
        """The container this host was built around."""
        return self._container

    @contextlib.contextmanager
    def activated(self) -> Generator[None]:
        """Publish the container for the duration of the block, opening no scope.

        What an integration uses outside a unit of work: an ASGI lifespan, a
        process-wide CLI setup, anything that resolves singletons through
        `hosted_container()` without a scope to open.

        Example:
            ```pycon
            >>> from depin import Container, Host, hosted_container
            >>> di = Container().freeze()
            >>> with Host(di).activated():
            ...     hosted_container() is di
            True

            ```
        """
        token = _hosted.set(self._container)
        try:
            yield
        finally:
            _hosted.reset(token)

    @contextlib.contextmanager
    def scope(self) -> Generator[ScopeFrame]:
        """Publish the container and open one synchronous scope around a unit of work.

        Yields the scope's frame so the caller can seed the framework's own
        objects into it with `ScopeFrame.provide` before anything resolves. On
        exit the scope's teardowns run first and the publication is undone
        after, so a teardown can still reach the container.

        Raises:
            TeardownError: An async provider left a teardown in this sync
                scope. Use `ascope()` instead.
            ExceptionGroup: One or more teardowns failed when the scope
                closed. Every failure is included; one does not hide another.

        Example:
            ```pycon
            >>> from depin import Container, Host, Token, hosted_container
            >>> job = Token[str]('job')
            >>> di = Container().scope_value(job).freeze()
            >>> with Host(di).scope() as frame:
            ...     frame.provide(job, 'reindex')
            ...     hosted_container().resolve(job)
            'reindex'

            ```
        """
        with self.activated(), self._container.scope() as frame:
            yield frame

    @contextlib.asynccontextmanager
    async def ascope(self) -> AsyncGenerator[ScopeFrame]:
        """Publish the container and open one asynchronous scope; the counterpart to `scope()`.

        Required when any provider in the scope is async. Otherwise identical:
        the frame is yielded for seeding, teardowns run before the publication
        is undone.

        Raises:
            ExceptionGroup: One or more teardowns failed when the scope
                closed. Every failure is included; one does not hide another.

        Example:
            ```pycon
            >>> import asyncio
            >>> from depin import Container, Host, Token, hosted_container
            >>> job = Token[str]('job')
            >>> di = Container().scope_value(job).freeze()
            >>> async def run() -> None:
            ...     async with Host(di).ascope() as frame:
            ...         frame.provide(job, 'reindex')
            ...         print(await hosted_container().aresolve(job))
            >>> asyncio.run(run())
            reindex

            ```
        """
        with self.activated():
            async with self._container.ascope() as frame:
                yield frame


def hosted_container() -> FrozenContainer:
    """Return the container hosted in this context.

    Raises:
        ContainerNotBoundError: No `Host` has published a container here.
            Open a scope with `Host.scope()` / `Host.ascope()`, or publish one
            with `Host.activated()`.

    Example:
        ```pycon
        >>> from depin import Container, Host, hosted_container
        >>> di = Container().freeze()
        >>> with Host(di).activated():
        ...     hosted_container() is di
        True

        ```
    """
    container = _hosted.get()
    if container is None:
        raise ContainerNotBoundError(
            'no container is hosted in this context; open a scope with Host.scope() or Host.ascope(), '
            'or publish one with Host.activated()'
        )
    return container


def optional_hosted_container() -> FrozenContainer | None:
    """Return the container hosted in this context, or ``None`` when there is none.

    The non-raising counterpart to `hosted_container()`. An integration uses it
    to raise its own message, naming the setup step its users actually
    forgot — installing a middleware, registering a plugin — rather than the
    contract-level one.

    Example:
        ```pycon
        >>> from depin import optional_hosted_container
        >>> optional_hosted_container() is None
        True

        ```
    """
    return _hosted.get()
