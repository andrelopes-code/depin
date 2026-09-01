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
| What does the full matrix cost? | ~50 s of checker time for 5 checkers × 2 install modes, cold. | baseline E.4 |
| Is wheel isolation provable portably? | Yes — run the identical commands against an empty venv and require an unresolved-import diagnostic from each. | baseline A.7 |
| Why does Pyrefly reject `Token[int]` where a key is expected? | `Token[T]`'s parameter is phantom; the typing spec's variance-inference algorithm tests covariance first and a phantom parameter passes it. Pyrefly 1.2.0 infers invariance. Four checkers conform, Pyrefly does not. | variance A |
| Which remedy? | **R4** — a non-generic supertype in the `Token[object]` positions. Clears Pyrefly to zero on the consumer corpus, `T` stays phantom, no new member on `Token`. | roadmap Step 6, `2816b09` |
| Why not R5? | Its `payload` member exists only to pin variance, its shape was dictated by `reportUnusedFunction`, and the false negative it repairs is a side effect of invariance rather than a designed constraint. | roadmap Step 6 |
| Why is stock Pyright not a Basedpyright result? | Basedpyright 1.39.10 is built on pyright 1.1.412; the newest stock Pyright is 1.1.411. Different engine commits, different rule sets. | baseline A.1 |
| Can an unconfigured Pyrefly be trusted? | No. Its default preset is `basic`, which does not report `bad-argument-type` at all. | baseline A.4 |
| What breaks ty on the current corpus? | Suppression spelling. ty honours a bare `# type: ignore` and `# ty: ignore[...]`, but not `# type: ignore[code]` or `# pyright: ignore[...]`; the repository writes every intentional negative with the pair ty cannot read. 25 of its 32 source diagnostics are that. | baseline A.6, B.4 |

## Corrections to the inputs

Three counts in the source documents do not survive checking. This design uses
the corrected values.

**Nine `Token[object]` annotation positions, not eight.** The roadmap and the
variance experiment both say eight. `depin/_core/spec.py` carries two,
`depin/_core/markers.py` two, and `depin/_core/introspect.py` five — two
`AnnotatedMeta` fields, their two mirrors as locals in `extract_annotated_meta`,
and the `TypeGuard` on `is_object_token`. A tenth mention, the docstring on
`is_object_token`, is prose. All nine annotations are converted.

**Five assignability categories, not three.** The baseline introduces its list
as "three further categories" and then enumerates five. All five are binding.

**The consumer corpus is 21 files.** The baseline's timing table says 13; that
figure counts the positive corpus only and times the eight negative fixtures
separately, because they are run one file at a time.

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

mypy, stock Pyright and Basedpyright are unaffected by the appended comment.
This is what lets ty's source count fall from 32 to the handful that are
genuinely upstream, rather than being managed as a baseline of spelling
artefacts.

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
`conformance/expected/pyrefly-source.txt`, each line a `file:rule` pair with a
one-line classification. The job fails when a diagnostic appears that the
register does not carry, and fails when the register carries one that no longer
appears. The first is a regression; the second means the register should shrink.
It is never falsely red, and it never silently accepts a new defect.

This replaces the current `ty (advisory)` job, whose check step ends in `exit 0`
and therefore establishes nothing. The register is what makes ty and Pyrefly
blocking without demanding a zero the project does not control.

The registers are small because the suppression spelling is repaired first. Of
ty's 32: 25 are lines already suppressed for mypy and Pyright, and gain the ty
spelling; one is `tests/typing/test_conformance.py:82`, removed by the oracle
rewrite; the remaining six are two `call-top-callable`/`invalid-return-type`
pairs from ty's gradual model of `Callable[..., object]` and four from ty
resolving `taskiq.TaskiqResult` through pydantic's `PydanticRecursiveRef`.
Those six enter the register with their classification. Pyrefly's three —
two `implicit-any-lambda`, one `implicit-any-type-argument`, all in private code
— enter theirs.

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
    ext/e01_fastapi.py … e04_frameworks.py
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

`corpus/core/` is checked in both install modes. Four modules under `depin/ext/`
import no third-party package at all — `ext/__init__`, `ext/asgi`, `ext/wsgi`
and `ext/cli` — and those are the generic seams the framework modules
specialise, carrying the bounded `RequestScope[ScopeT: ASGIScope, …]`,
`RequestScope[EnvironT, StartResponseT]`, `install[C: CommandContext]` and
`CommandContext.with_resource[T]`. They are checked in **both** modes, against a
consumer's own structural scope and context types.

The eight modules that do require an extra are checked in all-extras mode only.
In core-only mode the runner asserts each of those eight is *unresolvable*,
which is what proves the core carries no framework dependency.

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
fails when a name has no entry. It reads `depin.__all__` directly for the core.
For `depin/ext/` it parses each module with `ast` rather than importing it,
because `tests/unit/` runs on the free-threaded and pre-release jobs where no
framework is installed — the same technique `tests/unit/test_integration_contract.py`
already uses.

This is the mechanism the proposal asks for: a new public symbol cannot land
without an explicit type-test decision, because the unit gate fails until it has
one.

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
protocols only. Nine ext modules have no typing coverage at all today.

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
**routed to Step 8**, because both repairs break API and Step 8 is the last
window before the freeze:

