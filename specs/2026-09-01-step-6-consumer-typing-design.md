# Step 6 — consumer typing compatibility: design

Date: 2026-09-01
Baseline: 0.16.3 at `2816b09`
Target: 0.17.0
Status: approved, pending implementation plan

## Goal

Make consumer-visible type inference a tested contract. Five checkers — mypy,
stock Pyright, Basedpyright, ty and Pyrefly — become blocking gates over a
corpus of ordinary consumer code checked against the **installed wheel**, with
exact-inference promises separated from assignability promises, negative
fixtures proving invalid uses stay invalid, and a bounded version policy.

The decision this step implements is recorded in
`specs/proposals/2026-08-31-multi-checker-consumer-typing-proposal.md`. The
measurements it rests on are in
`specs/evidence/2026-09-01-consumer-typing-baseline.md` and
`specs/evidence/2026-09-01-token-variance-experiment.md`. Neither is re-derived
here; this document decides.

## What the evidence already settled

| Question | Answer | Source |
| --- | --- | --- |
| Do the five checkers agree on `Inject[T]`? | Yes, sync and async, both install modes. | baseline C |
| Does the Python target matter? | No. Byte-identical results at 3.12, 3.13 and 3.14 for all five. | baseline E.1 |
| What does the positive corpus cost? | ~50 s of checker time for 5 checkers × 2 install modes, cold. | baseline E.4 |
| Is wheel isolation provable portably? | Yes — run the identical commands against an empty venv and require an unresolved-import diagnostic from each. | baseline A.7 |
| Why does Pyrefly reject `Token[int]` where a key is expected? | `Token[T]`'s parameter is phantom; the typing spec's variance-inference algorithm tests covariance first and a phantom parameter passes it. Pyrefly 1.2.0 infers invariance. Four checkers conform, Pyrefly does not. | variance A |
| Which remedy? | **R4** — a non-generic supertype in the `Token[object]` positions. Clears Pyrefly to zero on the positive consumer corpus, `T` stays phantom, no new member on `Token`. | roadmap Step 6, `2816b09` |
| Why not R5? | Its `payload` member exists only to pin variance, its shape was dictated by `reportUnusedFunction`, and the false negative it repairs is a side effect of invariance rather than a designed constraint. | roadmap Step 6 |
| Why is stock Pyright not a Basedpyright result? | Basedpyright 1.39.10 is built on pyright 1.1.412; the newest stock Pyright is 1.1.411. Different engine commits, different rule sets. | baseline A.1 |
| Can an unconfigured Pyrefly be trusted? | No. Its default preset is `basic`, which does not report `bad-argument-type` at all. | baseline A.4 |
| What breaks ty on the current corpus? | Suppression spelling. ty honours a bare `# type: ignore` and `# ty: ignore[...]`, but not `# type: ignore[code]` or `# pyright: ignore[...]`; the repository writes every intentional negative with the pair ty cannot read. 25 of its 32 source diagnostics are that. | baseline A.6, B.4 |

## Corrections to the inputs

Three claims in the source documents do not survive checking. This design uses
the corrected values.

**Nine `Token[object]` annotation positions, not eight.** The roadmap and the
variance experiment both say eight. `depin/_core/spec.py` carries two,
`depin/_core/markers.py` two, and `depin/_core/introspect.py` five — two
`AnnotatedMeta` fields, their two mirrors as locals in `extract_annotated_meta`,
and the `TypeGuard` on `is_object_token`. A tenth mention, the docstring on
`is_object_token`, is prose. All nine annotations are converted.

**Five assignability categories, not three.** The baseline introduces its list
as "three further categories" and then enumerates five. All five are binding.

**The baseline's timing table is labelled "13 files" where the corpus is 21.**
The corpus size is stated correctly elsewhere in both evidence documents; only
the timing table's label is imprecise, because it counts the positive corpus and
times the eight negative fixtures separately. This design's corpus is larger
again, since it adds the divergence fixtures.

One further correction concerns authority rather than arithmetic. The variance
experiment's own verdict table marks **R5** recommended and R4 an acceptable
fallback. The roadmap took R4, with reasons, in `2816b09`. **The roadmap is
binding here.** This design implements R4 and does not reopen the choice.

## New measurements taken for this design

Two questions the baseline did not answer were measured against a wheel built
from `2816b09` and installed into an isolated interpreter.

### The assignability rewrite reaches zero on ty

One probe file carrying both spellings of the three disputed constructs:

```
$ uvx ty@0.0.77 check --config-file ty.toml --error all --output-format concise
p.py:22:5: error[assert-type-unspellable-subtype] Type `<class 'Decorated'>` does not match asserted type `type[Decorated]`
p.py:28:5: error[type-assertion-failure] Type `() -> Cache` does not match asserted type `() -> Cache`
p.py:59:9: error[type-assertion-failure] Type `CoroutineType[Any, Any, str]` does not match asserted type `Awaitable[str]`
Found 3 diagnostics
```

Lines 22, 28 and 59 are the exact `assert_type` forms. The same three
constructs written as typed-assignment witnesses, in the same file, produce no
diagnostic. mypy 2.3.1 and Pyrefly 1.2.0 under `--preset strict` report zero on
both spellings.

**A required-zero consumer gate for all five is therefore reachable.** ty's
three baseline diagnostics are entirely the oracle, not the library.

### The empty-venv control is defeated by the working directory

```
# cwd = the repository root
$ uvx mypy@2.3.1 --strict --python-executable <empty-venv>/bin/python <consumer>.py
Success: no issues found in 1 source file

# cwd = the consumer directory, outside the checkout
$ uvx mypy@2.3.1 --strict --python-executable <empty-venv>/bin/python p.py
p.py:4: error: Cannot find implementation or library stub for module named "depin"  [import-not-found]
p.py:24: error: Untyped decorator makes function "make_cache" untyped  [untyped-decorator]
p.py:28: error: Expression is of type "Any", not "Callable[[], Cache]"  [assert-type]
...
Found 7 errors in 1 file
```

