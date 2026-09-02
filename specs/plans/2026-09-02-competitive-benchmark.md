# Competitive Benchmark and Leadership Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` (recommended) or `executing-plans` to implement
> this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an accepted, reproducible competitor baseline that classifies
semantic equivalence before timing and issues separate competitive, absolute,
and secondary-metric verdicts per workload.

**Architecture:** The ordinary `benchmarks.workloads.WORKLOADS` inventory and
base-versus-head gate remain unchanged. A comparison-only package wraps those
contracts with versioned competitor candidates, a dedicated collector writes
counterbalanced reduced samples, and pure-data evaluators and renderers derive
all verdicts from the committed dataset.

**Tech Stack:** Python 3.12, PEP 695 typing, stdlib `dataclasses`, `tomllib`,
`importlib.metadata`, pytest, pytest-benchmark, uv, Dependency Injector 4.49.1,
Dishka 1.10.1, Wireup 2.12.0, svcs 26.1.0, GitHub Actions.

---

Date: 2026-09-02

Derived from `specs/2026-09-02-competitive-benchmark-design.md` and governed by
`specs/proposals/2026-09-02-competitive-performance-leadership-proposal.md`.

## Global constraints

- `AGENTS.md` governs every task. No `Any`, `typing.cast`, blanket suppression,
  swallowed exception, or framework import under `depin/`.
- New behavior is developed red-green-refactor. Run the named failing test before
  writing its implementation.
- Competitor packages remain exact pins in the `bench` dependency group and do
  not enter the wheel metadata.
- `benchmarks.harness` remains stdlib-only. Only adapter modules import competitor
  packages.
- The default `pytest` run does not collect competitor observation tests;
  `benchmarks/test_comparison.py` is exercised by the locked benchmark workflow.
- `benchmarks/budgets.toml` remains generated and untouched. Absolute targets
  live in the separately reviewed `benchmarks/leadership-targets.toml`.
- Commit after each task only after the five repository gates are green. The
  final documentation task additionally runs `mkdocs build --strict`.

## File structure

```text
benchmarks/
  leadership-targets.toml       authored additive overhead targets
  test_comparison.py            pytest-benchmark shell for locked competitors
  comparison/
    __init__.py                 comparison inventory export only
    contracts.py                equivalence, candidate, target, verdict shapes
    targets.py                  strict TOML loader
    shapes.py                   shared typed graphs used by all adapters
    inventory.py                complete workload × competitor matrix
    adapters/
      __init__.py               adapter protocol and ordered registry
      dependency_injector.py    Dependency Injector 4.49.1
      dishka.py                 Dishka 1.10.1
      wireup.py                 Wireup 2.12.0
      svcs.py                   svcs 26.1.0
  harness/
    comparison.py               counterbalanced collector and dataset parser
    leadership.py               pure-data per-workload evaluator
    comparison_report.py        dataset and verdicts to Markdown
tests/integration/
  test_comparison_contracts.py  model, target, and inventory invariants
  test_comparison_harness.py    synthetic collection and evaluator tests
  test_comparison_docs.py       generated report coherence
.github/workflows/
  competitive-benchmarks.yml   locked manual/calibration workflow
specs/evidence/
  2026-09-02-competitive-performance-baseline.md
```

### Task 1: Typed comparison contracts

**Files:**
- Create: `benchmarks/comparison/__init__.py`
- Create: `benchmarks/comparison/contracts.py`
- Create: `tests/integration/test_comparison_contracts.py`

- [ ] **Step 1: Write the failing invariant tests**

Create `tests/integration/test_comparison_contracts.py` with focused constructors
and these cases:

