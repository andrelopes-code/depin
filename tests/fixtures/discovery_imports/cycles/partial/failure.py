"""Deterministic failure reached after a local catalogue is complete."""

from . import state
from .declarations import partial_catalog

catalog = partial_catalog

if state.active:
    raise state.PartialImportError('partial fixture import stopped') from state.cause