From the repository root mypy resolves `depin` out of the checkout even when the
named interpreter has no `depin` installed. The negative control does not fail,
so it proves nothing. The baseline never saw this because it ran every command
from `/tmp/typing-baseline/consumer`.

The requirement is therefore stronger than the proposal's "the consumer is
located outside the repository source path": **the process working directory
must also be outside it, and the control must run the identical command line
from the identical directory as the gate it controls.**

The second half of that output matters on its own. With the wheel absent, mypy
does not stop at `import-not-found` — every decorated symbol degrades to `Any`
and the oracles fail with `[assert-type]`. Isolation and anti-erasure are the
same measurement taken from two directions, which is why removing the typing
marker is a fault-injection case for both.

### ty honours a third suppression spelling appended to the existing pair

```python
di.resolve(42)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType, reportUnusedCallResult]
# → error[invalid-argument-type]

di.resolve(42)  # type: ignore[arg-type]  # pyright: ignore[...]  # ty: ignore[invalid-argument-type]
# → clean
```

mypy, stock Pyright and Basedpyright are unaffected by the appended comment,
and the ty directive may sit first, last, or between the other two. One ordering
constraint applies to the pair that already exists: **mypy requires
`# type: ignore` to be the first comment on the line**, so the ty directive is
appended, never prepended.

The technique works. **It is not adopted**, for a reason measured after this
probe and recorded under the source layer below: ty has its own
`unused-ignore-comment` rule, so twenty-five hand-written directives would make
a blocking job depend on ty continuing to emit exactly the rules they name.

## The shape of the guarantee

Three layers, as the proposal recommends, with each checker's authority stated.

| Layer | Checkers | Scope | Verdict |
| --- | --- | --- | --- |
| 1. Implementation | mypy, Basedpyright | `depin tests examples`, strict | zero, blocking (unchanged) |
| 1. Implementation | stock Pyright | `depin tests examples`, strict | zero, blocking (**new**) |
| 1. Implementation | ty, Pyrefly | `depin tests examples` | **delta against a committed register**, blocking (**new**) |
| 2. Consumer contract | all five | the corpus, against the installed wheel, core-only and all-extras | **zero, blocking** |
| 3. Forward probe | all five | both scopes, newest releases, 3.13 and 3.14 targets | advisory, visible, opens an issue |

### Why the consumer gate requires zero and the source gate does not

The proposal forbids filtering known errors out of a positive fixture's output:
"If a checker has a genuine bug, the version policy and upstream-issue process
should handle it rather than hiding the error in the consumer corpus." A
baseline file is exactly that filter, so the consumer contract gets none. The
measurements above show zero is reachable for all five once R4 lands and the
oracles are rewritten.

The repository source is a different object. ty reports 32 diagnostics over
`depin tests examples` and Pyrefly 3 after R4. Demanding zero there would mean
either rewriting the repository's suppressions to suit a 0.0.x tool or
suppressing genuine upstream limitations. Both are worse than recording them.

So Layer 1 gets a **register**: `conformance/expected/ty-source.txt` and
`conformance/expected/pyrefly-source.txt`, each line a `file:rule:count` triple
with a one-line classification. The job fails when a diagnostic appears that the
register does not carry, when the register carries one that no longer appears,
and when a registered count moves in either direction. The first is a
regression; the second means the register should shrink.

The count is not decoration. A `file:rule` pair alone absorbs any number of new
diagnostics of that rule in that file, so a register built from pairs would
silently accept the second defect of a kind it already knows about — which is
exactly the property the register exists to deny. Line numbers would have been
the other option and they churn on every edit; counts do not.

This replaces the current `ty (advisory)` job, whose check step ends in `exit 0`
and therefore establishes nothing. The register is what makes ty and Pyrefly
blocking without demanding a zero the project does not control.

### Why the register absorbs the suppression spelling rather than repairing it

The obvious alternative is to append `# ty: ignore[<rule>]` to the twenty-five
lines that already carry a `# type: ignore[code]  # pyright: ignore[code]` pair.
It works — the appended comment silences ty and leaves the other three checkers
untouched — and it would cut ty's source count from 32 to six.

**It is rejected, because it recreates on a blocking gate the exact fragility
this design rejects two sections below.** ty has its own unused-directive rule,
and it fires:

```
$ uvx ty@0.0.77 check w.py        # a: int = f(1)  # ty: ignore[invalid-argument-type]
w.py:5:11: warning[unused-ignore-comment] Unused `ty: ignore` directive
exit=1
```

Under `--error all` it is an error rather than a warning, and a directive naming
two rules fails the same way when only one of them fires. Every one of the
twenty-five lines would have to name exactly the rule set ty currently emits,
and any ty release that stops emitting one of them turns a blocking job red for
a reason that is upstream's. That is the same defect as
`tests/typing/test_conformance.py:304`, which the design moves out of the gate
for precisely this reason.

Registering the twenty-five as classified expected diagnostics costs one line
each in a file, touches no source, and adds no checker-specific comment to a
repository whose conventions require every suppression to be individually
narrowest and individually explained. A mechanical sweep of twenty-five lines is
neither.

So the ty register carries three classifications: suppression-spelling
artefacts, where ty agrees with mypy and Pyright about invalid code and cannot
read their waiver; gradual inference, where ty leaves a type variable, a
`getattr` result or a `callable()` narrowing as `Unknown`, `Any` or
`Top[(...) -> object]`; and ty resolving `taskiq.TaskiqResult` through
pydantic's `PydanticRecursiveRef`. `conformance/expected/ty-source.txt` is the
count, not this paragraph: **30 entries covering 44 diagnostics** — 27
suppression-spelling, 13 gradual-inference, 4 `PydanticRecursiveRef`.