```python
from collections.abc import Callable

import pytest

from benchmarks.comparison.contracts import (
    AbsoluteTarget,
    Candidate,
    Competitor,
    Equivalence,
)
from benchmarks.contracts import Implementation, Observation, Prepared
from benchmarks.harness import HarnessError


def _implementation() -> Implementation:
    return Implementation(
        label='candidate-1.0',
        prepare=lambda: Prepared(call=object),
        observe=lambda: Observation(result='object', constructed=(), closed=()),
    )


@pytest.mark.parametrize('equivalence', [Equivalence.EQUIVALENT, Equivalence.PARTIAL])
def test_a_timed_candidate_requires_an_implementation(equivalence: Equivalence) -> None:
    with pytest.raises(HarnessError, match='requires an implementation'):
        Candidate('workload', Competitor('candidate', '1.0'), equivalence, 'stated difference', None)


def test_an_incomparable_candidate_cannot_carry_an_implementation() -> None:
    with pytest.raises(HarnessError, match='must not carry an implementation'):
        Candidate(
            'workload',
            Competitor('candidate', '1.0'),
            Equivalence.INCOMPARABLE,
            'different lifecycle',
            _implementation(),
        )


@pytest.mark.parametrize('reason', ['', ' padded', 'padded '])
def test_a_candidate_reason_is_non_empty_and_unpadded(reason: str) -> None:
    with pytest.raises(HarnessError, match='reason'):
        Candidate('workload', Competitor('candidate', '1.0'), Equivalence.PARTIAL, reason, _implementation())


def test_an_absolute_target_uses_the_lower_applicable_ceiling() -> None:
    target = AbsoluteTarget(12e-6, 0.1, 'handler budget')
    assert target.ceiling(80e-6) == pytest.approx(8e-6)
```

- [ ] **Step 2: Verify the tests fail because the package does not exist**

Run:

```bash
uv run pytest tests/integration/test_comparison_contracts.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named
'benchmarks.comparison'`.

- [ ] **Step 3: Implement the immutable model and invariants**

Create an empty module docstring in `benchmarks/comparison/__init__.py`, then
create `benchmarks/comparison/contracts.py` with:

```python
"""Immutable contracts for classifying and judging competitor implementations."""

from dataclasses import dataclass
from enum import Enum

from benchmarks.contracts import Implementation, Metric, Workload
from benchmarks.harness import HarnessError


class Equivalence(Enum):
    EQUIVALENT = 'equivalent'
    PARTIAL = 'partial'
    INCOMPARABLE = 'incomparable'


@dataclass(frozen=True, slots=True)
class Competitor:
    distribution: str
    version: str

    @property
    def label(self) -> str:
        return f'{self.distribution}-{self.version}'


@dataclass(frozen=True, slots=True)
class Candidate:
    workload: str
    competitor: Competitor
    equivalence: Equivalence
    reason: str
    implementation: Implementation | None

    def __post_init__(self) -> None:
        if not self.workload.isidentifier() or self.workload.lower() != self.workload:
            raise HarnessError(f'{self.workload!r}: candidate workload must be a stable lower-case identifier')
        if not self.reason or self.reason.strip() != self.reason:
            raise HarnessError(f'{self.competitor.label}: candidate reason must be non-empty and unpadded')
        if self.equivalence is Equivalence.INCOMPARABLE:
            if self.implementation is not None:
                raise HarnessError(f'{self.competitor.label}: incomparable candidate must not carry an implementation')
        elif self.implementation is None:
            raise HarnessError(
                f'{self.competitor.label}: {self.equivalence.value} candidate requires an implementation'
            )
        elif self.implementation.label != self.competitor.label:
            raise HarnessError(
                f'{self.competitor.label}: implementation label is {self.implementation.label!r}; '
                'dataset labels must include the pinned distribution and version'
            )


@dataclass(frozen=True, slots=True)
class AbsoluteTarget:
    fixed_seconds: float
    fraction_of_direct: float | None
    justification: str

    def __post_init__(self) -> None:
        if self.fixed_seconds <= 0.0:
            raise HarnessError(f'{self.fixed_seconds}: fixed target must be positive')
        if self.fraction_of_direct is not None and not 0.0 < self.fraction_of_direct <= 1.0:
            raise HarnessError(f'{self.fraction_of_direct}: direct fraction must be within (0, 1]')
        if not self.justification or self.justification.strip() != self.justification:
            raise HarnessError('target justification must be non-empty and unpadded')

    def ceiling(self, direct_seconds: float) -> float:
        proportional = self.fixed_seconds
        if self.fraction_of_direct is not None:
            proportional = direct_seconds * self.fraction_of_direct
        return min(self.fixed_seconds, proportional)


@dataclass(frozen=True, slots=True)
class ComparativeWorkload:
    workload: Workload
    candidates: tuple[Candidate, ...]
    target: AbsoluteTarget | None
    secondary_metrics: tuple[Metric, ...] = ()
```

