"""A service that works with or without a metrics sink.

Run with ``python -m examples.optional_dependencies.main``.
"""

from depin import Container, FrozenContainer


class MetricsSink:
    def __init__(self) -> None:
        self.events: list[str] = []

    def record(self, name: str) -> None:
        self.events.append(name)


class Checkout:
    """Completes an order, recording it when a metrics sink happens to be wired in."""

    def __init__(self, metrics: MetricsSink | None) -> None:
        self.metrics = metrics

    def complete(self, order_id: str) -> str:
        if self.metrics is not None:
            self.metrics.record(order_id)
        return f'order {order_id} completed'


def build(with_metrics: bool) -> FrozenContainer:
    container = Container()
    if with_metrics:
        container = container.bind(MetricsSink)
    return container.bind(Checkout).freeze()


def main() -> None:
    unmetered = build(with_metrics=False)
    print(unmetered[Checkout].complete('A1'))
    print('metrics sink:', unmetered[Checkout].metrics)

    metered = build(with_metrics=True)
    print(metered[Checkout].complete('A2'))
    print('recorded events:', metered[MetricsSink].events)


if __name__ == '__main__':
    main()
