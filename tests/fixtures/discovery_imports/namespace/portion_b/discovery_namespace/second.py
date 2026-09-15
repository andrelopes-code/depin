"""Provider from the second namespace-package portion."""

from depin import Catalog, provider


class Second: ...


second_catalog = Catalog(__name__, provider(Second))