- [ ] **Step 4: Run the contract tests and both type checkers**

Run:

```bash
uv run pytest tests/integration/test_comparison_contracts.py -q
uv run basedpyright benchmarks/comparison tests/integration/test_comparison_contracts.py
uv run mypy benchmarks/comparison tests/integration/test_comparison_contracts.py
```

Expected: all tests pass and both checkers report zero diagnostics.

- [ ] **Step 5: Commit the model**

```bash
git add benchmarks/comparison tests/integration/test_comparison_contracts.py
git commit -m "test: define competitor comparison contracts"
```

### Task 2: Strict absolute-target contract

**Files:**
- Create: `benchmarks/leadership-targets.toml`
- Create: `benchmarks/comparison/targets.py`
- Modify: `tests/integration/test_comparison_contracts.py`

- [ ] **Step 1: Add failing loader and inventory-coverage tests**

Append tests which write malformed TOML to `tmp_path`, require rejection of an
unknown key and non-positive target, load the committed file, and assert that the
target keys equal exactly the names of latency workloads with direct baselines:

```python
from pathlib import Path

from benchmarks.comparison.targets import load
from benchmarks.contracts import Metric
from benchmarks.workloads import WORKLOADS


def test_every_direct_latency_workload_has_one_absolute_target() -> None:
    targets = load(Path('benchmarks/leadership-targets.toml'))
    expected = {
        workload.name
        for workload in WORKLOADS
        if workload.claim.metric is Metric.LATENCY and workload.baseline is not None
    }
    assert set(targets) == expected


def test_an_unknown_target_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / 'targets.toml'
    path.write_text(
        '[case]\nfixed_seconds = 0.1\njustification = "reason"\nunknown = 1\n',
        encoding='utf-8',
    )
    with pytest.raises(HarnessError, match='unknown field'):
        load(path)
```

- [ ] **Step 2: Verify RED**

Run `uv run pytest tests/integration/test_comparison_contracts.py -q`.

Expected: import fails for `benchmarks.comparison.targets`.

- [ ] **Step 3: Implement the strict TOML loader**

`targets.load(path)` uses `tomllib.loads`, the narrowing helpers from
`benchmarks.harness`, allows only `fixed_seconds`, `fraction_of_direct`, and
`justification`, and returns `dict[str, AbsoluteTarget]`. It catches
`tomllib.TOMLDecodeError` and `OSError` and raises `HarnessError` with the path and
the underlying reason. Duplicate TOML tables are left to `tomllib` and therefore
also fail closed.

The complete narrowing loop is:

```python
allowed = {'fixed_seconds', 'fraction_of_direct', 'justification'}
targets: dict[str, AbsoluteTarget] = {}
for name, encoded in decoded.items():
    fields = require_object(encoded, name)
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise HarnessError(f'{name}: unknown field {unknown[0]!r}')
    fraction = fields.get('fraction_of_direct')
    targets[name] = AbsoluteTarget(
        fixed_seconds=require_number(fields.get('fixed_seconds'), f'{name}.fixed_seconds'),
        fraction_of_direct=None if fraction is None else require_number(fraction, f'{name}.fraction_of_direct'),
        justification=require_text(fields.get('justification'), f'{name}.justification'),
    )
return targets
```

- [ ] **Step 4: Add all 22 authored targets**

Create one TOML table for each direct latency workload. Use these fixed ceilings:

```text
resolve_cached_singleton=0.5us; alias=1.0us; two decorations=1.5us;
collection_10=5us; collection_100=50us; transient_chain=10us;
open_and_close_scope=12us; each inject wrapper=1us; async singleton=0.5us;
no override=0.5us; active override=1us; generic key=0.5us;
first singleton=0.5us; sync resource=3us; warmup_1000=500us;
request-shaped scope=3.5us; FastAPI light=12us; FastAPI scoped=16us;
FastAPI singleton/transient=16us; FastAPI async teardown=18us;
FastAPI representative work=12us; FastAPI startup=30us.
```

