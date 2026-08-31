# Step 3, cycle 1 verification evidence

Date: 2026-08-31

Baseline commit (`main`): `a974339128f916a438f16af236d4243591864ddf`
Measured implementation commit (this branch): `2d7f618b8e69dc3ab6134ed4977a98300cea5b9e`

This document covers Steps 1, 2, 4, and 5 of the Task 7 brief only. Step 3
(the mutation gate) and Step 6 (push, pull request) are out of scope for this
pass; see "Mutation gate" below for the reason Step 3 was not run locally.

The five repository gates, coverage, suppression counts, and benchmarks below
ran against a clean working tree, with `git status --short` empty before and
after every command.

## Gate sequence

```console
$ uv run ruff format
119 files left unchanged
EXIT=0

$ uv run ruff check
All checks passed!
EXIT=0

$ uv run basedpyright
0 errors, 0 warnings, 0 notes
EXIT=0

$ uv run mypy
Success: no issues found in 76 source files
EXIT=0

$ uv run pytest
531 passed, 6 skipped in 11.73s
EXIT=0

$ uv run --group docs mkdocs build --strict
INFO    -  Documentation built in 2.55 seconds
EXIT=0
```

The docs command printed Material for MkDocs' upstream MkDocs 2.0 advisory
banner, the same banner recorded in the Step 2 evidence; no MkDocs
diagnostic, exit 0. `uv run ruff format` left the tree unchanged, so no
revert was needed.

None of the six gates resolves an external link or a documentation anchor:
`mkdocs build --strict` fails on a broken internal `.md` reference, not on a
dead fragment in an absolute URL. That is how a `README.md` bullet kept
pointing at a `docs/support-policy.md` section this cycle deleted while all six
stayed green.

## Coverage

```console
$ uv run pytest --cov=depin --cov-report=term-missing
...
Name                         Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------
depin/__init__.py               14      0      0      0   100%
depin/_core/__init__.py          0      0      0      0   100%
depin/_core/bindings.py         50      0      4      0   100%
depin/_core/construct.py        49      0     22      1    99%   72->exit
depin/_core/container.py        11      0      0      0   100%
depin/_core/diagnostics.py      61      0      4      0   100%
depin/_core/frozen.py          223      4     86      7    96%   438, 445->447, 478, 485->487, 510->514, 549, 564
depin/_core/graph.py           167      0     72      0   100%
depin/_core/injection.py        39      0     16      1    98%   59->58
depin/_core/introspect.py       60      1     32      3    96%   42, 69->67, 72->67
depin/_core/markers.py          55      0      4      0   100%
depin/_core/overrides.py        23      0      4      0   100%
depin/_core/providers.py       104      1     48      1    99%   165
depin/_core/registry.py          8      0      0      0   100%
depin/_core/render.py          108      0     54      0   100%
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
depin/_core/spec.py             76      0      2      0   100%
depin/_core/teardown.py         45      0     14      2    97%   53->exit, 77->exit
depin/_core/typeguards.py       50      0     16      0   100%
depin/errors.py                 11      0      0      0   100%
depin/ext/__init__.py            0      0      0      0   100%
depin/ext/fastapi.py            33      0      6      0   100%
------------------------------------------------------------------------
TOTAL                         1420      9    458     18    99%
Required test coverage of 95.0% reached. Total coverage: 98.56%
531 passed, 6 skipped in 27.52s
EXIT=0
```

Total coverage 98.56%, above the 95% floor.

The six modules this cycle changed
(`git diff a974339 HEAD --stat -- depin/_core/*.py`) are `bindings.py`,
`construct.py`, `markers.py`, `providers.py`, `spec.py`, and `typeguards.py`.
`frozen.py`, `graph.py`, `diagnostics.py`, and `render.py` show no diff
against `main` — confirmed with `git diff a974339 HEAD --stat` over each —
matching the design's claim that the alias feature needed no change there.

Of the six changed modules, four are at 100% line and branch coverage
(`bindings.py`, `markers.py`, `spec.py`, `typeguards.py`). Two carry an
uncovered arc, and both are pre-existing:

- **`depin/_core/construct.py`, branch `72->exit`.** Not a gap this cycle
  introduced, and not specific to the alias arm. `sync()` dispatches on a
  `match spec.shape` with no wildcard case, so coverage records a fall-through
  arc from the last `case` line to the function exit — the arc taken when no
  arm matches, unreachable without an out-of-range `ProviderShape` value.
  Line 72 is that last `case` line only because `ALIAS` was appended after the
  async arm. `main` at `a974339` carries the identical arc at its own last
  `case` line: a detached worktree was built (`uv sync --no-default-groups`)
  and measured
  (`uv run coverage run -m pytest -q && uv run coverage report -m --include='*/construct.py'`),
  giving `depin/_core/construct.py 47 0 20 1 99% Missing 66->exit`, where line
  66 is `case ProviderShape.ASYNC_FUNCTION | ...`, the last arm before `ALIAS`
  existed. The arc is structural to the `match`; the alias arm moved its line
  number and nothing else.
