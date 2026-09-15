"""Deterministic state observed across a partial import failure."""

from depin import Container, Manifest


class Baseline: ...


class PartialImportError(Exception): ...


active = False
cause = LookupError('partial fixture cause')
published_manifest: Manifest | None = None
receiver = Container().bind(Baseline)