Every FastAPI table also sets `fraction_of_direct = 0.1`. Every table's
`justification` names the design formula that produced its fixed ceiling. Write
seconds as decimal literals, for example `fixed_seconds = 0.0000005`.

- [ ] **Step 5: Verify GREEN and commit**

Run:

```bash
uv run pytest tests/integration/test_comparison_contracts.py -q
uv run basedpyright benchmarks/comparison tests/integration/test_comparison_contracts.py
uv run mypy benchmarks/comparison tests/integration/test_comparison_contracts.py
```

Expected: pass with zero diagnostics.

```bash
git add benchmarks/leadership-targets.toml benchmarks/comparison/targets.py tests/integration/test_comparison_contracts.py
git commit -m "test: declare absolute performance targets"
```

### Task 3: Pin competitors and build shared comparison shapes

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `benchmarks/comparison/shapes.py`
- Create: `benchmarks/test_comparison.py`

- [ ] **Step 1: Add exact benchmark-only pins**

Run:

```bash
uv add --group bench 'dependency-injector==4.49.1' 'dishka==1.10.1' 'wireup==2.12.0' 'svcs==26.1.0'
```

Expected: only the `bench` group in `pyproject.toml` and `uv.lock` change. Confirm
`project.dependencies` remains empty.

- [ ] **Step 2: Write failing tests for a typed, observable chain**

In `benchmarks/test_comparison.py`, assert a five-node `Chain` constructs
`Node0..Node4`, returns `Node4`, resets its log between observations, and exposes
factories whose parameter and return annotations name the adjacent node types.

- [ ] **Step 3: Verify RED**

Run:

```bash
uv run --no-default-groups --group bench pytest benchmarks/test_comparison.py -q
```

Expected: import fails for `benchmarks.comparison.shapes`.

- [ ] **Step 4: Implement the shared chain**

Create `Chain` as a frozen, slotted record containing `nodes`, `factories`,
`leaf`, and `log`. `chain(size)` creates fresh node classes and one factory per
node. Each factory appends its node name, consumes the previous node when one
exists, and returns the current node. Assign exact runtime annotations as
`benchmarks.graphs._provider` does. Reject sizes below one with `HarnessError`.

Also implement:

```python
def observation(chain: Chain, value: object) -> Observation:
    return Observation(
        result=type(value).__name__,
        constructed=tuple(chain.log),
        closed=(),
    )
```

- [ ] **Step 5: Verify and commit**

Run the benchmark test plus ruff and both type checkers against
`benchmarks/comparison`. Expected: all pass.

```bash
git add pyproject.toml uv.lock benchmarks/comparison/shapes.py benchmarks/test_comparison.py
git commit -m "build: pin competitive benchmark dependencies"
```

### Task 4: Dependency Injector adapter

**Files:**
- Create: `benchmarks/comparison/adapters/__init__.py`
- Create: `benchmarks/comparison/adapters/dependency_injector.py`
- Modify: `benchmarks/test_comparison.py`

- [ ] **Step 1: Write failing observation tests**

Test warm singleton and a 20-node transient chain. Each candidate must carry
`Competitor('dependency-injector', '4.49.1')`; its observation must equal the
matching `depin` workload observation. Add a test proving the singleton uses
`providers.ThreadSafeSingleton`, not the weaker default singleton.

- [ ] **Step 2: Verify RED**

Run the two new node IDs with the locked `bench` group. Expected: module import
failure.

- [ ] **Step 3: Implement the adapter through public providers**

Build the warm chain by folding shared factories into
`providers.ThreadSafeSingleton(factory, previous_provider)` and the transient
chain with `providers.Factory`. Warm the leaf outside the timed call. The prepared
call invokes the leaf provider; the observation builds a fresh chain and records
its construction log. Close/reset providers from `Prepared.close` so one test
cannot retain state into another.

