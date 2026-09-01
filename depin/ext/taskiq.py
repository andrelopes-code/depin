"""Taskiq integration: one depin scope per message, seeded with its `TaskiqMessage`.

Importing this module requires the ``taskiq`` extra (``pip install
'pydepin[taskiq]'``); the depin core itself has no third-party dependencies.

Written against depin's public integration contract — `depin.Host` — so it
reaches nothing inside depin's internals.

Every other integration depin ships is handed a *block*: an ASGI application to
await inside one, a command context that owns a resource until it closes, a
fixture that yields. Taskiq is handed a *pair* — ``pre_execute`` before the task
body and ``post_execute`` after it — so the scope's `contextlib.AsyncExitStack`
has to survive between two calls that share no frame, and where it survives is
the whole design.

It cannot survive on the middleware instance. One `MessageScope` is registered
on a broker and every message that broker's worker handles goes through that one
object, so three messages in flight leave the attribute holding the third
message's stack: two scopes then never drain at all, and the first
``post_execute`` to run closes the third message's stack from a context that is
not the one that opened it, which fails outright with ``ValueError: Token was
created in a different Context``. The stack lives in a module-level
`contextvars.ContextVar` instead, because ``pre_execute``, the task body and
``post_execute`` share one asyncio task and therefore one
`contextvars.Context` — including when the task body is a synchronous function
Taskiq dispatches to its executor, which is what the ``taskiq>=0.11.19`` floor
buys. Concurrent messages are isolated by the same mechanism, and the value
never reaches the code that sent the message.
"""

from contextlib import AsyncExitStack
from contextvars import ContextVar
from typing import override

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from depin import FrozenContainer, Host

_message_scope: ContextVar[AsyncExitStack | None] = ContextVar('depin_taskiq_message_scope', default=None)


class MessageScope(TaskiqMiddleware):
    """Taskiq middleware that opens one depin async scope around every message.

    The scope opens before the task body runs and closes after it finishes,
    including when it finishes by raising: Taskiq calls ``post_execute`` for a
    failed task as well as a successful one, and the failure surfaces on the
    `taskiq.TaskiqResult` either way. Inside the scope the container is
    published to the message's context, so `depin.hosted_container()` reaches it
    from anywhere the task calls into, and the message is seeded under
    `taskiq.TaskiqMessage`. The scope's teardowns run when the message finishes,
    and the publication is undone after them.

    The seeding is half of a pair the container has to complete. A provider that
    declares a `taskiq.TaskiqMessage` parameter — and is then handed the task id,
    name, labels and arguments of the message it is resolving for — resolves only
    if the container declared that key with `depin.Container.scope_value`;
    without it `freeze()` reports `depin.errors.MissingProviderError` for
    `taskiq.TaskiqMessage`. What the middleware supplies is the value, never the
    binding.

    The scope is asynchronous, so an async task body has a place to await
    `depin.FrozenContainer.aresolve` and an async provider a place to run. A
    synchronous task body reaches the container too — from ``taskiq`` 0.11.19,
    the release whose receiver runs a ``def`` body under
    `contextvars.copy_context`, so the executor thread carries the message's
    context — but it cannot await, so it is limited to
    `depin.FrozenContainer.resolve`, and an async provider asked for there raises
    `depin.errors.AsyncInSyncContextError`.

    Register it **last**. Taskiq runs ``pre_execute`` in registration order and
    ``post_execute`` in reverse, so a middleware registered after this one that
    raises in its own ``pre_execute`` skips this one's ``post_execute``: the
    scope stays open and its teardowns never run.

    There is no counterpart that spans the broker's lifetime. Taskiq's
    ``startup`` and ``shutdown`` hooks run in different asyncio tasks, so a
    publication opened in one cannot be undone in the other —
    `depin.Host.activated()` raises ``ValueError: Token was created in a
    different Context``. Singletons need no such counterpart: they are cached on
    the container itself, so every message shares them.

    Args:
        container: The frozen container to host for the duration of each
            message.

    Raises:
        ExceptionGroup: One or more teardowns failed when the message's scope
            closed. Every failure is included; one does not hide another.

    Example:
        Declare the message as a scoped value, then register the middleware on
        the broker after every other one::

            di = Container().scope_value(TaskiqMessage).bind(Report, scope=Scope.SCOPED).freeze()

            broker = InMemoryBroker().with_middlewares(SimpleRetryMiddleware(), MessageScope(di))

        ``Report`` then declares a ``TaskiqMessage`` parameter and is built once
        per message, against the message being executed.
    """

    def __init__(self, container: FrozenContainer) -> None:
        super().__init__()
        self._host = Host(container)

    @override
    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Open the message's scope, seed the message into it, and hand the message on.

        Args:
            message: The message about to be executed.

        Returns:
            The message it was given, unmodified. Taskiq threads the return
            value of each ``pre_execute`` into the next one and finally into the
            task body, so returning anything else replaces the message.
        """
        async with AsyncExitStack() as stack:
            frame = await stack.enter_async_context(self._host.ascope())
            frame.provide(TaskiqMessage, message)
            _message_scope.set(stack.pop_all())
        return message

    @override
    async def post_execute(self, message: TaskiqMessage, result: TaskiqResult[object]) -> None:
        """Close the message's scope, running its teardowns and undoing the publication.

        Does nothing when no scope is open in this context, which is what a
        message whose ``pre_execute`` never ran looks like.

        Args:
            message: The message that finished.
            result: The outcome Taskiq recorded for it, successful or failed.
        """
        stack = _message_scope.get()
        if stack is None:
            return
        _message_scope.set(None)
        await stack.aclose()
