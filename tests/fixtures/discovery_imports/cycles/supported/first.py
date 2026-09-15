"""First half of a supported explicit import cycle."""

from depin import Catalog, Manifest, provider

from . import second


class First: ...


first_declaration = provider(First)
first_catalog = Catalog(__name__, first_declaration)
manifest = Manifest(__name__, first_catalog, second.second_catalog)