An earlier draft of this section estimated thirty-one entries, two of them from
the gradual model. The estimate was extrapolated from the baseline's 32, counted
under a bare `uvx ty check`; the gate runs `--error all`. Measured on the merged
tree, the same run is 31 bare and 44 under the flag, and the 13 the flag adds are
`unsound-return-statement` ten times, `unsound-assignment` twice and
`missing-type-argument` once. Eleven of those 13 are gradual inference and two
sit on a line already carrying the waiver pair, which is exactly how 2 became 13
and 25 became 27. The estimate was right about what it could see and had no way
to see the rest. `tests/typing/test_conformance.py:82` is removed by the oracle
rewrite rather than registered, but the file still carries one entry, for an
`unsound-return-statement` the bare run never emitted.

Pyrefly's register carries three: two `implicit-any-lambda` and one
`implicit-any-type-argument`, two in private modules and one in a unit test.
The `implicit-any-type-argument` entry names `Token[T]` in
`depin/_core/typeguards.py`, so it may disappear once that guard names
`TokenKey` — the register is built from measurement after R4 lands, not from
this estimate.

**Both registers are measured under the exact flags the gate runs.** ty's 32 was
counted under a bare `uvx ty check`; the gate adds `--error all`, and the
baseline verified that flag changes nothing only on the consumer corpus. The
source register is re-measured under the gate's own invocation before it is
committed.

## Corpus organisation

A top-level `conformance/` directory, following the precedent `benchmarks/`
sets: a top-level tree that sits outside `testpaths` and is exercised by its own
command.

It cannot live under `tests/`. `tests` is inside both `[tool.mypy] files` and
`[tool.basedpyright] include`, so a consumer corpus placed there would be
checked against the checkout — defeating its purpose — and its negative fixtures
would break the repository gates.

```
conformance/
  README.md                     how to run it, and what each tree means
  checkers.toml                 the pinned version of each of the five
  coverage.toml                 public symbol -> fixture, or a recorded decision
  corpus/
    core/c01_container.py … c09_hosting.py
    ext_core/    asgi, wsgi, cli — no extra needed, checked in both modes
    ext_extras/  the eight modules that require an extra
  negative/n01_… .py            one misuse per file, no suppressions
  divergence/d01_… .py          accepted today; per-checker expectation recorded
  config/                       one native configuration per checker, templated
  expected/
    negative.toml               fixture -> line and rule identifier, per checker
    divergence.toml             fixture -> accept/reject, per checker
    ty-source.txt               the Layer 1 register
    pyrefly-source.txt          the Layer 1 register
scripts/conformance.py          the runner: local entry point and CI entry point
tests/unit/test_conformance_coverage.py   enforces coverage.toml completeness
```

The corpus is ordinary consumer code. It imports only `depin`, `depin.errors`
and `depin.ext.*`, never `depin._core`, and the runner asserts that textually
before it checks anything.

`corpus/core/` is checked in both install modes.

The ext corpus is split **by install mode, not by framework**, which is why it
does not reuse the baseline's `e01…e04` layout. Four modules under `depin/ext/`
import no third-party package at all — `ext/__init__`, `ext/asgi`, `ext/wsgi`
and `ext/cli` — and those are the generic seams the framework modules
specialise, carrying the bounded `RequestScope[ScopeT: ASGIScope, …]`,
`RequestScope[EnvironT, StartResponseT]`, `install[C: CommandContext]` and
`CommandContext.with_resource[T]`. `corpus/ext_core/` exercises them against a
consumer's own structural scope and command-context types, and is checked in
**both** modes.

The baseline's own `ext/e03_cli.py` mixed `click.Context` and `typer.Context`
into the same file as the structural case, so it could not be checked without
the extras — and its core-only run covered nine files, no ext file among them.
Splitting by mode is what makes the both-modes claim executable.

`corpus/ext_extras/` covers the eight modules that require an extra and is
checked in all-extras mode only. In core-only mode the runner asserts each of
those eight is *unresolvable*, which is what proves the core carries no
framework dependency.

There is no aggregate `all` extra. The all-extras interpreter is installed by
naming the eight explicitly: `click`, `fastapi`, `flask`, `litestar`, `pytest`,
`starlette`, `taskiq`, `typer`.

### The coverage map

`conformance/coverage.toml` carries one entry per public symbol. An entry either
names the fixtures that exercise it or records an explicit decision not to:

```toml
[Token]
fixtures = ["core/c02_keys.py"]

[CONTRACT_VERSION]
decision = "not-type-dependent"
reason = "a module-level int; no call site infers from it"
```

`tests/unit/test_conformance_coverage.py` enumerates the public surface and
fails when a name has no entry. It reads `depin.__all__` and `depin.errors`
directly. For `depin/ext/` it parses each module with `ast` rather than
importing it, because `tests/unit/` runs on the free-threaded and pre-release
jobs where no framework is installed — the same technique
`tests/unit/test_integration_contract.py` already uses.

**Three sources, not one.** The proposal asks for "every symbol re-exported from
`depin`, every public exception surface whose typing affects control flow, and
`depin.ext`". `depin/errors.py` carries eleven public exceptions, none of them
in `depin.__all__`, and four of them inherit a builtin as well
(`InvalidProviderError(DepinError, TypeError)`,
`InvalidScopeError(DepinError, ValueError)`,
`TeardownError(DepinError, RuntimeError)`,
`ContainerNotBoundError(DepinError, RuntimeError)`) — which is precisely a
typing fact that changes what a consumer's `except` clause catches. They are
enumerated by import, since `depin.errors` needs no framework.

**The `ast` scanner's contract is specified, because the naive version misses
the most important symbol in the package.** Only `depin/ext/fastapi.py` declares
`__all__`; the other eleven do not. And `fastapi.py` has no top-level `Inject`
at all — its module body is `__all__` plus a single `If` node, with
`type Inject[T] = T` in the `TYPE_CHECKING` branch and `class Inject` in the
`else`. A scanner walking `tree.body` for `ClassDef`/`FunctionDef`/`Assign`
finds nothing. So the contract is:

- honour `__all__` when the module declares one;
- otherwise take every non-underscore top-level `ClassDef`, `FunctionDef`,
  `AsyncFunctionDef`, `Assign`, `AnnAssign` and `TypeAlias`;
- **descend into `If` bodies and their `else` branches**, so a symbol declared
  under `TYPE_CHECKING` is found;
- treat a module-level `import X as Y` where `Y` is public as a symbol, not an
  import — `from depin.ext.asgi import RequestScope as ASGIRequestScope` is how
  three framework modules publish their base.

`TypeAlias` matters on its own: `ext/asgi.py` declares two PEP 695 aliases at
module level and `ext/wsgi.py` one.

**Class members are out of scope, and the design says so rather than implying
coverage.** `RequestScope.__call__`, `CommandContext.with_resource[T]` and every
`Container` method are not top-level names, so adding `Container.foo()` passes
this gate. The map guards the *symbol* inventory; the corpus guards the members,
and the two are different promises. Extending the map to members would mean
walking every class body of a package whose public classes carry the bounded
generics the corpus already exercises directly — cost without a matching gain.
Step 8's surface review is where member-level inventory belongs.

Within that scope this is the mechanism the proposal asks for: a new public
symbol cannot land without an explicit type-test decision, because the unit gate
fails until it has one.

## Exact inference versus assignability

The rule, derived from the baseline's five categories and confirmed by the probe
above:

> `assert_type` is honest for a nominal class, a `Protocol`, a parameterised
> generic of a `depin` type, a builtin, `None`, and unions of those. It is
> dishonest for anything a decorator returned, anything awaitable, any context
> manager, and any enum member expression.

Those categories use a typed-assignment witness instead — a variable annotated
with the promised type, assigned the expression under test. A witness fails for
exactly the reasons the contract cares about (`Any`, unknown, an unrelated type,
a lost generic argument) and passes when a checker chooses a valid narrower
representation.

**A witness inside a function is named with a leading underscore.** `ruff check`
is the second of the five gates and `F` is selected, and an annotation does not
exempt an unused local:

```
F841 Local variable `pending` is assigned to but never used
  --> pending: Awaitable[str] = handler('n')
```

`_pending: Awaitable[str] = handler('n')` is exempt under ruff's default
`dummy-variable-rgx`. This is a naming rule for the whole corpus, not a note,
because the witness is the mechanism the contract rests on.

| Category | Why exact equality is dishonest | Form used |
| --- | --- | --- |
| Decorator-returned classes | ty infers the class-literal `<class 'Repo'>`, assignable to `type[Repo]` but not equal | `key: type[Repo] = Repo` |
| Decorator-returned functions | ty distinguishes the function type from the `Callable` protocol and prints both sides identically | `factory: Callable[[], Cache] = make_cache` |
| `@inject` wrapper signatures | the injected parameter survives with its marker default, so the wrapper is `Callable[[str, int, Config], str]` under every checker | assert the call site: `assert_type(handler('a', 1), str)` |
| Context managers | `_GeneratorContextManager[ScopeFrame, None, None]` under mypy/Pyright/ty, `_GeneratorContextManager[ScopeFrame]` under Pyrefly | assert the `with`-bound value: `assert_type(frame, ScopeFrame)` |
| Awaitables | `inject`'s two overloads both match an `async def`; four checkers pick the first and ty the second, giving `CoroutineType[Any, Any, str]` | `pending: Awaitable[str] = handler('n')` |

The repository corpus carries exactly one existing offender:
`tests/typing/test_conformance.py:82`,
`assert_type(handler(label='n'), Awaitable[str])`. It is rewritten as a witness.
`tests/typing/test_conformance.py:304` also draws a ty `no-matching-overload`;
the implementation classifies it under the proposal's taxonomy before changing
anything, and the plan carries that as an explicit task rather than a
presumption.

The enum form `assert_type(Scope.SINGLETON, Scope)` is not present in the
repository and must not be introduced; every checker narrows a member access to
its literal member type.

### What `tests/typing/` keeps, and what moves

`tests/typing/` stays. It is the fast in-checkout aid the proposal describes and
it runs under the two Layer 1 checkers on every commit, which the conformance
suite deliberately does not.

One thing moves out of it. `tests/typing/test_conformance.py:304` is the
repository's only negative typing assertion and it is expressed as
`# type: ignore[arg-type]  # pyright: ignore[reportArgumentType]`. That spelling
cannot survive a five-checker world twice over: ty honours neither half, and
mypy's `warn_unused_ignores` — implied by `strict` — turns the assertion into a
gate failure the moment any checker stops reporting the error it guards, which
is the opposite of what a negative fixture should do. Negatives move to
`conformance/negative/`, where the expected diagnostic is data in
`expected/negative.toml` rather than a comment in the code under test.

The gaps the existing corpus leaves are what `conformance/corpus/` has to close.
It exercises `singleton()` but not `scoped()` or `transient()`; it does not
touch `Registry` or its `|`, `Named`, `Tag`, `Bindings`, `Condition` in
annotation position, `Host.activated()`, `close`/`aclose`,
`awarmup`/`ahealth`, `Container(*sources)`/`include`, or `scope_value`; and of
the twelve `depin/ext/` modules it covers `fastapi.Inject` and the two pytest
protocols only. Ten of the twelve have no typing coverage at all today.

The two pytest protocols are covered in a way worth naming, because the corpus
must not repeat it: the assertions are made against the declared
`OverrideFactory` parameter, never against the real fixture. Whether the actual
`depin_override` — whose value is `FrozenContainer.override`'s
`_GeneratorContextManager` — satisfies the protocol it advertises is asserted
nowhere. The corpus binds the real fixture to the protocol and checks that the
widening holds.

### Anti-erasure