- **`depin/_core/providers.py`, line 165.** This is the `return None` inside
  `unwrap_container_type` for an empty `get_args(annotation)`. Confirmed
  pre-existing: a detached worktree at `main` (`a974339`) was built
  (`uv sync --no-default-groups`) and measured
  (`uv run coverage run -m pytest -q && uv run coverage report -m --include='*/providers.py'`),
  giving `depin/_core/providers.py 101 1 46 1 99% Missing 143` — the same
  `return None` line, at its pre-alias line number. `git diff a974339 HEAD --
  depin/_core/providers.py` shows only an inserted alias branch in
  `_record_to_spec`, with `unwrap_container_type` untouched. Not a finding
  introduced by this cycle.

No other changed module has an uncovered line or branch.

## Suppression count

**The shipped package holds exactly three suppressions, and this cycle adds
none.** `grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin` returns
`frozen.py:116`, `frozen.py:139`, and `markers.py:129`, byte-identical to `main`
at `a974339` in file, line, and text — verified line by line with
`git show a974339:depin/_core/frozen.py | grep -n ignore` and the same for
`markers.py` against the current tree. No suppression was added to `depin/` by
the `provides` signature change or by aliasing.

Everything below is supporting detail: the counts under the wider scopes the
brief's command covers, and the per-file diff behind them.

Command exactly as specified, scoped to `depin` and `examples`:

```console
$ grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin examples | wc -l
5
```

The five remaining occurrences:

```
depin/_core/frozen.py:116
depin/_core/frozen.py:139
depin/_core/markers.py:129
examples/fastapi_app/main.py:43
examples/fastapi_app/main.py:47
```

The same command against `main` at `a974339` (files read with
`git show a974339:<path>`, since checking out `main` in place would disturb
the working tree under verification):

```
depin/_core/frozen.py: 2
depin/_core/markers.py: 1
examples/fastapi_app/main.py: 2
examples/testing/main.py: 1
TOTAL = 6
```

Measured delta on the exact scope the command covers: 6 to 5, one fewer. The
figure is an artefact of the command's own directory list, not a shortfall
against the design. The three suppressions the design names as removed are
`examples/testing/main.py:15`,
`tests/unit/test_resolution.py:41`, and `tests/typing/test_conformance.py:138`;
two of the three live under `tests/`, which this command does not scan. Only
the `examples/testing/main.py` removal is visible in the `depin examples`
scope, which is exactly the one-fewer measured above.

Widening the same command to include `tests` gives the fuller picture:

```console
$ grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin examples tests | wc -l
30   # HEAD
31   # main at a974339, counted the same way via `git show a974339:<path>`
```

Per-file diff between `main` and HEAD, restricted to files whose count
changed:

| File | main | HEAD | Change |
| --- | ---: | ---: | --- |
| `examples/testing/main.py` | 1 | 0 | `type-abstract` suppression removed |
| `tests/typing/test_conformance.py` | 1 | 0 | `type-abstract` suppression removed |
| `tests/unit/test_resolution.py` | 2 | 1 | `type-abstract` suppression removed |
| `tests/unit/test_markers.py` | 0 | 1 | new: `provides('Store')  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]`, exercising the new runtime guard on a non-class argument — the same sanctioned "feed a runtime guard a statically invalid value" pattern already used at `tests/unit/test_resolution.py:31` |
| `tests/integration/test_fastapi_ext.py` | 3 | 4 | new: `# pyright: ignore[reportUnusedFunction]` on a fourth route handler, the same pre-existing pattern applied to a new route that resolves a dependency through an alias |

All three suppressions the design names as removed are confirmed removed,
individually, by file and line. The net repo-wide count (`depin examples
tests`) moves by only one (31 to 30) because two ordinary, unrelated
suppressions were added for testing the new runtime guard and the new
FastAPI route — not because fewer than three `type-abstract` suppressions
were removed.

`type-abstract` occurrence check:

```console
$ grep -rn "type-abstract" --include='*.py' --include='*.md' . --exclude-dir=.venv --exclude-dir=site --exclude-dir=.git
```

Every match is under `specs/`, the historical and planning record:
`specs/2026-08-28-roadmap-1.0-design.md`,
`specs/2026-08-31-step-3-provides-aliasing-design.md`,
`specs/plans/2026-08-31-step-3-provides-aliasing.md`, and this file, which
becomes a fourth match once committed. No match under `depin`, `examples`,
`tests`, or `docs`. No `type-abstract` suppression remains anywhere in the
shipped code.

## The `provides` signature: checker measurements

Restated from `specs/2026-08-31-step-3-provides-aliasing-design.md`, not
re-derived for this pass.

| Signature | mypy | basedpyright |
| --- | --- | --- |
| `type[A]`, `A` a type variable | `type-abstract` on both a `Protocol` target and an ABC target | clean |
| `type[A] \| str` | clean | clean |
| `type[object]` | clean | clean |

