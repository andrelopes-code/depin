# Step 4, cycle 2 verification evidence

Date: 2026-08-31

Baseline commit (`main`, 0.11.0): `d2b8ceb31b25ca88b0c279676fe54629390cfd9c`
Measured commit (this branch): `bfa4c705afff1708818a782b60512774b34e12e3`

This document covers Steps 1 through 7 of the Task 6 brief, plus the Task 6
addition (unifying the two examples' key-rendering helpers). All commands
below were run against the working tree at the measured commit; the evidence
file itself adds no other tracked path, so every claim about the tree remains
true once this file lands.

The full commit range this cycle covers, oldest first: `e59cacb` (design),
`29a5f71` (plan), `5bc34f5`, `c322034`, `3958c98`, `f130cd6`, `448b7dd`,
`a80ad2a`, `e10b843`, `b6bd53b` (implementation and docs), `7724d64`
(this task's examples fix), `b459d89` (this task's roadmap amendment).

A final whole-branch review against PR #46 (base `d2b8ceb`) found twelve
further defects, closed in one wave: `092de12`, `f484249`, `f701e6a`,
`76dd6bc`, `f6e768c`, `2fae869`, `bfa4c70`. That wave is covered under "Final
fix wave" below; every section after it that reports a number or a command's
output has been re-run against `bfa4c70` and reflects that tree, not
`b459d89`.

## Final fix wave (PR #46 review)

Twelve findings from a final whole-branch code review, applied together.

1. **Decorator check claim.** `docs/guide/operations.md` and the design
   spec's Semantics table both claimed a decorator can declare its own
   `check=`; `decorate()` has no such parameter, and the spec's Out of scope
   table already forbade one. Both corrected to state the real rule: a check
   on a decorated binding verifies the undecorated value and is keyed
   `Underlying(key, 0)`; `decorate()` takes no `check=`.
2. **`print()` in `test_health.py`.** Removed the live `print(excinfo.value)`
   and renamed
   `test_health_prints_the_refusal_message_naming_every_pending_key` to
   `test_health_refusal_message_names_every_pending_key`.
3. **T20 enforcement.** `[tool.ruff.lint] select` gains `"T20"`.
   `[tool.ruff.lint.per-file-ignores]` exempts `examples/**`,
   `scripts/check_mutation_threshold.py`, and `benchmarks/compare.py` — the
   only places printing is the file's purpose. Running `uv run ruff check`
   with the rule on turned up two more live prints, pre-existing and
   unrelated to this cycle's own work: `tests/unit/test_conditional.py`'s
   `test_explain_and_freeze_report_an_inactive_key_alike` printed
   `freeze_text` and `explain_text` for debugging; both calls deleted, the
   assertions they preceded are unaffected.
4. **Overload typing pinned for every shape.** `tests/typing/test_conformance.py`
   guarded the seven-overload `check=` fix only for `type[T]`. Added six
   `assert_type` cases — generator, async generator, `async def`,
   `@contextmanager`, `@asynccontextmanager`, and plain factories — each
   binding `check`'s parameter to the produced value's type. All pass under
   `basedpyright --strict` and `mypy --strict`.
5. **Async error-separation test.** Added
   `test_ahealth_propagates_a_resolution_error_instead_of_reporting_it`: a
   checked provider whose constructor raises, asserting the exception reaches
   the caller from `ahealth()` rather than becoming a `HealthResult`.
   Mutation proof: wrapping `ahealth()`'s `await self._aresolve_any(...)` in
   a `try`/`except Exception` that turns the error into a `HealthResult`
   made the new test fail with `Failed: DID NOT RAISE RuntimeError`;
   reverting the wrap restored the pass. The mutation was never committed.
6. **Check-property tautology.** `test_checks_reports_exactly_the_specs_the_plan_marked_checked`
   derived `expected` from `plan.order`'s `spec.check is not None` — exactly
   the predicate `checks()` itself filters on — so it could not detect a
   check dropped by `graph._with_async_flags` or `decoration._chain`.
   Renamed to `test_checks_reports_exactly_the_declared_checks` and rewritten
   to derive `expected` from `case.checks` alone (`_expected_checked_keys`),
   mapping each drawn index to the key it was registered under —
   `Underlying(key, 0)` for a decorated index. `_materialize` gained a
   `_materialize_with_keys` counterpart returning the per-index key objects
   the property needs but the container itself does not expose. A duplicated
   index is not represented in `_expected_checked_keys`: `_materialize`
   always binds it twice, which `Container.freeze()` always rejects as
   `DuplicateProviderError` before the plan exists, so the comparison never
   runs for that case. Mutation proof: changing `check=spec.check` to
   `check=None` in `graph._with_async_flags` made the rewritten property fail
   immediately, with a Hypothesis-shrunk counterexample
   (`GraphCase(size=3, registered=(False, False, True), checks=frozenset({2}), ...)`)
   showing `checks()` returning nothing where one check was declared;
   reverting the mutation restored the pass. The mutation was never
   committed.
7. **`warmup()` under an active override.** Added
   `test_warmup_honours_an_active_override`: warms inside
   `with di.override(Config, FakeConfig()):` and asserts the overridden
   value is what `warmup()` constructed.
8. **`awarmup`'s cached branch.** Added
   `test_a_second_awarmup_reports_everything_cached`: two `await
   di.awarmup()` calls; the second reports the singleton under `cached`,
   covering `frozen.py`'s `awarmup` cache-hit branch — lines 305-306 before
   this wave, now 308-309, shifted by the three-line `Raises:` block Fix 11
   adds to `awarmup`'s docstring above it.
9. **`as_check`'s raise, tested directly.** Added
   `test_as_check_raises_for_a_non_callable_check` to
   `tests/unit/test_typeguards.py`, calling `as_check(42, Store)` and
   asserting `InvalidProviderError` naming "is not callable". Note for the
   record: the precedent the task description named,
   `as_alias_target`/`as_collection_members`, is actually covered in
   `tests/unit/test_construct.py` (via `construct.sync` over a hand-built
   `ProviderSpec`), not in `test_typeguards.py` — no such tests existed there
   before this fix. The new test instead follows `test_typeguards.py`'s own
   existing convention of calling a `typeguards` function directly.
10. **Singular/plural refusal wording.** `warmup()`'s and `health()`'s
    refusal messages read "they require" even for one key. Both now choose
    the pronoun (and, for `health()`, the "check"/"checks" noun) by the
    count of pending keys. Printed before writing the docs, on this tree:
    - `warmup() cannot construct Pool: it requires async resolution. Call awarmup() instead.`
    - `warmup() cannot construct First, Second: they require async resolution. Call awarmup() instead.`
    - `health() cannot run the check for Pool: it requires an event loop, because the provider is async or the check is. Call ahealth() instead.`
    `docs/guide/operations.md`'s two doctests updated to match verbatim.
11. **Missing docstring sections.** `HealthCheck` and `HealthResult` gained
    an `Example:`, executed by the doctest gate. `awarmup` gained `Raises:
    CircularDependencyError`; `ahealth` gained `Raises: OutsideScopeError`
    and `CircularDependencyError` — both reachable through `_aresolve_any`,
    the same resolution path `aresolve()` documents those two exceptions
    for. Neither method can raise `AsyncInSyncContextError`, since both
    drive async providers directly, so neither Raises: section repeats it.
12. **Warmup benchmark timed `freeze()` too.** `test_warmup_a_chain` built
    and froze the container inside the timed callable. Rewritten to freeze a
    fresh container per round in `benchmark.pedantic`'s `setup` (outside the
    timed window), timing `warmup()` alone; `Benchmark`'s local `Protocol`
    gained a `pedantic` method. A single frozen container was rejected: a
    warmed container caches every singleton, so a second `warmup()` on the
    same one would measure the cached branch, not construction — matching
    the design spec's own semantics table entry for a repeated call. See
    "Benchmarks" below for the isolated figure.

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
160 files left unchanged
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
821 passed, 6 skipped in 18.94s
EXIT=0

