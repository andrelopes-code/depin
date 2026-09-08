# Cached and scoped synchronous instructions

This slice extends the accepted dense synchronous instruction program across
singleton and scoped providers. Each compiled operation carries its lifetime;
the executor performs claim-or-join through the existing `ScopeFrame` stores,
locks, and construction-context tracking. Values supplied directly and through
`scope_value()` are operations in the same immutable table.

The recurring warm root lookup remains on the existing direct cache path. A
cold deep root enters the instruction program, and every cached dependency then
claims, joins, publishes, or aborts through a runtime owned by the frozen
container. Active overrides and frame-sensitive defaults still select the
iterative executor.

## Decision diagnostics

Seven-repeat `timeit` medians compare this tree with `48fa33b`, the accepted
complete-call instruction runtime. Cold measurements reset the singleton cache
or open a fresh scope before resolving a 1,000-provider linear chain. Warm
measurements resolve the already-cached deepest key inside an existing
container or scope.

| Path | `48fa33b` | This slice | Change |
| --- | ---: | ---: | ---: |
| Cold singleton chain | 5,781.874 us | 4,402.904 us | -23.85% |
| Warm singleton root | 1.731 us | 1.845 us | +6.59% |
| Cold scoped chain | 6,383.748 us | 4,391.337 us | -31.21% |
| Warm scoped root | 1.828 us | 1.916 us | +4.82% |

The warm paths deliberately do not enter the new program. Their movements are
below the normal 10% diagnostic boundary. The cold paths remove plan and
lifetime dispatch from every constructed node while retaining the same cache
synchronisation.

The published `freeze_a_chain_of_1000` workload was measured in five paired,
alternating base/head processes. Median samples were 37.475 and 39.863
milliseconds, and the median paired change was +5.07%, below its 8% budget.
The positional-contract compiler avoids temporary name and dependency
containers for the dominant zero- and one-argument forms; this keeps the added
executable plan inside the existing startup budget.

## Call and memory diagnostics

One cold singleton resolution under `sys.setprofile` reduced Python calls from
17,007 to 11,016 (-35.23%). With the frozen containers constructed before
`tracemalloc` began, retained bytes after the cold resolution moved from
208,936 to 138,536 (-33.69%), and peak traced bytes moved from 430,864 to
304,620 (-29.30%). The compiled representation itself remains one operation
per provider and one integer edge per dependency; it adds no per-root expanded
schedule.

## Concurrency and failure recovery

Claim ownership is registered before `begin()` returns and remains on the
executor's LIFO cleanup stack until publication completes. Both publication and
abort reset the construction `ContextVar` in `finally`. The compiled runtime
requests atomic follower signalling from `ScopeFrame` after its lock is
released; the default `ScopeFrame` contract for the existing executors remains
unchanged.

Fault-injection tests cover interruption immediately after a root claim,
provider failure followed by retry, recursive resolution, and interruption
before publication with a follower already blocked. Removing the abort signal
from the interrupted-publication path makes the follower test fail with a live
thread and time out; restoring it makes the test pass. A critical concurrency
review reproduced root, dependency, and publication interruptions and found no
remaining flight or construction context.

Twenty-eight focused instruction tests pass. The broader cache, scope,
iterative, thread-safety, and free-threading selection passes 140 tests with six
free-threaded-only skips on the normal interpreter. The complete benchmark
contract suite passes 155 tests, and all seven published-benchmark seed checks
pass.

This slice is a GO. Synchronous resource ownership remains on the existing
executor until the next phase; asynchronous execution remains a later,
separately typed phase.
