"""Building every singleton at boot, and what warmup leaves alone.

Run with ``python -m examples.warmup.main``.
"""

from depin import Container, FrozenContainer, GraphNode, Scope

BUILT: list[str] = []


class Config:
    """A singleton warmup builds before the first request asks for it."""

    def __init__(self) -> None:
        BUILT.append('Config')


class Pool:
    """A second singleton, depending on the first, built in the same pass."""

    def __init__(self, config: Config) -> None:
        BUILT.append('Pool')
        self.config = config


class Session:
    """Scoped, so warmup never builds it: it belongs to a scope that opens per request."""

    def __init__(self) -> None:
        BUILT.append('Session')


def build() -> FrozenContainer:
    return Container().bind(Config).bind(Pool).bind(Session, scope=Scope.SCOPED).freeze()


def _names(nodes: tuple[GraphNode, ...]) -> list[str]:
    """`GraphNode.key` is a union of every key shape; every binding here is a
    plain class, so narrowing to `type` renders its name, and any other key
    shape still renders through `str` rather than being dropped."""
    return [node.key.__qualname__ if isinstance(node.key, type) else str(node.key) for node in nodes]


def main() -> None:
    BUILT.clear()
    di = build()

    report = di.warmup()
    print('constructed:', _names(report.constructed))
    print('cached:', _names(report.cached))
    print('built so far:', BUILT)

    # The second call finds both singletons already built; Session still isn't
    # among them because it has no boot-time instance to build.
    second = di.warmup()
    print('second call constructed:', _names(second.constructed))

    with di.scope():
        _ = di[Session]
    print('built after a scope opened:', BUILT)


if __name__ == '__main__':
    main()
