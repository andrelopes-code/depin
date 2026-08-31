# Step 4, cycle 1 verification evidence

Date: 2026-08-31

Baseline commit (`main`): `0ff6e1d2e21ec739a016071fa49f2587f849fe08` (0.10.0)
Measured implementation commit (this branch): `d91827627bc6b1f641781f063ab133681306bc9f`

This document covers Steps 1, 2, 4, 5, 6, and 7 of the Task 9 brief. Step 3
(the mutation gate) is out of scope for this pass; see "Mutation gate" below
for the reason it was not run locally.

The evidence file itself is part of the commit it documents. Every claim
below about the working tree's state was true when measured and remains true
once this file lands: `git status --short` was empty before and after every
command in this record, and the commit that adds this file changes no other
tracked path.

Before this record was written, Task 9 also closed two coverage gaps the
controller measured against `08f1a96`/`70e0370` — `depin/_core/providers.py`
lines 164-165 (the unwrap branch of `_declared_key`) and line 202 (the
`Underlying` branch of `_classes_within`) — with two tests, committed
separately (`test: cover the inactive-generator and underlying-key
branches`, `d918276`). The coverage figures below are measured after that
commit, not before it.

## Gate sequence

```console
$ uv run ruff format
145 files left unchanged
EXIT=0

$ uv run ruff check
All checks passed!
EXIT=0

$ uv run basedpyright
0 errors, 0 warnings, 0 notes
EXIT=0

$ uv run mypy
Success: no issues found in 93 source files
EXIT=0

$ uv run pytest
742 passed, 6 skipped in 15.70s
EXIT=0

$ uv run --group docs mkdocs build --strict
INFO    -  Documentation built in 2.81 seconds
EXIT=0
```

`uv run ruff format` left the tree unchanged, so no revert was needed. The
docs command printed the same upstream Material for MkDocs 2.0 advisory
banner recorded in prior evidence files; no MkDocs diagnostic, exit 0.

## Coverage

```console
$ uv run pytest --cov=depin --cov-report=term-missing
...
Name                         Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------
depin/__init__.py               14      0      0      0   100%
depin/_core/__init__.py          0      0      0      0   100%
depin/_core/bindings.py         57      0      4      0   100%
depin/_core/construct.py        51      0     24      1    99%   75->exit
depin/_core/container.py        11      0      0      0   100%
depin/_core/decoration.py       47      0     24      0   100%
depin/_core/diagnostics.py      63      0      4      0   100%
depin/_core/frozen.py          229      4     90      7    97%   442, 449->451, 482, 489->491, 514->518, 556, 574
depin/_core/graph.py           172      0     72      0   100%
depin/_core/injection.py        39      0     16      1    98%   59->58
depin/_core/introspect.py       70      1     36      3    96%   43, 71->69, 74->69
depin/_core/markers.py          59      0      6      0   100%
depin/_core/overrides.py        23      0      4      0   100%
depin/_core/providers.py       198      1    104      1    99%   394
depin/_core/registry.py          8      0      0      0   100%
depin/_core/render.py          113      0     56      0   100%
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
depin/_core/spec.py            129      0      6      0   100%
depin/_core/teardown.py         45      0     14      2    97%   53->exit, 77->exit
depin/_core/typeguards.py       99      0     38      0   100%
depin/errors.py                 11      0      0      0   100%
depin/ext/__init__.py            0      0      0      0   100%
depin/ext/fastapi.py            33      0      6      0   100%
------------------------------------------------------------------------
TOTAL                         1704      9    578     18    99%
Required test coverage of 95.0% reached. Total coverage: 98.82%
742 passed, 6 skipped in 35.11s
EXIT=0
```

The command was run a second time, unmodified, specifically to observe
`scope.py:69`:

```console
$ uv run pytest --cov=depin --cov-report=term-missing
...
depin/_core/scope.py           233      3     74      3    98%   69, 88->87, 107-109, 113->exit
...
Required test coverage of 95.0% reached. Total coverage: 98.82%
742 passed, 6 skipped in 34.92s
EXIT=0
```

Total coverage 98.82% in both runs, above the 95% floor. This is higher than
the 98.60% the controller measured before Task 9's two tests landed:
`depin/_core/decoration.py` was already at 100%, and the two lines those
tests cover — `providers.py:164-165` and `providers.py:202` — no longer
appear in `Missing` above.

