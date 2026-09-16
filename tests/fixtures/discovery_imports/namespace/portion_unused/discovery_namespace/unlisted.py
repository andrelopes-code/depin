"""Provider in a namespace portion intentionally absent from the manifest."""

from depin import Catalog, provider


class Unlisted: ...


unlisted_catalog = Catalog(__name__, provider(Unlisted))
