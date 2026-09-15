"""Provider from the first namespace-package portion."""

from depin import Catalog, provider


class First: ...


first_catalog = Catalog(__name__, provider(First))
