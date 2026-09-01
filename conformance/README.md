# The consumer typing conformance suite

Five type checkers — mypy, stock Pyright, Basedpyright, ty and Pyrefly — over a
corpus of ordinary consumer code, checked against the wheel this repository
builds, installed into interpreters that have never heard of the checkout.

```bash
uv run python -m scripts.conformance
uv run python -m scripts.conformance --checker ty --mode core --only positive
```

`--checker`, `--mode` and `--only` are repeatable and narrow the run. The runner
prints a per-checker, per-mode table and exits non-zero listing every failure,
not only the first.

It is a CI gate, not a sixth commit gate: it builds a wheel and creates three
interpreters, which does not belong in a per-commit loop.

## What is where

| Path | What it holds |
| --- | --- |
| `checkers.toml` | The pinned version of each checker, the language and OS targets, the eight extras, and the eight framework-requiring `depin.ext` modules |
| `config/` | One native configuration per checker, templated — `${venv}`, `${venv_parent}`, `${venv_name}` and `${python}` are substituted at run time, once per interpreter |
| `corpus/core/` | Consumer code that imports only `depin` and `depin.errors`. Checked in both install modes |
| `corpus/ext_core/` | The `depin.ext` modules that import no third-party package — `__init__`, `asgi`, `wsgi`, `cli` — against a consumer's own structural types. Checked in **both** modes |
| `negative/` | One misuse per file, no suppressions, checked one file at a time |
| `expected/negative.toml` | Per fixture and per checker: the line and the rule identifier |

The corpus imports only `depin`, `depin.errors` and `depin.ext.*`. It never
imports `depin._core`, and the runner asserts that textually before it checks
anything.

## The two install modes

`core` installs `pydepin` alone. `extras` installs it with all eight extras
named explicitly — there is no aggregate `all` extra. `corpus/core` and
`corpus/ext_core` are checked in both; in `core` mode the runner additionally
asserts that every one of the eight framework-requiring `depin.ext` modules
fails to import, which is what proves the core carries no framework dependency.

## Exact inference versus assignability

`assert_type` is honest for a nominal class, a `Protocol`, a parameterised
generic of a `depin` type, a builtin, `None`, and unions of those. It is
dishonest for anything a decorator returned, anything awaitable, any context
manager, and any enum member expression: the checkers pick different valid
representations there, and ty has printed both sides of one such disagreement
identically.

Those categories use a **typed-assignment witness** instead — a variable
annotated with the promised type, assigned the expression under test. A witness
fails on `Any`, on unknown, on an unrelated type and on a lost generic argument,
and passes when a checker chooses a valid narrower representation.

A witness inside a function carries a leading underscore. `ruff check` is the
second commit gate and `F` is selected; an annotation does not exempt an unused
local, and `_pending` is exempt under ruff's default `dummy-variable-rgx` where
`pending` is not.

`assert_type(Scope.SINGLETON, Scope)` must never appear: every checker narrows a
member access to its literal member type.

## Anti-erasure

`Any` satisfies an assignment in both directions, so neither `assert_type` nor a
witness is sufficient alone. Two checker-native rules carry the requirement:
Basedpyright with `reportAny` and `reportExplicitAny` at error over the whole
positive corpus, and mypy with `--disallow-any-expr` over `corpus/core` only —
it is unusable in all-extras mode, where third-party annotations produce `Any`
expressions the corpus does not own. ty cannot express an anti-`Any` rule at
all, so this requirement is two checkers' and the suite says so rather than
implying five-way coverage.

## What the runner asserts before it checks anything

1. **`RECORD` membership.** `depin/py.typed` appears in `pydepin-*.dist-info/RECORD`,
   located through the zip's central directory. A `namelist()` test alone would
   pass on a wheel whose RECORD and payload disagree.
2. **The install is not editable.** `direct_url.json` carries `archive_info`,
   not `dir_info: {"editable": true}`, and no `__editable__*.pth` exists in
   site-packages.
3. **`depin.__file__` is inside the venv**, and no `sys.path` entry is the
   checkout or inside it.
4. **The empty-interpreter control.** Each checker runs the identical command
   line, from the identical directory, against an interpreter with no `depin`,
   and must report its unresolved-import rule — mypy `import-not-found`, both
   Pyright engines `reportMissingImports`, ty `unresolved-import`, Pyrefly
   `missing-import`. If any checker reports success there, the harness fails:
   its isolation is broken.

