"""`Provider.configure()` rejects a tag that is not a string."""

from depin import provider


class Service: ...


def main() -> None:
    _ = provider(Service).configure(tag=42)