Export an `ADAPTER` object implementing the design's `Adapter` protocol, with
`candidates(workloads)` returning equivalent records for
`resolve_cached_singleton`, `resolve_a_transient_chain`, and
`construct_a_singleton_for_the_first_time`; classify scoped lifecycles as
incomparable because provider overrides are not nested scope frames; classify
other cases partial or incomparable with a concrete feature difference.

- [ ] **Step 4: Verify exact observations, type checking, and commit**

Run:

```bash
uv run --no-default-groups --group bench pytest benchmarks/test_comparison.py -q
uv run --no-default-groups --group bench basedpyright benchmarks/comparison
uv run --no-default-groups --group bench mypy benchmarks/comparison
```

Expected: pass with zero diagnostics.

```bash
git add benchmarks/comparison/adapters benchmarks/test_comparison.py
git commit -m "test: add Dependency Injector comparisons"
```

### Task 5: Dishka adapter

**Files:**
- Create: `benchmarks/comparison/adapters/dishka.py`
- Modify: `benchmarks/test_comparison.py`

- [ ] **Step 1: Add failing singleton, transient, and scoped observation tests**

The scoped case must enter `Scope.REQUEST`, construct the full chain, exit, and
prove the construction log matches `open_and_close_a_scope`. Add one identity test
showing two reads in the same request scope reuse the scoped leaf.

- [ ] **Step 2: Verify RED**

Run only the Dishka node IDs. Expected: import failure for the adapter.

- [ ] **Step 3: Implement with `Provider`, `provide`, and `make_container`**

Register singleton factories at `Scope.APP`, transient factories at `Scope.APP`
with `cache=False`, and scoped factories at `Scope.REQUEST`. Use
`with container() as request_container` for the scoped cycle. Close the root
container in `Prepared.close`. Label every implementation `dishka-1.10.1` from
`importlib.metadata.version('dishka')` and fail if the installed version differs.

The exported `ADAPTER` covers the three core shapes. Alias and resource records are
partial only when the adapter test demonstrates the named omitted guarantee;
unsupported framework and diagnostic shapes remain incomparable.

- [ ] **Step 4: Verify and commit**

Run the complete comparison observation module and both type checkers with the
locked group. Expected: pass.

```bash
git add benchmarks/comparison/adapters/dishka.py benchmarks/test_comparison.py
git commit -m "test: add Dishka comparisons"
```

### Task 6: Wireup adapter

**Files:**
- Create: `benchmarks/comparison/adapters/wireup.py`
- Modify: `benchmarks/test_comparison.py`

- [ ] **Step 1: Add failing singleton, transient, and scoped tests**

The tests require `create_sync_container`, root `get()` for singleton, and
`enter_scope()` for transient/scoped retrieval. They compare observations and
close every root container.

- [ ] **Step 2: Verify RED**

Run only Wireup node IDs. Expected: import failure.

- [ ] **Step 3: Implement with public injectable factories**

Decorate each shared factory with `wireup.injectable(lifetime=...)`, create one
sync container from the factory list, and retrieve the leaf by type. Use
`'singleton'`, `'transient'`, and `'scoped'` lifetimes exactly as documented.
Transient and scoped calls enter a scope because Wireup restricts those lifetimes
to scoped containers. The root container is closed by `Prepared.close`.

Export `ADAPTER` with complete records and verify the installed version equals
`2.12.0`.

- [ ] **Step 4: Verify and commit**

Run all comparison tests and both type checkers with `--group bench`.

```bash
git add benchmarks/comparison/adapters/wireup.py benchmarks/test_comparison.py
git commit -m "test: add Wireup comparisons"
```

### Task 7: svcs adapter and complete matrix

**Files:**
- Create: `benchmarks/comparison/adapters/svcs.py`
- Create: `benchmarks/comparison/inventory.py`
- Modify: `benchmarks/comparison/adapters/__init__.py`
- Modify: `benchmarks/comparison/__init__.py`
- Modify: `benchmarks/test_comparison.py`
- Modify: `tests/integration/test_comparison_contracts.py`

- [ ] **Step 1: Add failing svcs observation and matrix coverage tests**

The svcs test registers the shared factories in `svcs.Registry`, retrieves the
leaf through one `svcs.Container`, and closes container and registry. Classify it
partial because the per-container cache lacks the singleton single-flight and
nested lifetime contract.

