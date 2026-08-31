"""A wrapper stack over one binding, and what the graph says about it.

Run with ``python -m examples.decoration.main``.
"""

from typing import Protocol

from depin import Container, FrozenContainer

LOG: list[str] = []
READS: list[str] = []


class Store(Protocol):
    def get(self, key: str) -> str: ...


class SqlStore:
    """The registered binding. Every call it receives reaches the backing store."""

    def get(self, key: str) -> str:
        READS.append(key)
        return f'row-{key}'


class Cached:
    """Wraps `Store` and serves a repeated key from a local cache."""

    def __init__(self, inner: Store) -> None:
        self.inner = inner
        self._cache: dict[str, str] = {}

    def get(self, key: str) -> str:
        if key not in self._cache:
            self._cache[key] = self.inner.get(key)
        return self._cache[key]


class Logged:
    """Wraps `Cached` and records every call, cache hit or miss alike."""

    def __init__(self, inner: Store) -> None:
        self.inner = inner

    def get(self, key: str) -> str:
        LOG.append(key)
        return self.inner.get(key)


class Page:
    def __init__(self, store: Store) -> None:
        self.store = store

    def render(self, key: str) -> str:
        return self.store.get(key)


def build() -> FrozenContainer:
    return (
        Container().bind(SqlStore, provides=Store).decorate(Store, Cached).decorate(Store, Logged).bind(Page).freeze()
    )


def main() -> None:
    LOG.clear()
    READS.clear()
    di = build()
    page = di[Page]

    # Logged wraps Cached wraps SqlStore: every render is logged, but the
    # repeated read for 'a' never reaches SqlStore a second time.
    print(page.render('a'))
    print(page.render('a'))
    print(page.render('b'))

    print('logged calls:', LOG)
    print('backing reads:', READS)

    print(di.explain(Store))


if __name__ == '__main__':
    main()
