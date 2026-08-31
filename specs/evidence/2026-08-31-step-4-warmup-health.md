# Step 4, cycle 2 verification evidence

Date: 2026-08-31

Baseline commit (`main`, 0.11.0): `d2b8ceb31b25ca88b0c279676fe54629390cfd9c`
Measured commit (this branch): `b459d89ddc92e485f7b63efcf066a9c83b55a982`

This document covers Steps 1 through 7 of the Task 6 brief, plus the Task 6
addition (unifying the two examples' key-rendering helpers). All commands
below were run against the working tree at the measured commit; the evidence
file itself adds no other tracked path, so every claim about the tree remains
true once this file lands.

The full commit range this cycle covers, oldest first: `e59cacb` (design),
`29a5f71` (plan), `5bc34f5`, `c322034`, `3958c98`, `f130cd6`, `448b7dd`,
`a80ad2a`, `e10b843`, `b6bd53b` (implementation and docs), `7724d64`
(this task's examples fix), `b459d89` (this task's roadmap amendment).

## The examples fix

`examples/warmup/main.py`'s `_names` filtered non-`type` keys out with
`if isinstance(node.key, type)`, dropping any key that was not a class.
`examples/health/main.py`'s `_name` used a degrading ternary,
`key.__qualname__ if isinstance(key, type) else str(key)`, rendering every
key. Committed `7724d64` changes `_names` to the same degrading form:

```python
def _names(nodes: tuple[GraphNode, ...]) -> list[str]:
    return [node.key.__qualname__ if isinstance(node.key, type) else str(node.key) for node in nodes]
```

Neither `_names` nor `_name` is exercised by `tests/integration/test_examples.py`:
`test_warmup_example_builds_singletons_and_leaves_the_scoped_one_alone` and
`test_health_example_reports_one_passing_and_one_failing_check` assert
directly on `report.constructed` / `report.cached` / `report.results` and
their `.key` attributes, not on anything the two helpers print. Both examples'
bindings are plain classes, so the rendered lists are also unchanged for the
example's own output. No test assertion needed updating; confirmed by
grepping the test file for `_names`/`_name`/`main()`/`capsys`/`subprocess`,
none of which appear.

## Gate sequence

```console
$ uv run ruff format
159 files left unchanged
EXIT=0

$ uv run ruff check
All checks passed!
EXIT=0

$ uv run basedpyright
0 errors, 0 warnings, 0 notes
EXIT=0

$ uv run mypy
Success: no issues found in 102 source files
EXIT=0

$ uv run pytest
809 passed, 6 skipped in 19.16s
EXIT=0

$ uv run --group docs mkdocs build --strict
INFO    -  Documentation built in 3.33 seconds
EXIT=0
```

The docs command prints the same upstream Material for MkDocs 2.0 advisory
banner recorded in prior evidence files; no MkDocs diagnostic, exit 0.
`specs/` (this file included) sits outside `mkdocs.yml`'s `docs_dir`/`nav`.

## The `bind` overload defect, found and fixed mid-cycle

Not planned work: a checker defect measured while implementing Task 4 and
closed in the same task, `448b7dd`. Restated from
`.superpowers/sdd/2026-08-31-step-4-warmup-health/task-4-report.md` rather
than re-derived; the final-state checker runs below were re-run against the
tree this evidence lands in.

**What was measured wrong.** `BindingCollector.bind` at `f130cd6` had one
generic signature, `bind[T](source: type[T] | Callable[..., T], ...,
check: Callable[[T], object] | None = None)`. For a plain class or a
plain-return factory, `T` unifies with the produced value, and `check` types
correctly. For a generator, async-generator, context-manager, or
async-context-manager factory, `T` unifies with the *container* the factory
returns (e.g. `Generator[Pool, None, None]`), not the value `check` is
actually called with at runtime. Repro (`bind(pool, check=ping)` over
`def pool() -> Generator[Pool]: yield Pool()`, and the async-generator,
context-manager, and async-context-manager equivalents), before the fix:

```
basedpyright: 3 errors, 0 warnings, 0 notes
  check's declared parameter (Pool) does not match the inferred T
  (Generator[Pool, None, None] / CoroutineType[Any, Any, Pool])

mypy: 3 errors
  "Cannot infer value of type parameter \"T\" of \"bind\""
```

**The fix.** Seven `@overload`s on `bind`, one per provider shape
(`type[T]`, `Callable[..., Generator[T]]`, `Callable[..., AsyncGenerator[T]]`,
`Callable[..., AbstractContextManager[T]]`,
`Callable[..., AbstractAsyncContextManager[T]]`, `Callable[..., Awaitable[T]]`,
`Callable[..., T]`, container-returning forms ordered before the general
`Callable[..., T]`), each resolving `T` to the value the provider produces
rather than the container the factory returns. The implementation's own
`source` parameter widens to the union of all seven shapes, which is required
for overload/implementation consistency inside `bindings.py` itself (checked
only from inside the defining module, not from a call site).

**After**, same repro:

```
basedpyright: 0 errors, 0 warnings, 0 notes
mypy: Success: no issues found in 1 source file
```

**Re-run against this evidence file's own tree** (`depin/_core/bindings.py`
in isolation, since overload/implementation consistency is a module-internal
check):