`assert_type` and witnesses both fail on `Any` in the direction that matters,
but neither is sufficient alone, because `Any` satisfies an assignment in both
directions. Two checker-native rules carry the requirement:

- Basedpyright with `reportAny` and `reportExplicitAny` at error, over the
  positive corpus.
- mypy with `--disallow-any-expr`, over `corpus/core/` only.

`--disallow-any-expr` is unusable in all-extras mode — third-party annotations
produce `Any` expressions the corpus does not own — so it is scoped to the
core-only run, where it is meaningful. ty cannot express an anti-`Any` rule at
all; that requirement is Basedpyright's and mypy's, and the support policy says
so rather than implying five-way coverage of it.

## Negative fixtures

One misuse per file, no suppressions, run one file at a time so an unrelated
diagnostic cannot make a fixture pass by accident.

`conformance/expected/negative.toml` records, per fixture and per checker, the
**line** and the **rule identifier** — never message text:

```toml
[n01]
misuse = "resolve() called with a value that is not a key"
line = 12
mypy = "arg-type"
pyright = "reportArgumentType"
basedpyright = "reportArgumentType"
ty = "invalid-argument-type"
pyrefly = "bad-argument-type"
```

The harness requires a non-zero exit and at least one diagnostic on the recorded
line carrying the recorded identifier.

Message snapshots are excluded on measured grounds. For the same `Inject[T]`
misuse the three checkers that name a type name three different ones, and ty
printed both sides of one disagreement identically —
``Type `() -> Cache` does not match asserted type `() -> Cache` ``. A harness
matching on rendered text would be brittle where it is not simply useless.

### The divergence register

Two false negatives in the public API were found by the baseline and are
**routed to Step 8**, which is the last window before the freeze:

- `FrozenContainer.override(Config, Other())` — accepted by all five. No change
  to `Token` reaches it: `type[T]` is covariant by construction in the spec, and
  the measured alternative `override[T](key).using(replacement)` changes the
  call shape.
- `Container.value(Token[int], 'str')` — accepted by four. Pyrefly rejects it,
  and does so precisely because it reads `T` as invariant, which is why four of
  the eight measured remedies would have destroyed the signal. Its repair is
  R5, which changes no call site; it is deferred because the roadmap chose R4
  over R5, not because it is expensive.

They cannot be negative fixtures, because a fixture every checker accepts gates
nothing. They become `conformance/divergence/`, whose contract is the inverse:
`expected/divergence.toml` records the accept/reject verdict of each checker
today, and the harness fails when a verdict changes in either direction. A
checker that starts rejecting one is news the project wants; a checker that
stops is a regression. Step 8 moves them into `negative/` when the API is
repaired.

## Native configuration

Each checker gets an explicit configuration. None may read another's.

| Checker | Consumer config | Source config | Setting |
| --- | --- | --- | --- |
| mypy | CLI | `[tool.mypy]` (unchanged) | `--strict --warn-unreachable`, plus `--disallow-any-expr` in core-only mode |
| stock Pyright | `config/pyright.json` | **`config/pyright-source.json`**, passed with `-p` | `typeCheckingMode: "strict"`, `useLibraryCodeForTypes: false`, `reportMissingTypeStubs: true` |
| Basedpyright | `config/basedpyright.json` | `[tool.basedpyright]` (unchanged) | as above plus `reportImplicitOverride`, and `reportAny`/`reportExplicitAny` on the anti-erasure pass |
| ty | `config/ty.toml` | `[tool.ty.src]` (unchanged) | `--error all`; ty has no strict mode or preset system |
| Pyrefly | `config/pyrefly.toml` | **new `pyrefly.toml`** | `--preset strict` |

`useLibraryCodeForTypes: false` on the consumer runs is deliberate: it forces
both Pyright engines to rely on the wheel's inline annotations behind `py.typed`
rather than inferring from library code, which is the property the contract
claims.

Three configuration traps are confirmed and the implementation must avoid all
three:

- **Stock Pyright drops an absolute path in `include`** — it prints
  `Ignoring path "…" in "include" array because it is not relative`, then reports
  zero having checked nothing. Paths are relative to the config file, or passed
  on the command line.
- **`pythonPath` is not a stock-Pyright key.** It prints
  `Config contains unrecognized setting "pythonPath"` and continues.
  `venvPath` + `venv` is the working form.
- **An unconfigured Pyrefly uses the `basic` preset**, which does not report
  `bad-argument-type` at all. A green unconfigured Pyrefly run is not evidence.

Two guards catch the first two, which both produce a green run over an empty
file set: the runner asserts a **non-zero checked-file count** for every checker
that reports one, and asserts that stock Pyright's count matches mypy's.

**Stock Pyright's source configuration cannot live in `pyproject.toml`.** The
obvious placement, a `[tool.pyright]` table beside the existing
`[tool.basedpyright]`, breaks the repository's own commit gate:

```
$ uv run basedpyright        # pyproject.toml carrying both tables
Pyproject file parse attempt 1 Error: Pyproject file cannot have both `pyright`
and `basedpyright` sections. pick one
Config file ".../pyproject.toml" could not be parsed. Verify that format is correct.
exit=3
```

Basedpyright 1.39.10 — the pinned version — discards the whole file, losing
`include`, `typeCheckingMode` and `reportImplicitOverride`, and degrades to its
defaults over the working directory. Stock Pyright 1.1.411 tolerates both
tables; only Basedpyright refuses.

So the stock-Pyright source configuration is a named file,
`conformance/config/pyright-source.json`, passed explicitly with `-p`. AGENTS.md
bans reintroducing a root `pyrightconfig.json`, which Pyright discovers
implicitly; a named file passed on the command line is a different object and
does not compete with `[tool.basedpyright]` for discovery.

Pyrefly has no `pyproject.toml` table, so its source configuration is a
top-level `pyrefly.toml`.

## Wheel isolation

Four assertions, run by the harness before any checking:

1. **`RECORD` membership.** `depin/py.typed` appears in
   `pydepin-*.dist-info/RECORD`, read from the zip's central directory. A
   `namelist()` check alone would miss a wheel whose RECORD and payload
   disagree.
2. **`direct_url.json` carries `archive_info`**, not
   `dir_info: {"editable": true}`, and no `__editable__*.pth` exists in
   `site-packages`.
3. **`depin.__file__` is inside the venv** and the checkout is absent from
   `sys.path`.
4. **The empty-venv control.** The identical command line, from the identical
   working directory, against an interpreter with no `depin`, must produce an
   unresolved-import diagnostic from every checker:
   mypy `import-not-found`, Pyright and Basedpyright `reportMissingImports`,
   ty `unresolved-import`, Pyrefly `missing-import`.

The fourth is the decisive one, and the measurement above is why: it is a
positive assertion about behaviour rather than an enumeration of the variables
that could leak, so it catches a stray `.pth`, an `extraPaths` entry, a
`conftest.py`, a `MYPYPATH`, or a working directory, regardless of how it
arrived.

Which forces the runner's shape. It is invoked from the checkout — it has to be,
to be reachable as `uv run python -m scripts.conformance`, and in CI the
checkout is the default working directory. So the guard cannot be on the runner
process. Instead the runner **copies `conformance/` into a temporary directory
outside the checkout** and runs every checker subprocess with that directory as
its working directory, asserting for each subprocess that the checkout is not
the working directory and not an ancestor of it. The corpus is checked where the
baseline checked it — somewhere that has never heard of the source tree — and
the empty-interpreter control runs the identical command lines from the identical
directory, which is what makes it a control rather than a formality.

## The `Token` remedy: R4

`depin/_core/markers.py` gains a non-generic `TokenKey` carrying
`__slots__ = ('name',)`, `__init__`, `__repr__`, `__eq__` and `__hash__`.
`Token[T]` becomes `class Token[T](TokenKey)` with `__slots__ = ()`, stays
`@final`, and keeps its hash seed `'depin.Token'` so equality and hashing are
byte-compatible with 0.16. `__eq__` narrows on `TokenKey`.

All nine `Token[object]` annotation positions become `TokenKey`:
`spec.ProviderKey`, `spec.FrameBinding.key`, `markers.Named.key`,
`markers._InjectMarker.key`, the `AnnotatedMeta.token` and `.named` fields,
their two mirrors as locals in `extract_annotated_meta`, and the `TypeGuard` on
`is_object_token` — which is renamed `is_token_key`, since it is private and the
old name would now describe the wrong thing.

`is_token_key` narrows with `isinstance(value, TokenKey)`, not
`isinstance(value, Token)`. Checking the narrower class while narrowing to the
wider one would be sound but would make a consumer's `TokenKey` subclass behave
as a key statically and not at runtime.

**The same correction is due one module over, and the `Token[object]` grep does
not find it.** `depin/_core/typeguards.py` carries the runtime guard behind the
`ProviderKey` alias:

```python
def is_provider_key(value: object) -> TypeGuard[ProviderKey]:
    return isinstance(value, type | str | Token | Underlying) or is_generic_key(value)
```

Once `ProviderKey` admits `TokenKey`, this guard promises `TokenKey` while
admitting only `Token`, and it gates `FrozenContainer.explain`,
`DependencyGraph.find` and `DependencyGraph.node`. Its `isinstance` becomes
`type | str | TokenKey | Underlying`. The variance experiment's measured R4 diff
touched three modules and not this one, which is why the omission survived to
here.

### `TokenKey` is exported

`TokenKey` appears inside the public `ProviderKey` alias. A consumer who
annotates against `ProviderKey` and reads a diagnostic naming `TokenKey` must be
able to import it, so it joins `depin.__all__` with the docstring the public API
requires and a reference page.

Its docstring must not claim it is "not an extension point". `TokenKey` cannot
be `@final` — `Token` inherits it — and `__eq__` and `is_token_key` both narrow
on it, so a consumer's subclass really would compare equal to a `Token` of the
same name and really would flow through `extract_annotated_meta` as a key. A
docstring asserting a constraint the code does not enforce fails AGENTS.md's
rule that every statement be verifiable.

So it says the true thing instead: `Token` is the only implementation depin
provides, subclassing is unsupported, and the runtime will treat a subclass as a
key. Step 8 decides whether to seal it with `__init_subclass__` and whether it
stays exported at all — and because `TokenKey` is new in 0.17.0, sealing later
can only break code written against a type documented as unsupported.

`__all__` grows from 28 to 29. That is a symbol Step 8's surface review has to
justify, and the alternative — a public alias naming an unimportable type — is
worse.

### What R4 does not do

It does not repair `Container.value(Token[int], 'str')`. Under R4 `T` stays
phantom, so Pyrefly continues to catch that call and the other four continue to
miss it. That is the baseline's state, not a regression, and it is recorded in
`conformance/divergence/` and routed to Step 8.

## The `provides=` repair

Two public symbols are spelled `provides`, and only one is defective.

The **`provides()` decorator** annotates `abstract: type[object]` and rejects a
token both statically and at runtime, where `_reject_invalid_key` raises
`InvalidProviderError` for anything that is not a class or a parameterised
generic. That is deliberate and stays as it is. Widening the annotation without
the runtime would make the checker promise something the library then refuses.

The **`provides=` keyword** is the defect. It is annotated
`type[object] | None` in thirteen places in `depin/_core/bindings.py` — the
seven `bind` overloads, the `bind` implementation, `singleton`, `scoped`,
`transient`, `ScopeDecorator.__init__` and `_record_bind` — and is backed by
three more declarations: the `_BindFn` alias in the same module,
`BindRecord.provides` in `spec.py`, and `_resolve_key`'s `explicit` parameter in
`providers.py`. The runtime already accepts a token: `_resolve_key` passes
`explicit` straight to `as_provider_key`, which admits everything `ProviderKey`
admits bar `Underlying`. Only the annotation refuses it.

