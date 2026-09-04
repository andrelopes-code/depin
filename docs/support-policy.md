# Support policy

The [stability and compatibility policy](stability.md) defines which depin
surfaces are public and when the V1 Semantic Versioning commitment begins.

## Python versions

depin supports every CPython release that upstream still supports, from 3.12
upward. 3.12 is the floor because the library is written in PEP 695 generic
syntax throughout.

| Version | Status |
| --- | --- |
| 3.12 | Supported. The floor, and the version the type checkers are configured against. |
| 3.13 | Supported, including the free-threaded build. |
| 3.14 | Supported, including the free-threaded build. |
| 3.15 | Tested against the pre-release. Not yet a support commitment. |

A version is dropped in the first minor release after its upstream end of life,
and the removal is announced in the changelog of the release before it. Dropping
a version is a minor release, not a major one, because the alternative is
pinning the project to interpreters that no longer receive security fixes.

## Free-threaded builds

The free-threaded builds of 3.13 and 3.14 run the core test suite on every
change. depin's guarantee that a cached provider is constructed exactly once
under contention comes from its own locks, not from the GIL, and the CI job
asserts the GIL is disabled before it runs so the coverage cannot become
vacuous.

The optional FastAPI integration is not covered on free-threaded builds, because
its dependencies do not publish wheels for those interpreters.

## Operating systems

Linux, macOS, and Windows. The full matrix runs on Linux; macOS and Windows run
the floor version.

## Optional dependencies

`depin.ext.fastapi` declares a minimum for `fastapi` and `starlette`. CI resolves
those at their declared minimum in a dedicated job, so the floor is verified
rather than assumed, and separately at the current release.

## Type checkers

Five checkers are supported: mypy, stock Pyright, Basedpyright, ty and Pyrefly.
Support is measured from where a user stands — a consumer project that installs
the published wheel — and not from the repository checkout.

### Three layers, and what each checker decides in each

| Layer | What is checked | mypy | stock Pyright | Basedpyright | ty | Pyrefly |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Implementation | `depin tests examples scripts`, in the checkout | zero, blocking | zero, blocking | zero, blocking | register, blocking | register, blocking |
| 2. Consumer contract | a corpus of ordinary consumer code, against the installed wheel | zero, blocking | zero, blocking | zero, blocking | zero, blocking | zero, blocking |
| 3. Forward probe | both of the above, on the newest release of each checker | advisory | advisory | advisory | advisory | advisory |

Layer 2 is the support commitment. It is the only layer whose object is the
artifact a user installs, and every one of the five must report zero diagnostics
on it. No checker is authoritative over another: a change must satisfy all five.

Layer 1 keeps the existing discipline over private code, tests and examples.
mypy and Basedpyright run it on every commit; stock Pyright, ty and Pyrefly run
it in CI.

Layer 3 is advisory by construction. An upstream release is not a merge blocker,
but a failing probe opens a tracking issue naming the checker and the version,
and the release checklist requires each open issue to be resolved one of three
ways: make the new release green, retain and document the tested ceiling, or
document a verified upstream blocker.

### Versions and targets

`conformance/checkers.toml` is the only place these numbers appear. CI and the
local runner both read it, so a local run reproduces the gate exactly.

| Checker | Tested version |
| --- | --- |
| mypy | 2.3.1 |
| stock Pyright | 1.1.411 |
| Basedpyright | 1.39.10 |
| ty | 0.0.77 |
| Pyrefly | 1.2.0 |

The language target is Python 3.12 and the operating-system target is Linux.

Stock Pyright is run independently of Basedpyright, at both layers. Basedpyright
1.39.10 is built on a different pyright commit than stock Pyright 1.1.411 and
carries a different rule set, so a Basedpyright result is not counted as a
Pyright result.

### Minimum supported equals current tested

For all five checkers, the minimum supported version is the version in the table
above. Exactly one version of each has been measured; naming a lower minimum
would be a support claim with no evidence behind it.

- The **tested** version advances by a pull request that shows the whole suite
  green on the new version. It never advances automatically.
- The **minimum** version advances with it, unless the weekly probe has measured
  a lower version green and that measurement is recorded.
