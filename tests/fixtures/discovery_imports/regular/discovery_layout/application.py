"""Explicit regular-package manifest fixture."""

from depin import Manifest

from . import trap
from .first import first_catalog
from .second import second_catalog

manifest = Manifest(__name__, first_catalog, second_catalog, trap.trapped_catalog)