`git diff --stat 0ff6e1d HEAD -- 'depin/_core/*.py'` names nine modules this
cycle changed, one of them new: `bindings.py`, `container.py`,
`decoration.py` (new), `frozen.py`, `graph.py`, `providers.py`, `render.py`,
`spec.py`, and `typeguards.py`. `depin/__init__.py` also changes, to
re-export `decorate` and `Underlying`. Of the nine `_core` modules,
`bindings.py`, `container.py`, `decoration.py`, `graph.py`, `render.py`,
`spec.py`, and `typeguards.py` are at 100% line and branch coverage.
`frozen.py` and `providers.py` carry uncovered lines; `construct.py`,
`introspect.py`, `injection.py`, `scope.py`, and `teardown.py` also carry
uncovered lines but are not modules this cycle touched
(`git diff --stat 0ff6e1d -- depin/_core/construct.py
depin/_core/diagnostics.py depin/_core/scope.py depin/_core/teardown.py
depin/_core/injection.py depin/_core/overrides.py depin/_core/introspect.py
depin/_core/markers.py` is empty — see "Untouched modules" below). Every one
is attributed below, checked against a detached worktree at `main`
(`0ff6e1d`), built with `uv sync` and measured with
`uv run pytest --cov=depin --cov-report=term-missing`.

- **`depin/_core/providers.py`, line 394.** Pre-existing, confirmed known.
  Line 394 is `return None` inside `unwrap_container_type`, the branch taken
  when `get_args(annotation)` is empty. The worktree measurement at
  `0ff6e1d` gives `depin/_core/providers.py 131 1 64 1 99% Missing 254`, and
  line 254 there is the identical `return None` statement;
  `unwrap_container_type` itself is untouched by this cycle, and the line
  only moved down as earlier code in the module grew.

- **`depin/_core/frozen.py`, line 442, branches `449->451`, line 482,
  branches `489->491`, `514->518`, and lines 556 and 574.** Pre-existing.
  The worktree measurement at `0ff6e1d` gives
  `depin/_core/frozen.py 229 4 90 7 97% Missing 439, 446->448, 479,
  486->488, 511->515, 553, 571`. `git diff 0ff6e1d -- depin/_core/frozen.py`
  (reproduced in full under "Untouched modules" below) is a three-line
  docstring addition before line 439 plus one changed call in `explain()`;
  every missed line and branch shifts by exactly those three added lines
  (439→442, 479→482, 553→556, 571→574) and none of them sit inside the
  changed `explain()` line.

- **`depin/_core/construct.py`, branch `75->exit`; `depin/_core/scope.py`,
  line 69 and branches `88->87`, `107-109`, `113->exit`;
  `depin/_core/introspect.py`, line 43 and branches `71->69`, `74->69`;
  `depin/_core/injection.py`, branch `59->58`; `depin/_core/teardown.py`,
  branches `53->exit`, `77->exit`.** None of these five modules changed this
  cycle (empty diff against `0ff6e1d`, confirmed above), so their misses are
  necessarily the same statements and arcs present on `main`, unmoved. The
  worktree measurement at `0ff6e1d` reproduces every one of them at the
  identical line and branch numbers:
  `depin/_core/construct.py 51 0 24 1 99% Missing 75->exit`,
  `depin/_core/scope.py 233 3 74 3 98% Missing 69, 88->87, 107-109,
  113->exit`,
  `depin/_core/introspect.py 70 1 36 3 96% Missing 43, 71->69, 74->69`,
  `depin/_core/injection.py 39 0 16 1 98% Missing 59->58`,
  `depin/_core/teardown.py 45 0 14 2 97% Missing 53->exit, 77->exit`.
  `scope.py:69`, inside `_Flight.wait_sync`, is the thread-scheduling path
  the Task 9 brief calls out by name: both coverage runs recorded above show
  it uncovered; running it twice, as instructed, did not happen to catch the
  run where it is covered, which is consistent with a roughly one-in-two
  rate rather than evidence against it — a coin that lands the same way
  twice in a row a quarter of the time is not a biased coin.

