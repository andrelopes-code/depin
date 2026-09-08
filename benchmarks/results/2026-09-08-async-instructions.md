# Asynchronous instructions

This slice adds a separately typed asynchronous instruction executor for deep
plans. It shares the immutable synchronous operation types for synchronous
providers, but its execution loop has dedicated coroutine, async-generator, and
async-context-manager operations. The synchronous loop has no event-loop,
awaitability, or async-shape branch.

Cached operations claim and publish through the existing `ScopeFrame`. A
cancelled or failed owner aborts every outstanding claim in reverse order and
wakes its joiners. Async resources register their teardown immediately after
entry and before cache publication, preserving the existing ownership and LIFO
contracts. Active overrides and live-scope roots that could consume a supplied
value retain the explicit-stack fallback.

## Decision diagnostics

Seven-repeat `timeit` medians compare this tree with `f04e458`, the accepted
synchronous-resource instruction runtime. Each diagnostic graph has one async
provider followed by 999 synchronous consumers. The resource row uses an async
generator at the leaf and drains a new scope after every resolution.

| Path | `f04e458` | This slice | Change |
| --- | ---: | ---: | ---: |
| Async transient graph | 3,323.457 us | 923.730 us | -72.21% |
| Cold async singleton graph | 7,337.797 us | 5,476.476 us | -25.37% |
| Async scoped cycle | 8,111.153 us | 5,439.641 us | -32.94% |
| Async resource cycle | 8,056.404 us | 5,498.809 us | -31.75% |
| Freeze async graph | 64,481.229 us | 67,718.445 us | +5.02% |

One cold singleton resolution under `sys.setprofile` reduced Python calls from
25,057 to 17,072 (-31.87%). With both containers frozen before tracing,
retained bytes fell from 145,368 to 75,088 (-48.35%) and peak traced bytes fell
from 441,348 to 307,280 (-30.38%). The async program's counted shallow storage
was 160,352 bytes for 1,000 operations. A sync-only deep plan creates only the
async program wrapper and reuses the synchronous operation tuple, root map, and
frame-sensitive set by identity.

The published shallow `resolve_an_async_singleton` path remains on its existing
executor. Five alternating local processes measured base and head medians of
18.162 and 17.870 microseconds, with a -1.03% median paired change, inside its
5% budget. The complete published matrix remains the final-hybrid gate rather
than being inferred from these slice diagnostics.

## Correctness evidence

Seven focused tests force coroutine, async-generator, context-manager,
decorator, alias, collection, contention, and cancellation roots through the
new executor. They also prove override fallback and immutable sharing for
sync-only plans. The existing 1,000-provider, concurrency, generator, and
context-manager selection passes 19 tests.

The cancellation test was mutation-checked: removing the abort signal left its
joiner blocked until an external five-second timeout exited with status 124;
restoring the signal made the test pass. A critical concurrency review also
reproduced interruption after claim acquisition, interruption before
publication with a waiting joiner, and cancellation with nested claims. It
found no Critical or Important issue in claim ownership, token balance,
teardown registration, or LIFO abort behavior.

This slice is a GO. The final phase runs the complete differential and
performance matrix, then removes only production fallback code whose behavior
is fully represented by the selected hybrid.
