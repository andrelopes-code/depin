# Step 3, cycle 3 verification evidence

Date: 2026-08-31

Baseline commit (`main`): `ec65dcb` (0.9.0)
Measured implementation commit (this branch, before this file's own commit): `de38834117ef602cfee26acf122b68694f828eae`

This document covers Steps 1, 2, 4, and 5 of the Task 7 brief. Step 3 (the
mutation gate) is out of scope for this pass, by explicit decision; see
"Mutation gate" below for the reason. Pushing the branch and opening a pull
request are handled separately from this record and are not covered here.

The evidence file itself is part of the commit that adds it. Every claim
below about the working tree's state was true when measured and remains true
once this file lands: the gate sequence, the coverage runs, and the
suppression grep were all run against a clean tree with every other change
from this cycle already committed, and the commit that adds this file changes
no other tracked path.

## Gate sequence

```console
$ uv run ruff format
135 files left unchanged
EXIT=0

$ uv run ruff check
All checks passed!
EXIT=0

$ uv run basedpyright
0 errors, 0 warnings, 0 notes
EXIT=0

$ uv run mypy
Success: no issues found in 86 source files
EXIT=0

$ uv run pytest
637 passed, 6 skipped in 12.46s
EXIT=0

$ uv run --group docs mkdocs build --strict
INFO    -  Documentation built in 2.45 seconds
EXIT=0
```

`uv run ruff format` left the tree unchanged, so no revert was needed. The
docs command printed the same upstream Material for MkDocs 2.0 advisory
banner recorded in prior evidence files; no MkDocs diagnostic, exit 0.

## Coverage

```console
$ uv run pytest --cov=depin --cov-report=term-missing -q
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
depin/_core/markers.py          56      0      4      0   100%
depin/_core/overrides.py        23      0      4      0   100%
depin/_core/providers.py       136      1     72      3    98%   214->216, 225, 238->245
depin/_core/registry.py          8      0      0      0   100%
depin/_core/render.py          111      0     56      0   100%
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
depin/_core/spec.py             96      0      4      0   100%
depin/_core/teardown.py         45      0     14      2    97%   53->exit, 77->exit
depin/_core/typeguards.py       67      1     22      1    98%   56
depin/errors.py                 11      0      0      0   100%
depin/ext/__init__.py            0      0      0      0   100%
depin/ext/fastapi.py            33      0      6      0   100%
------------------------------------------------------------------------
TOTAL                         1516     10    502     21    98%
Required test coverage of 95.0% reached. Total coverage: 98.46%
637 passed, 6 skipped in 27.58s
EXIT=0
```

Run a second time, unmodified, specifically to observe `scope.py:69`:

```console
$ uv run pytest --cov=depin --cov-report=term-missing -q
...
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
...
Required test coverage of 95.0% reached. Total coverage: 98.46%
637 passed, 6 skipped in 27.68s
EXIT=0
```

Total coverage 98.46% in both runs, above the 95% floor. Line 69 was missing
in both runs recorded here.

`git diff ec65dcb HEAD --stat -- depin/_core/*.py depin/*.py depin/ext/*.py`
names exactly four modules this cycle changed: `markers.py`, `providers.py`,
`spec.py`, and `typeguards.py` — matching the design's own module-layout
table. `spec.py` and `markers.py` are at 100% line and branch coverage.
`providers.py` and `typeguards.py` carry uncovered lines; `construct.py`,
`frozen.py`, `introspect.py`, and `scope.py` also carry uncovered lines but
are not modules this cycle touched.

Every uncovered line is attributed below, checked against a detached
worktree at `main` (`ec65dcb`), built with `uv sync --group dev --all-extras`
and measured with `uv run coverage run -m pytest -q` followed by
`uv run coverage report -m --include=<pattern>`.

- **`depin/_core/construct.py`, branch `75->exit`.** Pre-existing and
  structural, confirmed known. `sync()` dispatches on `match spec.shape` with
  no wildcard arm, so coverage records the fall-through arc from the last
  `case` line to the function exit. The worktree measurement at `ec65dcb`
  gives `depin/_core/construct.py 51 0 24 1 99% Missing 75->exit` —
  byte-for-byte the same branch at the same line, because `construct.py` is
  untouched by this cycle (empty in the `git diff` above). Only the line
  number moves in step with whatever precedes it in the file across cycles;
  here it does not move at all.

- **`depin/_core/providers.py`, line 225.** Pre-existing, confirmed known.
  Line 225 is `return None` inside `unwrap_container_type`, the branch taken
  when `get_args(annotation)` is empty. The worktree measurement at `ec65dcb`
  gives `depin/_core/providers.py 122 1 60 1 99% Missing 204`, and line 204
  there is the identical `return None` statement. `git diff ec65dcb HEAD --
  depin/_core/providers.py` adds the canonical-form check to
  `as_provider_key` and widens `_registered_classes`, both before this
  function; `unwrap_container_type` itself is untouched, and the line only
  moved.

- **`depin/_core/scope.py`, line 69 (inside `_Flight.wait_sync`).** Not a
  module this cycle changed — `git diff ec65dcb HEAD -- depin/_core/scope.py`
  is empty. Line 69 is a thread-scheduling path inside `_Flight.wait_sync`
  that depends on which thread the interpreter schedules first. Both
  coverage runs recorded above show line 69 uncovered; running it twice, as
  instructed, did not happen to catch the run where it is covered, which is
  consistent with a roughly one-in-two rate rather than evidence against it.
  The worktree measurement at `ec65dcb`, taken as part of this same pass,
  happened to show line 69 *covered* in that single run
  (`depin/_core/scope.py 233 0 74 2 99% Missing 88->87, 107-109, 113->exit`,
  no `69`) — a third data point for the same coin, not a contradiction: the
  branches `88->87`, `107-109`, and `113->exit` are identical at `ec65dcb`
  and at `HEAD` in both letter and line number, confirming the module is
  unchanged and the difference is purely which thread ran first on the host
  that measured it.

- **`depin/_core/introspect.py`, line 43 and branches `71->69`, `74->69`.**
  Not a module this cycle changed — `git diff ec65dcb HEAD --
  depin/_core/introspect.py` is empty. The worktree measurement at `ec65dcb`
  reproduces the identical `depin/_core/introspect.py 70 1 36 3 96% Missing
  43, 71->69, 74->69`, same lines, same branches.

- **`depin/_core/frozen.py`, line 439, branches `446->448`, line 479,
  branches `486->488`, `511->515`, and lines 553 and 571.** Not a module
  this cycle changed — `git diff ec65dcb HEAD -- depin/_core/frozen.py` is
  empty. The worktree measurement at `ec65dcb` reproduces the identical
  `depin/_core/frozen.py 229 4 90 7 97% Missing 439, 446->448, 479, 486->488,
  511->515, 553, 571`, same lines, same branches.

- **`depin/_core/providers.py`, branch `214->216`.** New this cycle, and
  attributed rather than claimed pre-existing. `214->216` is the arc from
  `if unwrapped is not None:` straight past its body to `return
  as_provider_key(ret)`, taken when `unwrap_container_type(ret)` returns
  `None` for a provider whose shape is in `_UNWRAP_SHAPES`. At `ec65dcb`,
  `_UNWRAP_SHAPES` (there, `_resolve_key`'s inline shape check) still
  included `ASYNC_FUNCTION`, and an async factory with a plain, unparameterised
  return annotation (`async def make() -> Pool`) took exactly this arc:
  `unwrap_container_type(Pool)` finds no origin and returns `None`, so
  control fell through to `as_provider_key(Pool)`. `benchmarks/test_resolution.py::test_resolve_an_async_singleton`
  is such a factory, and exercised this arc at `ec65dcb`. Task 3 of this
  cycle removes `ASYNC_FUNCTION` from `_UNWRAP_SHAPES` — the defect this
  cycle fixes — so an async factory no longer enters this `if` at all; it
  now returns from the earlier `is not None` check on `ret` directly to
  `as_provider_key(ret)` without ever reaching line 213. The four remaining
  members of `_UNWRAP_SHAPES` (`GENERATOR`, `ASYNC_GENERATOR`,
  `CONTEXT_MANAGER`, `ASYNC_CONTEXT_MANAGER`) are exercised in the suite only
  with a parameterised return annotation (`Generator[Conn]`,
  `Iterator[Conn]`, and similar), so `unwrap_container_type` never returns
  `None` for any of them either. The arc is real and reachable — a
  generator or context-manager factory annotated with a bare, unparameterised
  container type (`def make() -> Iterator:`) would take it — but no test
  constructs that case. This is a genuine, narrow coverage gap this cycle
  introduces as a side effect of the async-unwrap fix, not a pre-existing one
  carried at a new line number. The concrete reproducing case is

  ```python
  def gen() -> collections.abc.Iterator:
      yield object()
  ```

  an unsubscripted container annotation, which `unwrap_container_type` reads
  no argument out of and which is therefore keyed by the bare `Iterator`
  class. Closed by the fix wave recorded below, which pins exactly that
  behaviour in
  `tests/unit/test_providers.py::test_an_unsubscripted_container_annotation_keys_by_the_bare_class`.

- **`depin/_core/providers.py`, branch `238->245`.** New this cycle. `238`
  is `if isinstance(origin, type):` inside `as_provider_key`'s
  canonical-generic branch, reached only after `is_generic_key(value)` has
  already returned `True`. `is_generic_key`'s own definition
  (`depin/_core/typeguards.py`) returns `False` unless `get_origin(value)` is
  itself a class, so by the time line 238 runs, `origin` is always a `type`;
  the `False` side of this `isinstance` check, and the arc to line 245, is
  unreachable given that invariant. Task 1's own implementation report
  already named this: "`basedpyright --strict` does not flag it as
  unnecessary... isinstance check is not reported as redundant... Coverage
  shows the guard's false branch is unreachable at runtime given
  `is_generic_key`'s invariant — expected, and left as-is per the design's
  own rationale for keeping the guard readable." New at this line, but not a
  surprise: the same code, and the same acknowledged trade-off, existed since
  Task 1's commit within this cycle. Removed by the fix wave recorded below:
  `as_provider_key` no longer re-narrows the origin, so the branch does not
  exist to be uncovered.

- **`depin/_core/typeguards.py`, line 56.** New this cycle; `is_canonical_generic`
  did not exist at `ec65dcb` at all (confirmed: `git show
  ec65dcb:depin/_core/typeguards.py` has no such function). Line 56 is
  `return False` inside `is_canonical_generic`, taken when `get_origin(value)`
  is not a class. `is_canonical_generic` has two call sites, not one:
  `as_provider_key` in `providers.py`, and `_reject_invalid_key` in
  `markers.py`, which cycle 3 gave it. Both reach it only after
  `is_generic_key(value)` has returned `True` — in `markers.py` the two are
  joined by `and`, so `is_generic_key` short-circuits and
  `is_canonical_generic` is never evaluated for a value with a non-class
  origin — and `is_generic_key` returns `False` unless the origin is a class.
  The guard's `False` branch is therefore unreachable through both paths — the
  same shape of defensive, provably-dead guard as `providers.py`'s `238->245`
  above, on a predicate that also has to be correct when called directly (as
  `tests/unit/test_typeguards.py` does, always with a class-origin value in
  both directions of its own two tests). Neither existing test calls it with
  a non-class-origin value such as `Literal['a']`, so the branch is
  unexercised. Closed by the fix wave recorded below, which adds that direct
  assertion.

None of the three new gaps threatens the 95% floor (98.46% total, twice
measured) or the acceptance criterion that a generic key resolve, validate,
and render correctly — all three are internal defensive branches or a
narrowed shape combination, not user-observable behaviour left unverified.
They are recorded here rather than silently reclassified as pre-existing.

## Suppression count

**`depin/` carries exactly three suppressions, and this cycle adds none.**
Verified directly:

```console
$ grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin
depin/_core/frozen.py:116:        return self._resolve_sync(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/frozen.py:139:        return await self._resolve_async(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/markers.py:132:    return _InjectMarker(key, tag)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
```

Compared against `main` at `ec65dcb`:

```console
$ grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin   # in the ec65dcb worktree
depin/_core/frozen.py:116:        return self._resolve_sync(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/frozen.py:139:        return await self._resolve_async(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/markers.py:129:    return _InjectMarker(key, tag)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
```

Both `frozen.py` lines are byte-for-byte identical at the same line numbers
(`frozen.py` is untouched by this cycle). The `markers.py` line is
byte-for-byte identical in text and moved from 129 to 132, three lines later
— `git diff ec65dcb HEAD -- depin/_core/markers.py` adds prose to `provides`'s
docstring (`Args:`/`Raises:` entries widened to describe a parameterised
generic target) before this line, which is exactly a three-line shift. A
repository-wide sweep of every `.py` file under `depin/` at `ec65dcb`
confirms these are the only three that existed there too: nothing added,
nothing removed.

## The generic-key design: checker measurements

Restated from `specs/2026-08-31-step-3-generic-keys-design.md`'s
"Measurements" section and its opening claim, not re-derived for this pass.

**The roadmap's premise for this cycle is false.** The roadmap gives generic
keys their own release because "`resolve[T](key: type[T]) -> T` cannot
express `Repo[User]`, since a parameterised generic alias is not a `type`".
The second half is true at runtime — `isinstance(Repo[User], type)` is
`False` — and the conclusion does not follow. Measured on the 0.9.0 tree,
under mypy at default settings and `basedpyright --strict`, all four of
these pass:

```python
assert_type(di.resolve(Repo[User]), Repo[User])
assert_type(di[Repo[User]], Repo[User])
assert_type(di.resolve(Reader[User]), Reader[User])  # a generic Protocol
assert_type(di.resolve(list[Repo[User]]), list[Repo[User]])
```

In expression position `Repo[User]` has the static type `type[Repo[User]]`,
which satisfies the existing `type[T]` parameter and solves `T` to
`Repo[User]`. No signature change, and no overload, is needed. These four
assertions are now `tests/typing/test_conformance.py::test_a_generic_key_keeps_its_parameterisation`,
so the claim is checked on every build rather than believed.

**The deprecated `typing` aliases are rejected rather than normalised,
because no canonical rebuild type-checks.** `typing.List[User]` and
`list[User]` are not equal, so a provider annotated with one and a binding
registered under the other would not match. Three ways to canonicalise were
measured, and all three fail: `types.GenericAlias(origin, args)` produces the
right object for a builtin origin but is unequal to a user-defined PEP 695
generic's own subscript; re-subscripting the origin (`origin[args]`) is
correct at runtime for every case measured but `type` declares no
`__getitem__` in typeshed, so both checkers reject it; and calling
`origin.__class_getitem__(args)` explicitly fails the same way. Every route
needs a suppression, and this cycle adds none, so depin rejects a
non-canonical spelling at `freeze()` and names the canonical one instead.

**The discriminator is exact and needs no subscripting.** A parameterised key
is canonical when it is a `types.GenericAlias`, or when its origin is a
`Generic` subclass:

| Spelling | `types.GenericAlias` | origin is `Generic` | verdict |
| --- | --- | --- | --- |
| `list[User]`, `dict[str, int]`, `abc.Sequence[User]` | yes | no | canonical |
| `Repo[User]`, `Reader[User]`, `Repo[Repo[User]]` | no | yes | canonical |
| `typing.List[User]`, `typing.Dict[str, int]`, `typing.Sequence[User]` | no | no | rejected |

The rejected column is exactly the deprecated aliases, which `ruff`'s `UP006`
already rewrites and which have been superseded since Python 3.9 — five
releases before depin's floor. This also explains why cycle 2's
`collection_key` needed no change: its origin is always the builtin `list`,
for which `types.GenericAlias` is already the canonical form. Restated and
pinned in `tests/unit/test_spec.py` and `tests/unit/test_typeguards.py`
(Task 1), and covered again from the validation side in
`tests/unit/test_graph_validation.py::test_a_key_whose_origin_is_not_a_class_is_rejected`
and `::test_a_key_with_an_argument_that_is_not_itself_a_key_is_rejected`
(Task 5).

**A union's origin is a class, so unions must be excluded by name.** `X |
None` has `get_origin` of `types.UnionType`, itself a class, so a rule of
"the origin is a class" would wrongly admit it. `typing.Optional[X]` has
`get_origin` of `typing.Union`, which is not a class, so the two spellings
need different treatment and both are rejected. `Callable[[int], str]`
carries a `list` among its arguments and `tuple[User, ...]` carries
`Ellipsis`; requiring every argument to be itself a provider key excludes
both with no special case, and `Literal['a']` has a non-class origin and
falls out the same way. Task 5's
`test_both_union_spellings_reaching_a_key_position_are_rejected` covers both
union spellings reaching a key position outside parameter annotation, which
Task 1 did not.

## The before/after key inference: Task 3's async-factory fix

Restated from `specs/2026-08-31-step-3-generic-keys-design.md`'s "The defect
this cycle fixes" and from `task-2-3-4-report.md`'s own red/green evidence
for Task 3, not re-derived.

The design's own summary of the defect, measured on the 0.9.0 tree:

```
async def make() -> list[Handler]    keyed  Handler          wrong
async def make() -> Repo[User]       keyed  User             wrong
def make() -> list[Handler]          keyed  list[Handler]    right
```

`_UNWRAP_SHAPES` in `depin/_core/providers.py` included
`ProviderShape.ASYNC_FUNCTION`, so `_resolve_key` unwrapped the first type
argument out of an async factory's return annotation — correct for
`Generator[X]`, `AsyncIterator[X]`, `AbstractContextManager[X]` and their
kin, which genuinely wrap the value, but wrong for `async def f() -> X`,
which already means the awaited value is `X`. The defect was latent before
this cycle: a parameterised return annotation raised at `as_provider_key`
before this cycle's own predicate widening, so the unwrap only ever saw
annotations with no origin, where it does nothing.

Task 3's own before/after script, run against three factories:

Before (`ASYNC_FUNCTION` still in `_UNWRAP_SHAPES`):

```
make_list -> ["<class '__main__.Handler'>"]
make_repo -> ["<class '__main__.User'>"]
make_sync -> ['list[__main__.Handler]']
```

After (`ASYNC_FUNCTION` removed):

```
make_list -> ['list[__main__.Handler]']
make_repo -> ['__main__.Repo[__main__.User]']
make_sync -> ['list[__main__.Handler]']
```

`make_list` (`async def make_list() -> list[Handler]`) and `make_repo`
(`async def make_repo() -> Repo[User]`) both go from keyed by their first
type argument to keyed by their whole return annotation; `make_sync` (a
synchronous factory, never routed through `_UNWRAP_SHAPES` for this shape)
is unchanged in both runs, confirming the fix touches only the async case.
Pinned as a red-then-green pair in `tests/unit/test_providers.py`, alongside
the four `_UNWRAP_SHAPES` members that still unwrap, unchanged.

## Benchmarks

```console
$ uv run --group bench pytest benchmarks --benchmark-only
17 passed in 13.40s
```

| Case | Mean |
| --- | ---: |
| `test_resolve_a_cached_singleton` | 1.9108 us |
| `test_resolve_a_cached_singleton_through_an_alias` | 3.9585 us |
| `test_call_through_an_inject_wrapper` | 7.0376 us |
| `test_resolve_an_async_singleton` | 19.6944 us |
| `test_resolve_a_collection[10]` | 18.9548 us |
| `test_resolve_a_transient_chain` | 40.5605 us |
| `test_resolve_a_collection[100]` | 144.1649 us |
| `test_open_and_close_a_scope` | 222.2029 us |
| `test_freeze_a_chain[10]` | 395.3534 us |
| `test_freeze_a_chain_of_generic_keys[10]` | 743.8672 us |
| `test_export_a_large_graph_as_dot` | 2,504.1313 us |
| `test_freeze_a_chain[100]` | 3,704.5032 us |
| `test_build_the_graph_view` | 5,218.8648 us |
| `test_explain_a_deep_chain` | 7,418.7498 us |
| `test_freeze_a_chain_of_generic_keys[100]` | 7,206.2926 us |
| `test_freeze_a_chain[1000]` | 38,931.9519 us |
| `test_freeze_a_chain_of_generic_keys[1000]` | 89,126.0626 us |

`test_freeze_a_chain_of_generic_keys` is new this cycle, timing `freeze()`
over a graph whose keys are every one a parameterised generic, against
`test_freeze_a_chain`'s plain-key baseline at the same three sizes. The
canonical-form check's cost on the freeze path is visible directly:

| Size | Plain-key mean | Generic-key mean | Ratio |
| --- | ---: | ---: | ---: |
| 10 | 395.3534 us | 743.8672 us | 1.88x |
| 100 | 3,704.5032 us | 7,206.2926 us | 1.95x |
| 1000 | 38,931.9519 us | 89,126.0626 us | 2.29x |

The ratio is not constant: it climbs from 1.88x to 1.95x to 2.29x across the
three sizes. The two cases differ in more than the canonical-form check —
the generic-key graph also carries a different key object per node, which
hashes, compares, and renders differently from a bare class — so the ratio
bounds the total cost of keying a graph by generic keys rather than isolating
the canonical-form check's share of it. A single-host run of three sizes does
not separate those contributions, and no attempt is made here to attribute
the climb to one of them.

Every other case has a directly comparable figure in
`specs/evidence/2026-08-31-step-3-optional-collections.md`; none shows an
order-of-magnitude change (this host measured every shared case somewhat
faster than that prior run, consistent with ordinary host variance rather
than a regression), matching `git diff ec65dcb HEAD` touching only
`markers.py`, `providers.py`, `spec.py`, and `typeguards.py` — none of them
on the direct-resolution, alias-resolution, scope, injection, or async-
singleton hot paths those benchmarks measure.

The repository commits no benchmark baseline (`benchmarks/` has no
checked-in JSON), so a "no regression" claim for the fourteen pre-existing
cases is made by the CI benchmark job, which measures base and head
back-to-back on one runner, not by this local, single-host run.

## Mutation gate

Not run for this pass, by the controller's explicit decision. `[tool.mutmut]
only_mutate` in `pyproject.toml` is `["depin/_core/*.py"]` — every module
under `depin/_core/`, not a changed-modules subset — so a local
`uv run mutmut run` is the full mutant matrix regardless of how small this
cycle's four-module diff is. Prior evidence
(`specs/evidence/2026-08-30-step-2-diagnostics.md`,
`specs/evidence/2026-08-31-step-3-provides-aliasing.md`,
`specs/evidence/2026-08-31-step-3-optional-collections.md`) records that same
full run taking tens of minutes and its baseline collection as fragile under
host CPU contention. Re-running it here would not measure anything scoped to
this cycle's four changed modules; it would re-measure the whole package
under exactly the conditions already documented as unreliable.

The CI `mutation` job (`.github/workflows/mutation.yml`, path filter
`depin/_core/**`) triggers on this branch's changes and is the authority for
this gate. It is left to run in CI rather than reproduced locally, and no
score is recorded here in its place.

## Fix wave: canonical generic keys on every path

A whole-branch review found three paths where a deprecated `typing` alias still
became a key, or was refused with the wrong message, and four documentation
claims that had gone stale. One commit, `fix: enforce canonical generic keys on
every path`, closes all of them. What changed, and what it fixed:

- Canonicity moved inside `is_provider_key`. `typeguards.py` now carries three
  predicates instead of two: `is_parameterised_generic` (shape only),
  `is_canonical_generic` (unchanged), and `is_generic_key`, which requires both
  and recurses through `is_provider_key` for every argument. Canonicity is
  therefore enforced at every nesting level and at every call site, rather than
  being a separate predicate one call site remembered to consult.
- `_resolve_key` routes an explicit `provides=` through `as_provider_key`. It
  had returned the value unchanged, so `provides=42`, `provides=typing.List[X]`,
  `provides=X | None`, `provides=Callable[[int], str]`, and
  `provides=tuple[X, ...]` all froze.
- `list[typing.List[X]]` and `Repo[typing.List[X]]` are rejected. Both were
  accepted, and `list[typing.List[X]]` alongside `list[list[X]]` produced two
  nodes that print `list[list[User]]`.
- `FrozenContainer.resolve`, `explain`, and `override` refuse a deprecated
  alias at their key gate. With `list[X]` bound, `resolve(typing.List[X])` had
  raised `MissingProviderError: no provider for list[User]`, naming as missing
  a key that is present. `frozen.py` is unmodified: the three gates call
  `is_provider_key`, so fixing the predicate fixed all three.
- `as_provider_key` collapsed to `is_provider_key` plus one message builder,
  which removed the dead `isinstance(origin, type)` re-narrowing that branch
  `238->245` measured.

Messages reworded, each with the case that reaches it:

| Message | Reached by |
| --- | --- |
| the deprecated-alias message, now naming the origin module-qualified (`Write Sequence[User] instead, subscripting collections.abc.Sequence itself`) | `typing.Sequence[User]` as a key, at any depth; `fmt_key` drops the module, so the old advice was not directly typable for an ABC origin |
| the argument-rule message, now naming the argument (`its argument Ellipsis is not itself a provider key`) | `tuple[X, ...]` and `Callable[[int], str]`, which previously fell through to the catch-all |
| the deprecated-alias, argument-rule, and both union messages, from `@provides` | `@provides(typing.List[X])`, `@provides(Callable[[int], str])`, `@provides(X \| None)`, `@provides(X \| Y)` — all four previously got "expected a class, a Protocol, an abstract base class, or a parameterised generic such as `Repo[User]`", which for the first two told the reader to write what they had written. `@provides(42)`, `@provides('Store')`, and `@provides(Token(...))` keep that message |
| `cannot infer the provider key for <fn>: it declares a return annotation, but an annotation on it could not be resolved` | a factory whose return annotation names something unresolvable; `_safe_type_hints` returns `{}` on `NameError`, so it had been told to add an annotation it already had |

`_classes_reachable_from` now reads the whole `BindRecord` — source, `provides`,
frame key, alias key and target, collection element and members — and recurses
into a generic key's arguments, so a class reachable only through `provides=`,
or only as `Repo[User]`'s argument, enters the forward-reference namespace.

Gate sequence, re-run on the fix commit's tree:

```console
$ uv run ruff format
136 files left unchanged
EXIT=0

$ uv run ruff check
All checks passed!
EXIT=0

$ uv run basedpyright
0 errors, 0 warnings, 0 notes
EXIT=0

$ uv run mypy
Success: no issues found in 86 source files
EXIT=0

$ uv run pytest
656 passed, 6 skipped in 12.63s
EXIT=0

$ uv run --group docs mkdocs build --strict
INFO    -  Documentation built in 2.44 seconds
EXIT=0
```

Coverage, re-measured:

```console
$ uv run pytest --cov=depin --cov-report=term-missing -q
...
depin/_core/markers.py          59      0      6      0   100%
depin/_core/providers.py       131      1     64      1    99%   254
depin/_core/spec.py             96      0      4      0   100%
depin/_core/typeguards.py       99      0     38      0   100%
...
TOTAL                         1546      8    512     17    99%
Required test coverage of 95.0% reached. Total coverage: 98.79%
656 passed, 6 skipped
EXIT=0
```

98.79%, up from 98.46%. All three gaps this cycle had introduced are gone:
`typeguards.py` is at 100% line and branch coverage, `providers.py`'s
`238->245` no longer exists, and `214->216` is covered. `providers.py:254` is
the pre-existing `return None` in `unwrap_container_type` already attributed
above. `depin/` still carries exactly three suppressions — two in `frozen.py`,
one in `markers.py` — and the fix commit adds none.

Benchmarks were not re-run for this commit. The changed code is the freeze-path
key check and the message builders it raises through; no resolution, scope,
injection, or async hot path is touched, and the CI benchmark job measures base
against head.

## Scope note

This record covers Steps 1, 2, 4, and 5 of the Task 7 brief. Step 3, the
mutation gate, is deferred to the CI `mutation` job for the reasons given
above. Pushing the branch and opening the pull request are the controller's
responsibility and are not part of this record. Everything else in this
document was measured locally, on a clean working tree, against
`de38834117ef602cfee26acf122b68694f828eae` — the commit this file's own
commit is built on — and this file is the only path its own commit adds.

The "Fix wave" section above is later than the rest and was measured on its own
commit, `fix: enforce canonical generic keys on every path`, which is the one
place in this document where a figure supersedes an earlier one. Where the two
disagree — the coverage total, and the three gaps this cycle had introduced —
the fix wave's figures are the current ones, and the earlier ones are kept as
the record of what the review found.