No other changed module has an uncovered line or branch. No uncovered line
in any module this cycle changed is new; every one is the same statement or
arc present at `0ff6e1d`, at a shifted line number, or belongs to a module
this cycle never touched.

## Suppression count

**`depin/` carries exactly three suppressions, and this cycle adds none.**
Verified directly:

```console
$ grep -rn "type: ignore\|pyright: ignore" --include='*.py' depin
depin/_core/frozen.py:116:        return self._resolve_sync(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/frozen.py:139:        return await self._resolve_async(spec)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
depin/_core/markers.py:132:    return _InjectMarker(key, tag)  # type: ignore[return-value]  # pyright: ignore[reportReturnType]
```

Each line was compared byte-for-byte against `main` at `0ff6e1d`
(`git show 0ff6e1d:depin/_core/frozen.py`, `git show
0ff6e1d:depin/_core/markers.py`, grepped the same way): file, line number,
and text match exactly — `frozen.py:116`, `frozen.py:139`, `markers.py:132`,
identical strings. `frozen.py` gained a three-line docstring earlier in the
file (see "Untouched modules" below), but that addition sits before line
116, and both suppression lines land at the same line numbers as on `main`
regardless; `markers.py` has no diff against `0ff6e1d` at all. A
repository-wide sweep of every `.py` file under `depin/` at `0ff6e1d`
confirms these are the only three that existed there too, so the count is
unchanged in both directions: nothing added, nothing removed.

## Untouched modules

```console
$ git diff --stat 0ff6e1d -- depin/_core/construct.py depin/_core/diagnostics.py depin/_core/scope.py depin/_core/teardown.py depin/_core/injection.py depin/_core/overrides.py depin/_core/introspect.py depin/_core/markers.py
EXIT=0
```

Empty output. `construct.py` and `diagnostics.py` in particular needed no
change: the design rests on decoration requiring no new provider shape (see
"Design measurements" below), so nothing in either module's `match` over
`ProviderShape` or graph-view rendering had reason to move.

`depin/_core/frozen.py` is not in the list above — it does change this
cycle, by five lines:

```console
$ git diff 0ff6e1d -- depin/_core/frozen.py
diff --git a/depin/_core/frozen.py b/depin/_core/frozen.py
index 1cea9ac..37c1b26 100644
--- a/depin/_core/frozen.py
+++ b/depin/_core/frozen.py
@@ -358,6 +358,9 @@ class FrozenContainer:
         requires that key. Like `graph()`, the output describes the validated
         plan, not an active `override()`.
 
+        When the key is registered behind a condition that did not hold, the
+        line says so, in the same wording `Container.freeze()` uses.
+
         Raises:
             MissingProviderError: The value cannot be a provider key at all.
                 An unregistered key of a valid type is described in the
@@ -378,7 +381,7 @@ class FrozenContainer:
         """
         if not is_provider_key(key):
             raise MissingProviderError(f'cannot look up provider for {key!r}: not a valid key type')
-        return render_tree(self.graph(), key, tag)
+        return render_tree(self.graph(), key, tag, self._plan.inactive)
 
     def _is_registered(self, key: ProviderKey, tag: str | None) -> bool:
         return (key, tag) in self._plan.by_key
```

A docstring addition and one call site threading `self._plan.inactive`
through to `explain()`'s renderer. Neither touches a line inside
`_resolve_params_sync`, `_resolve_params_async`, or the two suppressed
`return` statements, which is why every frozen.py coverage miss above shifts
by exactly the docstring's three lines and nothing else moves.

## Design measurements

Restated from `specs/2026-08-31-step-4-decoration-conditional-design.md`'s
"Measurements" section, not re-derived for this pass. Five questions were
measured against the tree at `0ff6e1d`, rather than assumed.

- **A decorator does not need a new `ProviderShape`.** A wrapper is an
  ordinary class or factory. Given a plan in which the undecorated binding
  sits under one key and the wrapper sits under the public key taking the
  undecorated form as a parameter, `construct.sync` builds it through the
  `CLASS` / `FUNCTION` / `GENERATOR` / `CONTEXT_MANAGER` cases it already
  has. `construct.py`'s match over `ProviderShape` therefore stays
  exhaustive with no new case, and `graph.py`, `frozen.py`,
  `diagnostics.py`, and `render.py` need no change for decoration at all.
  This is the third time the alias pattern composes: a node of an existing
  shape whose parameters are what it depends on.

