"""`Provider.configure()` rejects a health check for an unrelated type."""

from depin import provider


class Service: ...


class Other: ...


def check(other: Other) -> bool:
    return bool(other)


def main() -> None:
    _ = provider(Service).configure(check=check)