```console
$ uv run basedpyright depin/_core/bindings.py
0 errors, 0 warnings, 0 notes
EXIT=0

$ uv run mypy depin/_core/bindings.py
Success: no issues found in 1 source file
EXIT=0
```

The full-tree gate sequence above (`uv run basedpyright`, `uv run mypy`) also
covers `bindings.py` as part of the whole package and is clean.

The overload switch changed mypy's error code for six pre-existing
statically-invalid-input tests from `arg-type` to `call-overload` and made
basedpyright infer `Unknown` on four call sites whose result was used on a
later line; both were fixed as collateral in the same commit
(`448b7dd`) — narrowest correct suppression code per `AGENTS.md`, no
suppression added or removed in count.

## Coverage

```console
$ uv run pytest --cov=depin --cov-report=term-missing
...
Name                         Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------
depin/__init__.py               16      0      0      0   100%
depin/_core/__init__.py          0      0      0      0   100%
depin/_core/bindings.py         58      0      4      0   100%
depin/_core/construct.py        51      0     24      1    99%   75->exit
depin/_core/container.py        11      0      0      0   100%
depin/_core/decoration.py       47      0     24      0   100%
depin/_core/diagnostics.py      63      0      4      0   100%
depin/_core/frozen.py          269      6    100      8    96%   305-306, 582, 589->591, 622, 629->631, 654->658, 696, 714
depin/_core/graph.py           172      0     72      0   100%
depin/_core/health.py           59      0      6      0   100%
depin/_core/injection.py        39      0     16      1    98%   59->58
depin/_core/introspect.py       70      1     36      3    96%   43, 71->69, 74->69
depin/_core/markers.py          59      0      6      0   100%
depin/_core/overrides.py        23      0      4      0   100%
depin/_core/providers.py       205      1    108      1    99%   413
depin/_core/registry.py          8      0      0      0   100%
depin/_core/render.py          113      0     56      0   100%
depin/_core/scope.py           233      2     74      2    99%   88->87, 107-109, 113->exit
depin/_core/spec.py            131      0      6      0   100%
depin/_core/teardown.py         45      0     14      2    97%   53->exit, 77->exit
depin/_core/typeguards.py      105      1     42      1    99%   195
depin/_core/warmup.py           22      0      2      0   100%
depin/errors.py                 11      0      0      0   100%
depin/ext/__init__.py            0      0      0      0   100%
depin/ext/fastapi.py            33      0      6      0   100%
------------------------------------------------------------------------
TOTAL                         1843     11    604     19    99%
Required test coverage of 95.0% reached. Total coverage: 98.77%
809 passed, 6 skipped in 43.56s
EXIT=0
```

Run a second time, unmodified, specifically to observe `scope.py`'s
`_Flight.wait_sync` line:

```console
$ uv run pytest --cov=depin --cov-report=term-missing
...
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
...
Required test coverage of 95.0% reached. Total coverage: 98.69%
809 passed, 6 skipped in 43.84s
EXIT=0
```