$ uv run --group docs mkdocs build --strict
INFO    -  Documentation built in 3.31 seconds
EXIT=0
```

Re-run against `bfa4c70`, the final fix wave's tip. No `.py` file was added
by this wave (`git diff --stat cd6f463 -- '*.py'` names only modifications);
the `159` vs `160` file count between this run and the one above reflects
`ruff format`'s own file discovery on this host at the two points in time,
not a change this cycle made to what is tracked.

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

Re-measured after the final fix wave (`bfa4c70`). Both lines the wave set out
to close, `frozen.py`'s `awarmup` cache-hit branch and `typeguards.py`'s
`as_check` raise, no longer appear in `Missing`:

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
depin/_core/frozen.py          269      4    100      7    97%   591, 598->600, 631, 638->640, 663->667, 705, 723
depin/_core/graph.py           172      0     72      0   100%
depin/_core/health.py           61      0      6      0   100%
depin/_core/injection.py        39      0     16      1    98%   59->58
depin/_core/introspect.py       70      1     36      3    96%   43, 71->69, 74->69
depin/_core/markers.py          59      0      6      0   100%
depin/_core/overrides.py        23      0      4      0   100%
depin/_core/providers.py       205      1    108      1    99%   413
depin/_core/registry.py          8      0      0      0   100%
depin/_core/render.py          113      0     56      0   100%
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
depin/_core/spec.py            131      0      6      0   100%
depin/_core/teardown.py         45      0     14      2    97%   53->exit, 77->exit
depin/_core/typeguards.py      105      0     42      0   100%
depin/_core/warmup.py           23      0      2      0   100%
depin/errors.py                 11      0      0      0   100%
depin/ext/__init__.py            0      0      0      0   100%
depin/ext/fastapi.py            33      0      6      0   100%
------------------------------------------------------------------------
TOTAL                         1846      9    604     18    99%
Required test coverage of 95.0% reached. Total coverage: 98.90%
821 passed, 6 skipped in 40.11s
EXIT=0
```

