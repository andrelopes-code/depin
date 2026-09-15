"""First half of a supported explicit import cycle."""

from depin import Catalog, Manifest, provider


class First: ...


first_declaration = provider(First)
first_catalog = Catalog(__name__, first_declaration)

from . import second  # noqa: E402 - the local catalog must be bound before the supported cycle starts.

manifest = Manifest(__name__, first_catalog, second.second_catalog)
