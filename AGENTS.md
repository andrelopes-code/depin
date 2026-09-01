# Project instructions

Rules for any contributor — human or agent — working in this repository. Read
this before making any change.

This file is the single source of truth for repository conventions. `CLAUDE.md`
contains only `@AGENTS.md` and exists so Claude Code loads this file; other
agent harnesses read `AGENTS.md` directly. Do not duplicate rules across the
two.

## Project

`depin` is a type-first dependency-injection library for Python. The core has **zero runtime dependencies**. Framework integrations (FastAPI, etc.) live under `depin/ext/` and are optional installation extras.

The library leans heavily on Python's modern type system — PEP 695 generics, `Protocol`, `Annotated`, `@overload`, `ParamSpec` — to give consumers precise return types without a `# type: ignore` at call sites.

## Tooling

- **Package manager:** `uv`. Use `uv add <pkg>` / `uv remove <pkg>`. Commit `uv.lock`.
- **Type checkers:** `basedpyright` in strict mode, plus `mypy --strict` as a second checker. Configuration lives in `pyproject.toml` under `[tool.basedpyright]` and `[tool.mypy]` — do not reintroduce `pyrightconfig.json`. CI runs both against each Python version in the test matrix.
- **Formatter & linter:** `ruff`. Line length 120, single quotes.
- **Tests:** `pytest` + `pytest-asyncio`.
- **Python:** 3.12 or newer (PEP 695 syntax is used throughout).

### Before every commit

Run, in order, from the repo root:

```
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

A commit is only ready when all five pass with no warnings or waivers.
`pytest` is configured with `--doctest-modules` over `tests` and `depin`, so
every `Example:` in a public docstring is executed as part of the gate.

Documentation changes additionally require:

```
uv run --group docs mkdocs build --strict
```

## Type system

- Use PEP 695 syntax: `class Container: ... def bind[T](self, ...) -> Self: ...`. Do not mix the older `TypeVar(...)` form with the new syntax in the same module.
- Prefer `typing.Protocol` for abstractions. Abstract base classes are only acceptable when inheritance of concrete behaviour is genuinely needed.
- Use `@overload` whenever a return type depends on the input type; a single union return type that forces callers to narrow is a design smell.
- Use `Annotated[T, ...]` for any metadata the type system should carry. Metadata classes must be small, immutable, and have a clear purpose.
- Functions and methods declare their parameter and return types. Variable annotations are only added when inference is insufficient or ambiguous.

### Suppressions

**Do not use `# type: ignore`, `# pyright: ignore`, or `typing.cast` to silence diagnostics.** A type-checker error is a design signal. Treat it as a bug to be understood and resolved.

Acceptable reasons to suppress, in order of preference:

1. **Refactor the code** so the types line up naturally. This is almost always possible and almost always produces a better API.
2. **Introduce a narrower type** (a `Protocol`, a newtype, an overload) that captures the real contract.
3. **Push the unsafe boundary down** to a single private helper where the unsafety is confined and documented.

If, after exhausting the above, a suppression is still the only option, it must be:

- The narrowest possible form (`# pyright: ignore[specificRule]`, never blanket).
- Accompanied by a comment that names the underlying Python/runtime limitation forcing it (e.g. "`inspect.signature` returns `Any` for C-implemented callables").
- Reviewed — unexplained suppressions are rejected.

`typing.Any` is also a suppression. Treat it the same way: prefer `object` or a generic, constrain it, or narrow it with `isinstance`. `Any` in public signatures is nearly always a bug.

## Comments and documentation

- Do not write comments that restate what the code does.
- Do not use banner or separator comments (`# --- section ---`, `# Helpers`, etc.). If a file has sections that need labelling, split the file.
- Write a docstring when it adds something the signature cannot convey: invariants, preconditions, edge cases, or a short example for public API.
- If a piece of code needs a comment to be understood, rewrite the code. A required comment is a signal that names, structure, or decomposition are wrong.
- Inline comments are reserved for genuinely non-obvious reasoning: a workaround for a specific bug, a subtle invariant, a performance trade-off. They must explain *why*, never *what*.

### Docstrings on the public API

