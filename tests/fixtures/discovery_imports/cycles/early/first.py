"""Cycle module that binds its public value after importing its peer."""

from . import second

cycle_peer = second
ready = object()
