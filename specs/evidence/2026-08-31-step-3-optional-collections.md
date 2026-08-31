# Step 3, cycle 2 verification evidence

Date: 2026-08-31

Baseline commit (`main`): `ad334828725e05c5e272c66f5cb1f8efe4d2e585` (0.8.0)
Measured implementation commit (this branch): `64df9d3a04391e831d4e1e7e5d59b672c6099b1c`

This document covers Steps 1, 2, 4, 5, and 6 of the Task 8 brief. Step 3 (the
mutation gate) is out of scope for this pass; see "Mutation gate" below for
the reason it was not run locally. Pushing the branch and opening a pull
request are handled separately from this record and are not covered here.

The evidence file itself is part of the commit it documents. Every claim
below about the working tree's state was true when measured and remains true
once this file lands: `git status --short` was empty before and after every
command in this record, and the commit that adds this file changes no other
tracked path.

## Gate sequence

```console
$ uv run ruff format
128 files left unchanged
EXIT=0

$ uv run ruff check
All checks passed!
EXIT=0

$ uv run basedpyright
0 errors, 0 warnings, 0 notes
EXIT=0

$ uv run mypy
Success: no issues found in 82 source files
EXIT=0

$ uv run pytest
594 passed, 6 skipped in 12.81s
EXIT=0

$ uv run --group docs mkdocs build --strict
INFO    -  Documentation built in 2.58 seconds
EXIT=0
```

`uv run ruff format` left the tree unchanged, so no revert was needed. The
docs command printed the same upstream Material for MkDocs 2.0 advisory
banner recorded in prior evidence files; no MkDocs diagnostic, exit 0.

While gathering the coverage evidence below, two additional plain `pytest`
runs under `--cov` surfaced an unrelated, pre-existing flake: four tests in
`tests/unit/test_graph_properties.py` —
`test_every_planned_provider_appears_as_exactly_one_node`,
`test_every_edge_either_indexes_a_node_or_is_unsatisfied`,
`test_each_export_declares_one_entry_per_node`, and
`test_explain_names_every_key_reachable_from_its_root` — occasionally raised
`hypothesis.errors.DeadlineExceeded` under CPU contention, because none of the
four carried `@settings(deadline=None)`. Checked against `main` at `ad33482`:
all four already lacked that setting there, so the flake was not introduced by
this cycle, though this cycle's wider generative model — optionals,
collections, and a synthetic consumer bound per alias and per collection —
made each example strictly more expensive and raised the odds of hitting it in
CI. All four now carry `@settings(deadline=None)`, closing the flake. It did
not appear in the gate-sequence `pytest` run recorded above, nor in either of
the two coverage runs recorded below.

## Coverage

```console
$ uv run pytest --cov=depin --cov-report=term-missing
...
Name                         Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------
depin/__init__.py               14      0      0      0   100%
depin/_core/__init__.py          0      0      0      0   100%
depin/_core/bindings.py         53      0      4      0   100%
depin/_core/construct.py        51      0     24      1    99%   75->exit
depin/_core/container.py        11      0      0      0   100%
depin/_core/diagnostics.py      63      0      4      0   100%
depin/_core/frozen.py          229      4     90      7    97%   439, 446->448, 479, 486->488, 511->515, 553, 571
depin/_core/graph.py           167      0     72      0   100%
depin/_core/injection.py        39      0     16      1    98%   59->58
depin/_core/introspect.py       70      1     36      3    96%   43, 71->69, 74->69
depin/_core/markers.py          55      0      4      0   100%
depin/_core/overrides.py        23      0      4      0   100%
depin/_core/providers.py       119      1     58      1    99%   204
depin/_core/registry.py          8      0      0      0   100%
depin/_core/render.py          111      0     56      0   100%
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
depin/_core/spec.py             94      0      4      0   100%
depin/_core/teardown.py         45      0     14      2    97%   53->exit, 77->exit
depin/_core/typeguards.py       61      0     20      0   100%
depin/errors.py                 11      0      0      0   100%
depin/ext/__init__.py            0      0      0      0   100%
depin/ext/fastapi.py            33      0      6      0   100%
------------------------------------------------------------------------
TOTAL                         1490      9    486     18    99%
Required test coverage of 95.0% reached. Total coverage: 98.63%
594 passed, 6 skipped in 28.11s
EXIT=0
```

