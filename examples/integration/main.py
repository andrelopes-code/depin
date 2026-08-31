"""Hosting a container in a framework depin does not ship.

A job runner is the smallest host there is: it has a unit of work, an object of
its own to hand to providers, and a place to put setup and teardown. The same
four operations serve a web framework, a CLI, and a queue consumer.

Run with ``python -m examples.integration.main``.
"""

from collections.abc import Generator
from dataclasses import dataclass

from depin import Container, FrozenContainer, Host, Scope, hosted_container

LOG: list[str] = []


@dataclass(frozen=True, slots=True)
class Job:
    """The runner's own object, seeded into the scope it opens for each job."""

    name: str


class Metrics:
    """A singleton: one per process, outliving every job."""

    def __init__(self) -> None:
        self.completed = 0


class Workspace:
    """Scoped, with a teardown: one per job, cleaned up when the job ends."""

    def __init__(self, job: Job) -> None:
        self.job = job


def open_workspace(job: Job) -> Generator[Workspace]:
    LOG.append(f'open {job.name}')
    yield Workspace(job)
    LOG.append(f'close {job.name}')


def build() -> FrozenContainer:
    return Container().scope_value(Job).bind(Metrics).bind(open_workspace, scope=Scope.SCOPED).freeze()


class JobRunner:
    """The integration: it owns a `Host` and opens one scope per unit of work."""

    def __init__(self, container: FrozenContainer) -> None:
        self._host = Host(container)

    def run(self, name: str) -> str:
        with self._host.scope() as frame:
            frame.provide(Job, Job(name))
            return handle()


def handle() -> str:
    """A handler that carries no container reference, only the contract."""
    di = hosted_container()
    workspace = di.resolve(Workspace)
    metrics = di.resolve(Metrics)
    metrics.completed += 1
    return f'{workspace.job.name} (completed={metrics.completed})'


def main() -> None:
    LOG.clear()
    di = build()
    runner = JobRunner(di)

    print(runner.run('reindex'))
    print(runner.run('vacuum'))
    print('log:', LOG)

    # The singleton outlived both jobs; the workspaces did not.
    print('completed:', di[Metrics].completed)
    di.close()


if __name__ == '__main__':
    main()
