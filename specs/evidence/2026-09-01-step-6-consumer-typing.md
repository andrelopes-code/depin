# Step 6 — consumer typing compatibility: evidence

Date: 2026-09-01

Baseline commit (`main`, 0.16.3): `2816b09`
Measured commit (this branch): the tree this file lands in

Design: `specs/2026-09-01-step-6-consumer-typing-design.md`
Plan: `specs/plans/2026-09-01-step-6-consumer-typing.md`
Proposal whose acceptance criteria this document answers:
`specs/proposals/2026-08-31-multi-checker-consumer-typing-proposal.md`

The commits this step covers, oldest first: `acf12c0` (design and plan),
`ccb1fa0` (R4 and the `provides=` repair), `264d32e` (the corpus, the runner and
the consumer gate), `79a20d0` and `4762a2b` (two CI defects and the public-surface
coverage map), `03058f8` (the source layer).

Every command below was run against the working tree at the measured commit.
Every output is copied from a run performed while writing this document; nothing
is transcribed from an earlier one. Where a number in an input document did not
survive measurement, the last section says so.

## Normal results

### The consumer layer

```
$ uv run python -m scripts.conformance
checker       mode    stage         result
------------------------------------------
artifact      -       isolation     pass  pydepin-0.16.3-py3-none-any.whl
mypy          core    control       pass  16 import-not-found
mypy          core    positive      pass  12 files
mypy          core    anti-erasure  pass  9 files
mypy          extras  control       pass  42 import-not-found
mypy          extras  positive      pass  18 files
mypy          -       negative      pass  6 fixtures
mypy          -       divergence    pass  2 fixtures
pyright       core    control       pass  20 reportMissingImports
pyright       core    positive      pass  12 files
pyright       extras  control       pass  63 reportMissingImports
pyright       extras  positive      pass  18 files
pyright       -       negative      pass  6 fixtures
pyright       -       divergence    pass  2 fixtures
basedpyright  core    control       pass  20 reportMissingImports
basedpyright  core    positive      pass  12 files
basedpyright  core    anti-erasure  pass  12 files
basedpyright  extras  control       pass  63 reportMissingImports
basedpyright  extras  positive      pass  18 files
basedpyright  extras  anti-erasure  pass  18 files
basedpyright  -       negative      pass  6 fixtures
basedpyright  -       divergence    pass  2 fixtures
ty            core    control       pass  20 unresolved-import
ty            core    positive      pass  12 files, no count reported
ty            extras  control       pass  63 unresolved-import
ty            extras  positive      pass  18 files, no count reported
ty            -       negative      pass  6 fixtures
ty            -       divergence    pass  2 fixtures
pyrefly       core    control       pass  20 missing-import
pyrefly       core    positive      pass  12 files
pyrefly       extras  control       pass  63 missing-import
pyrefly       extras  positive      pass  18 files
pyrefly       -       negative      pass  6 fixtures
pyrefly       -       divergence    pass  2 fixtures

34 checks passed
```

Exit status 0.

**Checked-file counts.** The positive corpus is 12 files in core-only mode —
`corpus/core/c01`…`c09` plus `corpus/ext_core/e01`…`e03` — and 18 in all-extras
mode, adding `corpus/ext_extras/x01`…`x06`. Every checker that reports a count
reports the same one. ty reports none, and the table says so rather than
printing a number it did not get.

The anti-erasure counts are deliberately not the positive counts. Basedpyright
runs `reportAny` and `reportExplicitAny` over the whole positive corpus in both
modes, so it reports 12 and 18. mypy runs `--disallow-any-expr` over
`corpus/core` alone, which is 9 files: in all-extras mode third-party
annotations produce `Any` expressions the corpus does not own, and the flag is
unusable there.

**The control counts are the isolation proof, not a statistic.** Each is the
number of unresolved-import diagnostics that checker produced running the
identical command line, from the identical working directory, against an
interpreter with no `depin` installed. A zero there would mean the checker had
found `depin` somewhere it should not have been able to. The counts differ by
checker because each reports a different number of diagnostics per unresolved
import, and by mode because all-extras adds six files with framework imports the
empty interpreter also lacks.

