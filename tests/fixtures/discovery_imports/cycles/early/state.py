"""Deterministic state for the early-access import cycle fixture."""


class EarlyCycleError(Exception): ...


active = False
cause = LookupError('first.ready is not bound')
