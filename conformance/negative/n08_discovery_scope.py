"""`Provider.configure()` rejects a scope that is not a `Scope`."""

from depin import provider


class Service: ...


def main() -> None:
    _ = provider(Service).configure(scope='singleton')