The matrix test requires every `WORKLOADS` entry to have exactly one candidate
for each ordered distribution, unique implementation labels, no equivalent
candidate without observation equality, and an absolute target precisely when a
direct latency baseline exists.

- [ ] **Step 2: Verify RED**

Run the svcs and matrix tests. Expected: imports fail for `svcs` adapter and
inventory.

- [ ] **Step 3: Implement svcs and assemble the inventory**

`adapters.__init__` exports the ordered tuple `ADAPTERS` containing the four
modules' `ADAPTER` objects. `inventory.build()` loads targets, indexes the four
candidate sets by each candidate's `workload`,
and returns `tuple[ComparativeWorkload, ...]` in ordinary workload order. It
raises `HarnessError` on a missing, duplicate, or extra record and on target
coverage mismatch.

`comparison.__init__` exports only `WORKLOADS = inventory.build()`.

- [ ] **Step 4: Verify all contracts and commit**

Run the default comparison contract tests, the locked adapter tests, ruff, and
both type checkers. Expected: all green.

```bash
git add benchmarks/comparison benchmarks/test_comparison.py tests/integration/test_comparison_contracts.py
git commit -m "test: complete the competitor equivalence matrix"
```

### Task 8: Counterbalanced comparison collector

**Files:**
- Modify: `benchmarks/test_comparison.py`
- Create: `benchmarks/harness/comparison.py`
- Create: `tests/integration/test_comparison_harness.py`

- [ ] **Step 1: Write failing synthetic collector tests**

Use a child command that writes three deterministic pytest-benchmark-shaped
reports. Assert five repetitions alternate `forward`, `reverse`, `forward`,
`reverse`, `forward`; the dataset records source and harness revisions,
environment, pins, classifications, targets, order, medians, rounds, and duration;
and a dirty tree or wrong installed version raises `HarnessError` before timing.

- [ ] **Step 2: Verify RED**

Run `uv run pytest tests/integration/test_comparison_harness.py -q`.

Expected: import failure for `benchmarks.harness.comparison`.

- [ ] **Step 3: Add the comparison benchmark shell**

Parameterize only candidates with implementations. Use the environment variable
`DEPIN_COMPARISON_ORDER` to reverse the candidate order without changing IDs.
Before benchmarking, assert equivalent observations equal the subject. Put the
equivalence class and reason in `benchmark.extra_info`.

- [ ] **Step 4: Implement collection**

Reuse `reduce.load`, `environment.capture`, `write_json`, fixed hash seed, and
the existing sample-quality fields. Each repetition invokes an independent
process with:

```text
python -m pytest benchmarks/test_comparison.py --benchmark-only -q
  --benchmark-json={report}
```

The CLI is:

```text
python -m benchmarks.harness.comparison collect
  --repetitions 5 --out DIR
```

Write `DIR/comparison.json`; do not retain round-level reports. Refuse fewer than
five repetitions, a dirty tree unless `--allow-dirty` is explicitly present for
diagnosis, and any pin mismatch. Datasets collected with `--allow-dirty` carry
`accepted: false` and cannot be rendered as accepted evidence.

- [ ] **Step 5: Verify and commit**

Run the synthetic tests and one repetition with `--allow-dirty` to prove the real
shell starts. Do not call the diagnostic file accepted.

```bash
git add benchmarks/test_comparison.py benchmarks/harness/comparison.py tests/integration/test_comparison_harness.py
git commit -m "test: collect paired competitor samples"
```

### Task 9: Leadership evaluator and noise calibration

**Files:**
- Create: `benchmarks/harness/leadership.py`
- Modify: `tests/integration/test_comparison_harness.py`

- [ ] **Step 1: Write failing verdict tests**

Build minimal in-memory datasets for each status: `leader`, `shared-leader`,
`loss`, `absolute-failure`, `regression`, `unstable`, and
`no-equivalent-competitor`. Add boundary cases proving the fastest equivalent
median is selected, partial candidates are excluded, the upper confidence bound
uses the allowance, additive direct overhead uses the target's lower ceiling,
and null p99 above 5% is unstable rather than truncated.