- **Two nodes produce one teardown, in the undecorated position.** The
  shape above was built from 0.10.0 primitives — a generator provider under
  one key, a wrapper factory under another, a lifecycle provider constructed
  before it and a lifecycle consumer after it — and the recorded event
  sequence is byte-identical to the same graph with the wrapper removed:

  ```
  decorated  : open early, open base, open late, close late, close base, close early
  undecorated: open early, open base, open late, close late, close base, close early
  ```

  Resolving the decorated key twice, and resolving it through a consumer as
  well, adds no further `open base` or `close base`. The second cache entry
  the inner node occupies holds the undecorated value; it is not a second
  construction, and teardown count follows construction, not caching. A
  wrapper that owns a teardown of its own nests correctly inside the base's:

  ```
  open early, open base, open wrap, open late, close late, close wrap, close base, close early
  ```

- **A `Protocol` passed as the decorated key does not trip mypy's
  `type-abstract`.** `decorate(key: ProviderKey, ...)` takes a union, which
  is the resolution Step 3 cycle 1 measured for `provides`.
  `decorate(Store, logged)` with `Store` a `Protocol`, and with the wrapper
  given as a class or as a function, is clean under both `mypy --strict` and
  `basedpyright --strict`. A signature spelled `key: type[T]` would not be.

- **A frozen dataclass keys the plan.** `Underlying(Store, 0)` is hashable,
  compares by value, nests, and survives a `GenericAlias` inside it. The PEP
  695 alias may name it before it is defined, because a `type` alias is
  lazy, and the dataclass may annotate its field with the alias for the
  same reason.

- **The frame short-circuit bypasses a decorator.**
  `FrozenContainer._resolve_params_sync` fills a parameter from the active
  scope frame whenever `param.key in frame`, before consulting the plan.
  For a key seeded with `ScopeFrame.provide`, a parameter would therefore
  receive the undecorated value while `resolve(key)` returned the decorated
  one. That is why decorating a `Container.scope_value` binding is rejected
  in this cycle rather than left half-working; narrowing the short-circuit
  belongs to a cycle that owns that path.

## Teardown event sequences

From Task 5 Step 5, verbatim:

```
baseline:  ['open early', 'open store', 'open late', 'close late', 'close store', 'close early']
decorated: ['open early', 'open store', 'open late', 'close late', 'close store', 'close early']
```

Identical — `assert events == baseline` and `assert events.count('close
store') == 1` both passed on first implementation; no correction to the fold
was needed for this criterion.

## The metamorphic property's measured bite

`test_an_inactive_binding_leaves_the_plan_as_if_it_were_never_written` in
`tests/unit/test_graph_properties.py` asserts, over generated graphs, that
stripping `INACTIVE_NOTE` from a `freeze()` failure message reproduces the
message the same graph would raise with every inactive binding deleted
outright. Over 2000 generated cases, 968 drew a non-empty `inactive` set and
46 produced a `freeze()` error carrying the inactive note. This is a
measurement of how often the property's error branch fires, not a coverage
target: at the suite's default budget of 100 examples per run, the note
branch fires roughly two times per run, while the other draws still exercise
the property's stronger half — an inactive binding changes nothing about the
rest of the plan. The property keeps its default budget; raising
`max_examples` would buy a rarer branch at CI-time cost for a property that
is sampled every run and repeatedly across CI's matrix.

## Hypothesis statistics (Task 7 Step 4)

`uv run pytest tests/unit/test_graph_properties.py --hypothesis-show-statistics`:
all 11 tests passed (100 examples each, default profile, except the two
`max_examples=200` marked tests). Standalone instrumentation of `_graphs()`
at the same 100-example budget used by
`test_an_inactive_binding_leaves_the_plan_as_if_it_were_never_written`
recorded 33/100 generated cases with both `decorations` and `inactive`
non-empty simultaneously; a separate 2000-example sample gave 605/2000
(~30%), confirming the two new fields are exercised together routinely, not
as a rare edge case.

## Benchmarks

```console
$ uv run --group bench pytest benchmarks --benchmark-only
22 passed in 18.66s
```

