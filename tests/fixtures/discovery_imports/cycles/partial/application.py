"""Composition root that publishes only after every explicit import succeeds."""

from depin import Manifest

from . import failure, state

if state.active:
    manifest = Manifest(__name__, failure.catalog)
    state.published_manifest = manifest
    state.receiver.include(manifest)