The command was run a second time, unmodified, specifically to observe
`scope.py:69`:

```console
$ uv run pytest --cov=depin --cov-report=term-missing
...
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
...
Required test coverage of 95.0% reached. Total coverage: 98.63%
594 passed, 6 skipped in 27.24s
EXIT=0
```

Total coverage 98.63% in both runs, above the 95% floor.

`git diff ad33482 HEAD --stat -- depin/_core/*.py` names eleven modules this
cycle changed: `bindings.py`, `construct.py`, `container.py`,
`diagnostics.py`, `frozen.py`, `graph.py`, `introspect.py`, `providers.py`,
`render.py`, `spec.py`, and `typeguards.py`. No file outside `depin/_core/`
changed. Of these, `bindings.py`, `container.py`, `diagnostics.py`,
`graph.py`, `render.py`, `spec.py`, and `typeguards.py` are at 100% line and
branch coverage. `construct.py`, `frozen.py`, `introspect.py`, and
`providers.py` carry uncovered lines; `scope.py` also carries an uncovered
line but is not a module this cycle touched. Every one of them is attributed
below, checked against a detached worktree at `main`
(`ad334828725e05c5e272c66f5cb1f8efe4d2e585`), built with
`uv sync --no-default-groups` and measured with
`uv run coverage run -m pytest -q` followed by
`uv run coverage report -m --include=<pattern>`.

- **`depin/_core/construct.py`, branch `75->exit`.** Pre-existing and
  structural, confirmed known. `sync()` dispatches on `match spec.shape` with
  no wildcard arm, so coverage records the fall-through arc from the last
  `case` line to the function exit. At `ad33482` the last arm is
  `case ProviderShape.ALIAS:` on line 72, and the worktree measurement gives
  `depin/_core/construct.py 49 0 22 1 99% Missing 72->exit`. This cycle
  appends `case ProviderShape.COLLECTION:` after it, on line 75, which is why
  the arc moved from `72->exit` to `75->exit` and nothing else. The arm order
  and every other `case` line are unchanged.

- **`depin/_core/providers.py`, line 204.** Pre-existing, confirmed known.
  Line 204 is `return None` inside `unwrap_container_type`, the branch taken
  when `get_args(annotation)` is empty. The worktree measurement at `ad33482`
  gives `depin/_core/providers.py 104 1 48 1 99% Missing 165`, and line 165
  there is the identical `return None` statement. `git diff ad33482 HEAD --
  depin/_core/providers.py` shows 59 lines added for the collection key and
  `GenericAlias` support, all before this function; `unwrap_container_type`
  itself is untouched, and the line only moved.

- **`depin/_core/scope.py`, line 69 (inside `_Flight.wait_sync`).** Not a
  module this cycle changed — `git diff ad33482 HEAD -- depin/_core/scope.py`
  is empty. Line 69 is a thread-scheduling path inside `_Flight.wait_sync`
  that depends on which thread the interpreter schedules first; the worktree
  measurement at `ad33482` reproduces the identical
  `depin/_core/scope.py 233 3 74 3 98% Missing 69, 88->87, 107-109, 113->exit`.
  Both coverage runs recorded above show line 69 uncovered; running it twice,
  as instructed, did not happen to catch the run where it is covered, which
  is consistent with a roughly one-in-two rate rather than evidence against
  it — a coin that lands the same way twice in a row a quarter of the time is
  not a biased coin.

- **`depin/_core/introspect.py`, line 43 and branches `71->69`, `74->69`.**
  Pre-existing, not previously called out by name but verified the same way.
  The worktree measurement at `ad33482` gives
  `depin/_core/introspect.py 60 1 32 3 96% Missing 42, 69->67, 72->67`. Line
  42 is the early `return False` in `_wraps_async_generator`, reachable only
  if `detect_shape` called it after already confirming
  `inspect.isasyncgenfunction(source)` is true elsewhere, which it never does.
  Branches `69->67` and `72->67` are the loop-continuation arcs in
  `extract_annotated_meta` taken when a second `Token` or a second `Tag`
  appears among the same `Annotated` extras, an input combination no test
  constructs. `git diff ad33482 HEAD -- depin/_core/introspect.py` adds two
  import lines and one dataclass field before this code and appends
  `_reduce_optional` after it; the loop body itself is untouched. The shift
  from `42/69/72` to `43/71/74` is exactly the two added lines.