The two runs land on opposite sides of the coin: the first misses `scope.py`
nothing beyond its three pre-existing branches (line 69 covered), the second
misses line 69 as well. This is the roughly-one-in-two behaviour of
`_Flight.wait_sync`'s thread-scheduling path, not evidence the line's
coverage changed — `scope.py` is untouched by this cycle (see "Untouched
modules" below). Both totals, 98.77% and 98.69%, are above the 95% floor.

`git diff --stat d2b8ceb -- 'depin/_core/*.py' depin/__init__.py` names ten
modules this cycle changed, two of them new:

```
depin/__init__.py         |   6 ++
depin/_core/bindings.py   | 117 ++++++++++++++++++++++++++++++++--
depin/_core/decoration.py |   4 ++
depin/_core/frozen.py     | 140 +++++++++++++++++++++++++++++++++++++++++
depin/_core/graph.py      |   1 +
depin/_core/health.py     | 155 +++++++++++++++++++++++++++++++++++++++++++
depin/_core/providers.py  |  19 ++++++
depin/_core/spec.py       |   2 +
depin/_core/typeguards.py |  16 ++++-
depin/_core/warmup.py     |  84 +++++++++++++++++++++++++
```

`bindings.py`, `decoration.py`, `graph.py`, `health.py` (new), `spec.py`, and
`warmup.py` (new) are at 100% line and branch coverage. `frozen.py`,
`providers.py`, and `typeguards.py` carry uncovered lines; each is attributed
below, checked against a detached worktree at `main` (`d2b8ceb`), built with
`uv sync` and measured with `uv run pytest --cov=depin --cov-report=term-missing`.

- **`depin/_core/frozen.py`, lines 305-306.** New this cycle. `git blame`
  attributes both to `c3220344` (`feat: construct every singleton with
  warmup`): the `if self._is_cached(spec): cached.append(spec); continue`
  branch inside `awarmup`, taken when a singleton `awarmup` would build was
  already constructed by an earlier `warmup()`/`awarmup()` call. No test
  exercises `awarmup()` a second time against an already-warm container; the
  sync counterpart's equivalent branch inside `warmup` is covered.

- **`depin/_core/frozen.py`, line 582, branches `589->591`, line 622,
  branches `629->631`, `654->658`, and lines 696 and 714.** Pre-existing.
  The worktree measurement at `d2b8ceb` gives `depin/_core/frozen.py 229 4 90
  7 97% Missing 442, 449->451, 482, 489->491, 514->518, 556, 574`. `git diff
  d2b8ceb -- depin/_core/frozen.py` inserts 11 lines before line 116 (new
  imports), 126 net lines between the baseline's lines 236 and 247 (the
  `warmup`/`checks`/`health` methods), and 3 lines at baseline line 412 (the
  new `_is_cached` helper) — a cumulative +140-line shift for everything
  after it. Every baseline miss plus 140 lands exactly on the current miss:
  442+140=582, 449→589/451→591, 482+140=622, 489→629/491→631, 514→654/518→658,
  556+140=696, 574+140=714. None of these lines sit inside `_is_cached`,
  `warmup`, `awarmup`, `checks`, `health`, or `ahealth`; all five belong to
  `_resolve_cached_sync`, `_resolve_async`, `_is_constructing`,
  `_resolve_params_sync`, and `_resolve_params_async`, none of which this
  cycle's diff touches.

- **`depin/_core/providers.py`, line 413.** Pre-existing. The worktree
  measurement at `d2b8ceb` gives `depin/_core/providers.py 200 1 106 1 99%
  Missing 394`; line 394 there and line 413 here are both the `return None`
  inside `unwrap_container_type`, taken when `get_args(annotation)` is empty.
  `providers.py` grows by 19 lines this cycle (carrying `check` from record to
  spec); 394+19=413, and `unwrap_container_type` itself is outside the diff.

- **`depin/_core/typeguards.py`, line 195.** New this cycle. The worktree
  measurement at `d2b8ceb` gives `depin/_core/typeguards.py 101 0 40 0 100%`
  — no miss. Line 195 is the `raise InvalidProviderError(...)` branch of the
  new `as_check`, taken when a declared `check` is not callable. Its own
  docstring states the branch is unreachable through the public API, because
  `Container.freeze()` already rejects a non-callable `check` before
  `as_check` runs (mirroring `as_awaitable`'s equivalent raise, which is
  reached only through an internal path and stays covered). No test calls
  `as_check` directly or constructs a plan that reaches this branch.

- **`depin/_core/construct.py`, branch `75->exit`; `depin/_core/scope.py`,
  branches `88->87`, `107-109`, `113->exit` (plus line 69 on the second run);
  `depin/_core/introspect.py`, line 43 and branches `71->69`, `74->69`;
  `depin/_core/injection.py`, branch `59->58`; `depin/_core/teardown.py`,
  branches `53->exit`, `77->exit`.** None of these five modules changed this
  cycle (empty diff against `d2b8ceb`, confirmed under "Untouched modules"
  below), so their misses are the same statements and arcs present on `main`,
  unmoved. The worktree measurement at `d2b8ceb` reproduces every one at the
  identical line and branch numbers.

