# depin

Type-first dependency injection for Python 3.12+.

Declare bindings on a `Container`, call `freeze()` to validate the graph, then
resolve from the immutable `FrozenContainer` it returns. Resolution is driven by
type hints; `Protocol` and `Annotated` are first-class, and the core has zero
runtime dependencies.

- New here? Start with the [tutorial](tutorial/first-injection.md).
- Need a specific recipe? See the [how-to guides](how-to/index.md).
- Curious how it works? Read the [explanation](explanation/index.md).
- Looking up a symbol? Browse the [API reference](reference/index.md).

!!! note
    This site is being built out. The full narrative guides land in a later
    content pass; the API reference below is complete and generated from the
    source docstrings.
