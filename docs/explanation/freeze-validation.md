# What freeze() validates

The checks `Container.freeze()` runs before anything is constructed: missing providers,
cycles, duplicates, captive dependencies, and async/sync mismatches.

!!! note
    Full discussion coming in the content pass. See the [Container reference](../reference/container.md).
