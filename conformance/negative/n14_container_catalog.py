"""`Container` rejects a bare `Catalog` binding source."""

from depin import Catalog, Container, provider


class Service: ...


def main() -> None:
    catalog = Catalog(__name__, provider(Service))
    _ = Container(catalog)