- **`depin/_core/frozen.py`, line 439, branches `446->448`, line 479, branches
  `486->488`, `511->515`, and lines 553 and 571.** Pre-existing, not
  previously called out by name but verified the same way. The worktree
  measurement at `ad33482` gives
  `depin/_core/frozen.py 223 4 86 7 96% Missing 438, 445->447, 478, 485->487, 510->514, 549, 564`.
  `git diff ad33482 HEAD -- depin/_core/frozen.py` is a docstring edit before
  line 438 (net one line) plus, in each of `_resolve_params_sync` and
  `_resolve_params_async`, a new `if param.optional:` arm inserted between the
  existing `if param.has_default:` arm and the `raise MissingProviderError`
  that follows it. Lines 438, 478, and the two `->` branch pairs sit before
  either insertion and shift by exactly the docstring's one line (438→439,
  478→479, and likewise for the two branch pairs). Lines 549 and 564 are the
  two `raise MissingProviderError` statements themselves — dead by
  construction, since `freeze()` already rejects any graph where a required,
  non-optional, non-defaulted parameter would reach this point, so the raise
  is unreachable from a frozen container. They shift to 553 (docstring's one
  line, plus the three-line `if param.optional` block inserted before it in
  the same function) and to 571 (the same one line, plus both three-line
  blocks, since the async function's raise sits after both insertions).

No other changed module has an uncovered line or branch. No uncovered line
in any module this cycle changed is new; every one is the same statement or
arc present at `ad33482`, at a shifted line number.

## Suppression count

**`depin/` carries exactly three suppressions, and this cycle adds none.**
Verified directly:

```console
$ grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin
depin/_core/markers.py:129:    return _InjectMarker(key, tag)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/frozen.py:116:        return self._resolve_sync(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/frozen.py:139:        return await self._resolve_async(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
```

Each line was compared byte-for-byte against `main` at `ad33482`
(`git show ad33482:depin/_core/frozen.py`, `git show ad33482:depin/_core/markers.py`,
grepped the same way): file, line number, and text match exactly —
`frozen.py:116`, `frozen.py:139`, `markers.py:129`, identical strings. A
repository-wide sweep of every `.py` file under `depin/` at `ad33482`
confirms these are the only three that existed there too, so the count is
unchanged in both directions: nothing added, nothing removed.

## The optional/collection design: checker measurements

Restated from `specs/2026-08-31-step-3-optional-collections-design.md`'s
"Measurements" section, not re-derived for this pass.

- **A parameterised generic written at a call site is already a valid
  `ProviderKey`.** `list[Handler]` in expression position has the static type
  `type[list[Handler]]`, assignable to the existing `type[object]` member of
  the alias. No change was needed for a consumer who writes the key literally.

- **Building that key from a runtime value is a mypy `valid-type` error.**
  `list[element]`, where `element` is a parameter rather than a literal type,
  is `error: Variable "element" is not valid as a type [valid-type]` under
  mypy. `types.GenericAlias(list, (element,))` produces an object equal to,
  and hashing as, `list[Handler]` — same type, same equality, same hash —
  which is why `ProviderKey` gained a `GenericAlias` member:

  ```python
  type ProviderKey = type[object] | Token[object] | str | GenericAlias
  ```

- **`resolve` needs no new overload.** `resolve[T](key: type[T] | Token[T]) -> T`
  already infers `list[Handler]` from `resolve(list[Handler])`, and so do
  `__getitem__`, `aresolve`, `override`, and `injected`. A dedicated
  `type[list[T]] -> list[T]` overload was written and confirmed to also work,
  and was not added: it never changes an inferred type, so it is surface with
  no contract behind it.

- **`X | None` and `typing.Optional[X]` carry different origins.** `X | None`
  has `get_origin` of `types.UnionType`; `typing.Optional[X]` has
  `typing.Union`. Detection handles both. `list[X]` and `typing.List[X]` both
  have `get_origin` of `list`, so the collection key needed no equivalent
  special case — but the two are not equal to each other, which this cycle
  does not own.

## The carried Step 2 finding: chain evidence

Script run against a detached worktree at `main` (`ad33482`):

```console
freeze : no provider for C (required by B.c; resolution chain: B -> C)
explain: no provider for C2 (required by B2.c; resolution chain: A2 -> B2 -> C2)
```

The same script run against this branch's `HEAD` (`64df9d3`):

```console
freeze : no provider for C (required by B.c; resolution chain: A -> B -> C)
explain: no provider for C2 (required by B2.c; resolution chain: A2 -> B2 -> C2)
```

At `ad33482`, `freeze()`'s chain (`B -> C`) stops at the nearest requiring
provider, skipping the bound-and-defaulted intermediate `A`, while
`explain()`'s chain (`A2 -> B2 -> C2`) already runs from the root. At `HEAD`
the two agree: `freeze()` now reports `A -> B -> C`, the full chain from the
root, matching what `explain()` printed all along. This is the "Chain
divergence on a bound-and-defaulted intermediate" finding the roadmap
carried from Step 2, closed.

## Benchmarks

```console
$ uv run --group bench pytest benchmarks --benchmark-only
14 passed in 11.76s
```

| Case | Mean |
| --- | ---: |
| `test_resolve_a_cached_singleton` | 2.1144 us |
| `test_resolve_a_cached_singleton_through_an_alias` | 4.3424 us |
| `test_call_through_an_inject_wrapper` | 7.0073 us |
| `test_resolve_a_collection[10]` | 24.2163 us |
| `test_resolve_an_async_singleton` | 24.9095 us |
| `test_resolve_a_transient_chain` | 49.3719 us |
| `test_resolve_a_collection[100]` | 168.0193 us |
| `test_open_and_close_a_scope` | 288.2676 us |
| `test_freeze_a_chain[10]` | 431.8460 us |
| `test_export_a_large_graph_as_dot` | 2,756.1136 us |
| `test_freeze_a_chain[100]` | 3,985.9119 us |
| `test_build_the_graph_view` | 5,967.1716 us |
| `test_explain_a_deep_chain` | 9,347.9878 us |
| `test_freeze_a_chain[1000]` | 44,632.1082 us |

`test_resolve_a_collection[10]` and `test_resolve_a_collection[100]` are new
this cycle; there is no prior-cycle figure to compare them against. Every
other case has a directly comparable figure in
`specs/evidence/2026-08-31-step-3-provides-aliasing.md`; none shows an
order-of-magnitude change, consistent with `git diff ad33482 HEAD --
depin/_core/scope.py depin/_core/teardown.py` being empty and
`depin/_core/frozen.py`'s and `depin/_core/construct.py`'s diffs both being
additive arms on paths not exercised by the direct-resolution and
alias-resolution benchmarks.

The repository commits no benchmark baseline (`benchmarks/` has no checked-in
JSON), so a "no regression" claim for the twelve pre-existing cases is made by
the CI benchmark job, which measures base and head back-to-back on one
runner, not by this local, single-host run.

## Mutation gate

Not run for this pass, by the controller's explicit decision. `[tool.mutmut]
only_mutate` in `pyproject.toml` is `["depin/_core/*.py"]` — every module
under `depin/_core/`, not a changed-modules subset — so a local
`uv run mutmut run` is the full mutant matrix regardless of how small this
cycle's eleven-module diff is. Prior evidence
(`specs/evidence/2026-08-30-step-2-diagnostics.md`,
`specs/evidence/2026-08-31-step-3-provides-aliasing.md`) records that same
full run taking tens of minutes and its baseline collection as fragile under
host CPU contention. Re-running it here would not measure anything scoped to
this cycle's eleven changed modules; it would re-measure the whole package
under exactly the conditions already documented as unreliable.

The CI `mutation` job (`.github/workflows/mutation.yml`, path filter
`depin/_core/**`) triggers on this branch's changes and is the authority for
this gate. It is left to run in CI rather than reproduced locally, and no
score is recorded here in its place.

## Scope note

This record covers Steps 1, 2, 4, 5, and 6 of the Task 8 brief. Step 3, the
mutation gate, is deferred to the CI `mutation` job for the reasons given
above. Pushing the branch and opening the pull request are the controller's
responsibility and are not part of this record. Everything else in this
document was measured locally, on a clean working tree, against
`64df9d3a04391e831d4e1e7e5d59b672c6099b1c`.