**The corpus is 258 `assert_type` calls and 88 typed witnesses**, across the 18
files. The split is the design's rule: `assert_type` for a nominal class, a
`Protocol`, a parameterised generic of a depin type, a builtin, `None`, and
unions of those; a typed witness for anything a decorator returned, anything
awaitable, any context manager, and any enum member expression.

### The source layer

```
$ uv run python -m scripts.conformance --source
checker  mode  stage   result
-----------------------------
pyright  -     source  pass  154 files, mypy 154
ty       -     source  pass  44 diagnostics, 30 registered
pyrefly  -     source  pass  2 diagnostics, 2 registered

3 checks passed
```

Exit status 0.

Stock Pyright's 154 is asserted equal to mypy's 154 over the same file list.
A count of its own catches only a total drop; an absolute path silently ignored
in `include` produces a green run over a smaller file set, and only the
comparison catches that.

`uv sync --all-extras` is a precondition for this layer. Without it the three
checkers report unresolved framework imports for `depin/ext/litestar.py` and its
neighbours, and the run fails with 25 unregistered diagnostics. CI's
`typing-source` job syncs the extras for the same reason: four of ty's register
entries exist only because ty resolves `taskiq.TaskiqResult` through pydantic's
`PydanticRecursiveRef`.

### The two registers, and how they classify

**ty: 30 entries, 44 diagnostics.**

| Classification | Diagnostics | What it is |
| --- | --- | --- |
| Suppression spelling | 27 | The line already carries a `# type: ignore[code]  # pyright: ignore[code]` pair. ty honours a bare `# type: ignore` and its own `# ty: ignore[...]`, and reads neither of those two |
| Gradual inference | 13 | ty leaves a type variable, a `getattr` result or a `callable()` narrowing as `Unknown`, `Any` or `Top[(...) -> object]` where the other four solve it |
| `PydanticRecursiveRef` | 4 | ty resolves `taskiq.TaskiqResult` through pydantic's recursive reference, so a constructed result reads as `BaseModel \| None \| Any` |

**Pyrefly: 2 entries, 2 diagnostics.** Both `implicit-any-lambda`, both the same
gap: Pyrefly does not propagate a `key=`/`filter` parameter type into the lambda
passed to it, one in `depin/_core/graph.py` and one in
`tests/unit/test_graph_properties.py`. A further 31 diagnostics are suppressed
without a register entry, because Pyrefly honours `# type: ignore` by default and
so reads the mypy half of every waiver pair in the repository.

Under `--preset basic` the same Pyrefly run reports 0 where `strict` reports 2.
An unconfigured Pyrefly is not evidence, which is why both layers pass an
explicit configuration.

## Fault injection

Eight injections. **Each was applied, measured and reverted while writing this
document**; none is transcribed from an earlier run. The commands are given
verbatim and the output is trimmed only where the table above already carries the
passing rows.

| # | Injection | Gate that must fail | Measured |
| --- | --- | --- | --- |
| 1 | `depin/py.typed` excluded from the wheel build | the artifact stage, on both the RECORD listing and the payload | 2 failures, exit 1 |
| 2 | the runner checks the corpus in place instead of the copied directory | the per-subprocess working-directory guard, before any checker runs | raised before the first checker |
| 3 | a wrong `assert_type` in the corpus | all five, each with its own rule identifier | 5 failures, exit 1 |
| 4 | a negative fixture's misuse rewritten as valid | all five, for a missing expected rejection | 5 failures |
| 5 | a name added to `depin.__all__` with no `coverage.toml` entry | the unit gate, naming the symbol | 1 failed test |
| 6 | a recorded divergence verdict flipped | the divergence stage, naming fixture, recorded verdict and observed verdict | 1 failure |
| 7 | a second diagnostic of a rule the ty register already carries | the source stage, on the count | 1 failure |
| 8 | a register entry deleted while its diagnostic still occurs | the source stage, on the unregistered diagnostic | 1 failure |

### 1 — the wheel loses its typing marker

`[tool.hatch.build.targets.wheel]` gained `exclude = ["depin/py.typed"]`, and the
wheel was rebuilt.

```
$ uv build --wheel --out-dir <tmp>/dist
Successfully built <tmp>/dist/pydepin-0.16.3-py3-none-any.whl

$ uv run python -m scripts.conformance --verify-artifact --wheel <tmp>/dist/pydepin-0.16.3-py3-none-any.whl

2 failures
  artifact / - / wheel: pydepin-0.16.3.dist-info/RECORD does not list depin/py.typed
  artifact / - / wheel: the wheel payload carries no depin/py.typed
EXIT=1
```

