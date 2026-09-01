"""`depin.ext.taskiq`: one scope per message, installed as broker middleware.

`MessageScope` is a `taskiq.TaskiqMiddleware`, so the promise a consumer needs
is that it is accepted where the broker asks for one and that the container it
was built with is reachable from a task body through
`depin.hosted_container()`.

Requires the `taskiq` extra, so this file is checked in all-extras mode only.
"""

from taskiq import InMemoryBroker, TaskiqMiddleware

from depin import Container, FrozenContainer, hosted_container
from depin.ext.taskiq import MessageScope


class Database:
    def __init__(self) -> None:
        self.url = 'sqlite://'


class Report:
    def __init__(self, database: Database) -> None:
        self.database = database

    def summary(self) -> str:
        return self.database.url


def build() -> FrozenContainer:
    return Container().bind(Database).bind(Report).freeze()


def the_middleware_is_a_taskiq_middleware() -> None:
    _middleware: TaskiqMiddleware = MessageScope(build())


def the_middleware_installs_on_a_broker() -> None:
    broker = InMemoryBroker()
    _configured = broker.with_middlewares(MessageScope(build()))


async def a_task_body_reaches_the_hosted_container() -> None:
    report = hosted_container().resolve(Report)
    _summary: str = report.summary()
    _awaited: Report = await hosted_container().aresolve(Report)