Every remaining miss is one already attributed below (`frozen.py`'s seven
pre-existing entries, shifted by the fix wave's own docstring insertions;
`providers.py:413`; `construct.py`, `introspect.py`, `injection.py`,
`teardown.py`, all pre-existing and untouched by this cycle) plus
`scope.py`'s `_Flight.wait_sync` line, the same roughly-one-in-two
thread-scheduling branch prior evidence in this file already recorded as
flaky rather than a regression — `scope.py` is untouched by this cycle (see
"Untouched modules" below). Three consecutive runs on this tree missed line
69 each time; that is a sample of the coin, not evidence the line's coverage
changed. 98.90% is above the 95% floor.

`frozen.py`'s seven remaining pre-existing miss entries moved from `582,
589->591, 622, 629->631, 654->658, 696, 714` (recorded earlier in this file,
against `b459d89`) to `591, 598->600, 631, 638->640, 663->667, 705, 723` — a
uniform +9-line shift, matching the two `Raises:` blocks the fix wave adds to
`awarmup` (3 lines) and `ahealth` (6 lines), both above every one of these
lines in the file. None of the shifted lines sit inside `awarmup`, `ahealth`,
`checks`, or `health`; they remain in `_resolve_cached_sync`, `_resolve_async`,
`_is_constructing`, `_resolve_params_sync`, and `_resolve_params_async`, as
attributed below.

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

- **`depin/_core/frozen.py`, lines 305-306 at `b459d89` — closed by the final
  fix wave's Fix 8.** `git blame` attributed both to `c3220344` (`feat:
  construct every singleton with warmup`): the `if self._is_cached(spec):
  cached.append(spec); continue` branch inside `awarmup`, taken when a
  singleton `awarmup` would build was already constructed by an earlier
  `warmup()`/`awarmup()` call. `tests/unit/test_warmup.py`'s
  `test_a_second_awarmup_reports_everything_cached` (Fix 8) now exercises it;
  the branch is at lines 308-309 on the current tree (the fix wave's own
  `Raises:` addition to `awarmup`'s docstring shifts it by 3) and no longer
  appears in `Missing`, confirmed in "Coverage" above.

- **`depin/_core/frozen.py`, lines 591, branches `598->600`, line 631,
  branches `638->640`, `663->667`, and lines 705 and 723 (current tree).**
  Pre-existing, and still the same statements/arcs the design cycle
  measured — this is the same bullet as originally recorded, with the fix
  wave's own further line shift applied. The worktree measurement at
  `d2b8ceb` gives `depin/_core/frozen.py 229 4 90 7 97% Missing 442,
  449->451, 482, 489->491, 514->518, 556, 574`; `b459d89` (this cycle's own
  work) shifted every one by +140 (582, 589->591, 622, 629->631, 654->658,
  696, 714, recorded earlier in this file); the final fix wave's `Raises:`
  additions to `awarmup` (3 lines) and `ahealth` (6 lines) in
  `depin/_core/frozen.py`, both above every line in this bullet, shift them a
  further uniform +9: 582+9=591, 589→598/591→600, 622+9=631, 629→638/631→640,
  654→663/658→667, 696+9=705, 714+9=723 — exactly the current `Missing` list.
  None of these lines sit inside `_is_cached`, `warmup`, `awarmup`, `checks`,
  `health`, or `ahealth`; all five belong to `_resolve_cached_sync`,
  `_resolve_async`, `_is_constructing`, `_resolve_params_sync`, and
  `_resolve_params_async`, none of which either cycle's diff touches.

- **`depin/_core/providers.py`, line 413.** Pre-existing. The worktree
  measurement at `d2b8ceb` gives `depin/_core/providers.py 200 1 106 1 99%
  Missing 394`; line 394 there and line 413 here are both the `return None`
  inside `unwrap_container_type`, taken when `get_args(annotation)` is empty.
  `providers.py` grows by 19 lines this cycle (carrying `check` from record to
  spec); 394+19=413, and `unwrap_container_type` itself is outside the diff.
  Untouched by the final fix wave.

- **`depin/_core/typeguards.py`, line 195 at `b459d89` — closed by the final
  fix wave's Fix 9.** The worktree measurement at `d2b8ceb` gives
  `depin/_core/typeguards.py 101 0 40 0 100%` — no miss. Line 195 is the
  `raise InvalidProviderError(...)` branch of `as_check`, taken when a
  declared `check` is not callable; its docstring still states the branch is
  unreachable through the public API, because `Container.freeze()` already
  rejects a non-callable `check` before `as_check` runs. Fix 9 adds
  `tests/unit/test_typeguards.py::test_as_check_raises_for_a_non_callable_check`,
  calling `as_check(42, Store)` directly — the same way the module's other
  narrowing functions are tested, bypassing the public API precisely because
  the branch is unreachable through it. `depin/_core/typeguards.py` is at
  100% line and branch coverage on the current tree, confirmed in "Coverage"
  above.

- **`depin/_core/construct.py`, branch `75->exit`; `depin/_core/scope.py`,
  branches `88->87`, `107-109`, `113->exit` (plus line 69, observed missed on
  every run against the current tree — see "Coverage" above);
  `depin/_core/introspect.py`, line 43 and branches `71->69`, `74->69`;
  `depin/_core/injection.py`, branch `59->58`; `depin/_core/teardown.py`,
  branches `53->exit`, `77->exit`.** None of these five modules changed this
  cycle or the final fix wave (empty diff against `d2b8ceb`, confirmed under
  "Untouched modules" below), so their misses are the same statements and
  arcs present on `main`, unmoved. The worktree measurement at `d2b8ceb`
  reproduces every one at the identical line and branch numbers.

Both misses the design cycle introduced are now closed: `frozen.py`'s
`awarmup` already-cached branch (Fix 8) and `typeguards.py`'s `as_check`
raise (Fix 9). The current tree's only misses are pre-existing ones untouched
by either the design cycle or the final fix wave, plus `scope.py`'s
already-documented flaky line. 98.90% is comfortably above the 95% floor.

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

Re-run against `bfa4c70`, the final fix wave's tip: identical output, same
two lines at 127 and 150. The wave's `Raises:` additions to `awarmup` and
`ahealth` land after both suppressions in the file, so neither line moves.
Still exactly three, still none added.

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

The final fix wave (`bfa4c70`) touches none of the eleven modules above, nor
`graph.py` beyond what is already shown, nor `bindings.py` at all — confirmed
by `git diff --stat cd6f463 -- <same path list>`, empty. Its `depin/`
changes are confined to `frozen.py`, `health.py`, and `warmup.py`, covered
under "Final fix wave" above.

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

Re-run against `bfa4c70`, after Fix 12 rewrote `test_warmup_a_chain` to time
`warmup()` alone (`benchmark.pedantic` with a fresh `freeze()` per round in
`setup`, outside the timed window) instead of `freeze()` plus `warmup()`
together:

```console
$ uv run --group bench pytest benchmarks --benchmark-only
23 passed in 22.14s
```

| Case | Mean |
| --- | ---: |
| `test_resolve_a_singleton_through_a_two_deep_decoration_chain` | 2.1497 us |
| `test_resolve_a_cached_singleton` | 2.2040 us |
| `test_resolve_a_cached_singleton_through_an_alias` | 4.3603 us |
| `test_call_through_an_inject_wrapper` | 6.9127 us |
| `test_resolve_an_async_singleton` | 20.1513 us |
| `test_resolve_a_collection[10]` | 21.6292 us |
| `test_resolve_a_transient_chain` | 43.0597 us |
| `test_resolve_a_collection[100]` | 154.6166 us |
| `test_open_and_close_a_scope` | 227.1355 us |
| `test_freeze_a_chain[10]` | 452.5388 us |
| `test_freeze_a_chain_of_generic_keys[10]` | 805.2872 us |
| `test_freeze_a_chain_with_every_node_decorated[10]` | 1,095.5650 us |
| `test_export_a_large_graph_as_dot` | 2,659.4799 us |
| `test_freeze_a_chain[100]` | 4,211.2316 us |
| `test_build_the_graph_view` | 5,307.8598 us |
| `test_explain_a_deep_chain` | 7,685.2405 us |
| `test_freeze_a_chain_of_generic_keys[100]` | 7,924.3394 us |
| `test_freeze_a_chain_with_every_node_decorated[100]` | 11,240.8021 us |
| `test_warmup_a_chain` | 15,734.4638 us |
| `test_explain_a_deep_chain_with_every_node_decorated` | 22,412.2398 us |
| `test_freeze_a_chain[1000]` | 44,116.7890 us |
| `test_freeze_a_chain_of_generic_keys[1000]` | 98,461.5422 us |
| `test_freeze_a_chain_with_every_node_decorated[1000]` | 119,920.1163 us |

`test_warmup_a_chain` is not comparable to its `62,572.0068 us` figure
recorded earlier in this file: that number timed `freeze()` plus `warmup()`
over a 1000-node chain together, and `freeze()` alone over the same size
(`test_freeze_a_chain[1000]`, `44,116.7890 us` here) accounts for nearly all
of it. The isolated figure, `15,734.4638 us`, is what Fix 12 exists to make
visible — a `warmup()` regression no longer hides inside the larger
`freeze()` cost it used to share a measurement with. Every other case has a
directly comparable figure either earlier in this file (unchanged in shape,
though the absolute numbers move with host load run to run) or in
`specs/evidence/2026-08-31-step-4-decoration-conditional.md`; none shows an
order-of-magnitude change, consistent with the final fix wave touching no
line in `construct.py` and adding no new `ProviderShape`.

The repository commits no benchmark baseline, so a "no regression" claim for
the pre-existing cases is made by the CI benchmark job, which measures base
and head back-to-back on one runner, not by this local, single-host run.

## Mutation gate

**Failed in CI.** The `mutation` job (`.github/workflows/mutation.yml`, PR
#46) ran `mutmut` over `depin/_core/*.py` and scored 94.3% — 2250 killed, 135
survived, 2385 total — against a 95% floor. 45 of the 135 survivors sat in
this cycle's two new modules, `depin/_core/warmup.py` and
`depin/_core/health.py`:

| Function | Survivors |
| --- | --- |
| `health.reject_async_checks` | 17 |
| `warmup.reject_async_singletons` | 10 |
| `health.run_check` | 7 |
| `health.run_check_async` | 5 |
| `warmup.warmup_report` | 4 |
| `health._outcome` | 1 |
| `health.declared_checks` | 1 |

The remaining 90 survivors sit in `typeguards`, `providers`, `overrides`,
`markers`, `introspect`, `graph`, `construct`, and `render` — pre-existing on
`main`, out of scope for this fix, and left for the roadmap.

**Cause.** `reject_async_checks` and `reject_async_singletons` build a
refusal message by choosing a noun/pronoun on the pending-key count and
joining every pending key; every existing test asserted the message with
`in` (substring) or `match=` (regex fragment) rather than `==` (the whole
string), so mutating any word, the separator, or the singular/plural branch
left the tests green. `run_check` and `run_check_async` had the same gap on
`InvalidProviderError`'s awaitable-check message, plus untested `key=`/`tag=`
propagation on the `except Exception` branch: every prior test used an
untagged binding, so `tag=spec.tag` and a mutated `tag=None` produced the
same observed result. `run_check_async`'s `is_awaitable(outcome)` guard was
untested in the one direction that matters: an async check returning
`False`. Inverting the guard leaves the coroutine unawaited, and an
unawaited coroutine object is never `is False`, so the mutant reports the
same `healthy=True` a correctly awaited `True` would — no prior test used a
`False`-returning async check to tell the two apart. `warmup_report` had the
same untested tag propagation on both `constructed=` and `cached=`.
`declared_checks` was missing a tagged-binding case for the same reason.

**Fix — tests only, `depin/` unchanged.** No behavioural gap was found;
every survivor traced to a missing assertion, not a missing check. Added to
`tests/unit/test_health.py`:

- Exact (`==`) refusal-message assertions for `reject_async_checks`, one key
  and two keys, replacing the `in`/`match=` checks; the expected text is
  built with `fmt_key` rather than hardcoded, since a class defined inside a
  test function carries that function in its own `__qualname__`.
- An exact-message assertion on the `InvalidProviderError` `run_check`
  raises for an awaitable check result.
- `test_a_raising_check_is_unhealthy_with_the_exception_on_the_result` and
  its async counterpart now bind under `tag='primary'` and assert
  `result.key`/`result.tag`, closing the untested `tag=` propagation on the
  raising branch of both `run_check` and `run_check_async`.
- `test_ahealth_gives_the_async_check_the_resolved_value`: an async check
  that records what it received, asserting it is the resolved `Service`
  instance — kills the inverted `is_awaitable` guard.
- `test_ahealth_runs_an_async_check_that_returns_false`: an async check
  returning `False`, asserting `healthy=False` — the direction that
  distinguishes an awaited result from an unawaited coroutine object.
- `test_run_check_names_the_specs_own_provider_when_the_check_is_not_callable`
  and its async counterpart: call `run_check`/`run_check_async` directly
  over a hand-built `ProviderSpec` with a non-callable `check`, asserting the
  exact `as_check` message — the only way to reach that branch, since
  `Container.freeze()` already rejects a non-callable `check` before either
  function runs.
- `test_a_check_result_carries_its_binding_tag`,
  `test_an_async_check_result_carries_its_binding_tag`,
  `test_checks_reports_the_binding_tag`: a tagged binding through
  `health()`, `ahealth()`, and `checks()`.

Added to `tests/unit/test_warmup.py`:

- Exact refusal-message assertions for `reject_async_singletons`, one key
  and two keys (`test_warmup_refuses_an_async_singleton_before_constructing_anything`,
  new `test_warmup_refusal_message_names_every_pending_singleton`), by the
  same `fmt_key` construction.
- `report.constructed`/`report.cached` strengthened from
  `[node.key for node in ...]` to full `GraphNode` equality against
  `di.graph().node(...)` in `test_warmup_constructs_every_singleton`,
  `test_warmup_reports_an_already_built_singleton_as_cached`, and
  `test_a_decorated_singleton_reports_both_nodes` — pins order, scope,
  shape, and dependencies, not just the key.
- `test_warmup_reports_the_binding_tag_on_a_constructed_node` and
  `test_warmup_reports_the_binding_tag_on_a_cached_node`: a tagged
  singleton, closing `warmup_report`'s untested `tag=` propagation on both
  tuples.

**Verification.** `uv run mutmut run '<pattern>'` accepts a mutant-name
pattern positionally, as documented; both scoped patterns below ran to
completion under mutmut 3.7.0. Mutmut's baseline collection runs the whole
`tests/unit` suite (`pytest_add_cli_args_test_selection`), which on this
host intermittently fails independently of these changes:
`tests/unit/test_graph_properties.py`'s Hypothesis property tests
occasionally exceed `pytest_add_cli_args`'s `--timeout=2` or raise
`FlakyStrategyDefinition` under load, and
`tests/unit/test_graph_render.py::test_the_exports_do_not_depend_on_the_hash_seed`
spawns a subprocess that can also exceed the 2-second timeout — both
pre-existing, unrelated to `health`/`warmup`, and consistent with this
file's prior note that a full local mutation run is fragile under host CPU
contention. Working around it locally only — raising the pytest timeout and
deselecting the two flaky tests through the `PYTEST_ADDOPTS` environment
variable, which pytest reads directly; `pyproject.toml`'s `[tool.mutmut]`
was not edited — let both scoped runs complete:

```console
$ PYTEST_ADDOPTS="--timeout=30 --deselect=tests/unit/test_graph_properties.py --deselect=tests/unit/test_graph_render.py::test_the_exports_do_not_depend_on_the_hash_seed" uv run mutmut run 'depin._core.health.*'
$ uv run mutmut results | grep 'depin\._core\.health\.' | grep -v 'not checked'
(no output — every checked health.py mutant killed)

$ PYTEST_ADDOPTS="--timeout=30 --deselect=tests/unit/test_graph_properties.py --deselect=tests/unit/test_graph_render.py::test_the_exports_do_not_depend_on_the_hash_seed" uv run mutmut run 'depin._core.warmup.*'
$ uv run mutmut results | grep 'depin\._core\.warmup\.' | grep -v 'not checked'
(no output — every checked warmup.py mutant killed)
```

Both scoped runs were repeated after each round of new tests; the first
pass over `health.*` still left 7 survivors (`run_check`'s and
`run_check_async`'s `as_check(spec.check, None)`, `key=None`/`tag=None`
mutants), and the first pass over `warmup.*` still left 4
(`warmup_report`'s `tag=None` mutants on both tuples) — both closed by the
tag- and direct-call tests listed above, then reconfirmed at zero survivors.
`mutants/` is `.gitignore`d and was not committed.

`uv run ruff format`, `uv run ruff check`, `uv run basedpyright`,
`uv run mypy`, and `uv run pytest` (no override, no deselect) all pass clean
on the final tree — `832 passed, 6 skipped`, up from `821` before this fix's
11 new tests. The CI `mutation` job remains the authority for the
whole-package score; this fix targets exactly the two modules and the 45
survivors CI attributed to them, and leaves the 90 pre-existing survivors in
other modules untouched, as scoped.