Both assertions fire, and they are two assertions rather than one on purpose: a
`namelist()` membership test alone passes on a wheel whose RECORD and payload
disagree, and RECORD is what an installer copies from.

### 2 — the corpus is checked where it lives

`scripts/conformance/workspace.py`'s `build_workspace` was changed to return
`corpus=CONFORMANCE` — the checkout's own `conformance/` — instead of the copy it
makes under a temporary directory.

```
$ uv run python -m scripts.conformance --checker mypy --mode core --only positive
conformance: refusing to check from /…/conformance: the checkout /… is that
directory or an ancestor of it, so a checker would resolve depin out of the
source tree and report success against an empty interpreter
```

No checker ran. The guard is on each subprocess rather than on the runner
process, because `uv run python -m scripts.conformance` resolves from the
checkout by definition and in CI the checkout is the default working directory.

This case exists because of a measurement taken during the design. From the
repository root, mypy resolves `depin` out of the checkout even when the
interpreter it was pointed at has no `depin` installed at all, and reports
`Success: no issues found in 1 source file`. The empty-interpreter control would
have passed while proving nothing.

### 3 — a wrong `assert_type`

`conformance/corpus/core/c02_keys.py:54` was changed from
`assert_type(di.resolve(Config), Config)` to `assert_type(di.resolve(Config), str)`.

```
$ uv run python -m scripts.conformance --mode core --only positive
checker       mode  stage      result
-------------------------------------
artifact      -     isolation  pass  pydepin-0.16.3-py3-none-any.whl
mypy          core  positive   FAIL  12 files
pyright       core  positive   FAIL  12 files
basedpyright  core  positive   FAIL  12 files
ty            core  positive   FAIL  12 files, no count reported
pyrefly       core  positive   FAIL  12 files

5 failures
  mypy / core / positive: corpus/core/c02_keys.py:54 assert-type
  pyright / core / positive: /tmp/depin-conformance-2ssoqcwn/conformance/corpus/core/c02_keys.py:54 reportAssertTypeFailure
  basedpyright / core / positive: /tmp/depin-conformance-2ssoqcwn/conformance/corpus/core/c02_keys.py:54 reportAssertTypeFailure
  ty / core / positive: corpus/core/c02_keys.py:54 type-assertion-failure
  pyrefly / core / positive: corpus/core/c02_keys.py:54 assert-type
```

Five checkers, five rule identifiers, one line: mypy `assert-type`, both Pyright
engines `reportAssertTypeFailure`, ty `type-assertion-failure`, Pyrefly
`assert-type`. This is what a single-checker gate cannot show — that the promise
is the same promise under all five, spelled five ways.

### 4 — a negative fixture stops being negative

`conformance/negative/n01_resolve_non_key.py`'s `di.resolve(42)` was rewritten as
`di.resolve(Config)`, which is valid.

```
$ uv run python -m scripts.conformance --only negative
checker       mode  stage      result
-------------------------------------
artifact      -     isolation  pass  pydepin-0.16.3-py3-none-any.whl
mypy          -     negative   FAIL  6 fixtures
pyright       -     negative   FAIL  6 fixtures
basedpyright  -     negative   FAIL  6 fixtures
ty            -     negative   FAIL  6 fixtures
pyrefly       -     negative   FAIL  6 fixtures

5 failures
  mypy / core / negative: n01: exit 0, the misuse was accepted
  pyright / core / negative: n01: exit 0, the misuse was accepted
  basedpyright / core / negative: n01: exit 0, the misuse was accepted
  ty / core / negative: n01: exit 0, the misuse was accepted
  pyrefly / core / negative: n01: exit 0, the misuse was accepted
```

All five report `exit 0, the misuse was accepted`. The fixtures are run one file
at a time, so an unrelated diagnostic elsewhere in the tree cannot make one pass
by accident.

### 5 — a public symbol arrives without a coverage decision

`Nonce = Token` was added to `depin/__init__.py` and `'Nonce'` to `depin.__all__`.

