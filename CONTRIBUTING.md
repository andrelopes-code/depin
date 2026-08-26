# Contributing to depin

`depin` (published on PyPI as `pydepin`) is a type-first dependency-injection
library for Python 3.12+ with a zero-dependency core and an optional FastAPI
integration. See the [README](README.md) for an overview and
[AGENTS.md](AGENTS.md) for the full repository conventions.

Thank you for taking the time to contribute. This guide covers everything you
need to get a change merged.

## Development setup

Requires Python 3.12 or newer and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
```

This installs the core, the FastAPI extra, and all development tooling
(`ruff`, `basedpyright`, `pytest`, `pytest-asyncio`, `pytest-cov`).

Optionally, install the git hooks so formatting and linting run before a commit
is written:

```bash
uvx pre-commit install
```

The hooks reproduce the first two gates only. The type check and the test suite
still have to be run explicitly, because both need the project environment.

## The four gates

Run these four commands, **in this exact order**, from the repository root
before every commit. A change is only ready when all four pass with no
warnings or waivers.

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run pytest
```

- `uv run ruff format` — formats the code (line length 120, single quotes).
- `uv run ruff check` — lints.
- `uv run basedpyright` — type-checks in strict mode. No `# type: ignore`,
  `# pyright: ignore`, `typing.cast`, or `Any` shortcuts.
- `uv run pytest` — runs the test suite, the doctests embedded in the
  public-API docstrings, the doctests in `docs/guide/`, and the programs under
  `examples/`.

## Commits

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
The release tooling reads your commit history to compute the next version and
to assemble the changelog, so the prefix matters.

Allowed prefixes:

| Prefix      | Use for                                              |
| ----------- | ---------------------------------------------------- |
| `feat:`     | A new feature                                        |
| `fix:`      | A bug fix                                            |
| `chore:`    | Maintenance that doesn't touch source behaviour      |
| `docs:`     | Documentation only                                   |
| `test:`     | Adding or adjusting tests                            |
| `build:`    | Build system, packaging, or workflow changes         |
| `refactor:` | A code change that neither fixes a bug nor adds a feature |
| `perf:`     | A performance improvement                            |

There is no `ci:` prefix — workflow and CI changes use `build:`.

Other rules:

- One logical change per commit; unrelated cleanups go in their own commit.
- Subject line ≤ 72 characters, imperative mood.
- Add a body only when context is needed beyond the subject.
- A breaking change is marked with `!` (for example `feat!:`) and/or a
  `BREAKING CHANGE:` footer.

## Tests

- New behaviour in `depin/_core/` is developed **test-first**: write the
  failing test, then make it pass.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI
  machinery.
- Prefer `pytest.mark.parametrize` over duplicated test bodies.
- Tests must be deterministic: no sleeps, no network, no clock dependence
  without a fake clock.
- Coverage floor: **≥ 95% for `depin/`**, measured over the whole package. No
  untested branches in public API code paths.
- A test that guards a concurrency invariant must fail when the guard is
  removed. Synchronise with `threading.Barrier` or `asyncio.Event`; never with a
  timed sleep.

You can check coverage locally with:

```bash
uv run pytest --cov=depin --cov-report=term-missing
```

## Documentation

The site is built with MkDocs and Material, and the API reference is generated
from the source docstrings by `mkdocstrings`. Build it locally with:

```bash
uv run --group docs mkdocs serve
```

`mkdocs build --strict` runs in CI: a broken cross-reference or an orphaned page
fails the build. `docs/reference/` is generated from the docstrings — edit the
source, not the page. `docs/guide/` is hand-written, and its `pycon` blocks are
doctests executed by `uv run pytest`.

## Pull request flow

1. Create a topic branch off `main`.
2. Make your change, keeping commits focused and conventional.
3. Ensure the four gates pass locally and that coverage holds.
4. Push the branch and open a pull request against `main`.
5. Give the PR a Conventional-Commit-style title — it becomes the squashed
   commit subject and feeds the release tooling.
6. Fill in the pull request template and make sure CI is green.

A maintainer will review and merge once CI passes and the change meets the
conventions above.

## Releasing

Releases are automated and driven by your conventional commits — maintainers do
not hand-edit versions or the changelog.

1. As conventional commits land on `main`, release-please opens and maintains a
   release pull request. It proposes the next version and updates
   `CHANGELOG.md` and the package version.
2. Merging that release pull request tags `vX.Y.Z`, creates a GitHub Release,
   and triggers the publish job in `release.yml`.
3. The publish job builds the distributions and uploads them to PyPI using
   [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — no API
   tokens are stored in the repository.

### One-time maintainer setup

These steps are required once, by a maintainer, before the first automated
publish:

- On PyPI, register a Trusted Publisher for the project `pydepin` with:
  - **Owner:** `andrelopes-code`
  - **Repository:** `depin`
  - **Workflow:** `release.yml`
  - **Environment:** `pypi`
- In the GitHub repository settings, create a protected
  [Environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
  named `pypi`.
