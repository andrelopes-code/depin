# depin

Type-first dependency injection for Python 3.12+.

Declare bindings on a `Container`, call `freeze()` to validate the graph, then
resolve from the immutable `FrozenContainer` it returns. Resolution is driven by
type hints; `Protocol` and `Annotated` are first-class, and the core has zero
runtime dependencies.

See the [API reference](reference/index.md) for the full public API, generated
from the source docstrings.