```
$ uv run pytest tests/unit/test_conformance_coverage.py -q
_____________ test_every_public_symbol_has_a_coverage_entry[Nonce] _____________
E       AssertionError: Nonce is public but conformance/coverage.toml carries no
        entry for it; add the fixtures that exercise it, or a decision and a reason
1 failed, 238 passed in 1.71s
```

The failing parameter names the symbol, so the message is actionable without
opening the map. The gate fails the other way too: an entry naming a symbol that
is no longer public is a failure, so the map shrinks when the surface does.

### 6 — a divergence verdict is flipped

`conformance/expected/divergence.toml`'s `[d02] pyrefly` was changed from
`reject` to `accept`.

```
$ uv run python -m scripts.conformance --only divergence --checker pyrefly
checker   mode  stage       result
----------------------------------
artifact  -     isolation   pass  pydepin-0.16.3-py3-none-any.whl
pyrefly   -     divergence  FAIL  2 fixtures

1 failures
  pyrefly / core / divergence: d02: recorded accept, observed reject — it now
  rejects a call the register records as accepted; record the new verdict
  deliberately. divergence/d02_value_of_the_wrong_type.py:26 bad-argument-type
```

The failure names the fixture, the recorded verdict and the observed verdict, and
says what to do. The register carries verdicts only — no line, no rule
identifier — so that a blocking gate does not depend on Pyrefly continuing to
spell `bad-argument-type` the way it does today. The rule appears in the failure
message as context, not as an expectation.

### 7 — a second diagnostic of a registered rule

A second `frozen.resolve(43)` misuse, carrying the same waiver pair, was added to
`tests/unit/test_resolution.py` beside the existing one. The register carries
`tests/unit/test_resolution.py:invalid-argument-type:1`.

```
$ uv run python -m scripts.conformance --source --checker ty
checker  mode  stage   result
-----------------------------
ty       -     source  FAIL  45 diagnostics, 30 registered

1 failures
  ty / - / source: ty-source.txt registers 1 invalid-argument-type in
  tests/unit/test_resolution.py, 2 appear; a count moves in either direction
  only by a deliberate edit to the register
```

This is the case the count exists for. A bare `file:rule` pair would have
absorbed the second diagnostic silently, which is precisely the property the
register exists to deny.

### 8 — a register entry is deleted while it still occurs

The `tests/unit/test_resolution.py:invalid-argument-type:1` line was removed from
`conformance/expected/ty-source.txt`, with the source unchanged.

```
$ uv run python -m scripts.conformance --source --checker ty
checker  mode  stage   result
-----------------------------
ty       -     source  FAIL  44 diagnostics, 29 registered

1 failures
  ty / - / source: tests/unit/test_resolution.py: 1 invalid-argument-type that
  ty-source.txt does not carry, and must
```

The register fails in three directions and 7 and 8 measure two of them; the third
— an entry that no longer appears — is the one that makes the register shrink
when the underlying limitation is fixed upstream.

## The R4 control

The fault injections show the suite detects a break. This shows the library
change under it is load-bearing rather than decorative.

One consumer program, importing nothing 0.16.3 did not already export, checked
against two wheels: one built from `2816b09`, one built from the merged tree.
Both are installed into their own interpreter, and the program is checked from a
directory outside the checkout.

```python
from typing import assert_type

from depin import Container, ProviderKey, Token

port = Token[int]('port')


def make_port() -> int:
    return 8080


def a_token_names_the_binding_it_registers() -> None:
    di = Container().bind(make_port, provides=port).freeze()
    assert_type(di.resolve(port), int)


def a_token_is_a_provider_key() -> None:
    _key: ProviderKey = port
```

Against the wheel built from `2816b09`:

