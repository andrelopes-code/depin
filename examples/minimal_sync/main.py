"""The smallest useful graph: a token, a factory, a class, and a teardown.

Run with ``python -m examples.minimal_sync.main``.
"""

from collections.abc import Generator
from typing import Annotated

from depin import Container, FrozenContainer, Scope, Token

db_url: Token[str] = Token[str]('db.url')


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.closed = False


class UserRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def all(self) -> list[str]:
        return ['ana', 'bia']


def open_database(url: Annotated[str, db_url]) -> Generator[Database]:
    """A provider that owns a resource yields it; the code after the yield is the teardown."""
    db = Database(url)
    yield db
    db.closed = True


def build() -> FrozenContainer:
    """Declare the graph and validate it. Nothing is constructed yet."""
    return (
        Container()
        .value(db_url, 'postgres://example')
        .bind(open_database, scope=Scope.SINGLETON)
        .bind(UserRepo, scope=Scope.SINGLETON)
        .freeze()
    )


def main() -> None:
    di = build()
    try:
        repo = di[UserRepo]
        print(repo.all())
        print(repo.db.url)
    finally:
        # Drains the singleton teardowns declared above. `aclose()` is the
        # counterpart for a graph that contains async providers.
        di.close()


if __name__ == '__main__':
    main()