Two new misses this cycle: `frozen.py:305-306` (an untested `awarmup`
already-cached branch) and `typeguards.py:195` (an `as_check` raise branch
its own docstring documents as unreachable through the public API, the same
class of defensive branch as other narrowing functions in the module). Both
are within the 95% floor at either coverage run.

## Suppression count

**`depin/` carries exactly three suppressions, and this cycle adds none.**

```console
$ grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin
depin/_core/frozen.py:127:        return self._resolve_sync(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/frozen.py:150:        return await self._resolve_async(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/markers.py:132:    return _InjectMarker(key, tag)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
```

`markers.py:132` is byte-identical to `d2b8ceb` at the same line number
(`markers.py` has no diff against `d2b8ceb` at all — see "Untouched modules").
`frozen.py`'s two suppressions carry identical text but at shifted line
numbers, `116→127` and `139→150`, both moved by exactly the 11 lines this
cycle's new imports add before line 116
(`git show d2b8ceb:depin/_core/frozen.py` gives the same two lines at 116 and
139). Text unchanged in both directions: nothing added, nothing removed.

## Untouched modules

```console
$ git diff --stat d2b8ceb -- depin/_core/construct.py depin/_core/diagnostics.py depin/_core/render.py depin/_core/scope.py depin/_core/teardown.py depin/_core/injection.py depin/_core/overrides.py depin/_core/introspect.py depin/_core/markers.py depin/_core/container.py depin/_core/registry.py
EXIT=0
```

Empty output. This cycle adds no validation rule and no `ProviderShape`:
`graph.py` changes by a single argument,

```console
$ git diff d2b8ceb -- depin/_core/graph.py
diff --git a/depin/_core/graph.py b/depin/_core/graph.py
index 5a9487d..7c90011 100644
--- a/depin/_core/graph.py
+++ b/depin/_core/graph.py
@@ -366,4 +366,5 @@ def _with_async_flags(order: Iterable[ProviderSpec], by_key: _Index) -> Iterable
             shape=spec.shape,
             needs_async=own,
             params=spec.params,
+            check=spec.check,
         )
```

and `construct.py`, `diagnostics.py`, and `render.py` change not at all —
confirmed above, and expected: `construct.py`'s `match` over `ProviderShape`
needs no new case for a check that runs after resolution rather than during
it, and neither `graph()`'s view nor its renderings gain a field to display.

`depin/_core/bindings.py` is not in the untouched list above — it changes by
117 lines, and beyond the brief's expectation of a `check=` keyword addition:
it gained seven `@overload`s mid-cycle, a defect found and fixed rather than
planned, recorded in full under "The `bind` overload defect" above.

## Design measurements

Restated from `specs/2026-08-31-step-4-warmup-health-design.md`'s
"Measurements" section, not re-derived for this pass. Four questions were
measured against the tree at `d2b8ceb`, rather than assumed.

- **A singleton's cache entry is observable without new machinery.**
  `FrozenContainer._resolve_cached_sync` caches under `(spec.key, spec.tag)`
  on the root frame, and `ScopeFrame.lookup` reports absence as `MISSING`
  without raising. Reading `self._root.lookup((spec.key, spec.tag))`
  distinguishes a singleton already built from one this call must build,
  using the frame API that already exists.

- **`needs_async` is already per-spec, and that is the rule to match.**
  `resolve` raises `AsyncInSyncContextError` when *the spec it was asked for*
  has `needs_async`, not when the graph contains an async provider anywhere.
  A graph with an async singleton reports `needs_async` on that singleton and
  on every singleton depending on it, measured directly off the plan.
  `warmup()` gates on the singletons it would construct, the existing rule
  applied to a set of keys rather than to one.

- **A single `check: Callable[[T], object]` signature binds `T` to the
  factory's declared return type, which is wrong for four provider shapes.**
  Full measurement and fix restated above under "The `bind` overload defect".

- **A decorated singleton is two singleton nodes.** After
  `bind(Config).decorate(Config, Loud)`, the plan holds `Config
  (undecorated)` and `Config`, both singletons. Warming both is idempotent —
  building the public node builds the inner one as its parameter — and a
  generator singleton warmed twice opens once and closes once, measured
  through `close()`.

## Named-scopes decision

Recorded in `specs/2026-08-28-roadmap-1.0-design.md` (`b459d89`) and reasoned
in full in `specs/2026-08-31-step-4-warmup-health-design.md`'s "Custom named
scopes — rejected" section.