```
$ uvx mypy@2.3.1 --strict --python-executable ../venv-old/bin/python control.py
control.py:19: error: No overload variant of "bind" of "BindingCollector" matches argument types "Callable[[], int]", "Token[int]"  [call-overload]
control.py:20: error: Expression is of type "Any", not "int"  [assert-type]
Found 2 errors in 1 file (checked 1 source file)

$ uvx pyright@1.1.411 --pythonpath ../venv-old/bin/python control.py
3 errors, 0 warnings, 0 informations

$ uvx basedpyright@1.39.10 --pythonpath ../venv-old/bin/python control.py
3 errors, 3 warnings, 0 notes

$ uvx ty@0.0.77 check --python ../venv-old --error all --output-format concise control.py
control.py:19:10: error[no-matching-overload] No overload of bound method `BindingCollector.bind` matches arguments
control.py:20:5: error[type-assertion-failure] Type `Unknown` does not match asserted type `int`
Found 2 diagnostics

$ uvx pyrefly@1.2.0 check --preset strict --python-interpreter-path ../venv-old/bin/python control.py
ERROR No matching overload found for function `depin._core.bindings.BindingCollector.bind` called with arguments: (() -> int, provides=Token[int]) [no-matching-overload]
ERROR assert_type(Unknown, int) failed [assert-type]
ERROR `Token[int]` is not assignable to `GenericAlias | Token[object] | Underlying | str | type[object]` [bad-assignment]
 INFO 3 errors
```

Against the wheel built from the merged tree, the identical commands:

```
$ uvx mypy@2.3.1 --strict --python-executable ../venv-new/bin/python control.py
Success: no issues found in 1 source file

$ uvx pyright@1.1.411 --pythonpath ../venv-new/bin/python control.py
0 errors, 0 warnings, 0 informations

$ uvx basedpyright@1.39.10 --pythonpath ../venv-new/bin/python control.py
0 errors, 1 warning, 0 notes

$ uvx ty@0.0.77 check --python ../venv-new --error all --output-format concise control.py
All checks passed!

$ uvx pyrefly@1.2.0 check --preset strict --python-interpreter-path ../venv-new/bin/python control.py
 INFO 0 errors
```

Basedpyright's remaining warning is `reportUnusedCallResult` on the
`assert_type` call, raised because this control is run without the corpus
configuration; it is not an error and does not name a depin type.

Three things are visible here that a single number would hide.

