# Synchronous resource instructions

This slice extends the dense synchronous program to generator and context-
manager providers. They are dedicated typed operations, not a fallback through
the generic construction dispatcher. Each operation reuses the compiled keyword
slots, validates the provider's runtime shape, opens it, and registers one
teardown record on the frame that owns its lifetime before the cache claim is
published.

The executor still appends teardown records in construction order. Existing
`ScopeFrame` drains reverse that list, so a decorator closes before the binding
it wraps and a resource closes before the dependency it consumed. Aliases and
collections remain non-owning operations; the resource target keeps its cache
and teardown.

## Decision diagnostics

Seven-repeat `timeit` medians compare this tree with `a616089`, the accepted
cached/scoped instruction runtime. The diagnostic graph has one synchronous
generator resource followed by 999 ordinary consumers. The singleton cycle
resets the prior cache and drains its resource before cold resolution. The
scoped cycle opens a fresh scope, resolves the deepest key, and drains the
resource on exit.

| Path | `a616089` | This slice | Change |
| --- | ---: | ---: | ---: |
| Cold singleton resource graph | 7,694.414 us | 5,234.384 us | -31.97% |
| Scoped resource cycle | 8,423.711 us | 5,287.776 us | -37.23% |
| Freeze resource graph | 65,436.966 us | 65,487.686 us | +0.08% |

One cold singleton resolution under `sys.setprofile` reduced Python calls from
27,025 to 17,032 (-36.98%). With both frozen containers built before tracing,
retained bytes fell from 145,368 to 74,976 (-48.42%), and peak traced bytes fell
from 511,328 to 304,964 (-40.36%).

The published shallow `resolve_a_sync_resource_with_teardown` guard remains on
its existing executor. Five alternating paired processes measured base and head
medians of 15.845 and 15.546 microseconds and a +0.50% median paired change,
inside its existing budget.

## Correctness evidence

Four focused tests force deep generator, context-manager, and generator-
decorator roots through instructions by replacing the iterative executor with a
failure sentinel. They verify singleton identity and exactly-once close, scoped
identity, dependency and decorator LIFO order, and interruption after a resource
opened but before its claim published. The interrupted resource retains its
teardown, the claim retries successfully, and final close drains both acquired
resources in reverse acquisition order.

The focused resource, teardown, reset, alias, decoration, instruction, and
thread-safety selection passes 110 tests. Ruff, Basedpyright, and mypy pass with
no diagnostics.

This slice is a GO. The next phase adds a separately typed asynchronous
instruction executor; the synchronous loop retains no event-loop or
awaitability branch per node.
