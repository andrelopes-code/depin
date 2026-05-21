# Project instructions

Rules for any contributor — human or agent — working in this repository. Read this before making any change.

## Project

`depin` is a type-first dependency-injection library for Python. The core has **zero runtime dependencies**. Framework integrations (FastAPI, etc.) live under `depin/ext/` and are optional installation extras.

The library leans heavily on Python's modern type system — PEP 695 generics, `Protocol`, `Annotated`, `@overload`, `ParamSpec` — to give consumers precise return types without any `# type: ignore` at call sites.

## Tooling

- **Package manager:** `uv`. Use `uv add <pkg>` / `uv remove <pkg>`. Commit `uv.lock`.
- **Type checker:** `basedpyright` in strict mode. Configuration lives in `pyproject.toml` under `[tool.basedpyright]` — do not reintroduce `pyrightconfig.json`.
- **Formatter & linter:** `ruff`. Line length 120, single quotes.
- **Tests:** `pytest` + `pytest-asyncio`.
- **Python:** 3.12 or newer (PEP 695 syntax is used throughout).

### Before every commit

Run, in order, from the repo root:

```
uv run ruff format
uv run ruff check
uv run basedpyright
uv run pytest
```

A commit is only ready when all four pass with no warnings or waivers.

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

## Error handling

- Never swallow exceptions. `except: pass` and `except Exception: pass` are forbidden.
- When cleaning up multiple resources, collect failures and raise an `ExceptionGroup`. Never let one teardown failure hide another.
- Error messages must be actionable. Include the key that failed, the chain that led to it, and — when possible — a concrete next step for the user.
- Raise the most specific exception type available. Custom exceptions live in `depin/errors.py` and inherit `DepinError`.

## Tests

- New behaviour in `depin/_core/` is developed test-first.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery.
- Prefer `pytest.mark.parametrize` over duplicated test bodies.
- Integration tests for `depin.ext.fastapi` use a real `httpx.AsyncClient` against a real `FastAPI` app.
- Coverage target: **≥ 95% for `depin/_core/`**. No untested branches in public API code paths.
- Tests must be deterministic. No sleeps, no network, no clock dependence without a fake clock.

## Dependencies

- Core modules (`depin/`, excluding `depin/ext/`) must not import any third-party library. `fastapi`, `starlette`, `pydantic`, etc. appear **only** under `depin/ext/`.
- New runtime dependencies are not accepted in the core.
- Dev dependencies go under the `dev` group in `pyproject.toml`. Pin conservatively; do not add tools casually.

## Code organisation

- One responsibility per module. If a file exceeds roughly 400 lines or mixes unrelated concerns, split it.
- Public API is re-exported from `depin/__init__.py`. Internal modules live under `depin/_core/` and are never imported directly by users.
- Immutability is the default for data structures. Use `@dataclass(frozen=True, slots=True)`.
- No module-level mutable state. No implicit global container.
- No import-time side effects beyond registering into explicit `Registry` objects.

## Commits

- Conventional-commit prefixes: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `build:`, `refactor:`, `perf:`.
- One logical change per commit. Unrelated cleanups go in their own commit.
- Subject line ≤ 72 characters, imperative mood.
- Body only when context is needed beyond the subject.
- **Do not add co-author trailers, tool attributions, or any reference to automation / assistants / AI in commits, PR descriptions, or code.** Everything in the history must read as written by the repository authors.

## What not to do

- Do not use `# type: ignore`, `# pyright: ignore`, `typing.cast`, or `Any` as shortcuts.
- Do not swallow exceptions.
- Do not add separator comments or comments that restate the code.
- Do not introduce global containers or shared mutable state.
- Do not leave `print()`, `breakpoint()`, or commented-out code in committed files.
- Do not mix unrelated changes in a single commit.
- Do not add framework imports to core modules.
- Do not reintroduce dependencies that the core has deliberately shed.