**Criterion.** The roadmap admits named scopes only if Step 3 or Step 4
surfaces a concrete use case the three fixed scopes (`SINGLETON`, `SCOPED`,
`TRANSIENT`) cannot express.

**Decision: rejected.** Neither step surfaced such a case. Step 3 shipped
aliasing, optional dependencies, collection injection, generic keys, and the
`provides` repair — all statements about what a key resolves to, none about a
lifetime the three fixed scopes cannot express. Step 4 cycle 1 (decoration)
was the one place a fourth lifetime could plausibly have been needed — a
wrapper could in principle outlive or be outlived by what it wraps — and the
design measured that it must not: every identified use wants the wrapper to
live exactly as long as the value it decorates. Step 4 cycle 2 (this one)
confirms it: warmup partitions the plan by `Scope.SINGLETON` alone, and
health checks run against whatever lifetime their binding already has. Not
revisited before 1.0.

## Benchmarks

```console
$ uv run --group bench pytest benchmarks --benchmark-only
23 passed in 19.64s
```

| Case | Mean |
| --- | ---: |
| `test_resolve_a_singleton_through_a_two_deep_decoration_chain` | 2.1846 us |
| `test_resolve_a_cached_singleton` | 2.2124 us |
| `test_resolve_a_cached_singleton_through_an_alias` | 4.4787 us |
| `test_call_through_an_inject_wrapper` | 7.1832 us |
| `test_resolve_an_async_singleton` | 20.4643 us |
| `test_resolve_a_collection[10]` | 22.5160 us |
| `test_resolve_a_transient_chain` | 43.4174 us |
| `test_resolve_a_collection[100]` | 159.2778 us |
| `test_open_and_close_a_scope` | 234.7579 us |
| `test_freeze_a_chain[10]` | 466.1812 us |
| `test_freeze_a_chain_of_generic_keys[10]` | 838.9590 us |
| `test_freeze_a_chain_with_every_node_decorated[10]` | 1,154.0123 us |
| `test_export_a_large_graph_as_dot` | 2,676.7727 us |
| `test_freeze_a_chain[100]` | 4,367.7477 us |
| `test_build_the_graph_view` | 5,555.4300 us |
| `test_explain_a_deep_chain` | 7,931.8106 us |
| `test_freeze_a_chain_of_generic_keys[100]` | 8,261.9137 us |
| `test_freeze_a_chain_with_every_node_decorated[100]` | 11,151.1989 us |
| `test_explain_a_deep_chain_with_every_node_decorated` | 21,723.7628 us |
| `test_freeze_a_chain[1000]` | 44,673.6185 us |
| `test_warmup_a_chain` | 62,572.0068 us |
| `test_freeze_a_chain_of_generic_keys[1000]` | 104,233.3590 us |
| `test_freeze_a_chain_with_every_node_decorated[1000]` | 114,403.7324 us |

`test_warmup_a_chain` is the only new case this cycle
(`git log -p d2b8ceb..HEAD -- benchmarks/` shows exactly this one function
added, none removed). Every other case has a directly comparable figure in
`specs/evidence/2026-08-31-step-4-decoration-conditional.md`; none shows an
order-of-magnitude change, consistent with this cycle touching no line in
`construct.py` and adding no new `ProviderShape`.

The repository commits no benchmark baseline, so a "no regression" claim for
the pre-existing cases is made by the CI benchmark job, which measures base
and head back-to-back on one runner, not by this local, single-host run.

## Mutation gate

**Not run locally for this pass.** `[tool.mutmut] only_mutate` in
`pyproject.toml` is `["depin/_core/*.py"]` — every module under
`depin/_core/`, not a changed-modules subset — so a local `uv run mutmut run`
is the full mutant matrix regardless of how small this cycle's ten-module
diff is. Prior evidence
(`specs/evidence/2026-08-30-step-2-diagnostics.md`,
`specs/evidence/2026-08-31-step-3-provides-aliasing.md`,
`specs/evidence/2026-08-31-step-4-decoration-conditional.md`) records that
same full run taking tens of minutes and its baseline collection as fragile
under host CPU contention. Re-running it here would not measure anything
scoped to this cycle's ten changed modules; it would re-measure the whole
package under exactly the conditions already documented as unreliable.

The CI `mutation` job (`.github/workflows/mutation.yml`, path filter
`depin/_core/**`) triggers on this branch's changes and is the authority for
this gate. It is left to run in CI rather than reproduced locally, and no
score is recorded here in its place.
