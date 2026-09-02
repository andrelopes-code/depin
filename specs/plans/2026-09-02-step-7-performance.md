# Step 7 — performance evidence and regression protection: implementation plan

Date: 2026-09-02

Derived from `specs/2026-09-02-step-7-performance-design.md`. Measurements come
from `specs/evidence/2026-09-02-step-7-performance-baseline.md` and are not
re-derived.

Release: one squash-merged pull request titled with `perf:`, which cuts 0.18.0.

## Global constraints

- `AGENTS.md` governs. No `# type: ignore`, no `typing.cast`, no `Any`, no
  swallowed exception, no separator comment, no comment restating code.
- The core keeps zero runtime dependencies. `benchmarks/harness/` is stdlib only.
- `benchmarks/` is not in the type-checker file lists today. Task 10 attempts
  adding it and records the outcome either way.
- Contract and equivalence tests go under `tests/integration/`, never
  `tests/unit/`, so the free-threaded job and `[tool.mutmut] also_copy` are
  untouched.
- No `>>>` in `docs/performance/`: every markdown file under `docs/` is collected
  as a doctest.
- `uv sync --all-extras --resolution lowest-direct` rewrites `uv.lock`. Check
  `git status` and restore with `git checkout -- uv.lock`.

## File structure

```
benchmarks/
  contracts.py            Claim, Implementation, Observation, Prepared, Workload  [done]
  graphs.py               existing builders, plus a layered-DAG generator
  budgets.toml            per-workload budgets, each with its justification
  seeds/                  the three seeded regressions, as patches
  results/<date>-<commit>/ the accepted dataset
  harness/
    environment.py        host, interpreter and dependency metadata
    reduce.py             pytest-benchmark JSON -> per-repetition aggregates
    stats.py              paired log-ratio, percentile bootstrap
    budgets.py            budget file, class floors, verdicts
    work.py               Python calls per operation
    memory.py             allocations and retained bytes per operation
    scaling.py            an operation's cost curve over sizes
    pairs.py              CLI: R counterbalanced repetitions of base and head
    gate.py               CLI: verdicts over two datasets
    report.py             CLI: dataset -> the published markdown tables
  workloads/
    __init__.py           the inventory; every tier registers into it
    micro.py              tier 1
    component.py          tier 2, including the error paths
    application.py        tier 3, FastAPI
    scale.py              tier 4
  test_latency.py         pytest-benchmark shells over the inventory
  test_diagnostics.py     existing, corrected
tests/integration/
  test_workload_contracts.py    every workload has a complete claim
  test_workload_equivalence.py  Observation equality, subject against baseline
  test_benchmark_harness.py     the harness's own unit tests
  test_performance_docs.py      the published page matches the dataset
docs/performance/               index, methodology, results, reproducing
```

## Harness API

Fixed here so the tasks can be built in parallel against it.

- `environment.capture() -> dict[str, object]`.
- `reduce.Aggregate` — frozen, slots: `name`, `rounds`, `minimum`, `median`,
  `mean`, `stddev`, `iqr`. `reduce.load(path) -> dict[str, Aggregate]`, raising
  `HarnessError` on a payload that is not an object, carries no `benchmarks`
  array, or carries an empty one.
- `stats.Paired` — frozen, slots: `ratio`, `low`, `high`, `n`.
  `stats.paired_ratio(base, head, *, seed, resamples=2000) -> Paired`, the
  statistic being the median of paired log ratios and the interval a percentile
  bootstrap over the paired differences.
- `budgets.Budget` — frozen, slots: `workload`, `metric`, `limit`, `noise`,
  `justification`. `budgets.load(path)` keyed by `(workload, metric)`, rejecting
  a limit below its noise class floor.
- `work.calls_per_operation(call, *, operations) -> int`.
- `memory.Allocation` — frozen, slots: `blocks`, `size`, `peak`.
  `memory.allocations_per_operation(...)`, `memory.retained(build) -> int`.
- `scaling.curve(build, sizes) -> dict[int, float]`.
- Exit codes for both CLIs: 0 pass, 1 regression, 2 malformed or misused, 3
  inconclusive.

## Task 1 — the harness

`benchmarks/harness/`, `benchmarks/budgets.toml`,
`tests/integration/test_benchmark_harness.py`.

