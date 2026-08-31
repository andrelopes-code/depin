"""A plugin point: several handlers gathered under one collection.

Run with ``python -m examples.collections.main``.
"""

from typing import Protocol

from depin import Container, FrozenContainer


class Handler(Protocol):
    def handle(self, event: str) -> str: ...


class EmailHandler:
    def handle(self, event: str) -> str:
        return f'emailed: {event}'


class SmsHandler:
    def handle(self, event: str) -> str:
        return f'texted: {event}'


class WebhookHandler:
    def handle(self, event: str) -> str:
        return f'posted: {event}'


class Dispatcher:
    """Fans one event out to every handler currently plugged into the collection."""

    def __init__(self, handlers: list[Handler]) -> None:
        self.handlers = handlers

    def dispatch(self, event: str) -> list[str]:
        return [handler.handle(event) for handler in self.handlers]


def build() -> FrozenContainer:
    return (
        Container()
        .bind(EmailHandler)
        .bind(SmsHandler)
        .bind(WebhookHandler)
        .collect(Handler, [EmailHandler, SmsHandler, WebhookHandler])
        .bind(Dispatcher)
        .freeze()
    )


def main() -> None:
    di = build()
    for outcome in di[Dispatcher].dispatch('order.shipped'):
        print(outcome)

    print(di.explain(list[Handler]))


if __name__ == '__main__':
    main()
