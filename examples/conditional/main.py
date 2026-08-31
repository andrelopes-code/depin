"""A binding chosen by a predicate over settings, and a binding switched off entirely.

Run with ``python -m examples.conditional.main``.
"""

from dataclasses import dataclass
from typing import override

from depin import Container, FrozenContainer


@dataclass
class Settings:
    environment: str
    use_metrics: bool


class Store:
    def get(self) -> str:
        raise NotImplementedError


class PostgresStore(Store):
    @override
    def get(self) -> str:
        return 'pg'


class MemoryStore(Store):
    @override
    def get(self) -> str:
        return 'mem'


class Metrics:
    def __init__(self) -> None:
        self.events: list[str] = []

    def record(self, event: str) -> None:
        self.events.append(event)


class Checkout:
    def __init__(self, store: Store, metrics: Metrics | None) -> None:
        self.store = store
        self.metrics = metrics

    def complete(self) -> str:
        if self.metrics is not None:
            self.metrics.record('checkout.completed')
        return self.store.get()


def build(settings: Settings) -> FrozenContainer:
    return (
        Container()
        .bind(PostgresStore, provides=Store, when=lambda: settings.environment == 'production')
        .bind(MemoryStore, provides=Store, when=lambda: settings.environment != 'production')
        .bind(Metrics, when=settings.use_metrics)
        .bind(Checkout)
        .freeze()
    )


def main() -> None:
    di = build(Settings(environment='development', use_metrics=False))
    checkout = di[Checkout]

    # The predicate over settings.environment picked MemoryStore; no Metrics
    # binding entered the plan, so Checkout received None for it instead of
    # failing to resolve.
    print(checkout.complete())
    print('metrics:', checkout.metrics)

    print(di.explain(Metrics))


if __name__ == '__main__':
    main()
