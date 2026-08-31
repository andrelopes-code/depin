"""One instance under two names, and what the graph says about it.

Run with ``python -m examples.aliasing.main``.
"""

from typing import Protocol

from depin import Container, FrozenContainer


class Store(Protocol):
    def get(self, key: str) -> str: ...


class Cache(Protocol):
    def get(self, key: str) -> str: ...


class RedisStore:
    """Serves both roles in this application, and is built exactly once."""

    def __init__(self) -> None:
        self.reads: list[str] = []

    def get(self, key: str) -> str:
        self.reads.append(key)
        return f'value-for-{key}'


class Page:
    def __init__(self, store: Store, cache: Cache) -> None:
        self.store = store
        self.cache = cache

    def render(self) -> str:
        return f'{self.cache.get("head")} + {self.store.get("body")}'


def build() -> FrozenContainer:
    return Container().bind(RedisStore).alias(Store, to=RedisStore).alias(Cache, to=RedisStore).bind(Page).freeze()


def main() -> None:
    di = build()
    page = di[Page]

    print(page.render())

    # Two names, one object: the alias node caches nothing, so the cache
    # identity on both paths is RedisStore's own.
    print('same instance:', page.store is page.cache is di[RedisStore])
    print(di[RedisStore].reads)

    print(di.explain(Page))


if __name__ == '__main__':
    main()
