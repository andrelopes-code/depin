"""Second half of a supported explicit import cycle."""

from depin import Catalog, provider

from . import first


class Second: ...


second_declaration = provider(Second)
second_catalog = Catalog(__name__, second_declaration)


def observed_first() -> type[object]:
    return first.First


def observed_declaration() -> object:
    return first.first_declaration