- A version is dropped when its line is superseded and no measurement is
  retained for it.

The probe's previous-release leg is what will make it possible to name a lower
minimum honestly. Until then the two numbers are the same number.

### Two install modes

The consumer corpus is checked twice, against two interpreters built from the
same wheel.

- **core-only** installs `pydepin` alone. The corpus covers `depin`,
  `depin.errors`, and the four `depin.ext` modules that import no third-party
  package. The runner additionally asserts that all eight framework-requiring
  `depin.ext` modules — `click`, `fastapi`, `flask`, `litestar`, `pytest`,
  `starlette`, `taskiq`, `typer` — are **unresolvable** in this interpreter,
  which is what proves the core carries no framework dependency.
- **all-extras** installs the wheel with all eight extras named explicitly and
  adds the eight framework modules to the corpus.

### One target per pull request, four more once a week

Each pull request runs one Python target, 3.12, and one operating system, Linux.
The weekly probe runs 3.13 and 3.14, and Windows and macOS.

The Python axis is a regression detector: the three targets were measured
byte-identical for all five checkers in both install modes, so a per-pull-request
matrix would triple the job count and buy nothing.

The operating-system axis exists for the isolation guard, not for inference.
What a checker infers from a wheel does not vary by host; path-ancestry
comparison and `.pth` discovery in `site-packages` do, and those are what the
guard rests on.

### The anti-`Any` requirement is carried by two checkers, not five

`Any` satisfies an assignment in both directions, so neither an exact type
assertion nor a typed witness detects it on its own. Two checker-native rules
carry the requirement:

- Basedpyright with `reportAny` and `reportExplicitAny` at error, over the whole
  positive corpus;
- mypy with `--disallow-any-expr`, over the core corpus only — in all-extras
  mode, third-party annotations produce `Any` expressions the corpus does not
  own.

ty cannot express an anti-`Any` rule at all, and stock Pyright has no equivalent
of `reportAny`. This requirement is therefore two checkers' and not five's, and
the policy says so rather than implying coverage it does not have.

### Two known false negatives

Two public signatures accept a call they should reject. Both are recorded as
divergence fixtures whose gate is each checker's verdict rather than rejection,
and both are routed to the Step 8 surface review, which is the last window in
which the call shape may change.

| Call | Verdict today |
| --- | --- |
| `FrozenContainer.override(Config, Other())` | accepted by all five |
| `Container.value(Token[int], 'str')` | accepted by four; rejected by Pyrefly |

In both, the type variable appears in the key parameter and in the value
parameter, so the solver widens it to the join of the two. The gate fails when a
verdict moves in either direction: a checker that starts rejecting one is news to
be recorded deliberately, and a checker that stops rejecting one is a loss of
detection.

Pyrefly rejects the second because it infers the phantom parameter of `Token[T]`
as invariant where the typing specification's variance-inference algorithm tests
covariance first, and where the other four infer covariance. That divergence is
reported upstream as
[facebook/pyrefly#4777](https://github.com/facebook/pyrefly/issues/4777), with a
nine-line reproducer that imports nothing from depin.

### Why ty and Pyrefly gate against a register on Layer 1

On Layer 2 every checker is held at zero and no baseline file exists, because
filtering known errors out of a positive fixture is not compatibility.

The repository source is a different object. It writes every intentional negative
as a `# type: ignore[code]  # pyright: ignore[code]` pair, and ty reads neither
spelling, so it re-reports code the other checkers have already been told about.
Holding ty at zero there would mean either rewriting those suppressions to suit a
`0.0.x` tool or hiding genuine upstream limitations.

So ty and Pyrefly are gated against `conformance/expected/ty-source.txt` and
`conformance/expected/pyrefly-source.txt`. Each line is a `file:rule:count`
triple with a one-line classification, and the job fails three ways: on a
diagnostic no entry carries, on an entry that no longer appears, and on a count
that moves in either direction.

That is stricter than the advisory job it replaced, not more lenient. The
previous arrangement ended in `exit 0` and could not fail. A register cannot
absorb a second diagnostic of a rule it already knows about, cannot absorb a
diagnostic in a file it does not name, and forces a deliberate edit — with a
written classification — before any of that changes.
