"""First explicitly imported regular-package provider."""

from depin import Catalog, provider


class First: ...


FirstAlias = First
first_catalog = Catalog(__name__, provider(First))
