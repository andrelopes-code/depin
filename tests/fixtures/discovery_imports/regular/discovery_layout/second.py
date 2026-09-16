"""Second explicitly imported regular-package provider."""

from depin import Catalog, provider


class Second: ...


second_catalog = Catalog(__name__, provider(Second))
