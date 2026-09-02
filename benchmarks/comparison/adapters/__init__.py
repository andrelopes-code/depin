"""Protocols shared by competitor benchmark adapters."""

from collections.abc import Sequence
from typing import Protocol

from benchmarks.comparison.contracts import Candidate, Competitor
from benchmarks.contracts import Workload


class Adapter(Protocol):
    """A pinned competitor implementation and its classification for every workload."""

    @property
    def competitor(self) -> Competitor: ...

    def candidates(self, workloads: Sequence[Workload]) -> tuple[Candidate, ...]: ...