- [ ] **Step 2: Verify RED**

Run the evaluator node IDs. Expected: import failure.

- [ ] **Step 3: Implement pure-data evaluation**

Define frozen `Status`, `CompetitorVerdict`, and `WorkloadVerdict` records. Parse
JSON through the existing narrowing helpers. Use `stats.paired_ratio` with the
dataset seed and qualified per-repetition medians. Compute additive overhead from
paired `depin - direct` values. Keep competitive, absolute, and secondary fields
separate even when the final status is a loss.

Add CLI forms:

```text
python -m benchmarks.harness.leadership calibrate NULL_DIR --out calibration.json
python -m benchmarks.harness.leadership evaluate DATASET --calibration calibration.json
```

Calibration rounds p99 upward to 0.001 and records eligibility without changing
`benchmarks/budgets.toml`. Evaluation exits 0 only when every eligible required
workload is leader/shared-leader or explicitly has no equivalent competitor; 1
for a measured failure; 2 for malformed input; 3 for unstable evidence.

- [ ] **Step 4: Verify and commit**

Run the complete harness tests, ruff, and both type checkers.

```bash
git add benchmarks/harness/leadership.py tests/integration/test_comparison_harness.py
git commit -m "test: evaluate per-workload performance leadership"
```

### Task 10: Generated comparison report

**Files:**
- Create: `benchmarks/harness/comparison_report.py`
- Create: `tests/integration/test_comparison_docs.py`
- Create after accepted collection: `docs/performance/comparison-baseline.md`

- [ ] **Step 1: Write failing renderer tests**

Use a small accepted fixture with one equivalent, one partial, and one
incomparable candidate. Assert the Markdown includes the claim, classification
reasons, medians and confidence interval, noise allowance, direct overhead,
absolute target, secondary verdict, and per-workload status. Assert it contains
none of `overall winner`, `geometric mean`, `score`, or `fastest library`.

- [ ] **Step 2: Verify RED**

Run the new test module. Expected: import failure.

- [ ] **Step 3: Implement deterministic rendering**

`render(dataset, calibration) -> str` calls the same evaluator as the CLI and
orders rows by inventory, then competitor registry. It renders partial and
incomparable rows with an em dash for timings and their reason beside them. The
footer records source revision, harness revision, dependency versions, host, and
collection command. `main()` writes stdout only.

- [ ] **Step 4: Add coherence test and commit implementation**

The initial coherence test renders a small committed fixture under
`tests/fixtures/comparison/` and compares it with a committed expected Markdown
fixture; do not skip it. Task 12 replaces those fixture paths with the fixed
accepted dataset and public page paths.

```bash
git add benchmarks/harness/comparison_report.py tests/integration/test_comparison_docs.py tests/fixtures/comparison
git commit -m "test: generate the comparative performance report"
```

### Task 11: Dedicated locked workflow and checker environment

