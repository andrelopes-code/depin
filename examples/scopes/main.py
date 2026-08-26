"""Scoped lifetimes: one instance per unit of work, torn down when the work ends.

Run with ``python -m examples.scopes.main``.
"""

from collections.abc import Generator

from depin import Container, FrozenContainer, Scope

AUDIT: list[str] = []


class Connection:
    def __init__(self, pool: 'Pool') -> None:
        self.pool = pool


class Pool:
    """A singleton: built once, shared by every unit of work."""

    def __init__(self) -> None:
        AUDIT.append('pool created')


class UnitOfWork:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def run(self, label: str) -> str:
        return f'{label}@{id(self.connection):x}'


def checkout(pool: Pool) -> Generator[Connection]:
    """Scoped provider: one connection per scope, returned to the pool on exit."""
    AUDIT.append('connection checked out')
    connection = Connection(pool)
    yield connection
    AUDIT.append('connection returned')


def build() -> FrozenContainer:
    return (
        Container()
        .bind(Pool, scope=Scope.SINGLETON)
        .bind(checkout, scope=Scope.SCOPED)
        .bind(UnitOfWork, scope=Scope.SCOPED)
        .freeze()
    )


def main() -> None:
    di = build()

    for label in ('first', 'second'):
        # Each scope gets its own Connection and UnitOfWork; the Pool is shared.
        with di.scope():
            print(di[UnitOfWork].run(label))

    # A nested scope reuses the outer scope's instances rather than rebuilding
    # them. Open sibling scopes when you want independent ones.
    with di.scope():
        outer = di[Connection]
        with di.scope():
            assert di[Connection] is outer

    print(AUDIT)


if __name__ == '__main__':
    main()