The public API — everything re-exported from `depin/__init__.py`, the exceptions
in `depin/errors.py`, and `depin/ext/fastapi.py` — carries Google-style
docstrings (`Args:`, `Returns:`, `Raises:`, `Example:`). Because the library is
type-first, **docstrings never restate types**: the signature already carries
them. Document only what the signature cannot:

- semantics of lifetimes and scope (singleton / scoped / transient);
- teardown order and guarantees;
- error conditions — every public callable lists the exceptions it raises under
  `Raises:`, with the trigger and, where useful, how to resolve it;
- sync vs async rules (when `resolve` rejects async; when `aresolve` / `ascope`
  are required);
- what `freeze()` validates.

Rules:

- Omit types from `Args:` / `Returns:` — describe meaning and contracts, not the
  type the annotation already states.
- Every `Example:` uses doctest (`>>>`) and is executed by the default `pytest`
  run, which is configured with `--doctest-modules --doctest-glob=*.md` over
  `tests`, `depin`, and `docs`. Keep examples short and self-contained; prefer
  one focused example over many.
- Do not document private helpers in `_core` just to document them. Add a
  docstring only where it conveys an invariant, precondition, edge case, or
  example — the same bar this file already sets for comments.
- One-line module docstrings state the module's role; the package docstring in
  `depin/__init__.py` gives the mental model (Container → freeze →
  FrozenContainer) and a minimal runnable example.

### The documentation site

`docs/` is built by MkDocs. `docs/reference/` is generated from the docstrings
and must never restate them by hand. `docs/guide/` is the narrative half —
lifetimes, composition, testing, FastAPI — and its `pycon` blocks are doctests
run by the normal test command, so a guide cannot drift from the API.

### Examples

`examples/` holds runnable programs, one per concept, each exercised by
`tests/integration/test_examples.py`. An example must be executable
(`python -m examples.<name>.main`), free of module-level container construction,
and listed in `examples/README.md`.

## Error handling

- Never swallow exceptions. `except: pass` and `except Exception: pass` are forbidden.
- **Every exception depin raises inherits `DepinError`.** No code path may raise a bare `TypeError`, `ValueError`, `RuntimeError`, or `AssertionError`. When a standard type is also the right one for callers to catch, inherit both (`InvalidProviderError(DepinError, TypeError)`).
- **Never use `assert` to validate runtime input.** `python -O` strips asserts, and the invariant then fails silently somewhere unrelated. `assert` is for test bodies only; in library code, raise.
- When cleaning up multiple resources, collect failures and raise an `ExceptionGroup`. Never let one teardown failure hide another.
- Error messages must be actionable. Include the key that failed, the chain that led to it, and — when possible — a concrete next step for the user.
- Custom exceptions live in `depin/errors.py`.

## Public API naming

- No trailing-underscore names in the public API (`from_`, `with_`). If a name
  collides with a keyword, the API is wrong: change the shape instead
  (`Container(*sources)` rather than `Container.from_(*sources)`).
- Prefer a positional argument over a keyword whose name only exists to dodge a
  keyword clash.
- One verb per concept across `Container`, `Registry`, and `ScopeFrame`. A method
  that means the same thing on two classes must be named the same and live on
  the shared base in `_core/bindings.py`.

## Tests

- New behaviour in `depin/_core/` is developed test-first.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery.
- Prefer `pytest.mark.parametrize` over duplicated test bodies.
- Integration tests for `depin.ext.fastapi` use a real `httpx.AsyncClient` against a real `FastAPI` app.
- Coverage target: **≥ 95% for `depin/`**, measured over the whole package including `depin/ext/`. No untested branches in public API code paths.
- Tests must be deterministic. No sleeps, no network, no clock dependence without a fake clock. To reproduce a concurrency bug, synchronise explicitly — `threading.Barrier`, `asyncio.Event`, a reduced `sys.setswitchinterval` — never a timed sleep.
- A test that guards a concurrency invariant must be shown to fail when the guard is removed. If deleting the lock keeps the suite green, the test proves nothing.

## Dependencies

