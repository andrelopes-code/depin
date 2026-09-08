# Dense instruction runtime plan

**Goal:** Add one linear immutable operation model that complements the bounded
generated transient fast path and can grow across the proposal's complete sync,
async, lifetime, override, and teardown matrix.

**Accepted base:** The security-bounded generated fast path through `52e0217`,
plus the namespace-sharing experiment that rejected broader source generation.

**Method:** Keep the interpreter as the differential oracle. Land one runtime
slice at a time, measure it before broadening eligibility, and retain the
generated path only where it remains both faster and bounded.

### Task 1: Prove the linear transient instruction model

- Compile `ResolutionPlan.order` into one tuple of immutable operations with
  integer dependency slots and an immutable key-to-index map.
- Execute a requested transient root with an explicit stack over operation
  indexes; do not store one transitive schedule per key and do not memoize
  transient dependencies.
- Start with exact synchronous function call contracts already proven safe by
  the generated compiler, while keeping every other shape on the interpreter.
- Add differential value, order, exception, tag, repeated-transient, deep-chain,
  and shared-DAG tests; prove stored operations and dependency slots grow
  linearly.
- Compare calls, allocations, latency, and retained bytes against both the
  interpreter and bounded generated path before integrating routing.

Result: GO. The model stores one operation and one dependency edge per provider
in a chain, resolves 1,000 providers without recursion, and is routed for deep
sync transient `resolve()` and `inject()` calls when no override is active. It
measured 724.930 microseconds against the iterative executor's 2,617.506 at
depth 1,000, with a +6.21% deep transient freeze cost. The 20-provider result
remained slower than generated functions, so shallow routing is unchanged.

### Task 2: Encode complete synchronous calls and overrides

- Add explicit positional and keyword slots for defaults, optional parameters,
  keyword-only parameters, aliases, collections, and decorators.
- Read override state once at the root and either execute an override-aware
  instruction path or fall back without changing nested override semantics.
- Carry stable key, tag, and dependency-chain metadata for actionable errors.

Result: GO. Immutable resolved/default/optional keyword slots and dedicated
alias and collection operations now cover teardown-free synchronous functions,
classes, decorators, aliases, and collections. Override state is read once at
the root and any active override falls back to the iterative executor. A root
whose subgraph contains an unbound default or optional also falls back inside a
live scope so frame-provided values retain precedence. A 256-provider
keyword-only chain improved from 704.564 to 430.698 microseconds (-38.87%),
while representation growth remained linear at a 0.976 exponent. The accepted
positional deep path remained within the 10% regression boundary.

### Task 3: Integrate singleton and scoped claims

Result: GO. Cached instructions use `ScopeFrame` as the sole cache,
synchronization, and teardown authority. Cold singleton and scoped graphs
improved by 23.85% and 31.21%; contention, recursive construction, failure,
interruption, and follower wakeup tests preserve the existing contract.

- Add operations that enter the existing cache claim-or-join and scope-frame
  machinery rather than duplicating locks or cache state.
- Differentially prove cold, warm, failing, recursive, threaded, and
  free-threaded behavior, including tests that fail when synchronization is
  removed.

### Task 4: Integrate lifecycle-owning shapes

- Add sync generator and context-manager operations using the current teardown
  records and sinks.
- Preserve partial-construction cleanup, LIFO order, repeated close, and grouped
  teardown failures.

Result: GO. Dedicated generator and context-manager operations improved the
1,000-provider singleton and scoped resource diagnostics by 31.97% and 37.23%,
while retaining exactly-once registration, partial-construction cleanup, and
reverse acquisition order.

### Task 5: Add the typed async executor

- Reuse the immutable operation tuple with a separate async execution loop for
  coroutine, async-generator, and async-context-manager operations.
- Preserve task-local scopes, async single-flight, cancellation, and the
  1,000-provider iterative guarantee without adding awaitability branches to
  the sync loop.

Result: GO. The separate async loop improved the 1,000-provider transient,
cold-singleton, scoped, and resource diagnostics by 72.21%, 25.37%, 32.94%,
and 31.75%. Mutation testing proves cancelled owners wake joiners; sync-only
plans share the existing immutable operation representation.

### Task 6: Select and simplify the final hybrid

- Run the complete differential matrix and every published benchmark contract.
- Keep generated functions only for the bounded slice where they beat the
  instruction executor materially; route every broader shape through the dense
  program.
- Remove interpreter production paths only after the executable model covers
  the matrix, diagnostics remain stable, and full paired evidence passes without
  wider budgets.

Result: partial GO, universal replacement NO-GO. A reviewed candidate routed
all shallow non-generated shapes through dense instructions, but the exact
published gates rejected it: request-shaped scope work rose from 88 to 97
calls, allocation blocks from 27 to 29, and a frozen 100-provider container
retained 78.15% more memory against a 2% budget. The candidate was removed.
The final hybrid keeps the bounded generated shallow path, dense deep sync and
async paths, and the existing shallow/dynamic fallbacks. No budget was widened.
