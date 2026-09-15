"""Completed local catalogue available before the partial import fails."""

from depin import Catalog, provider


class Partial: ...


partial_declaration = provider(Partial)
partial_catalog = Catalog(__name__, partial_declaration)
