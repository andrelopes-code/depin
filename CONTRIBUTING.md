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
(`ruff`, `basedpyright`, `mypy`, `pytest`, `pytest-asyncio`, `pytest-cov`).

Optionally, install the git hooks so formatting and linting run before a commit
is written:

```bash
uvx pre-commit install
```

The hooks reproduce the first two gates only. The type checks and the test
suite still have to be run explicitly, because all three need the project
environment.

## The five gates

Run these five commands, **in this exact order**, from the repository root
before every commit. A change is only ready when all five pass with no
warnings or waivers.

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

- `uv run ruff format` — formats the code (line length 120, single quotes).
- `uv run ruff check` — lints.
- `uv run basedpyright` — type-checks in strict mode. No `# type: ignore`,
  `# pyright: ignore`, `typing.cast`, or `Any` shortcuts.
- `uv run mypy` — type-checks in strict mode with the second checker.
- `uv run pytest` — runs the test suite, the doctests embedded in the
  public-API docstrings, the doctests in `docs/guide/`, and the programs under
  `examples/`.

## The typing conformance suite

Five type checkers — mypy, stock Pyright, Basedpyright, ty and Pyrefly — are
gated in three layers. The
[support policy](https://andrelopes-code.github.io/depin/latest/support-policy/) states
each checker's authority in each layer; this section is how to run them.

| Layer | Object | How it runs |
| --- | --- | --- |
| 1. Implementation | `depin tests examples scripts`, in the checkout | mypy and Basedpyright at zero, in the five gates above. Stock Pyright at zero, ty and Pyrefly against a committed register, in CI's `typing-source` job |
| 2. Consumer contract | `conformance/`, checked against the built wheel installed into an isolated interpreter | CI's `typing-artifact` and `typing-consumer` jobs, all five at zero, in both install modes |
| 3. Forward probe | both, on the newest release of each checker | the weekly `typing-forward` workflow, advisory |

**The five gates above are unchanged, and the conformance suite is not a sixth
one.** It builds a wheel and creates three interpreters before it checks
anything, which does not belong in a per-commit loop. It is a CI gate. Run it
locally when you change the public surface, the corpus, the runner, or a pinned
checker version — and let CI run it otherwise.

```bash
uv run python -m scripts.conformance
uv run python -m scripts.conformance --source
```

The first checks the consumer corpus against a freshly built wheel; the second
checks the repository source. Both print a per-checker, per-mode table and exit
non-zero listing every failure rather than only the first.

Four flags narrow a run. `--checker`, `--mode` and `--only` are repeatable.

| Flag | Values | Effect |
| --- | --- | --- |
| `--checker` | `mypy`, `pyright`, `basedpyright`, `ty`, `pyrefly` | Run one checker instead of all five |
| `--mode` | `core`, `extras` | Run one install mode instead of both |
| `--only` | `control`, `positive`, `anti-erasure`, `negative`, `divergence` | Run one stage instead of all of them. The wheel and isolation assertions always run |
| `--source` | — | Check the repository source instead of the corpus. `--mode` and `--only` do not apply |

```bash
uv run python -m scripts.conformance --checker ty --mode core --only positive
uv run python -m scripts.conformance --source --checker pyrefly
```

`--source` needs the project environment complete, because the file list it
checks includes the integration tests: run `uv sync --all-extras` first, or the
three checkers report unresolved framework imports.

`conformance/README.md` documents what each tree holds, what the runner asserts
before it checks anything, and why the corpus is copied out of the checkout
before any checker sees it.

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

### Mutation testing

Mutation testing verifies that the unit suite rejects behavior changes in
`depin/_core/`. Run the complete local gate with:

```bash
rm -rf mutants
uv run mutmut run
uv run mutmut export-cicd-stats
uv run python -m scripts.check_mutation_threshold mutants/mutmut-cicd-stats.json
uv run mutmut results
```

The run requires at least 95% killed mutants, at most 5% surviving mutants,
and zero inconclusive results. Mutmut gives each selected test a two-second
watchdog so a deadlock is reported as a killed mutant instead of an inconclusive
timeout. It runs weekly, on demand, and for pull requests that change the core,
tests, its configuration, or this gate. `mutants/` is disposable generated
state and must never be committed.

## Benchmarks

`benchmarks/` holds the performance evidence system: the workload inventory,
the measurement harness, and the regression gates. It sits outside `testpaths`,
so a plain `uv run pytest` does not collect it; run it explicitly:

```bash
uv run --group bench pytest benchmarks --benchmark-only
```

Every workload carries a claim contract naming what it measures and what it
cannot be read as saying, and every workload is paired with a direct-Python
baseline doing the same useful work. `tests/integration/test_workload_contracts.py`
and `tests/integration/test_workload_equivalence.py` enforce both, and they run
in the ordinary suite — a workload whose baseline stops being equivalent fails as
a normal test, before anything is timed.

The methodology, the environments, and the reasoning behind the budgets are on
the [performance pages](https://andrelopes-code.github.io/depin/latest/performance/methodology/)
and in `specs/2026-09-02-step-7-performance-design.md`.

### What CI checks

Two different things, with different sensitivities.

The **latency gate** measures the base commit and the head commit on the same
runner across several paired repetitions, alternating which side runs first, and
compares each workload against a budget derived from that workload's measured
noise. It fails only when the regression is larger than the budget with
confidence, and an inconclusive result is re-measured once at double the
repetitions.

The **deterministic gates** — Python calls per operation, allocations per
operation, and scaling ratios — need no pairing and carry no noise. They catch
what the latency gate structurally cannot: a change that adds work to the
resolution path but stays inside the timing noise floor.

### When a check fails

Classify before changing anything, and never change a budget to make a pull
request green.

| Classification | What to do |
| --- | --- |
| Real regression | Reproduce, profile, then fix it or document the trade-off deliberately |
| Harness defect | Fix the setup, the timing boundary, the semantic validation or the parsing; withdraw any published result it affected |
| Environmental noise | Re-measure under the documented policy; improve isolation if it recurs |
| Workload drift | The semantics changed: start a new result series and explain the change |
| Dependency or interpreter change | Isolate the external movement and report both it and its user impact |
| Budget defect | Revise a threshold only with accumulated noise data and an impact argument |

A budget below its workload's measured noise floor is rejected by the harness, so
the last row cannot be used to silence the first. `benchmarks/budgets.toml` is
generated by `python -m benchmarks.harness.calibrate` over a collection of
identical code and is not edited by hand; the last row means re-measuring, not
retyping.

## Documentation

The site is built with MkDocs and Material, and the API reference is generated
from the source docstrings by `mkdocstrings`. Build it locally with:

```bash
uv run --group docs mkdocs serve
```

`mkdocs build --strict` runs in CI: a broken cross-reference or an orphaned page
fails the build. It does not check absolute links back at the site, and the
site is versioned with `mike`, so a link below the root needs the `latest/`
alias — `<site>/latest/guide/fastapi/`, never `<site>/guide/fastapi/`, which
404s. `tests/integration/test_documentation_links.py` enforces it. `docs/reference/` is generated from the docstrings — edit the
source, not the page. `docs/guide/` is hand-written, and its `pycon` blocks are
doctests executed by `uv run pytest`.

## Pull request flow

1. Create a topic branch off `main`.
2. Make your change, keeping commits focused and conventional.
3. Ensure the five gates pass locally and that coverage holds.
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
