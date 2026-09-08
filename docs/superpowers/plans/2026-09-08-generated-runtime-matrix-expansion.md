# Generated runtime matrix expansion plan

**Outcome:** Stopped after Task 1. Namespace sharing succeeded, but executable
storage remained superlinear because every root still owns duplicated nested
bytecode. The proposal records this expansion as a NO-GO and selects the dense
instruction complement. Tasks 2 through 6 below are retained as the rejected
route's original acceptance criteria, not active work.

**Goal:** Expand the accepted generated synchronous transient representation across the proposal's runtime matrix without losing its measured latency/allocation gains or the existing interpreter's lifecycle, concurrency, override, and deep-graph guarantees.

**Accepted base:** security-hardened revision `2ea58f5`, the complete `c196d7c` paired matrix, and the focused `2ea58f5` hardening dataset retained in `benchmarks/results/2026-09-08-generated-sync-functions/`.

**Method:** Land one independently measurable runtime slice at a time. Every slice starts with differential RED tests, retains the interpreter as its control/fallback, and is removed if it fails correctness or an existing performance budget. Budgets are never widened to admit a slice.

### Task 1: Deduplicate executable storage and measure eligible retention

- Share immutable provider namespaces across generated programs without changing generated call expressions or runtime routing.
- Preserve the hard compiler budgets for shared DAG expansion and cumulative source size; add a retained-memory workload for an adversarial shared DAG.
- Add a deterministic retained-memory workload for generated transient chains at 20, 100, and 160 providers; report executable bytes per provider and total retained bytes.
- Require linear retained growth across the bounded range, unchanged 12-block/1,224-byte transient allocation evidence, and no latency regression outside the existing interval.

Result: one provider namespace was shared across all programs, but executable
bytes were 12,120, 132,440, and 298,280 at 20, 100, and 160 providers. The 1.54
growth exponent failed the linear requirement. Runtime and freeze diagnostics
remained inside the accepted result, so namespace sharing stays while broader
function generation stops.

### Task 2: Encode the complete synchronous call contract

- Extend the immutable execution model with explicit positional and keyword argument slots captured during provider inspection; never interpolate user parameter names into source.
- Add differential coverage for positional-or-keyword, keyword-only, defaults, optional dependencies, tagged dependencies, callable wrappers, aliases, collections, decorators, and factory exceptions.
- Generate only shapes whose exact call contract is represented; keep every other shape on the interpreter.
- Carry stable key, tag, and dependency-chain metadata in the executable model so provider failures do not collapse into an opaque generated frame.
- Measure each newly eligible slice before continuing.

### Task 3: Add cached and scoped execution without weakening concurrency

- Generate leaf executors that enter the existing singleton/scoped claim-or-join and teardown machinery rather than replacing it.
- Prove cold, warm, failing, recursive, threaded, and free-threaded cache invariants with the real `FrozenContainer`; show concurrency tests fail when the guard is removed.
- Keep cached/no-override work at or below the accepted baseline and retain all current contention semantics.

### Task 4: Add lifecycle-owning synchronous shapes

- Generate sync generator and context-manager construction around the existing teardown records and sinks.
- Prove LIFO teardown, partial-construction cleanup, repeated close, and `ExceptionGroup` behavior differentially.
- Measure scope entry/exit, resource resolution, allocations, and retained memory before accepting the slice.

### Task 5: Add asynchronous execution

- Generate coroutine, async-generator, and async-context-manager executors from the same immutable slot model.
- Preserve task-local scopes, async single-flight, cancellation, teardown ordering, and the 1,000-provider async iterative path.
- Run differential sync/async matrices and application-tier FastAPI workloads before accepting async generation.

### Task 6: Decide the hybrid runtime

- Compare the expanded generated representation with a dense typed instruction program on deep graphs, mixed-lifetime DAGs, active overrides, startup, traceback quality, executable size, and every published benchmark contract.
- Select generated functions alone only if they pass the full matrix. Otherwise retain them as a shallow leaf fast path and use the instruction program for deep or mixed graphs.
- Update the proposal with complete paired evidence, tighten budgets only from identical-code calibration, and write the migration implementation plan for the selected hybrid.
