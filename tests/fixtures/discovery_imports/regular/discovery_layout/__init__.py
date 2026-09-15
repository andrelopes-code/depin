"""Regular-package fixture with explicit declarative reexports."""

from . import trap as _trap
from .application import manifest
from .first import First, FirstAlias
from .reexports import ReexportedFirst, reexported_manifest

getattr_calls = _trap.getattr_calls

__all__ = [
    'First',
    'FirstAlias',
    'ReexportedFirst',
    'getattr_calls',
    'manifest',
    'reexported_manifest',
]
