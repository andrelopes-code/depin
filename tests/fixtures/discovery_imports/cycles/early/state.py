"""Deterministic state for the early-access import cycle fixture."""


class EarlyCycleError(Exception): ...


active: bool = False
cause = LookupError('first.ready is not bound')
