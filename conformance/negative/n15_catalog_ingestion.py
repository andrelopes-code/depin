"""`Registry.include()` rejects a bare `Catalog` binding source."""

from depin import Catalog, Registry, provider


class Service: ...


def main() -> None:
    catalog = Catalog(__name__, provider(Service))
    _ = Registry().include(catalog)
