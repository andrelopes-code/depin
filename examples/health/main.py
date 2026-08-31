"""Declaring how to verify a binding's value, and reading the report.

Run with ``python -m examples.health.main``.
"""

from depin import Container, FrozenContainer, ProviderKey


class Database:
    """Reachable in this example; its check always passes."""

    def __init__(self) -> None:
        self.connected = True

    def ping(self) -> bool:
        return self.connected


class Cache:
    """Down in this example, so its check fails without raising."""

    def __init__(self) -> None:
        self.connected = False

    def ping(self) -> bool:
        return self.connected


def check_database(db: Database) -> bool:
    return db.ping()


def check_cache(cache: Cache) -> bool:
    return cache.ping()


def build() -> FrozenContainer:
    return Container().bind(Database, check=check_database).bind(Cache, check=check_cache).freeze()


def _name(key: ProviderKey) -> str:
    """Every key checked here is a plain class; narrowing to `type` is enough
    to print its name out of `ProviderKey`'s wider union."""
    return key.__qualname__ if isinstance(key, type) else str(key)


def main() -> None:
    di = build()

    # checks() describes what was declared; it resolves and runs nothing.
    print('declared:', [_name(check.key) for check in di.checks()])

    report = di.health()
    print('healthy:', report.healthy)
    for result in report.results:
        print(_name(result.key), result.healthy)


if __name__ == '__main__':
    main()
