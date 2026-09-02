"""The workload inventory: every tier, in one ordered tuple.

`WORKLOADS` is what the gate expects a result for, what the contract tests walk,
and what the published report renders. A workload that is not here is not
measured, and a measurement whose workload is not here is not published.

The tiers are kept in order — isolated, component, application, scaling —
because that is the order results are read in, and because a reader who reaches
an application figure should already have passed the isolated one it decomposes
into.

`application` imports `fastapi`, so importing this package requires the `bench`
or `dev` dependency group. Nothing under `tests/unit` imports it, which is what
keeps the free-threaded job free of framework dependencies.
"""

from benchmarks.contracts import Workload
from benchmarks.workloads import application, component, micro, resources, scale

WORKLOADS: tuple[Workload, ...] = (
    *micro.WORKLOADS,
    *component.WORKLOADS,
    *application.WORKLOADS,
    *resources.WORKLOADS,
    *scale.WORKLOADS,
)

_names = [workload.name for workload in WORKLOADS]
if len(_names) != len(set(_names)):
    duplicates = sorted({name for name in _names if _names.count(name) > 1})
    raise ValueError(f'duplicate workload names in the inventory: {", ".join(duplicates)}')
