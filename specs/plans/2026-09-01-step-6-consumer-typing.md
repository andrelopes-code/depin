# Step 6 — consumer typing compatibility: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make consumer-visible type inference a tested contract under five type
checkers, against the installed wheel — for the 0.17.0 milestone.

**Architecture:** Three layers. Layer 1 keeps mypy and Basedpyright strict over
`depin tests examples` and adds stock Pyright at zero plus ty and Pyrefly against
a committed register of classified diagnostics. Layer 2 is the new contract: a
`conformance/` corpus of ordinary consumer code, checked by all five against a
built wheel installed into an isolated interpreter, in a core-only and an
all-extras mode, at zero. Layer 3 is a weekly forward probe. One runner,
`scripts/conformance.py`, is both the local entry point and the CI entry point.

**Tech Stack:** Python 3.12–3.14, uv, mypy 2.3.1, stock Pyright 1.1.411,
Basedpyright 1.39.10, ty 0.0.77, Pyrefly 1.2.0. No new runtime dependencies; the
three non-repo checkers are invoked through `uvx <tool>@<version>` and never
enter `uv.lock`.

**Spec:** `specs/2026-09-01-step-6-consumer-typing-design.md` — read it. Every
decision below is argued there, and the spec is binding over this plan.

**Evidence, already measured — do not re-derive:**
`specs/evidence/2026-09-01-consumer-typing-baseline.md` and
`specs/evidence/2026-09-01-token-variance-experiment.md`.

## Global constraints

Every task inherits these from `AGENTS.md`, the roadmap, and the spec.

- The core keeps zero runtime dependencies. No task adds one.
- **No `# type: ignore`, `# pyright: ignore`, `typing.cast`, `typing.Any`, or
  `# noqa` is added to `depin/`.** `depin/` carries exactly three suppressions
  today — two in `depin/_core/frozen.py`, one in `depin/_core/markers.py` — and
  must carry exactly those three when this step ends, **unchanged**. An earlier
  draft of this plan appended a ty spelling to them; that is rejected — see
  Task 4. Confirm the census with
  `grep -rn "type: ignore\|pyright: ignore\|noqa" depin`; the `# noqa: B008`
  inside a docstring in `depin/ext/fastapi.py` is prose.
- Use PEP 695 syntax throughout. No `TypeVar`. `ruff UP046` fails the first gate
  command on a `Generic[...]` base, which is measured in the variance evidence.
