"""Manifest explicitly composing named namespace-package modules."""

from typing import TYPE_CHECKING

from depin import Manifest

if TYPE_CHECKING or not __package__:
    from tests.fixtures.discovery_imports.namespace.portion_a.discovery_namespace.first import first_catalog
    from tests.fixtures.discovery_imports.namespace.portion_b.discovery_namespace import trap
    from tests.fixtures.discovery_imports.namespace.portion_b.discovery_namespace.second import second_catalog
else:
    from . import trap
    from .first import first_catalog
    from .second import second_catalog

manifest = Manifest(__name__, first_catalog, second_catalog, trap.trapped_catalog)