**Files:**
- Create: `.github/workflows/competitive-benchmarks.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `CONTRIBUTING.md`
- Test: `tests/integration/test_comparison_contracts.py`

- [ ] **Step 1: Add failing workflow-structure tests**

Parse both YAML files as text and assert the competitive workflow runs only on
manual dispatch or the exact `competitive-benchmark` PR label, installs
`--no-default-groups --group bench --locked`, runs observation tests before
collection, uploads collection and calibration artifacts, and never uses an
unpinned competitor requirement. Assert the source-checking sync in `ci.yml`
includes `--group bench`.

- [ ] **Step 2: Verify RED**

Run the workflow node IDs. Expected: missing workflow assertion fails.

- [ ] **Step 3: Implement workflow and contributor commands**

The workflow has `contents: read`, a 120-minute timeout, fixed Python 3.12, and
these ordered steps: locked bench sync; adapter observation tests; null
collection; calibration; real collection; evaluation; Markdown summary; artifact
upload on `always()`. A labeled PR can exercise a workflow not yet on the default
branch, matching the existing calibration policy.

Update the source-checking job's sync to include `--group bench`. Document exact
local commands and the distinction between diagnostic dirty data and accepted
clean data.

- [ ] **Step 4: Verify and commit**

Run workflow tests, both type checkers, and `uv lock --check`.

```bash
git add .github/workflows/competitive-benchmarks.yml .github/workflows/ci.yml CONTRIBUTING.md tests/integration/test_comparison_contracts.py
git commit -m "ci: collect locked competitor benchmarks"
```

### Task 12: Prove the gate and publish accepted baseline evidence

**Files:**
- Create: `benchmarks/seeds/competitive-cached-lookup.patch`
- Modify: `benchmarks/seeds/README.md`
- Create: `benchmarks/results/2026-09-02-competitive-baseline/comparison.json`
- Create: `benchmarks/results/2026-09-02-competitive-baseline/calibration.json`
- Create: `specs/evidence/2026-09-02-competitive-performance-baseline.md`
- Create: `docs/performance/comparison-baseline.md`
- Modify: `tests/integration/test_comparison_docs.py`
- Modify: `specs/proposals/2026-09-02-competitive-performance-leadership-proposal.md`
- Modify: `specs/2026-08-28-roadmap-1.0-design.md`

- [ ] **Step 1: Create and verify a seeded loss**

The patch adds one container-owned dictionary allocation and lookup to the warm
cached resolution path. Apply it in a scratch worktree, collect the focused warm
singleton comparison, and prove the evaluator changes that workload from its
unseeded status to `loss` or `regression`. Reverse the patch and prove the
unseeded verdict is restored. Record exact commands and both exit codes in the
seed README.

- [ ] **Step 2: Collect clean null and competitor datasets**

From a clean committed tree run the locked workflow commands with at least five
repetitions. The source revision in the output must equal `git rev-parse HEAD`,
all package versions must equal their pins, every sample must qualify, and no
accepted flag may be false. If a workload's null p99 exceeds 5%, stabilize the
measurement or record it as unstable; never truncate or delete it.

- [ ] **Step 3: Write evidence before changing proposal status**

The evidence report names the host, interpreter, revisions, dependencies,
commands, equivalence decisions, raw dataset paths, every competitive loss,
every absolute failure, every unstable workload, and the later proposal that
owns each residual. Include profiles for the three preliminary core gaps and the
FastAPI gap. State explicitly that the dataset makes no aggregate claim.

- [ ] **Step 4: Generate documentation and update status**

Generate `docs/performance/comparison-baseline.md` from the accepted dataset and
run its exact coherence test. Change the governing proposal to `Status: accepted,
active`; do not close it until all three optimization proposals finish. Update
the roadmap sequence with links to design, plan, dataset, and evidence.

- [ ] **Step 5: Run every final gate**

Run in this exact order:

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
uv run --no-default-groups --group bench pytest benchmarks/test_comparison.py -q
uv run --no-default-groups --group bench python -m benchmarks.harness.leadership evaluate \
  benchmarks/results/2026-09-02-competitive-baseline/comparison.json \
  --calibration benchmarks/results/2026-09-02-competitive-baseline/calibration.json
```

Expected: formatting unchanged, zero lint/type diagnostics, all tests pass with
only the documented free-threaded skips, strict docs build succeeds, all adapter
observations pass, and the evaluator reports the baseline's truthful mix of
per-workload statuses without malformed or unstable data.

- [ ] **Step 6: Commit the accepted evidence**

```bash
git add benchmarks/seeds benchmarks/results specs/evidence docs/performance \
  specs/proposals/2026-09-02-competitive-performance-leadership-proposal.md \
  specs/2026-08-28-roadmap-1.0-design.md
git commit -m "perf: publish the competitive performance baseline"
```

## Definition of done

- The ordinary regression gate is unchanged and all repository gates pass.
- Every required workload has one classification per pinned competitor and every
  direct latency workload has one authored absolute target.
- Equivalent adapters pass observation equality before timing.
- Collection is counterbalanced, process-isolated, version-locked, and
  reproducible from reduced raw samples.
- Competitive, absolute, and secondary verdicts remain independent in code,
  JSON, evidence, and generated documentation.
- A seeded regression proves the leadership evaluator can fail.
- The accepted baseline routes concrete residuals into the compiled-runtime and
  FastAPI designs; the native proposal remains gated on their results.
