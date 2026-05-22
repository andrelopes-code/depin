from typing import Annotated

from depin import Container, FrozenContainer, Scope, Token

db_url: Token[str] = Token[str]('db.url')


class Database:
    def __init__(self, url: str) -> None:
        self.url = url


def make_db(url: Annotated[str, db_url]) -> Database:
    return Database(url)


class UserRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def all(self) -> list[str]:
        return ['ana', 'bia']


def build() -> FrozenContainer:
    return (
        Container()
        .value(db_url, 'postgres://example')
        .bind(make_db, scope=Scope.SINGLETON, provides=Database)
        .bind(UserRepo, scope=Scope.SINGLETON)
        .freeze()
    )


def main() -> None:
    di = build()
    repo = di[UserRepo]
    print(repo.all())


if __name__ == '__main__':
    main()
