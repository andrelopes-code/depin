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


def _load_adapters() -> tuple[Adapter, ...]:
    from benchmarks.comparison.adapters.dependency_injector import ADAPTER as dependency_injector_adapter
    from benchmarks.comparison.adapters.dishka import ADAPTER as dishka_adapter
    from benchmarks.comparison.adapters.svcs import ADAPTER as svcs_adapter
    from benchmarks.comparison.adapters.wireup import ADAPTER as wireup_adapter

    return dependency_injector_adapter, dishka_adapter, wireup_adapter, svcs_adapter


ADAPTERS = _load_adapters()