**Pyrefly's third error is the one nothing else reports.** `_key: ProviderKey =
port` is a plain assignment of a `Token[int]` to the public key alias. mypy,
both Pyright engines and ty accept it, because they infer the phantom parameter
covariant. Pyrefly does not, and that assignment is what the non-generic
supertype repairs. Without R4 it would remain, whatever else changed.

**One bad argument costs more than one diagnostic.** The `provides=` rejection
degrades the whole chain to `Unknown`, so a two-line program produces two mypy
errors, three Pyright errors, and — in the fuller version of this probe measured
during the design — seven under strict mode. That is the shape of the defect the
consumer contract exists to catch: a program that runs correctly and that every
checker rejects.

**The two changes had to land together.** Written against `Token[object]`, the
`provides=` repair works under the four checkers that infer the phantom
parameter covariant and fails under Pyrefly, which does not. It would have
depended on exactly the variance R4 exists to stop depending on.

## Two CI defects found en route

Neither is a defect in the typing work. Both are recorded because each was a red
job whose cause was somewhere the job's name did not point.

### `mutation` failed on a file the unit suite reads at collection time

mutmut runs `pytest tests/unit` from inside a generated `mutants/` directory, and
copies only what `[tool.mutmut] also_copy` lists. The list was `["scripts"]`.

`tests/unit/test_conformance_coverage.py` parametrises over
`conformance/coverage.toml`, which it reads at **collection** time — before any
test body runs, and therefore before any failure could be attributed to a mutant.
Inside `mutants/` the file did not exist, so collection failed and the whole
mutation gate went red.

The fix is `also_copy = ["scripts", "conformance"]`, with a comment stating the
rule the omission broke: anything the unit suite reads from the working tree has
to be copied into `mutants/` too. The general form of this defect is that a
generated-tree test runner is only as complete as its copy list, and a test that
reads data at collection time is the case that surfaces it.

### `checks (ubuntu-latest, 3.13)` failed on a correct library

Three integration tests — Flask, Litestar and Starlette — asserted that two
requests get independent scoped instances by recording `id(counter)` during each
request and comparing the two integers.

`id()` is unique only among **live** objects. The first instance is dropped when
its request scope closes, which happens before the second request allocates its
own; CPython's allocator then reuses the freed block, and the two addresses can
be equal. The assertion `seen[0] != seen[1]` therefore fails on a library that
behaved correctly.

It failed that way on Python 3.13 in CI. The fix holds the instances rather than
their addresses — `seen: list[Counter]`, `seen[0] is not seen[1]` — which keeps
both alive and makes the identity comparison both sound and deterministic.

The other `id()` comparisons in the integration suite were audited and left
alone: the Click and Taskiq cases compare instances cached in a scope that stays
open across every recording, and the Flask streaming case holds its resource in a
list for the length of the test. The rule is that comparing `id()` is sound only
while every object compared is provably alive.

## The proposal's acceptance criteria, item by item

The proposal's list is in
`specs/proposals/2026-08-31-multi-checker-consumer-typing-proposal.md` under
"Acceptance criteria for the future implementation". Each is answered with the
evidence, and each not delivered says so.

**1. A wheel-built, isolated consumer compatibility suite is a required CI gate.**
Delivered. `.github/workflows/ci.yml` carries `typing-artifact` (builds one wheel,
checks its metadata, asserts the typing marker, uploads it) and `typing-consumer`
(five job instances, one per checker, each downloading that wheel). Neither uses
`continue-on-error`; both fail the build. One wheel is built once and shared, so
five jobs cannot disagree about what they measured.

**2. All five pass the positive consumer corpus with zero diagnostics.**
Delivered, in both install modes. The normal-results table above, `positive` rows:
12 files in core-only mode and 18 in all-extras, for each of the five, with no
baseline file and nothing filtered.

**3. Every checker preserves the exact or assignable types the corpus classifies,
including generic arguments and callable signatures.** Delivered. 258
`assert_type` calls and 88 typed witnesses, classified by the rule in the design:
exact assertion for a nominal class, a `Protocol`, a parameterised generic of a
depin type, a builtin, `None` and unions of those; a typed witness for anything a
decorator returned, anything awaitable, any context manager and any enum member
expression. Injection 3 shows a wrong exact assertion failing all five.

**4. Every negative fixture is rejected by all five for the intended reason.**
Delivered. Six fixtures, one misuse each, no suppressions, run one file at a
time. `conformance/expected/negative.toml` records the **line** and the **rule
identifier** per checker, never message text: for the same misuse the three
checkers that name a type name three different ones, and ty has printed both
sides of one disagreement identically as ``Type `() -> Cache` does not match
asserted type `() -> Cache` ``. Injection 4 shows the stage failing when a
fixture stops being invalid.

**5. The suite detects `Any` or unknown leakage.** Delivered, **by two checkers
and not five**. Basedpyright runs `reportAny` and `reportExplicitAny` at error
over the whole positive corpus; mypy runs `--disallow-any-expr` over
`corpus/core` only. ty cannot express an anti-`Any` rule at all and stock Pyright
has no equivalent of `reportAny`. `docs/support-policy.md` states the assignment
rather than implying five-way coverage — which is the honest answer to this
criterion, not a partial one.

**6. Core and FastAPI covered without a runtime dependency reaching the core.**
Delivered, and wider than the criterion asks. `depin/ext/` now holds twelve
modules. The corpus splits them by install mode rather than by framework:
`corpus/ext_core/` covers the four that import no third-party package —
`__init__`, `asgi`, `wsgi`, `cli` — and is checked in **both** modes;
`corpus/ext_extras/` covers the eight that require an extra, in all-extras mode.
In core-only mode the runner asserts all eight are **unresolvable**, which is the
positive proof that the core carries no framework dependency.

**7. The wheel is proven to carry `depin/py.typed`, and the consumer is proven to
import from it.** Delivered, four ways: `RECORD` membership read through the zip
central directory; `direct_url.json` carrying `archive_info` rather than
`dir_info: {"editable": true}` with no `__editable__*.pth` in site-packages;
`depin.__file__` inside the venv with no `sys.path` entry at or inside the
checkout; and the empty-interpreter control, which requires every checker to
report its unresolved-import rule from the identical command line and directory.
Injection 1 fails the first; injection 2 fails the working-directory guard the
fourth depends on.

**8. Stock Pyright runs independently of Basedpyright.** Delivered, at both
layers. Layer 2 gives it `conformance/config/pyright.json`; Layer 1 gives it
`conformance/config/pyright-source.json`, passed with `-p`. That configuration
cannot live in `pyproject.toml`: Basedpyright 1.39.10 refuses to parse a file
carrying both a `pyright` and a `basedpyright` table, exits 3, and discards the
whole configuration — which would silently degrade the repository's own commit
gate to its defaults. A named file passed on the command line is also not the
root `pyrightconfig.json` that AGENTS.md bans, which Pyright discovers
implicitly.

**9. ty and Pyrefly propagate a real exit status.** Delivered. The advisory `ty`
job whose check step ended in `exit 0` is removed. Both now run in
`typing-consumer` at zero and in `typing-source` against a register, and the
runner exits non-zero listing every failure. Injections 3, 4, 7 and 8 are the
demonstration that neither can pass unconditionally.

**10. No positive fixture relies on a checker-specific suppression.** Delivered.
`conformance/corpus/`, `conformance/negative/` and `conformance/divergence/`
contain no `# type: ignore`, no `# pyright: ignore`, no `# ty: ignore`, no
`# pyrefly: ignore` and no `typing.cast`. The single textual match is a docstring
in `negative/n02_check_parameter.py` quoting the spelling that the negative
fixtures exist to replace.