Measured on the current tree, the rejection cascades:

```
error: Argument of type "Token[Store]" cannot be assigned to parameter "provides"
  of type "type[object] | None" in function "bind" (reportArgumentType)
error: No overloads for "bind" match the provided arguments (reportCallIssue)
error: Type of "di" is unknown (reportUnknownVariableType)
... 7 errors, 0 warnings, 0 notes
```

One bad argument poisons the chain to `Unknown`, so this single defect produces
seven strict-mode diagnostics in a five-line consumer program that runs
correctly.

The sixteen positions are widened to what the position actually accepts, which
is measured rather than assumed. `provides=42` raises `InvalidProviderError`;
`provides='some-key'` **succeeds today** and resolves the binding, because
`as_provider_key` admits a string key. Of the five members of `ProviderKey`,
`Underlying` is the only one it rejects.

So the spelling is `type[object] | TokenKey | str | None`. Widening to
`ProviderKey` itself would additionally promise `Underlying`, which raises;
stopping at `type[object] | TokenKey | None` would keep refusing a string the
library has always accepted, and the rule this design applies — annotate what
the position accepts — does not admit an exception for the member nobody
noticed.

**The two changes must land in the same commit.** Written against
`Token[object]` the repair works under the four checkers that infer the phantom
parameter covariant and fails under Pyrefly, which does not — it would depend on
precisely the variance R4 exists to stop depending on.

The pull request carrying both is a `feat:`, not a `fix:`. It adds `TokenKey` to
the public API, and 0.17.0 is the target; a `fix:` would cut 0.16.4.

## Version policy

### What is pinned, and where

`conformance/checkers.toml` declares the exact version of each of the five, and
both CI and the local runner read it. Nothing else names a version.

```toml
[targets]
python = "3.12"
os = "linux"

[checkers]
mypy = "2.3.1"
pyright = "1.1.411"
basedpyright = "1.39.10"
ty = "0.0.77"
pyrefly = "1.2.0"
```

The language target belongs in the file, not only in CI YAML and prose: the
proposal's criterion is that "checker versions **and Python language targets**
are recorded reproducibly", and a local run must reproduce the gate exactly.

All five are invoked through `uvx <tool>@<version>`. ty and Pyrefly stay out of
`uv.lock` and out of every contributor's environment for the reason the existing
CI comment gives: a 0.0.x tool with no stable API has no business there. mypy
and Basedpyright remain in the `dev` group as well, because they are also the
Layer 1 gates run by `uv run`; the runner asserts that the pinned conformance
version equals the one `uv.lock` resolves, so the two cannot drift apart
silently. Comparing against the declared floor instead would be useless: `dev`
declares `mypy>=1.18`, so every future resolution satisfies it while `uv run
mypy` and `uvx mypy@2.3.1` diverge — and the repository takes weekly Dependabot
updates, so that divergence is scheduled rather than hypothetical.

### Minimum supported and current tested

The project has measured exactly one version of each checker. Declaring a lower
minimum would be a support claim with no evidence behind it, which the proposal
forbids. So the initial policy sets **minimum supported = current tested** for
all five, and states the rule for advancing:

This defers, rather than answers, the proposal's request to "evaluate testing
both the oldest supported version and the current supported version" for the
stable lines. Naming an older minimum today would be a support claim with
nothing behind it; the forward job's previous-release probe is what will build
the evidence to lower one honestly. The deferral is recorded here so a later
reader does not mistake it for a decision that the question does not apply.

- The **current tested** version advances by a pull request that shows the whole
  suite green on the new version. It is never advanced automatically.
- The **minimum supported** version advances when the current tested one does,
  unless a lower version has been measured green by the forward job and recorded.
- A version is dropped when its line is superseded and no measurement is retained
  for it.

The forward job builds the evidence that would let a minimum be lowered later,
by probing one release behind for the three stable lines.

### Forward detection

A weekly scheduled `typing-forward` job resolves the newest release of each of
the five and runs the complete suite against it, in both install modes, and
additionally at the 3.13 and 3.14 language targets. It is advisory: an upstream
release is not a merge blocker.

It is not silent. On failure it opens or updates one tracking issue per checker,
titled for the checker and version, carrying the diagnostics. It never edits
`checkers.toml`. Before a release, the release checklist requires reviewing the
open forward issues and choosing one of three outcomes the proposal names: make
the new release green, retain and document the supported ceiling, or document a
verified upstream blocker.

The Pyrefly variance-inference divergence is exactly such a blocker and is
reported upstream with the nine-line reproducer the baseline isolated, which
imports nothing from `depin`. The support policy links the issue.

## CI

Per pull request, three new job definitions replacing the current
`ty (advisory)` job. They expand through their matrices to nine job instances.

| Job | Matrix | Blocking | What it does |
| --- | --- | --- | --- |
| `typing-artifact` | — | yes | Builds the wheel once, asserts `RECORD` carries `depin/py.typed`, asserts the metadata, uploads it for the other jobs |
| `typing-consumer` | mypy, pyright, basedpyright, ty, pyrefly | yes | Downloads the wheel, builds the core-only, all-extras and empty venvs, runs the positive corpus in both modes at zero, the negative fixtures, the divergence register, and the four isolation assertions |
| `typing-source` | pyright, ty, pyrefly | yes | Full-source check: stock Pyright at zero, ty and Pyrefly against their registers |

Five consumer jobs rather than one, so the PR check list names the checker that
broke without a reviewer opening a log. That choice already pays the venv
creation five times over, so splitting the two install modes as well would be
the wrong economy: each job creates its three interpreters once and checks both
modes inside them.

**One Python target per pull request: 3.12.** The baseline measured
byte-identical results at 3.12, 3.13 and 3.14 for all five checkers in both
install modes; a per-PR target matrix would triple the job count and buy
nothing. The targets are not abandoned — `typing-forward` runs them weekly as a
regression detector, which is the honest place for a check whose last three
measurements were identical.