- `FrozenContainer.override(Config, Other())` — accepted by all five. No change
  to `Token` reaches it: `type[T]` is covariant by construction in the spec, and
  the measured alternative `override[T](key).using(replacement)` changes the
  call shape.
- `Container.value(Token[int], 'str')` — accepted by four. Pyrefly rejects it,
  and does so precisely because it reads `T` as invariant, which is why four of
  the eight measured remedies would have destroyed the signal.

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
| stock Pyright | `config/pyright.json` | **new `[tool.pyright]`** | `typeCheckingMode: "strict"`, `useLibraryCodeForTypes: false`, `reportMissingTypeStubs: true` |
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

AGENTS.md forbids reintroducing `pyrightconfig.json`; it does not forbid a
`[tool.pyright]` table, and that is where the stock-Pyright source configuration
goes. The implementation must confirm that Basedpyright still prefers
`[tool.basedpyright]` when both tables are present, and the plan carries that as
a verification step rather than an assumption.

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
arrived. The runner therefore **runs every checker from the consumer directory**
and refuses to start if its own working directory is inside the checkout.

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

### `TokenKey` is exported

`TokenKey` appears inside the public `ProviderKey` alias. A consumer who
annotates against `ProviderKey` and reads a diagnostic naming `TokenKey` must be
able to import it, so it joins `depin.__all__` with the docstring the public API
requires and a reference page. Its docstring states that `Token` is its only
intended implementation; it is not an extension point, and Step 8 decides
whether to seal it.

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

The sixteen positions are widened to admit a token. The widening is **not** to
`ProviderKey`: that alias also admits `str` and `Underlying`, and
`as_provider_key` raises on the latter. The narrowest change that matches what
the position actually accepts is the two-member union.

**The spelling is the R4 one, `type[object] | TokenKey | None`, and the two
changes must land in the same commit.** Written against `Token[object]` the
repair works under the four checkers that infer the phantom parameter covariant
and fails under Pyrefly, which does not — it would depend on precisely the
variance R4 exists to stop depending on. The repair is a `fix:`; it changes what
a consumer can write.

## Version policy

### What is pinned, and where

`conformance/checkers.toml` declares the exact version of each of the five, and
both CI and the local runner read it. Nothing else names a version.

```toml
[checkers]
mypy = "2.3.1"
pyright = "1.1.411"
basedpyright = "1.39.10"
ty = "0.0.77"
pyrefly = "1.2.0"
```

All five are invoked through `uvx <tool>@<version>`. ty and Pyrefly stay out of
`uv.lock` and out of every contributor's environment for the reason the existing
CI comment gives: a 0.0.x tool with no stable API has no business there. mypy
and Basedpyright remain in the `dev` group as well, because they are also the
Layer 1 gates run by `uv run`; the runner asserts that the pinned conformance
version satisfies the `dev` floor, so the two cannot drift apart silently.

### Minimum supported and current tested

The project has measured exactly one version of each checker. Declaring a lower
minimum would be a support claim with no evidence behind it, which the proposal
forbids. So the initial policy sets **minimum supported = current tested** for
all five, and states the rule for advancing:

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

Per pull request, six new jobs replacing the current `ty (advisory)` job.

| Job | Matrix | Blocking | What it does |
| --- | --- | --- | --- |
| `typing-artifact` | — | yes | Builds the wheel once, asserts `RECORD` carries `depin/py.typed`, asserts the metadata, uploads it for the other jobs |
| `typing-consumer` | mypy, pyright, basedpyright, ty, pyrefly | yes | Downloads the wheel, builds the core-only, all-extras and empty venvs, runs the positive corpus in both modes at zero, the negative fixtures, the divergence register, and the four isolation assertions |
| `typing-source` | pyright, ty, pyrefly | yes | Full-source check: stock Pyright at zero, ty and Pyrefly against their registers |

Five consumer jobs rather than one, so the PR check list names the checker that
broke without a reviewer opening a log. Both install modes inside each job,
because the wheel build and the venv creation dominate and splitting them would
double that cost for no added signal.

**One Python target per pull request: 3.12.** The baseline measured
byte-identical results at 3.12, 3.13 and 3.14 for all five checkers in both
install modes; a per-PR target matrix would triple the job count and buy
nothing. The targets are not abandoned — `typing-forward` runs them weekly as a
regression detector, which is the honest place for a check whose last three
measurements were identical.

The measured cost supports the shape: ~50 s of checker time for five checkers
across two install modes, of which mypy's cold start on a small corpus is the
largest single term, plus one wheel build and the venv creation.

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
| the runner invoked from the repository root | the isolation guard, before any checking |
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
  `Container.value(Token[int], 'str')` — both repairs break call shapes.
- Whether `TokenKey` stays exported, and whether it is sealed against
  subclassing.

Routed to **Step 7**: everything about performance. The conformance suite is
timed only to size the CI budget.

Not undertaken: separate `.pyi` stubs, checker-identical diagnostic wording, and
any support claim for a checker version the project has not measured.