**11. Every exported symbol has an explicit coverage decision.** Delivered within
a stated scope. `conformance/coverage.toml` carries 76 entries — 71 naming
fixtures, 5 recording a decision and a reason — over three sources:
`depin.__all__` and `depin.errors` by import, and `depin/ext/` parsed with `ast`
rather than imported, because the test also runs on the free-threaded and
pre-release jobs where no framework is installed.
`tests/unit/test_conformance_coverage.py` fails in both directions. Injection 5
shows a new public symbol failing it.

**Class members are out of scope, and that is a decision rather than an
omission.** `RequestScope.__call__`, `CommandContext.with_resource[T]` and every
`Container` method are not top-level names, so adding `Container.foo()` passes
this gate. The corpus guards members by exercising them, but nothing fails when a
*new* member arrives untested. Step 8's surface review is where member-level
inventory belongs.

**12. Contributor documentation and the support policy describe the matrix CI
enforces.** Delivered. `docs/support-policy.md`'s "Type checkers" section
carries the three layers with each checker's authority, the five pinned versions,
the language and OS targets, the minimum-equals-current rule, the two install
modes, the per-pull-request target and the weekly probe, the anti-`Any`
assignment, the two false negatives and the upstream link. `CONTRIBUTING.md`
gains a "typing conformance suite" section with the layer table and the four
flags, and states that the five commit gates are unchanged.
`.github/PULL_REQUEST_TEMPLATE.md` gains one line naming the three jobs and
saying they are CI gates.

**13. Checker versions and Python language targets are recorded reproducibly.**
Delivered. `conformance/checkers.toml` is the only place a version appears for
this suite; CI and the local runner both read it, and the runner asserts that the
pinned mypy and Basedpyright versions **equal** what `uv.lock` resolves rather
than merely satisfying the `dev` floor — `dev` declares `mypy>=1.18`, which every
future resolution satisfies while `uv run mypy` and `uvx mypy@2.3.1` drift apart,
and Dependabot runs weekly. The language target `python = "3.12"` and the OS
target `os = "linux"` are in the same file, so a local run reproduces the gate
exactly.

**Not delivered, and deliberately: testing both the oldest and the current
supported version of each stable line.** The proposal asks the design to evaluate
it. The evaluation concluded that the project has measured exactly one version of
each checker, and that naming a lower minimum on that basis would be a support
claim with no evidence behind it — which the proposal itself forbids. So minimum
supported equals current tested for all five, the support policy says why, and
the weekly probe's previous-release leg is what will build the evidence to lower
one honestly. This is a deferral with a stated mechanism, not a gap.

**14. Representative fault injection proves the suite is sensitive.** Delivered.
Eight injections above, each applied, measured and reverted. The proposal's two
named minimum cases are both covered: removing the wheel's typing marker fails
the artifact guard (injection 1), and degrading a type-dependent promise fails
all five consumer jobs (injection 3). The R4 control adds the case the proposal
did not ask for and the design did — that the library change under the suite is
load-bearing.

**15. The ordinary repository gate remains green.** Delivered. The five commit
gates, `mkdocs build --strict`, and both conformance layers all pass on the
measured commit. Two CI defects surfaced during the work and are recorded above;
both were fixed in the commits that found them.

## Corrections the work made to its own inputs

Five claims in the documents this step was handed did not survive measurement.
Each is corrected in the document that made it; they are collected here so a
later reader can see what moved and why.

