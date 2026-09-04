# The typing conformance suite

Five type checkers — mypy, stock Pyright, Basedpyright, ty and Pyrefly — over
two objects: a corpus of ordinary consumer code, checked against the wheel this
repository builds and installed into interpreters that have never heard of the
checkout, and the repository's own source.

```bash
uv run python -m scripts.conformance
uv run python -m scripts.conformance --checker ty --mode core --only positive
uv run python -m scripts.conformance --source
```

`--checker`, `--mode` and `--only` are repeatable and narrow the run. `--source`
switches to the source layer instead of the corpus. `--pin ty=0.0.80` and
`--target-python 3.14` run one checker or one language target away from what
`checkers.toml` names, which is what the weekly `typing-forward` workflow does.
The runner prints a per-checker, per-mode table and exits non-zero listing every
failure, not only the first.

It is a CI gate, not a sixth commit gate: it builds a wheel and creates three
interpreters, which does not belong in a per-commit loop.

## What is where

| Path | What it holds |
| --- | --- |
| `checkers.toml` | The pinned version of each checker, the language and OS targets, the eight extras, and the eight framework-requiring `depin.ext` modules |
| `coverage.toml` | One entry per public symbol: the fixtures that exercise it, or a decision and a reason |
| `config/` | One native configuration per checker, templated — `${venv}`, `${venv_parent}`, `${venv_name}`, `${python}` and `${python_version}` are substituted at run time, once per interpreter |
| `config/pyright-source.json` | Stock Pyright's configuration for the **repository source**, passed with `-p`. Not templated: it names no interpreter the runner creates |
| `corpus/core/` | Consumer code that imports only `depin` and `depin.errors`. Checked in both install modes |
| `corpus/ext_core/` | The `depin.ext` modules that import no third-party package — `__init__`, `asgi`, `wsgi`, `cli` — against a consumer's own structural types. Checked in **both** modes |
| `corpus/ext_extras/` | The eight `depin.ext` modules that require an extra. Checked in all-extras mode only |
| `negative/` | One misuse per file, no suppressions, checked one file at a time |
| `divergence/` | Known false negatives in the public API, gated on each checker's verdict rather than on rejection |
| `expected/negative.toml` | Per fixture and per checker: the line and the rule identifier |
| `expected/divergence.toml` | Per fixture and per checker: `accept` or `reject`, as measured today |
| `expected/ty-source.txt` | ty over the repository source: one `file:rule:count` triple and a classification per entry |
| `expected/pyrefly-source.txt` | Pyrefly over the repository source, in the same form |

The corpus imports only `depin`, `depin.errors` and `depin.ext.*`. It never
imports `depin._core`, and the runner asserts that textually before it checks
anything.

## The two install modes

`core` installs `pydepin` alone. `extras` installs it with all eight extras
named explicitly — there is no aggregate `all` extra. `corpus/core` and
`corpus/ext_core` are checked in both; in `core` mode the runner additionally
asserts that every one of the eight framework-requiring `depin.ext` modules
fails to import, which is what proves the core carries no framework dependency.

## The source layer

`--source` checks `depin tests examples scripts` — the same file list
`[tool.basedpyright] include` and `[tool.mypy] files` name — rather than the
corpus. mypy and Basedpyright already gate that list at zero through `uv run`,
so the source layer adds the three that did not run:

- **Stock Pyright, at zero**, configured by `config/pyright-source.json` passed
  with `-p`. It cannot live in `pyproject.toml`: Basedpyright 1.39.10 refuses to
  parse a file carrying both a `pyright` and a `basedpyright` table, exits 3,
  and discards the whole configuration — which would silently degrade the
  repository's own commit gate to its defaults. A named file passed on the
  command line is also not the root `pyrightconfig.json` that `AGENTS.md` bans,
  which Pyright discovers implicitly.
- **ty and Pyrefly, against a register.** The consumer corpus is held at zero
  and gets no baseline file, because a baseline is exactly the filter that
  contract forbids. The repository source is a different object: it writes every
  intentional negative as a `# type: ignore[code]  # pyright: ignore[code]`
  pair, and ty reads neither spelling, so 27 of its 44 diagnostics are that pair
  being invisible to it.

Appending `# ty: ignore[<rule>]` to those 27 lines does silence ty. It is not
done. ty's own `unused-ignore-comment` rule fires as an error under
`--error all`, so every directive would have to keep naming exactly the rules ty
currently emits, and any release that renames one turns a blocking job red for a
reason that is upstream's. It would also add 27 checker-specific ignores to a
repository whose conventions require each suppression to be individually
narrowest and individually explained.

So each register line is a **`file:rule:count` triple and a one-line
classification**, and the stage fails three ways: on a diagnostic no entry
carries, on an entry that no longer appears, and on a count that moved in either
direction. The count is load-bearing — a bare `file:rule` pair would absorb any
number of further diagnostics of that rule in that file, which is the property
the register exists to deny. Line numbers were the other option and they churn
on every edit.

Both registers were measured under the exact invocation the gate runs. ty's
`--error all` is not the same measurement as a bare `uvx ty check`: it adds the
unsoundness lints, and 32 diagnostics became 44.

Pyrefly has no `pyproject.toml` table at all, so its source configuration is the
root `pyrefly.toml`. The configuration traps below apply to this layer as much
as to the corpus.

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
  reports zero having checked nothing. Paths in `config/pyright.json` and
  `config/pyright-source.json` are relative to the config file, and on the
  corpus the file set is passed on the command line as well.
