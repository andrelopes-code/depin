"""`Provider` cannot be constructed directly."""

from depin import Provider


class Service: ...


def main() -> None:
    Provider[Service]()
