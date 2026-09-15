"""`Provider.configure()` rejects an invalid condition."""

from depin import provider


class Service: ...


def main() -> None:
    _ = provider(Service).configure(when=42)