The fourth is the decisive one. It is a positive assertion about behaviour
rather than an enumeration of the variables that could leak, so it catches a
stray `.pth`, an `extraPaths` entry, a `MYPYPATH`, or a working directory,
regardless of how it arrived.

## Why the corpus is copied out of the checkout

Run from the repository root, mypy resolves `depin` out of the checkout even
when the interpreter it was pointed at has no `depin` installed at all, and
reports `Success: no issues found`. The working directory is as much a leak as
`PYTHONPATH` is, and the empty-interpreter control would pass while proving
nothing.

So the runner copies `conformance/` into a temporary directory outside the
checkout and gives every checker subprocess that directory as its working
directory, asserting per subprocess that the checkout is neither that directory
nor an ancestor of it. The guard is on the subprocess, never on the runner
process: `uv run python -m scripts.conformance` resolves from the checkout by
definition, and in CI the checkout is the default working directory.

## Configuration traps this suite is shaped around

- **Stock Pyright silently drops an absolute path in `include`.** It prints
  `Ignoring path "…" in "include" array because it is not relative` and then
  reports zero having checked nothing. Paths in `config/pyright.json` are
  relative to the config file, and the file set is passed on the command line.
- **`pythonPath` is not a stock-Pyright key.** It prints
  `Config contains unrecognized setting "pythonPath"` and continues.
  `venvPath` plus `venv` is the working form, which is why the templates carry
  the venv's parent and its name separately.
- **An unconfigured Pyrefly runs the `basic` preset**, which does not report
  `bad-argument-type` at all. The runner always passes an explicit config and
  `--preset strict`.
- **ty has no strict mode and no presets.** `--error all` is the closest honest
  equivalent.

The first two produce a green run over an empty file set, so the runner asserts
a **non-zero checked-file count** for every checker that reports one: mypy,
both Pyright engines, and Pyrefly. ty reports none, and the table says so.

## Expected diagnostics are data, never message text

`expected/negative.toml` records, per fixture and per checker, the **line** and
the **rule identifier**. The harness requires a non-zero exit and at least one
diagnostic on that line carrying that identifier.

Message snapshots are excluded on measured grounds: for the same misuse the
three checkers that name a type name three different ones, and ty has printed
both sides of one disagreement identically as
``Type `() -> Cache` does not match asserted type `() -> Cache` ``. A harness
matching rendered text would be brittle where it is not simply useless.

## How the repository's own tooling sees this directory

- **Outside** `[tool.mypy] files` and `[tool.basedpyright] include`. It has to
  be: the negative fixtures would break the commit gates, and the corpus must be
  checked against the installed wheel rather than the checkout.
- **Outside** `[tool.pytest.ini_options] testpaths`, so nothing here is
  collected and `--doctest-glob=*.md` does not reach this file.
- **Inside** `ruff format` and `ruff check`, and that is wanted. Deliberately
  ill-*typed* code is still ordinary Python and lints clean. No fixture needs a
  `per-file-ignores` entry today; one is added only for a rule that genuinely
  conflicts with a fixture's purpose, naming the fixture and the reason in the
  same edit.

## Version policy

`checkers.toml` is the only place a checker version is named for this suite.
All five run through `uvx <tool>@<version>` and none enters `uv.lock` — a 0.0.x
tool with no stable API has no business in every contributor's environment.

mypy and Basedpyright are also the Layer 1 gates run by `uv run`, so they are in
the `dev` group as well. The runner asserts the pinned version **equals what
`uv.lock` resolves**, not that it satisfies the `dev` floor: `dev` declares
`mypy>=1.18`, which every future resolution satisfies while `uv run mypy` and
`uvx mypy@2.3.1` drift apart, and Dependabot runs weekly.

Minimum supported equals current tested for all five, because exactly one
version of each has been measured. A pin advances by a pull request that shows
the whole suite green on the new version.

## What this directory does not guard

Class-member *inventory* is out of scope, and that is a decision rather than an
omission. The corpus guards members by exercising them — `Container.bind`,
`RequestScope.__call__` — but adding a method to a public class creates no
obligation here, and nothing fails when one arrives untested.
