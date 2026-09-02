"""The complete ordered competitor comparison inventory."""

from benchmarks.comparison.inventory import build as _build

WORKLOADS = _build()

del _build

__all__ = ('WORKLOADS',)