The roadmap's third option, making `A` load-bearing via
`__call__[C: A]`, is refuted: mypy rejects every class passed to it,
including one that satisfies the target (`Value of type variable "C" of
"__call__" of "_ProvidesDecorator" cannot be "Good"`), and basedpyright
rejects the declaration itself (`TypeVar constraint type cannot be
generic`). `type[object]` was adopted over the clean union because `A` is
observable in no return type a consumer can reach — `_ProvidesDecorator` is
private and unexported — so the union's only function would be a `str`
member the function rejects at runtime, advertising a parameter shape it
does not accept.

## Benchmarks

```console
$ uv run --group bench pytest benchmarks --benchmark-only
12 passed in 9.27s
```

| Case | Mean |
| --- | ---: |
| `test_resolve_a_cached_singleton` | 2.0614 us |
| `test_resolve_a_cached_singleton_through_an_alias` | 4.3475 us |
| `test_call_through_an_inject_wrapper` | 6.9701 us |
| `test_resolve_an_async_singleton` | 19.9110 us |
| `test_resolve_a_transient_chain` | 43.4455 us |
| `test_open_and_close_a_scope` | 217.3388 us |
| `test_freeze_a_chain[10]` | 383.0172 us |
| `test_export_a_large_graph_as_dot` | 2,665.5191 us |
| `test_freeze_a_chain[100]` | 3,636.4913 us |
| `test_build_the_graph_view` | 5,065.8070 us |
| `test_explain_a_deep_chain` | 7,465.0199 us |
| `test_freeze_a_chain[1000]` | 36,261.6563 us |

`test_resolve_a_cached_singleton` (2.0614 us) against
`test_resolve_a_cached_singleton_through_an_alias` (4.3475 us): the
difference is the alias hop — one extra `ProviderSpec` lookup and dispatch
through the `ALIAS` shape before reaching the same cached singleton. The
direct path's mean (2.0614 us) sits within noise of the Step 2 evidence's own
measurement of the same case (2.09 us), confirming the direct resolution
path is unchanged by this cycle, consistent with
`git diff a974339 HEAD -- depin/_core/frozen.py depin/_core/scope.py depin/_core/construct.py`
showing `construct.py`'s only change is the additive `ALIAS` match arm, and
`frozen.py`/`scope.py` untouched.

The repository commits no benchmark baseline (`benchmarks/` has no checked-in
JSON), so a "no regression" claim for the eight pre-existing cases is made by
the CI benchmark job, which measures base and head back-to-back on one
runner, not by this local, single-host run.

## Alias semantics: empirical validation

Restated from `specs/2026-08-31-step-3-provides-aliasing-design.md`'s
"Semantics" section. Three forms were probed against the real
`FrozenContainer` before the shipped one was adopted:

- Registering the target's own `ProviderSpec` under a second identity gives
  one instance, but the alias never enters `ResolutionPlan.order`, so
  `graph()`, `explain()`, `dot()`, and `mermaid()` cannot see it — a feature
  invisible to the diagnostics surface Step 2 built.
- Copying the target's `ProviderSpec` under the alias key gives **two**
  instances: the singleton cache is keyed on `(spec.key, spec.tag)`, and the
  copy carries a different key, so the "without a second singleton"
  requirement fails outright.
- The adopted form — a transient node whose single dependency is its target,
  with no cache entry of its own — gives one instance
  (`di[Store] is di[PostgresStore]`, and the same object again when reached
  as another provider's dependency), and `_check_captive` reports
  `Service -> Store -> PostgresStore` for a singleton aliased onto a scoped
  target. This is the only one of the three that is both correct (one
  instance, one teardown) and visible to `graph()`/`explain()`.

## Mutation gate

Not run for this pass. `[tool.mutmut] only_mutate` in `pyproject.toml` is
`["depin/_core/*.py"]` — every module under `depin/_core/`, not a
changed-modules subset — so a local `uv run mutmut run` is the full
1,491-mutant matrix regardless of how small this cycle's diff is. The Step 2
evidence (`specs/evidence/2026-08-30-step-2-diagnostics.md`) records that
same full run taking tens of minutes and needing a temporary, reverted
`--timeout` change to get a clean baseline collection past host CPU
contention. Re-running it here would not measure anything scoped to this
cycle's six changed modules; it would re-measure the whole package.

The CI `mutation` job (`.github/workflows/mutation.yml`, path filter
`depin/_core/**`) triggers on this branch's changes and is the authority for
this gate. It is left to run in CI rather than reproduced locally.

## Scope note

Two steps of the Task 7 brief were not performed for this pass. Step 3, the
mutation gate, is deferred to the CI `mutation` job, which is its authority
here; the reason a local run measures nothing scoped to this cycle is recorded
under "Mutation gate" above. Step 6, pushing the branch and opening the pull
request, is handled separately from this record. Everything else in this
document was measured locally against a clean working tree.