**Eight `Token[object]` positions were nine.** The roadmap and the variance
experiment both said eight. `depin/_core/spec.py` carries two,
`depin/_core/markers.py` two, and `depin/_core/introspect.py` five — two
`AnnotatedMeta` fields, their two mirrors as locals in `extract_annotated_meta`,
and the `TypeGuard` on what was `is_object_token`. A tenth mention, that
function's docstring, is prose. The correction matters beyond arithmetic: a
grep for `Token[object]` also misses `depin/_core/typeguards.py`, whose runtime
guard promised `ProviderKey` while admitting only `Token`, and which gates
`FrozenContainer.explain`, `DependencyGraph.find` and `DependencyGraph.node`.

**The `provides=` union needed `str`.** The design first wrote
`type[object] | TokenKey | None`. Measured against the runtime,
`provides='some-key'` **already succeeded** and resolved the binding, because
`as_provider_key` admits a string key; of the five members of `ProviderKey`, only
`Underlying` raises. The rule the design applies is to annotate what the position
accepts, and that rule does not admit an exception for the member nobody had
noticed. The spelling is `type[object] | TokenKey | str | None`. Widening all the
way to `ProviderKey` would have promised `Underlying`, which raises.

**ty's 32 became 44 under the gate's flags.** The baseline counted 32 under a
bare `uvx ty check`. The gate runs `--error all`. Measured on the merged tree the
same run is 31 bare and 44 under the flag, and the 13 the flag adds are
`unsound-return-statement` ten times, `unsound-assignment` twice and
`missing-type-argument` once. Eleven of those are gradual inference and two sit
on a line already carrying the waiver pair, which is how the design's estimate of
two gradual entries became 13 and its 25 suppression-spelling entries became 27.
The estimate was right about what it could see. The register is measured under
the exact invocation the gate runs, and its header says so.

**Two `depin.errors` exceptions inheriting a builtin were four.** The design named
`InvalidProviderError(DepinError, TypeError)` and
`TeardownError(DepinError, RuntimeError)`. `depin/errors.py` also carries
`InvalidScopeError(DepinError, ValueError)` and
`ContainerNotBoundError(DepinError, RuntimeError)`. The second base is a typing
fact rather than a detail: it decides what a consumer's existing
`except ValueError` or `except RuntimeError` now catches, which is exactly why the
coverage map enumerates `depin.errors` as a source of its own.

**The predicted Pyrefly `implicit-any-type-argument` entry disappeared.** The
design predicted a three-entry Pyrefly register — two `implicit-any-lambda` and
one `implicit-any-type-argument` naming `Token[T]` in
`depin/_core/typeguards.py` — and said it might disappear once that guard named
`TokenKey`. It did. The register is two entries, and its header records the
absence rather than leaving a later reader to wonder whether the entry was
dropped or never existed.

One further correction is about the plan rather than the design.
**`scripts/conformance.py` shipped as `scripts/conformance/`.** One file measured
687 code lines against the roughly-400 limit AGENTS.md sets, so the runner is a
package: `cli`, `model`, `pins`, `workspace`, `isolation`, `checkers`, `stages`
and `source`. The plan's file table is corrected.

## The upstream report

The Pyrefly variance divergence is reported as
[facebook/pyrefly#4777](https://github.com/facebook/pyrefly/issues/4777),
"Unused (phantom) PEP 695 type parameter is inferred invariant, not covariant".

The existing issue search was run first over `facebook/pyrefly` for `variance`,
`phantom`, `unused type parameter invariant` and `unused typevar`. The `variance` search
returned thirty issues, open and closed, and none is this one; the nearest, #498,
is an `isinstance` in a constructor defeating inference for a parameter that *is*
used. `phantom` and `unused type parameter invariant` returned nothing relevant.

The report carries the nine-line reproducer the baseline isolated, which imports
nothing from depin, plus the second probe that narrows the divergence to the
unused case: Pyrefly accepts the covariant relation when `T` is used covariantly
and when covariance is declared with a legacy `TypeVar(covariant=True)`, and
rejects it only for the phantom parameter. `pyrefly@latest` resolves to 1.2.0 at
the time of writing and reproduces.

`docs/support-policy.md` links the issue from the paragraph that explains why
Pyrefly rejects `Container.value(Token[int], 'str')` where the other four accept
it.