**One operating system per pull request: Linux.** The ordinary `checks` matrix
runs Windows and macOS at the floor version, and it is the right place for
runtime behaviour. What a checker infers from a wheel does not vary by host —
but two things the isolation guard rests on do: path-ancestry comparison and
`.pth` discovery in `site-packages`. `typing-forward` runs the full suite on all
three hosts weekly, so a platform-specific break in the guard surfaces without
tripling the per-PR cost. If it ever fires, the guard moves to the per-PR
matrix.

The baseline's ~50 s of checker time sizes this but understates it: that figure
covers the positive corpus alone. The jobs also run the negative fixtures one
file at a time, the divergence fixtures, the empty-interpreter control for all
five, and two separate anti-erasure passes, on top of one wheel build and three
interpreters per job. The shape is affordable; the number is a floor, not an
estimate.

## Contributor experience

- `uv run python -m scripts.conformance` runs everything and prints a per-checker,
  per-mode table.
- `--checker ty`, `--mode core`, `--only negative` narrow it for a focused loop.
- `CONTRIBUTING.md` gains a section describing the layer model and the command;
  the five gates are unchanged, because the conformance suite needs a built
  wheel and does not belong in a per-commit loop.
- The pull request template gains one line for the conformance suite, phrased so
  it is clear it is a CI gate rather than a sixth local gate.
- `docs/support-policy.md` replaces its "Type checkers" section with the matrix,
  the pinned versions, the anti-`Any` assignment, the two documented false
  negatives, and the Pyrefly upstream link.

`scripts/` is currently outside `[tool.mypy] files` and
`[tool.basedpyright] include`, so `scripts/conformance.py` would ship unchecked.
The implementation adds `scripts` to both include lists. If
`scripts/check_mutation_threshold.py` proves not to be clean under strict mode,
that is a defect to fix, not a reason to leave the new runner unchecked.

## Verification

### Fault injection

The proposal requires evidence that the suite is sensitive. Each case is applied,
measured, and reverted; the evidence report records the command and the output.

| Injection | Must fail |
| --- | --- |
| `FrozenContainer.resolve` return widened to `object` | all five `typing-consumer` jobs |
| `Inject[T]` loses its parameter | the all-extras mode of all five |
| `depin/py.typed` removed from the wheel build | `typing-artifact`, and the empty-venv-shaped `Any` cascade in all five |
| R4 reverted (`TokenKey` removed) | Pyrefly's `typing-consumer` job, with six `bad-argument-type`/`bad-return` |
| the runner made to check the corpus in place instead of the copied directory | the per-subprocess working-directory assertion, before any checking |
| one negative fixture's misuse rewritten as valid code | the negative harness, for a missing expected rejection |
| a new name added to `depin.__all__` | `tests/unit/test_conformance_coverage.py` |
| a diagnostic added to a file in the ty register | `typing-source`, as an unregistered diagnostic |

The fourth case is the one that proves R4 is load-bearing rather than
decorative. The fifth is the one the new measurement in this document made
necessary.

### Ordinary gates

The five commit gates, the mutation gate at its 95% floor — R4 touches
`depin/_core/`, so it runs — coverage at or above 95% measured with
`coverage run -m pytest`, `mkdocs build --strict`, and the `minimum declared
versions` job, run before the pull request opens.

## Acceptance criteria

- [ ] A wheel-built, isolated consumer suite is a required CI gate.
- [ ] All five checkers pass the positive corpus with **zero** diagnostics, in
      both install modes.
- [ ] Every exact-inference promise is asserted with `assert_type`; every
      assignability promise with a typed witness; each classified in
      `coverage.toml`.
- [ ] Every negative fixture is rejected by all five for the recorded rule
      identifier, with no message-text matching.
- [ ] The two documented false negatives are in `divergence/` with per-checker
      verdicts, and routed to Step 8 in the roadmap.
- [ ] `Any`/unknown leakage is detected by Basedpyright's `reportAny` and mypy's
      `--disallow-any-expr`, and the policy names them rather than implying
      five-way coverage.
- [ ] Core and FastAPI — and the other seven extras — are covered without a
      runtime dependency reaching the core; core-only mode asserts the ext
      modules are unresolvable.
- [ ] The wheel is proven to carry `depin/py.typed` via `RECORD`, and the
      consumer is proven to import from it via `direct_url.json` and the
      empty-venv control.
- [ ] Stock Pyright runs independently of Basedpyright, at both layers.
- [ ] ty and Pyrefly propagate a real exit status; no job ends in `exit 0`.
- [ ] No positive fixture carries a checker-specific suppression.
- [ ] Every public symbol has a coverage decision, enforced by a unit test.
- [ ] `CONTRIBUTING.md`, the PR template and `docs/support-policy.md` describe
      the matrix CI enforces.
- [ ] Checker versions live in one file that CI and the local runner both read.
- [ ] Fault injection shows every gate failing when the behaviour it guards
      regresses.
- [ ] The ordinary repository gates stay green.

## Out of scope

Routed to **Step 8**, where the API may still change:

- `FrozenContainer.override(Config, Other())` and
  `Container.value(Token[int], 'str')`. `override`'s measured repair changes
  the call shape to `override[T](key).using(replacement)`. `value`'s does not:
  its measured repair is R5, which adds a member to `Token` and leaves every
  call site alone. It is deferred because the roadmap took R4 over R5 at
  `2816b09`, not because it breaks API — saying otherwise would contradict the
  evidence this design cites.
- Whether `TokenKey` stays exported, and whether it is sealed against
  subclassing.

Routed to **Step 7**: everything about performance. The conformance suite is
timed only to size the CI budget.

Not undertaken: separate `.pyi` stubs, checker-identical diagnostic wording, and
any support claim for a checker version the project has not measured.