The statistics, the budget rules, the malformed-input handling and the verdict
rule are the parts that gate a release, so they are developed test-first. The
tests must include: a known paired difference recovered from synthetic data; a
bootstrap interval that is reproducible from its seed; a budget below its class
floor rejected; every malformed-report shape rejected; and each of pass, fail and
inconclusive produced deliberately.

## Task 2 — tiers 1 and 2

`benchmarks/workloads/micro.py`, `component.py`, the layered-DAG generator in
`graphs.py`, and the two contract tests.

Every workload carries a direct-Python baseline that performs the same useful
work. Tier 2 adds what the suite has never covered: the failing-freeze path and
the missing-key `explain()` path, which is where both repaired costs live.

## Task 3 — tier 3

`benchmarks/workloads/application.py`; `fastapi` and `httpx` added to the `bench`
dependency group.

Two applications, sync and async, driven through `httpx.ASGITransport` in
process. Each paired with the same application wired explicitly. Startup measured
apart from per-request cost. Throughput reported with CPU time beside it.

## Task 4 — tier 4

`benchmarks/workloads/scale.py`. Curves over graph size, depth, fan-out,
collection size and teardown count, plus the error paths by size. The cold
resolution depth cliff at 332 is pinned by a test so it cannot move unnoticed.

## Task 5 — the two repairs

`depin/_core/graph.py`, `depin/_core/render.py`, one new `depin/_core/` module,
and their tests. Specified in full in the design under "The two repairs Step 7
owns". Developed test-first, with the Hypothesis differential test written before
the optimisation.

## Task 6 — the corrected existing cases

`test_diagnostics.py` gains an `explain()` case over a layered DAG, so the
subtree-elision guard is exercised. The decoration-resolution case is re-based
onto the same graph size as the cached-singleton case it compares itself with.
The async case gains its bare-coroutine baseline. Each correction cites the
baseline measurement that motivated it.

## Task 7 — CI

The `benchmarks` job runs `benchmarks.harness.pairs` for R counterbalanced
repetitions, then `benchmarks.harness.gate`. An inconclusive verdict escalates
once at double R. The deterministic gates — work, allocations, scaling — run as
their own step, since they need one repetition and no pairing. Round-level
reports are uploaded as artifacts, not committed. `benchmarks/compare.py` is
removed and `CONTRIBUTING.md` updated with the failure triage.

## Task 8 — the seeded regressions

`benchmarks/seeds/`, three patches, each applied to a scratch worktree, shown to
fail its gate, removed, shown to pass. The commands are recorded so the
demonstration is reproducible.

## Task 9 — dataset, budgets and documentation

Run the null experiment against the delivered suite; derive `budgets.toml` by the
design's formula, each entry carrying its measured justification. Generate the
accepted dataset. Generate `docs/performance/results.md` from it, with the
coherence test asserting the page matches the data. Write the narrative pages.
Link from `README.md` without embedding a number. Update `mkdocs.yml`.

## Task 10 — checker coverage for `benchmarks/`

Attempt adding `benchmarks` to `[tool.basedpyright] include`, `[tool.mypy] files`,
`[tool.ty.src] include`, `pyrefly.toml` and `conformance/config/pyright-source.json`,
then regenerate the ty and Pyrefly expectation files. Keep it if the regeneration
is mechanical and the new diagnostics are few and classifiable. Otherwise revert
and record the measured reason. Not a blocker for the release.

## Task 11 — evidence, proposal, roadmap

The evidence report; the proposal's `Status:` closed in the same change; the
roadmap's Step 7 section marked delivered, with "Carried from Step 7" recording
the depth cliff and the plan-compilation evidence, both routed to Step 8.

## Definition of done

- The five ordinary gates green, coverage at or above 95%, mutation threshold
  met, `mkdocs build --strict` green.
- Every workload carries a complete claim; every workload with a baseline proves
  `Observation` equality.
- The differential test passes and the complexity tests fail against the
  pre-repair implementations.
- Three seeded regressions each fail their gate and pass once removed.
- The published page is generated from the committed dataset and matches it.
- No aggregate ranking, and no competitor number, is published.
- The proposal's status is closed.