- Core modules (`depin/`, excluding `depin/ext/`) must not import any third-party library. `fastapi`, `starlette`, `pydantic`, etc. appear **only** under `depin/ext/`.
- New runtime dependencies are not accepted in the core.
- Dev dependencies go under the `dev` group in `pyproject.toml`. Pin conservatively; do not add tools casually.

## Code organisation

- One responsibility per module. If a file exceeds roughly 400 lines of code — docstrings do not count, and public-API docstrings are long by design — or mixes unrelated concerns, split it. The current `_core` map:

| Module | Responsibility |
| --- | --- |
| `bindings.py` | The registration surface shared by `Container` and `Registry`. |
| `container.py` | `Container.freeze()`. |
| `registry.py` | `Registry` and its `|` composition. |
| `providers.py` | `BindRecord` → `ProviderSpec`: key, shape, parameters. |
| `graph.py` | Validation and ordering into a `ResolutionPlan`. |
| `diagnostics.py` | The public graph view over a validated plan. |
| `render.py` | The resolution tree, `dot`, and `mermaid` renderings of that view. |
| `frozen.py` | The runtime: resolve, scope, inject, override. |
| `hosting.py` | The public integration contract: `Host` and the ambient container. |
| `construct.py` | Calling a provider according to its shape. |
| `scope.py` | Lifetimes, the scope frame, and its locks. |
| `teardown.py` | Teardown records and the drains that run them. |
| `typeguards.py` | Narrowing the plan's `object` to a concrete shape. |
| `overrides.py` | Context-local provider substitution. |
| `injection.py` | The `@inject` wrapper. |
| `introspect.py` | Shape detection and `Annotated` metadata. |
| `markers.py`, `spec.py` | Public markers; internal data structures. |
- Public API is re-exported from `depin/__init__.py`. Internal modules live under `depin/_core/` and are never imported directly by users.
- `benchmarks/` is a top-level package of `pytest-benchmark` suites guarding hot paths — resolution, scope entry, injection — against regressions. It sits outside `testpaths`; see `CONTRIBUTING.md` for how to run it.
- Immutability is the default for data structures. Use `@dataclass(frozen=True, slots=True)`.
- No module-level mutable state. No implicit global container — a container
  published context-locally through an explicit `Host` is not one, because
  nothing reaches it unless a `Host` published it in that context and the
  publication is undone on exit.
- No import-time side effects beyond registering into explicit `Registry` objects.

## Commits

- Conventional-commit prefixes: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `build:`, `refactor:`, `perf:`.
- One logical change per commit. Unrelated cleanups go in their own commit.
- Subject line ≤ 72 characters, imperative mood.
- Body only when context is needed beyond the subject.
- **Do not add co-author trailers, tool attributions, or any reference to automation / assistants / AI in commits, PR descriptions, or code.** Everything in the history must read as written by the repository authors.

### Which prefixes cut a release

`release-please-config.json` lists every prefix under `changelog-sections`, and
the ones marked `hidden` produce no changelog entry. A release is skipped
entirely when the changelog would be empty, so **only `feat:`, `fix:`, `perf:`,
`deps:` and `revert:` open a release pull request**. Everything else — `docs:`,
`chore:`, `refactor:`, `test:`, `build:`, `ci:`, `style:` — rides along in the
next release that a user-facing change creates.

This is deliberate. A version published to PyPI is a claim that something
changed for the person installing it; a roadmap edit or a test refactor is not
that. Four patch releases were cut for documentation before the sections were
declared explicitly.

The one case that needs care is a **declared dependency floor**, which is
user-facing but conventionally written as `build:`. Widening a floor can wait
for the next release. Raising one changes what a consumer can install, so write
it as `fix:` and let it cut a release of its own.

## What not to do

- Do not use `# type: ignore`, `# pyright: ignore`, `typing.cast`, or `Any` as shortcuts.
- Do not swallow exceptions.
- Do not add separator comments or comments that restate the code.
- Do not introduce global containers or shared mutable state — the
  context-local publication behind `Host` is neither, because it reaches only
  the context a `Host` published it in and is undone on exit.
- Do not leave `print()`, `breakpoint()`, or commented-out code in committed files.
- Do not mix unrelated changes in a single commit.
- Do not add framework imports to core modules.
- Do not reintroduce dependencies that the core has deliberately shed.
