"""`Provider.configure()` rejects an invalid provider key."""

from depin import provider


class Service: ...


def main() -> None:
    _ = provider(Service).configure(provides=42)
