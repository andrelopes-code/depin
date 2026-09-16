"""Cycle module that can attempt access before its peer binds a value."""

from . import first, state

if state.active and not hasattr(first, 'ready'):
    raise state.EarlyCycleError('cycle accessed first.ready before first.ready existed') from state.cause
