"""Inspecting a validated graph: the resolution tree and the two exports.

Run with ``python -m examples.graph_diagnostics.main``.
"""

from collections.abc import Generator

from depin import Container, FrozenContainer, Scope


class Settings:
    def __init__(self) -> None:
        self.dsn = 'postgres://example'


class Pool:
    def __init__(self, settings: Settings) -> None:
        self.dsn = settings.dsn


class Connection:
    def __init__(self, pool: Pool) -> None:
        self.pool = pool


def connection(pool: Pool) -> Generator[Connection]:
    conn = Connection(pool)
    yield conn


class Repo:
    def __init__(self, connection: Connection, settings: Settings) -> None:
        self.connection = connection
        self.settings = settings


def build() -> FrozenContainer:
    return (
        Container()
        .bind(Settings)
        .bind(Pool)
        .bind(connection, scope=Scope.SCOPED)
        .bind(Repo, scope=Scope.SCOPED)
        .freeze()
    )


def main() -> None:
    di = build()
    print(di.explain(Repo))
    print()
    print(di.graph().mermaid())


if __name__ == '__main__':
    main()