- **`pythonPath` is not a stock-Pyright key.** It prints
  `Config contains unrecognized setting "pythonPath"` and continues.
  `venvPath` plus `venv` is the working form, which is why the templates carry
  the venv's parent and its name separately.
- **An unconfigured Pyrefly runs the `basic` preset**, which does not report
  `bad-argument-type` at all. Both layers pass an explicit config and
  `--preset strict`; under `basic` the source layer reports 0 where `strict`
  reports 2.
- **ty has no strict mode and no presets.** `--error all` is the closest honest
  equivalent.

The first two produce a green run over an empty file set, so the runner asserts
a **non-zero checked-file count** for every checker that reports one: mypy,
both Pyright engines, and Pyrefly. ty reports none, and the table says so. On
the source layer stock Pyright's count is asserted **equal to mypy's** as well,
because a count of its own catches only a total drop.

## Expected diagnostics are data, never message text

`expected/negative.toml` records, per fixture and per checker, the **line** and
the **rule identifier**. The harness requires a non-zero exit and at least one
diagnostic on that line carrying that identifier.

Message snapshots are excluded on measured grounds: for the same misuse the
three checkers that name a type name three different ones, and ty has printed
both sides of one disagreement identically as
``Type `() -> Cache` does not match asserted type `() -> Cache` ``. A harness
matching rendered text would be brittle where it is not simply useless.

## The divergence register

One false negative in the public API is routed to Step 8:
`Container.value(Token[int], 'str')`, accepted by four and rejected by Pyrefly.

They cannot be negative fixtures. A fixture every checker accepts gates nothing,
and one that four accept would fail four checkers for a state the project has
decided to keep until the API may change again. So `divergence/` inverts the
contract: `expected/divergence.toml` records each checker's `accept` / `reject`
verdict as measured today, and the stage fails when a verdict moves **in either
direction**. A checker that starts rejecting one of these is news the project
wants to record deliberately; a checker that stops rejecting one is a regression
in what the suite detects, and four of the eight remedies measured for the
`Token` variance experiment would have caused exactly that.

The register carries verdicts only — no line, no rule identifier. Pinning the
rule a rejecting checker emits would make a blocking gate depend on that checker
continuing to spell it the same way, which is the fragility this suite rejects
elsewhere. What is promised is that the call is caught, not how it is named.

## The coverage map

`coverage.toml` carries one entry per public symbol, naming either the fixtures
that exercise it or an explicit decision and a reason.
`tests/unit/test_conformance_coverage.py` enumerates the public surface and
fails when a name has no entry, so a new public symbol cannot land without a
consumer-typing decision behind it. It fails the other way too: an entry naming
a symbol that is no longer public is a failure, so the map shrinks when the
surface does.

Three sources, not one:

- `depin.__all__`, imported.
- `depin.errors`, imported — eleven exceptions, none of them in `__all__`, four
  of which inherit a builtin as well. That second base decides what a consumer's
  existing `except TypeError` now catches, which makes it a typing fact rather
  than a detail.
- `depin/ext/`, **parsed with `ast` and never imported**: that test runs on the
  free-threaded and pre-release jobs, where no framework is installed.
  `tests/unit/test_integration_contract.py` uses the same technique.

The scanner's contract is specified, because the naive version misses the single
most important symbol in the package. It honours `__all__` when a module
declares one — only `fastapi.py` does; otherwise it takes every non-underscore
top-level `ClassDef`, `FunctionDef`, `AsyncFunctionDef`, `Assign`, `AnnAssign`
and `TypeAlias`; it descends into `If` bodies **and their `else` branches**; and
it treats a module-level `import X as Y` with a public `Y` as a symbol rather
than an import. Three cases force each of those clauses and each has its own
test: `ext/fastapi.py` has no top-level `Inject` at all — its body is `__all__`
plus one `If`, with `type Inject[T] = T` in the `TYPE_CHECKING` branch and
`class Inject` in the `else`; `ext/asgi.py` declares two module-level PEP 695
aliases and `ext/wsgi.py` one; and three framework modules publish their base as
`from depin.ext.asgi import RequestScope as ASGIRequestScope`.

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

`.github/workflows/typing-forward.yml` runs weekly and builds the evidence a
later change to that policy would need. It resolves the newest release of each
of the five and runs both layers against it — both install modes, the 3.13 and
3.14 language targets, and Windows and macOS, the last for the isolation guard
rather than for inference — and probes one release behind for the three stable
lines. It reaches the runner through `--pin` and `--target-python`, which
override `checkers.toml` for one run and stand the lockstep assertion aside for
exactly the checker they name. **It never writes `checkers.toml`.** It is
advisory but not silent: each failing leg becomes a tracking issue titled for
the checker and the version, carrying the diagnostics.

## What this directory does not guard

**Class-member inventory is out of scope, and that is a decision rather than an
omission.** `coverage.toml` and the unit test behind it guard the *symbol*
inventory: every name `depin.__all__`, `depin.errors` and `depin/ext/` publish
at module level. `RequestScope.__call__`, `CommandContext.with_resource[T]` and
every `Container` method are not top-level names, so adding `Container.foo()`
passes that gate.

The corpus guards members the other way, by exercising them — `Container.bind`,
`FrozenContainer.resolve`, `ScopeFrame.provide` — and a member whose type drifts
fails the positive stage. But nothing fails when a *new* member arrives
untested. Extending the map to members would mean walking every class body of a
package whose public classes carry the bounded generics the corpus already
exercises directly; the two are different promises, and Step 8's surface review
is where member-level inventory belongs.