- Public API carries Google-style docstrings that omit types from
  `Args:`/`Returns:`, list every exception under `Raises:`, and carry an
  `Example:`. A ```pycon fence is **executed as a doctest** by the default
  `pytest` run; paste real output.
- `tests/unit/` **imports no framework.** The free-threaded and pre-release jobs
  run `uv sync --no-default-groups --group threads` then `pytest tests/unit`
  only. Anything needing a framework goes in `tests/integration/`, imported
  without a guard.
- `tests/unit/test_integration_contract.py` walks every `.py` under `depin/ext/`
  and forbids the **literal string** `_core` anywhere in the file, prose
  included. Write "depin's internals".
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI
  machinery. Tests are deterministic: no sleeps, no network, no clock.
- **Never assert on a library's rendered output or formatting.** This applies
  doubly here: no conformance assertion may match checker message text. Rule
  identifiers and line numbers only.
- Coverage over `depin/` stays at or above 95%, measured with
  `uv run coverage run -m pytest` then `uv run coverage report`. **Never
  `pytest --cov`** — the `pytest11` entry point imports `depin` before the
  collector starts and it under-reports (~73% against a true 99%).
- The mutation gate runs whenever `depin/_core/**` or `tests/**` changes. It is
  green on `main` at 97.7% against a 95.0% floor and must stay green. Task 1
  touches `_core`.
- Before every commit, in this exact order:

  ```bash
  uv run ruff format
  uv run ruff check
  uv run basedpyright
  uv run mypy
  uv run pytest
  ```

- Any commit that changes prose also runs
  `uv run --group docs mkdocs build --strict`.
- **Before opening each pull request**, run
  `uv sync --all-extras --resolution lowest-direct` then `uv run --no-sync pytest`;
  that is what the `minimum declared versions` job runs and it has caught
  failures the ordinary suite did not, twice. Restore with
  `uv sync --locked --all-extras`, then check `git status` — the `lowest-direct`
  sync **rewrites `uv.lock`**; recover it with `git checkout -- uv.lock` if it
  moved.
- `uv run ruff format` reformats Python inside markdown fences, including under
  `specs/` and `docs/`. Never revert that.
- Every example needs `build()`/`main()` plus a `__main__` guard, no
  module-level container, a line in `examples/README.md`, and a case in
  `tests/integration/test_examples.py`.
- Commits are focused, conventional, at most 72 characters in the subject, and
  carry **no attribution, co-author trailer, or automation language**.
- **Merge is squash**, so each pull request becomes one conventional commit and
  its title is what release-please reads. The prefixes are chosen below for
  that reason.

## Pull requests

Four, in order. Each is one squashed conventional commit.

| # | Title | Cuts a release? | Tasks |
| --- | --- | --- | --- |
| A | `feat: accept a Token wherever a provider key is accepted` | yes — minor, 0.17.0 | 1, 2 |
| B | `test: gate the consumer typing contract on five checkers` | no, rides along | 3 |
| C | `ci: make ty and Pyrefly block on the repository source` | no, rides along | 4, 5 |
| D | `docs: record what Step 6 closed and what it routed on` | no, rides along | 6 |

PR A is the only one that opens a release. 0.16.3 is unpublished tooling and
rides into 0.17.0 with it.

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `depin/_core/markers.py` | **`TokenKey`**, the non-generic supertype; `Token[T](TokenKey)` | 1 |
| `depin/_core/spec.py` | `ProviderKey` and `FrameBinding.key` take `TokenKey`; `BindRecord.provides` widened | 1, 2 |
| `depin/_core/introspect.py` | five positions take `TokenKey`; `is_object_token` → `is_token_key` | 1 |
| `depin/_core/typeguards.py` | `is_provider_key`'s `isinstance` names `TokenKey` | 1 |
| `depin/_core/bindings.py` | thirteen `provides=` annotations and the `_BindFn` alias widened | 2 |
| `depin/_core/providers.py` | `_resolve_key`'s `explicit` widened | 2 |
| `depin/__init__.py` | `TokenKey` exported | 1 |
| `tests/unit/test_markers.py` | `TokenKey` identity, equality, hashing, slots | 1 |
| `tests/unit/test_bindings.py` | `provides=` with a token, end to end | 2 |
| `tests/typing/test_conformance.py` | line 82 rewritten as a witness; `TokenKey` and `provides=` cases | 1, 2 |
| `docs/reference/markers.md`, `mkdocs.yml` | `TokenKey` on the markers page | 1 |
| `docs/guide/composition.md` | `provides=` with a token | 2 |
| `conformance/` | **New.** The corpus, fixtures, configs and expected data | 3 |
| `scripts/conformance.py` | **New.** The runner | 3 |
| `tests/unit/test_conformance_coverage.py` | **New.** Enforces the coverage map | 3 |
| `.github/workflows/ci.yml` | `typing-artifact`, `typing-consumer`; then `typing-source`, old `ty` job removed | 3, 4 |
| `.github/workflows/typing-forward.yml` | **New.** The weekly probe | 5 |
| `pyproject.toml` | `scripts` added to both include lists. **No `[tool.pyright]`** | 4 |
| `conformance/config/pyright-source.json` | **New.** Stock Pyright's source config, passed with `-p` | 4 |
| `pyrefly.toml` | **New.** Pyrefly's source configuration | 4 |
| `conformance/expected/ty-source.txt`, `pyrefly-source.txt` | The Layer 1 registers | 4 |
| `docs/support-policy.md`, `CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE.md` | The matrix as documented | 6 |
| `specs/evidence/2026-09-01-step-6-consumer-typing.md` | **New.** Evidence and fault injection | 6 |
| `specs/2026-08-28-roadmap-1.0-design.md` | Step 6 closed, Step 8 inherits two items | 6 |

---

## Task 1 — R4: the `TokenKey` supertype

**Files:** `depin/_core/markers.py`, `depin/_core/spec.py`,
`depin/_core/introspect.py`, `depin/__init__.py`, `tests/unit/test_markers.py`,
`tests/typing/test_conformance.py`, `docs/reference/markers.md`, `mkdocs.yml`

Test-first: `depin/_core/` is developed test-first.

- [ ] Add `TokenKey` to `depin/_core/markers.py`: non-generic, `__slots__ = ('name',)`,
      `__init__(self, name: str)`, `__repr__`, `__eq__`, `__hash__`. It is **not**
      `@final`. Its `__hash__` keeps the existing seed `hash(('depin.Token', self.name))`
      so equality and hashing stay byte-compatible with 0.16, and `__eq__` narrows
      on `TokenKey`.
- [ ] Its docstring states that `Token` is the only intended implementation and
      that it exists so a non-generic key position does not have to name a type
      argument. It is not an extension point.
- [ ] `Token[T]` becomes `class Token[T](TokenKey)` with `__slots__ = ()`. It
      stays `@final`. Its own `__init__`/`__repr__`/`__eq__`/`__hash__` move to
      the base; verify no `__dict__` appears on an instance.
- [ ] Convert **all nine** `Token[object]` annotation positions to `TokenKey`:
      `spec.ProviderKey`, `spec.FrameBinding.key`, `markers.Named.key`,
      `markers._InjectMarker.key`, `introspect.AnnotatedMeta.token`,
      `introspect.AnnotatedMeta.named`, the two locals in
      `introspect.extract_annotated_meta`, and the `TypeGuard` on
      `is_object_token`. The roadmap and the variance evidence both say eight;
      the source carries nine. The tenth mention, the docstring on
      `is_object_token`, is prose and is rewritten to match.
- [ ] Rename `is_object_token` to `is_token_key` and update its call sites. It
      is private, and the old name would now describe the wrong thing.
- [ ] **Also fix `depin/_core/typeguards.py`, which the `Token[object]` grep does
      not find.** `is_provider_key` returns `TypeGuard[ProviderKey]` while its
      `isinstance` admits `type | str | Token | Underlying`. Once `ProviderKey`
      admits `TokenKey`, the guard promises more than it checks, and it gates
      `FrozenContainer.explain`, `DependencyGraph.find` and `DependencyGraph.node`
      — so a `TokenKey` would typecheck there and raise at runtime. Change the
      `isinstance` to `type | str | TokenKey | Underlying` and check the error
      message near `typeguards.py:117` still reads correctly.
- [ ] `is_token_key` narrows with `isinstance(value, TokenKey)`, not
      `isinstance(value, Token)`. Checking the narrower class while narrowing to
      the wider one would let a `TokenKey` subclass typecheck as a key and fail
      at runtime.
- [ ] Export `TokenKey` from `depin/__init__.py`; `__all__` goes from 28 to 29
      names, alphabetically ordered as the existing tuple is.
- [ ] `tests/unit/test_markers.py`: a `Token` is a `TokenKey`; two tokens with
      the same name are equal and hash equally across the class boundary; a
      `Token` instance has no `__dict__`; `repr` is unchanged.
- [ ] `tests/typing/test_conformance.py`: a `Token[int]` is accepted where a
      `ProviderKey` is expected, and `TokenKey` is usable as an annotation.
- [ ] `docs/reference/markers.md` documents `TokenKey`; no new nav entry is
      needed if it joins the existing markers page.
- [ ] Five gates, plus `mkdocs build --strict`.
- [ ] **Mutation check.** `_core` changed, so run mutmut over
      `depin/_core/markers.py` and confirm the new members' mutants are killed.
      If `__repr__` or `__eq__` mutants survive, the unit tests above are not
      specific enough — strengthen them rather than lowering the floor.

**Watch for:** `Token` is `@final`, which permits a base class but forbids
subclassing `Token` itself; that is unchanged. `depin/ext/` files may not
contain the literal string `_core`, so nothing in this task may add it there.

## Task 2 — the `provides=` repair

**Files:** `depin/_core/bindings.py`, `depin/_core/spec.py`,
`depin/_core/providers.py`, `tests/unit/test_bindings.py`,
`tests/typing/test_conformance.py`, `docs/guide/composition.md`

Depends on Task 1. **Must land in the same pull request**, because written
against `Token[object]` this repair depends on the phantom-parameter variance
that R4 exists to stop depending on — it would work under four checkers and fail
under Pyrefly.

- [ ] Widen the **keyword** `provides` from `type[object] | None` to
      `type[object] | TokenKey | str | None` in `depin/_core/bindings.py`: the
      seven `bind` overloads, the `bind` implementation, `singleton`, `scoped`,
      `transient`, `ScopeDecorator.__init__`, and `_record_bind`.
- [ ] `str` is in that union because **`provides='some-key'` succeeds today** —
      `as_provider_key` admits a string key. Measured: `provides=42` raises
      `InvalidProviderError`, `provides='name'` resolves the binding. Of the five
      members of `ProviderKey`, `Underlying` is the only one `as_provider_key`
      rejects, which is why the union stops short of the alias itself.
- [ ] Widen the third element of the `_BindFn` alias in the same module.
- [ ] Widen `BindRecord.provides` in `depin/_core/spec.py`.
- [ ] Widen `_resolve_key`'s `explicit` parameter in `depin/_core/providers.py`
      and add the import it needs.
- [ ] **Do not touch the `provides()` decorator.** It annotates
      `abstract: type[object]` and rejects a token at runtime through
      `_reject_invalid_key`, which raises `InvalidProviderError`. Widening the
      annotation alone would make the checker promise what the library refuses.
- [ ] **Do not widen to `ProviderKey`.** That alias also admits `str` and
      `Underlying`, and `as_provider_key` raises on the latter. The two-member
      union is the narrowest change matching what the position accepts.
- [ ] Tests in the file where `provides=` is already exercised:
      `bind(factory, provides=SOME_TOKEN)` registers under the token and resolves
      through it; `singleton(provides=SOME_TOKEN)` likewise;
      `provides='some-key'` resolves. The runtime negative is **`provides=42`
      only** — asserting that `provides='name'` raises would be a test written
      against a fact that is not true.
- [ ] `tests/typing/test_conformance.py`: `provides=` with a token and with a
      string both typecheck; `provides=42` stays rejected.
- [ ] `docs/guide/composition.md` shows the token form in a ```pycon block with
      real output.
- [ ] Five gates, `mkdocs build --strict`, mutation check.
- [ ] `uv sync --all-extras --resolution lowest-direct` + `pytest`, then restore
      the lockfile.
- [ ] Open **PR A**, `feat: accept a Token wherever a provider key is accepted`.
      Wait for all checks, then merge.

## Task 3 — the conformance suite

**Files:** `conformance/**`, `scripts/conformance.py`,
`tests/unit/test_conformance_coverage.py`, `.github/workflows/ci.yml`,
`tests/typing/test_conformance.py`

Depends on PR A being merged, because the corpus is checked against a wheel
built from `main`.

### 3a — the runner

- [ ] `conformance/checkers.toml` declares the five pinned versions —
      mypy 2.3.1, pyright 1.1.411, basedpyright 1.39.10, ty 0.0.77,
      pyrefly 1.2.0 — **and the language and OS targets**, `python = "3.12"` and
      `os = "linux"`. The proposal's criterion is that versions *and Python
      language targets* be recorded reproducibly, and a local run must reproduce
      the gate exactly. Nothing else in the repository names a checker version
      for this suite.
- [ ] The runner asserts the pinned mypy and basedpyright versions **equal what
      `uv.lock` resolves**, not that they satisfy the `dev` floor. A floor check
      cannot see drift: `dev` declares `mypy>=1.18`, so every future resolution
      satisfies it while `uv run mypy` and `uvx mypy@2.3.1` diverge — and
      Dependabot runs weekly, so that divergence is scheduled.
- [ ] `scripts/conformance.py`: builds the wheel outside the checkout, **copies
      `conformance/` into a temporary directory outside the checkout**, creates
      the core-only, all-extras and empty interpreters there, and runs every
      checker subprocess with that directory as its working directory. It
      asserts per subprocess that the checkout is neither the working directory
      nor an ancestor of it.
- [ ] The guard is on the checker subprocess, **not on the runner process**. The
      runner is invoked from the checkout by definition — that is where
      `uv run python -m scripts.conformance` resolves, and in CI the checkout is
      the default working directory. A guard on the runner would fail every run.
      The design records why the subprocess guard is needed: run from the
      repository root, mypy resolved `depin` from the checkout and reported
      `Success` against an interpreter with no `depin` installed at all, so the
      empty-interpreter control passed while proving nothing.
- [ ] Install with the `name[extras] @ <path>` form.
      `uv pip install "<wheelpath>[extra]"` is a parse error.
- [ ] Isolation assertions, before any checking: `depin/py.typed` is in
      `.dist-info/RECORD` read from the zip central directory (not `namelist()`);
      `direct_url.json` carries `archive_info` and no `__editable__*.pth` exists;
      `depin.__file__` is inside the venv and the checkout is off `sys.path`;
      and the empty-interpreter control produces mypy `import-not-found`,
      Pyright and Basedpyright `reportMissingImports`, ty `unresolved-import`,
      Pyrefly `missing-import` — from the identical command line and directory
      as the real gate.
- [ ] A **non-zero checked-file count** assertion for every checker that reports
      one. Stock Pyright silently drops an absolute path in `include` and
      reports zero having checked nothing; `pythonPath` is not a recognised key
      and is ignored with a warning. Both produce a green run over an empty file
      set.
- [ ] A textual assertion that no corpus file contains `depin._core` or
      `from depin import _`.
- [ ] CLI: `uv run python -m scripts.conformance`, with `--checker`, `--mode`
      and `--only` to narrow. Prints a per-checker, per-mode table and exits
      non-zero listing every failure, not just the first.

**How the existing tooling sees `conformance/`.** Verify each of these rather
than assuming it:

- `[tool.mypy] files` and `[tool.basedpyright] include` are
  `["depin", "tests", "examples"]`, so the repository gates do **not** see
  `conformance/`. That is essential — the negative fixtures would break them.
  Task 4 adds `scripts` to both lists and must **not** add `conformance`.
- `[tool.pytest.ini_options] testpaths` is `["tests", "depin", "docs"]`, so
  nothing under `conformance/` is collected and `--doctest-glob=*.md` does not
  reach its README.
- `ruff format` and `ruff check` **do** cover it, and that is wanted: the
  fixtures stay readable and consistently formatted. Deliberately
  ill-*typed* code is still ordinary Python, so it should lint clean. Reach for
  `[tool.ruff.lint.per-file-ignores]` only for a rule that genuinely conflicts
  with a fixture's purpose, and say which fixture and why in the same edit.

### 3b — the corpus

- [ ] `conformance/corpus/core/c01…c09` covering the areas the proposal's table
      names: container construction, keys, providers, resolution, injection,
      lifetimes, registration, diagnostics, hosting.
- [ ] Split the ext corpus **by install mode, not by framework**.
      `conformance/corpus/ext_core/` covers `ext/__init__`, `ext/asgi`,
      `ext/wsgi` and `ext/cli`, which import no third-party package, against a
      consumer's own structural scope and command-context types — they carry the
      bounded generics `RequestScope[ScopeT: ASGIScope, …]`,
      `install[C: CommandContext]` and `CommandContext.with_resource[T]`. It is
      checked in **both** modes.
- [ ] `conformance/corpus/ext_extras/` covers the other eight and is checked in
      all-extras mode only; core-only mode asserts each of those eight is
      unresolvable. Do **not** reuse the baseline's `e01…e04` layout: its
      `e03_cli.py` mixed `click.Context` and `typer.Context` into the same file
      as the structural case, so it could not run without the extras, and its
      core-only run covered nine files with no ext file among them.
- [ ] There is no aggregate `all` extra. Install the all-extras interpreter by
      naming the eight: `click`, `fastapi`, `flask`, `litestar`, `pytest`,
      `starlette`, `taskiq`, `typer`.
- [ ] Close the gaps the existing `tests/typing/` corpus leaves: `Registry` and
      its `|`, `scoped()` and `transient()`, `Named`, `Tag`, `Bindings`,
      `Condition` in annotation position, `Host.activated()`, `close`/`aclose`,
      `awarmup`/`ahealth`, `Container(*sources)`/`include`, `scope_value`, and
      the nine ext modules with no coverage today.
- [ ] Bind the **real** `depin_override` fixture to the `OverrideFactory`
      protocol and check the widening holds. The existing corpus asserts against
      the declared parameter only, so whether the actual
      `_GeneratorContextManager` satisfies the advertised
      `AbstractContextManager[FrozenContainer]` is asserted nowhere.
- [ ] **Name every witness inside a function with a leading underscore.**
      `ruff check` is gate 2, `F` is selected, and an annotation does not exempt
      an unused local: `pending: Awaitable[str] = handler('n')` fails with
      `F841`. `_pending` is exempt under ruff's default `dummy-variable-rgx`.
      This applies to the `tests/typing/test_conformance.py:82` rewrite too.
- [ ] Apply the exact-versus-assignability rule from the spec. `assert_type` for
      a nominal class, a `Protocol`, a parameterised generic of a `depin` type,
      a builtin, `None`, and unions of those. A typed-assignment witness for
      decorator-returned classes, decorator-returned functions, `@inject`
      wrapper signatures, context managers, awaitables, and enum members.
      `assert_type(Scope.SINGLETON, Scope)` must never appear.
- [ ] Anti-erasure: a Basedpyright pass with `reportAny` and `reportExplicitAny`
      at error over the whole positive corpus, and a mypy `--disallow-any-expr`
      pass over `corpus/core/` only — it is unusable in all-extras mode, where
      third-party annotations produce `Any` expressions the corpus does not own.

### 3c — negatives and divergence

- [ ] `conformance/negative/` — one misuse per file, no suppressions, run one
      file at a time. Cover at minimum: a non-key argument to `resolve`, an
      incompatible `check=`, a wrong generic argument on resolution, a wrong
      argument to an `@inject`-wrapped call, an invalid alias or collection
      member, and an `Inject[T]` misuse.
- [ ] `conformance/expected/negative.toml` records, per fixture and per checker,
      the **line** and the **rule identifier**. Never message text: for one
      `Inject[T]` misuse the three checkers that name a type name three
      different ones, and ty printed both sides of one disagreement identically
      as ``Type `() -> Cache` does not match asserted type `() -> Cache` ``.
- [ ] `conformance/divergence/` — the two false negatives routed to Step 8:
      `FrozenContainer.override(Config, Other())`, accepted by all five, and
      `Container.value(Token[int], 'str')`, accepted by four and rejected by
      Pyrefly. `expected/divergence.toml` records each checker's verdict today
      and the harness fails when one changes **in either direction**.
- [ ] Rewrite `tests/typing/test_conformance.py:82`,
      `assert_type(handler(label='n'), Awaitable[str])`, as a witness:
      `pending: Awaitable[str] = handler('n')`. Both `inject` overloads match an
      `async def`; four checkers pick the first and ty the second, and
      `CoroutineType[Any, Any, str]` preserves every operation `Awaitable[str]`
      promises.
- [ ] Classify `tests/typing/test_conformance.py:304` under the proposal's
      failure taxonomy **before** changing it. It is the repository's only
      negative typing assertion and is written as
      `# type: ignore[arg-type]  # pyright: ignore[reportArgumentType]`; ty
      honours neither half, and mypy's `warn_unused_ignores` — implied by
      `strict` — fails the gate if any checker stops reporting it. Move it to
      `conformance/negative/`.

### 3d — the coverage map and CI

- [ ] `conformance/coverage.toml`: one entry per public symbol, naming either
      the fixtures that exercise it or an explicit
      `decision = "not-type-dependent"` with a reason.
- [ ] `tests/unit/test_conformance_coverage.py` enumerates **three** sources:
      `depin.__all__`, `depin.errors` (eleven public exceptions, none of them in
      `__all__`, two inheriting a builtin as well — a typing fact that changes
      what a consumer's `except` catches), and `depin/ext/`. The first two are
      imported; `depin.errors` needs no framework.
- [ ] `depin/ext/` is parsed with `ast`, not imported — this test runs on the
      free-threaded and pre-release jobs where no framework is installed. The
      scanner contract, because the naive version misses the single most
      important symbol in the package: honour `__all__` when the module declares
      one (**only `fastapi.py` does**); otherwise take every non-underscore
      top-level `ClassDef`, `FunctionDef`, `AsyncFunctionDef`, `Assign`,
      `AnnAssign` and **`TypeAlias`**; **descend into `If` bodies and their
      `else` branches**; and treat a module-level `import X as Y` with a public
      `Y` as a symbol rather than an import.
- [ ] Verify the scanner against three known-hard cases: `ext/fastapi.py` has no
      top-level `Inject` at all — its body is `__all__` plus one `If`, with
      `type Inject[T] = T` in the `TYPE_CHECKING` branch and `class Inject` in
      the `else`; `ext/asgi.py` declares two module-level PEP 695 aliases and
      `ext/wsgi.py` one; and three framework modules publish their base as
      `from depin.ext.asgi import RequestScope as ASGIRequestScope`.
- [ ] **Class members are out of scope**, and the map says so. Adding
      `Container.foo()` passes this gate; the corpus is what guards members.
      Say it in `conformance/README.md` so the omission is a decision on the
      record rather than a hole.
- [ ] `.github/workflows/ci.yml` gains `typing-artifact` — builds the wheel once,
      asserts the `RECORD` membership and the metadata, uploads it — and
      `typing-consumer`, a matrix over the five checkers that downloads it and
      runs the whole suite in both modes. Both blocking. Five jobs rather than
      one, so the check list names the checker that broke.
- [ ] One Python target per pull request, 3.12, and one OS, Linux. The baseline
      measured byte-identical results at 3.12, 3.13 and 3.14 for all five in both
      modes. Task 5 keeps the other targets **and the other two operating
      systems** as a weekly regression detector: what a checker infers does not
      vary by host, but path-ancestry comparison and `.pth` discovery — the two
      things the isolation guard rests on — do.
- [ ] Five gates, `lowest-direct` pre-flight, then open **PR B**,
      `test: gate the consumer typing contract on five checkers`. Merge when green.

## Task 4 — the source layer

**Files:** `pyproject.toml`, `pyrefly.toml`, `.github/workflows/ci.yml`,
`conformance/expected/ty-source.txt`, `conformance/expected/pyrefly-source.txt`,
and the intentional-negative lines across `depin/` and `tests/`

- [ ] **Do not add `[tool.pyright]` to `pyproject.toml`.** Measured:
      Basedpyright 1.39.10 refuses to parse a file carrying both tables —
      `Pyproject file cannot have both 'pyright' and 'basedpyright' sections.
      pick one`, exit 3 — and discards the whole configuration, degrading the
      repository's own commit gate to its defaults.
- [ ] Put stock Pyright's source configuration in
      `conformance/config/pyright-source.json`, passed with `-p`. AGENTS.md bans
      a root `pyrightconfig.json`, which Pyright discovers implicitly; a named
      file passed on the command line does not compete for discovery.
- [ ] Mirror `[tool.basedpyright] include` exactly:
      `typeCheckingMode = "strict"`, `pythonVersion = "3.12"`, `venvPath`,
      `venv`, `reportMissingTypeStubs = false`. **Paths relative to the config
      file** — absolute entries are silently dropped and the run then reports
      zero having checked nothing. **Never `pythonPath`**: not a recognised key.
      Assert a non-zero checked-file count.
- [ ] Add `pyrefly.toml` at the repository root; Pyrefly has no `pyproject.toml`
      table and defaults to the `basic` preset, which does not report
      `bad-argument-type` at all. The source gate runs `--preset strict`.
- [ ] **Do not re-spell the twenty-five suppression lines.** Appending
      `# ty: ignore[<rule>]` does silence ty, but ty has its own
      `unused-ignore-comment` rule that fires — a warning by default, an error
      under `--error all`, non-zero either way — so twenty-five hand-written
      directives would make a blocking job depend on ty continuing to emit
      exactly the rules they name. That is the same fragility this plan removes
      from `tests/typing/test_conformance.py:304`. It would also add twenty-five
      checker-specific ignores to a repository whose conventions require each
      suppression to be individually narrowest and individually explained.
- [ ] Register the twenty-five instead, as classified expected diagnostics.
      `depin/`'s three existing waivers stay exactly as they are.
- [ ] Build `conformance/expected/ty-source.txt`. Each line is a
      **`file:rule:count` triple** with a one-line classification. The count is
      load-bearing: a bare `file:rule` pair would absorb any number of further
      diagnostics of that rule in that file, which is the property the register
      exists to deny. Line numbers were the alternative and they churn on every
      edit.
- [ ] Expect roughly thirty-one entries at three classifications — twenty-five
      suppression-spelling artefacts, two from ty's gradual model of
      `Callable[..., object]`, four from ty resolving `taskiq.TaskiqResult`
      through pydantic's `PydanticRecursiveRef`. The thirty-second,
      `tests/typing/test_conformance.py:82`, is removed by the oracle rewrite in
      Task 3 rather than registered. **Record what is measured, not this
      estimate.**
- [ ] Measure both registers under **the exact invocation the gate runs**. ty's
      32 was counted under a bare `uvx ty check`; the gate adds `--error all`,
      and the baseline verified that flag changes nothing only on the consumer
      corpus.
- [ ] Build `conformance/expected/pyrefly-source.txt`: two
      `implicit-any-lambda` and one `implicit-any-type-argument` after R4 removes
      the fourteen-error variance cluster — two in private modules, one in a unit
      test. The `implicit-any-type-argument` entry names `Token[T]` in
      `depin/_core/typeguards.py` and **may disappear** once Task 1 makes that
      guard name `TokenKey`. Measure; do not transcribe.
- [ ] Extend `scripts/conformance.py` with a register comparison: fail on a
      diagnostic the register does not carry, **and** fail on a register entry
      that no longer appears. The second is what stops the register growing
      stale.
- [ ] `.github/workflows/ci.yml`: add `typing-source`, a blocking matrix over
      stock Pyright (at zero), ty and Pyrefly (against their registers), and
      **delete the `ty (advisory)` job**, whose check step ends in `exit 0` and
      therefore establishes nothing.
- [ ] Add `scripts` to `[tool.mypy] files` and `[tool.basedpyright] include` so
      `scripts/conformance.py` is checked. `scripts/check_mutation_threshold.py`
      is already clean under both in strict mode, so this should be a two-line
      configuration change.

## Task 5 — the forward probe

**Files:** `.github/workflows/typing-forward.yml`

- [ ] A weekly scheduled workflow, also runnable by `workflow_dispatch`, that
      resolves the newest release of each of the five, runs the complete
      conformance suite against it in both install modes, additionally at the
      3.13 and 3.14 language targets, and additionally on Windows and macOS.
      The OS axis is there for the isolation guard, not for inference.
- [ ] Advisory: an upstream release does not block a merge. **But not silent** —
      on failure it opens or updates one tracking issue per checker, titled for
      the checker and version, carrying the diagnostics. It never edits
      `conformance/checkers.toml`; advancing a pin is a human pull request that
      shows the suite green.
- [ ] It also probes one release behind for the three stable lines, so the
      project accumulates the evidence that would let a declared minimum be
      lowered later. The initial policy sets minimum equal to current tested for
      all five, because exactly one version of each has been measured.
- [ ] Five gates, then open **PR C**,
      `ci: make ty and Pyrefly block on the repository source`. Merge when green.

## Task 6 — documentation, evidence, roadmap

**Files:** `docs/support-policy.md`, `CONTRIBUTING.md`,
`.github/PULL_REQUEST_TEMPLATE.md`,
`specs/evidence/2026-09-01-step-6-consumer-typing.md`,
`specs/2026-08-28-roadmap-1.0-design.md`

- [ ] Rewrite the "Type checkers" section of `docs/support-policy.md`: the three
      layers, the five pinned versions, the minimum-equals-current rule and how
      it advances, the two install modes, the single Python target with the
      weekly multi-target probe, the anti-`Any` requirement carried by
      Basedpyright and mypy alone — ty cannot express one — and the two
      documented false negatives with their Step 8 routing.
- [ ] Report the Pyrefly variance-inference divergence upstream, using the
      nine-line reproducer the baseline isolated, which imports nothing from
      `depin`. Link the issue from the support policy. If the report cannot be
      filed, say so in the evidence report rather than implying it was.
- [ ] `CONTRIBUTING.md`: a section on the layer model and
      `uv run python -m scripts.conformance`. The five gates are unchanged — the
      conformance suite needs a built wheel and does not belong in a per-commit
      loop, and the document must say so rather than leaving a reader to guess.
- [ ] `.github/PULL_REQUEST_TEMPLATE.md`: one line for the conformance gate,
      phrased so it reads as a CI gate rather than a sixth local one.
- [ ] `specs/evidence/2026-09-01-step-6-consumer-typing.md`: the normal results
      for all five in both modes, and the **fault injection** table, each case
      applied, measured, reverted, with the command and the real output:
      - `FrozenContainer.resolve` return widened to `object` → all five
        `typing-consumer` jobs fail;
      - `Inject[T]` loses its parameter → the all-extras mode of all five fails;
      - `depin/py.typed` removed from the wheel build → `typing-artifact` fails
        and all five report the `Any` cascade;
      - R4 reverted → Pyrefly's job fails with six
        `bad-argument-type`/`bad-return`, which is what proves R4 is load-bearing
        rather than decorative;
      - the runner made to check the corpus in place rather than the copied
        directory → the per-subprocess working-directory assertion fires before
        any checking;
      - a negative fixture's misuse rewritten as valid code → the negative
        harness fails for a missing expected rejection;
      - a name added to `depin.__all__` → the coverage test fails;
      - a diagnostic added to a file in the ty register → `typing-source` fails.
- [ ] Update `specs/2026-08-28-roadmap-1.0-design.md`: mark Step 6 closed with
      what it delivered, record that the `provides=` repair landed, and hand
      Step 8 the two false negatives plus the open question of whether `TokenKey`
      stays exported and whether it is sealed against subclassing.
- [ ] Five gates, `mkdocs build --strict`, then open **PR D**,
      `docs: record what Step 6 closed and what it routed on`. Merge when green.

## Task 7 — release 0.17.0

- [ ] Confirm release-please opened a release pull request and that it proposes
      **0.17.0** — PR A's `feat:` is what makes it minor. Only `feat:`, `fix:`,
      `perf:`, `deps:` and `revert:` open one; B, C and D ride along.
- [ ] Verify the changelog carries the 0.16.3 entries too. 0.16.3 was never
      published; it is tooling and rides into this release rather than being
      published on its own.
- [ ] Merge the release pull request, then approve the `pypi` environment
      deployment. **Do not remove the environment protection.** Confirm the ids
      dynamically rather than pasting a remembered one.
- [ ] Confirm the published version from the `publish` job log, not only the
      PyPI API — its cache lags.

## Definition of done

- [ ] Five checkers run against the installed wheel, in two install modes, with
      a declared version policy.
- [ ] R4 implemented; a `Token` is accepted wherever a provider key is, under
      all five.
- [ ] The over-promising assertions are witnesses; every remaining `assert_type`
      is classified in `coverage.toml`.
- [ ] The corpus is in the repository with a coverage map that fails the unit
      gate when a public symbol arrives without a typing decision.
- [ ] No CI job is ever falsely red, and none passes unconditionally.
- [ ] Fault injection shows every gate failing when the behaviour it guards
      regresses.
- [ ] 0.17.0 published to PyPI.
- [ ] The roadmap records what Step 6 closed and what Steps 7 and 8 inherit.
