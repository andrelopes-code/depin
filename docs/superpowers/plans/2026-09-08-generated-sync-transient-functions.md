# Generated synchronous transient functions experiment

**Goal:** Test whether one generated Python function per eligible shallow synchronous transient resolution keeps the closure experiment's latency win without its allocation and unrelated hot-path regressions.

**Baseline:** `d5d8d03` records the closure NO-GO and contains no prototype runtime code.

**Safety boundary:** Generated source contains only project-owned identifiers, integer namespace indexes, calls, parentheses, and commas. Provider objects live in a namespace tuple. User names, annotations, keys, tags, and representations are never interpolated into source.

### Task 1: Generate bounded resolver functions

**Files:** create `depin/_core/generated.py`; create `tests/unit/test_generated_resolution.py`.

- Add RED tests for a zero-dependency factory, a 20-provider positional chain, tagged dependencies, and ineligible keyword-only/default/optional/cached/resource/async/deep providers.
- Compile only synchronous transient `FUNCTION` subgraphs whose parameters are all positional-or-keyword and whose dependencies are themselves eligible.
- Generate a single nested call expression per requested key. Keep provider objects in an immutable namespace tuple and return an immutable `Mapping[Ident, Program]`.
- Compile with a fixed synthetic filename and narrow the `exec` result without `Any`, `cast`, or suppressions.
- Verify focused tests, ruff, Basedpyright, and mypy.

### Task 2: Route only eligible transient resolutions

**Files:** modify `depin/_core/frozen.py`, `depin/_core/overrides.py`, and `tests/unit/test_generated_resolution.py`.

- Store generated programs only for plans below the recursive-depth threshold.
- After the existing root lookup selects a transient spec, use a generated program only when that identity is compiled and the override stack is empty.
- Do not add an override-stack read or generated-program lookup to singleton, scoped, async, resource, alias, collection, decoration, or deep iterative paths.
- Add route spies proving generated execution and interpreter fallback for unrelated, nested, and real dependency overrides.
- Preserve the 1,000-provider sync and async depth guarantees.

### Task 3: Prove parity and the allocation hypothesis

**Files:** modify `tests/unit/test_generated_resolution.py` only unless a test proves a production defect.

- Compare generated and forced-interpreter results, construction logs, factory exception type/message, tagged dependencies, repeated resolution, and transient identity.
- Run neighboring resolution, override, provider-contract, workload-equivalence, and depth suites.
- Require 100% line and branch coverage of `depin._core.generated`.
- Run the repository gates in order.

### Task 4: Measure and decide

- Quick-measure `resolve_a_transient_chain` against the recorded 34.125 microsecond baseline.
- Measure calls and deterministic allocations before running the full pair harness. Stop early if the chain improves by less than 10%, allocations exceed 52 blocks/4,904 bytes/5,688 peak bytes, or any work is added to cached/no-override paths.
- Only after those checks pass, collect five paired repetitions against `d5d8d03` and apply existing budgets unchanged.
- GO requires a decisive >=10% transient-chain gain, no allocation/work regression, no unrelated workload regression, green depth guarantees, and bounded freeze/retained memory.
- On NO-GO, remove all prototype code/tests and record exact results in the proposal. On GO, retain the evidence and plan expansion across the full proposal matrix.

