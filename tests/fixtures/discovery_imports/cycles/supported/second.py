"""Second half of a supported explicit import cycle."""

from depin import Catalog, provider


class Second: ...


second_declaration = provider(Second)
second_catalog = Catalog(__name__, second_declaration)

from . import first  # noqa: E402 - the local catalog must be bound before the supported cycle starts.


def observed_first() -> type[object]:
    return first.First


def observed_declaration() -> object:
    return first.first_declaration