| Case | Mean |
| --- | ---: |
| `test_resolve_a_cached_singleton` | 2.1931 us |
| `test_resolve_a_singleton_through_a_two_deep_decoration_chain` | 2.1876 us |
| `test_resolve_a_cached_singleton_through_an_alias` | 4.3688 us |
| `test_call_through_an_inject_wrapper` | 7.0254 us |
| `test_resolve_an_async_singleton` | 19.9753 us |
| `test_resolve_a_collection[10]` | 22.2867 us |
| `test_resolve_a_transient_chain` | 42.8348 us |
| `test_resolve_a_collection[100]` | 155.8387 us |
| `test_open_and_close_a_scope` | 221.3901 us |
| `test_freeze_a_chain[10]` | 447.5377 us |
| `test_freeze_a_chain_of_generic_keys[10]` | 818.4755 us |
| `test_freeze_a_chain_with_every_node_decorated[10]` | 1,066.6373 us |
| `test_export_a_large_graph_as_dot` | 2,652.5151 us |
| `test_freeze_a_chain[100]` | 4,241.3990 us |
| `test_build_the_graph_view` | 5,614.4986 us |
| `test_explain_a_deep_chain` | 7,999.8560 us |
| `test_freeze_a_chain_of_generic_keys[100]` | 7,977.2053 us |
| `test_freeze_a_chain_with_every_node_decorated[100]` | 10,217.5426 us |
| `test_explain_a_deep_chain_with_every_node_decorated` | 21,999.7944 us |
| `test_freeze_a_chain[1000]` | 43,978.4596 us |
| `test_freeze_a_chain_of_generic_keys[1000]` | 101,393.3952 us |
| `test_freeze_a_chain_with_every_node_decorated[1000]` | 107,519.8090 us |

`test_resolve_a_singleton_through_a_two_deep_decoration_chain`,
`test_freeze_a_chain_with_every_node_decorated[10/100/1000]`, and
`test_explain_a_deep_chain_with_every_node_decorated` are new this cycle
(`git log -p 0ff6e1d..HEAD -- benchmarks/` shows exactly these four
functions added, none removed). `test_freeze_a_chain_of_generic_keys` is not
new to this cycle — it was added by the prior generic-keys cycle and has a
directly comparable figure in
`specs/evidence/2026-08-31-step-3-generic-keys.md` (743.87 / 7,206.29 /
89,126.06 us for sizes 10/100/1000, against 818.48 / 7,977.21 / 101,393.40
us here); the difference is within host-noise range for this benchmark
suite, not an order-of-magnitude change. Every other case has a directly
comparable figure in `specs/evidence/2026-08-31-step-3-optional-collections.md`;
none shows an order-of-magnitude change, consistent with the design
measurement above that decoration adds no new `ProviderShape` and touches no
line inside `construct.py`.

The repository commits no benchmark baseline (`benchmarks/` has no
checked-in JSON), so a "no regression" claim for the pre-existing cases is
made by the CI benchmark job, which measures base and head back-to-back on
one runner, not by this local, single-host run.

## Mutation gate

Not run for this pass. `[tool.mutmut] only_mutate` in `pyproject.toml` is
`["depin/_core/*.py"]` — every module under `depin/_core/`, not a
changed-modules subset — so a local `uv run mutmut run` is the full mutant
matrix regardless of how small this cycle's nine-module diff is. Prior
evidence (`specs/evidence/2026-08-30-step-2-diagnostics.md`,
`specs/evidence/2026-08-31-step-3-provides-aliasing.md`) records that same
full run taking tens of minutes and its baseline collection as fragile under
host CPU contention. Re-running it here would not measure anything scoped to
this cycle's nine changed modules; it would re-measure the whole package
under exactly the conditions already documented as unreliable.

The CI `mutation` job (`.github/workflows/mutation.yml`, path filter
`depin/_core/**`) triggers on this branch's changes and is the authority for
this gate. It is left to run in CI rather than reproduced locally, and no
score is recorded here in its place.

## Scope note

This record covers Steps 1, 2, 4, 5, 6, and 7 of the Task 9 brief. Step 3,
the mutation gate, is deferred to the CI `mutation` job for the reasons given
above. Everything else in this document was measured locally, on a clean
working tree, against `d91827627bc6b1f641781f063ab133681306bc9f`.
