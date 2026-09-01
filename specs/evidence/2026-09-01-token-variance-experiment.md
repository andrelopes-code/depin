# `Token[T]` phantom-variance remedy experiment

Decision experiment for the open question left by
`specs/evidence/2026-09-01-consumer-typing-baseline.md`, Disagreement 1 and
section E.6.1: `depin._core.markers.Token[T]` declares a phantom type parameter;
Pyrefly 1.2.0 infers it invariant where mypy, stock Pyright, Basedpyright and ty
infer it covariant, and the divergence costs 6 consumer-visible diagnostics.

Date measured: 2026-09-01
Worktree: `/home/dreco/dev/depin/.claude/worktrees/agent-a3ea7bca7a3dae9f6`,
branch `fix-threads-timeout`, HEAD `3b65ef6`
Distribution version measured: `pydepin 0.16.3`
Checkers: mypy 2.3.1, pyright 1.1.411, basedpyright 1.39.10, ty 0.0.77,
pyrefly 1.2.0 — the same five versions the baseline pinned.

Nothing was committed. The working tree carries the recommended remedy (R5);
the exact diff is listed under *Repository state*.

---

# A. What the typing spec actually requires

`https://typing.python.org/en/latest/spec/generics.html#variance-inference`,
step 3 of the auto-variance algorithm:

> Determine whether `lower` can be assigned to `upper` using normal
> assignability rules. If so, the target type parameter is **covariant**. If
> not, determine whether `upper` can be assigned to `lower`. If so, the target
> type parameter is contravariant. If neither of these combinations are
> assignable, the target type parameter is invariant.

For a phantom parameter, `upper = Token[object]` and `lower = Token[T]` have
byte-identical member sets, so `lower` **is** assignable to `upper` and the
first test succeeds. Covariance is the spec-mandated answer, and it is tested
first. mypy, Pyright, Basedpyright and ty conform. **Pyrefly 1.2.0 does not.**
This is a conformance defect upstream, not an under-specified corner.

PEP 695, *Rejected Ideas → Explicit Variance*:

> We considered adding syntax for specifying whether a type parameter is
> intended to be invariant, covariant, or contravariant. […] We rejected this
> idea because variance can generally be inferred […]

**There is therefore no PEP 695 spelling that pins variance.** `infer_variance`
exists only on the legacy `TypeVar` constructor, and PEP 695 states that
parameters allocated with the new syntax "always have `__infer_variance__` set
to `True`" — the new syntax is *permanently* on the inference path. The only
declaration-level lever left is the class body itself.

PEP 696 type-parameter defaults (`class Token[T = object]`) were tested and are
irrelevant twice over: they do not touch variance, and they are a syntax error
on the project's 3.12 floor (measured in C.1).

---

# B. Method

## B.1 Reused artifacts

`/tmp/typing-baseline/` from the baseline run was intact and was reused
unchanged: the 21-file / 1062-line consumer corpus (`consumer/core`,
`consumer/ext`, `consumer/neg`), the three venvs (`.venv-core`, `.venv-extras`,
`.venv-empty`), and all ten per-checker config files. Nothing was rebuilt.

Three scripts were added under `/tmp/typing-baseline/remedy/`:

- `build-install.sh <name>` — `uv build` from the worktree into
  `dist/<name>/`, then `uv pip install --no-deps --force-reinstall` into both
  consumer venvs, printing the wheel's SHA-256 prefix and the SHA-256 prefix of
  the **installed** `markers.py`, `spec.py` and `bindings.py`.
- `run-all.sh` — the baseline's `run-positives.sh` (core-only and extras modes,
  five checkers) concatenated with the `n03` / `n05` negative fixtures.
- `run-repo.sh` — the AGENTS.md commit gate (`ruff check`, `basedpyright`,
  `mypy`, `pytest`) plus stock Pyright, ty and Pyrefly over
  `depin tests examples`.

## B.2 Wheel-staleness proof

Every remedy produced a distinct wheel. The version string never changes
(`0.16.3`), so the hashes are the only evidence that matters:

```
1d9d07dc007a0340  R0   (unmodified source)
b231702cc13eda95  R1   TYPE_CHECKING method returning T
81c0da81cb64f67f  R1b  TYPE_CHECKING property returning T
3611e973f5ced7d4  R1d  TYPE_CHECKING bare attribute `_payload: T`
cc8ad014ad96931b  R2   legacy TypeVar('T_co', covariant=True)
a0e3717bd4959551  R3   ProviderKey widened to a structural Protocol
9bbf6d199c4fd313  R4   non-generic base class TokenKey
3c2d53c67d6a3272  R5   R4 + a real invariant use site
3c2d53c67d6a3272  R5v  R5 rebuilt from scratch — byte-identical, reproducible
```

R5 was rebuilt after a full restore-and-reapply cycle and produced the identical
hash, which also proves the restore procedure between remedies was exact.

## B.3 R0 reproduces the baseline

The baseline was measured at `pydepin 0.16.2` on branch
`step-6-consumer-typing`; this worktree is `0.16.3` on `fix-threads-timeout`. R0
was measured first to prove the two are comparable.

```
$ bash /tmp/typing-baseline/remedy/run-all.sh
================ CORE-ONLY ================
--- mypy ---         Success: no issues found in 9 source files      exit=0
--- pyright ---      0 errors, 0 warnings, 0 informations            exit=0
--- basedpyright --- 0 errors, 0 warnings, 0 notes                   exit=0
--- ty ---           Found 3 diagnostics                             exit=1
--- pyrefly ---
ERROR core/c02_keys.py:39:36-40: Argument `Token[int]` is not assignable to parameter `key` with type
  `GenericAlias | Token[object] | Underlying | str | type[object]` in function `token_is_a_provider_key` [bad-argument-type]
ERROR core/c07_registration.py:51:48-54: Argument `Token[str]` ... in function `BindingCollector.alias`
ERROR core/c07_registration.py:51:59-65: Argument `Token[str]` ... in function `BindingCollector.alias`
                                                                     exit=1
================ EXTRAS ================
(the same 3, plus)
ERROR ext/e02_asgi_wsgi.py:33:16-51: Returned type `tuple[Token[str], str]` is not assignable to
  declared return type `tuple[ProviderKey, object] | None` [bad-return]
ERROR ext/e02_asgi_wsgi.py:55:16-58: (same, wsgi seed)
ERROR ext/e03_cli.py:35:16-43: (same, cli seed)
```

Six Pyrefly consumer diagnostics; ty's three oracle artefacts unchanged;
mypy / Pyright / Basedpyright clean. Repository source gates:

```
--- ruff-check ---   All checks passed!                              exit=0
--- basedpyright --- 0 errors, 0 warnings, 0 notes                   exit=0
--- mypy ---         Success: no issues found in 139 source files    exit=0
--- pyright ---      0 errors, 0 warnings, 0 informations            exit=0
--- ty ---           Found 32 diagnostics                            exit=1
--- pyrefly ---      INFO 17 errors (32 suppressed)                  exit=1
--- pytest ---       1081 passed, 6 skipped, 5 warnings in 44.31s    exit=0
```

Identical to the baseline in every number. **R0 is the baseline.**

---

# C. Standalone probes (no `depin` import)

## C.1 Declaration-level levers — `/tmp/typing-baseline/remedy/probe1/p.py`

Seven phantom-`Token` shapes, each passed as `X[int]` to a parameter typed
`X[object]`.

| Shape | mypy | Pyright | Basedpyright | ty | Pyrefly |
| --- | --- | --- | --- | --- | --- |
| `@final class TCOnly[T]` + `if TYPE_CHECKING: def _payload(self) -> T` | accept | accept | accept | accept | **accept** |
| `@final class PropOnly[T]` + TYPE_CHECKING `@property -> T` | accept | accept | accept | accept | **accept** |
| `class NonFinal[T]` (phantom, `@final` removed) | accept | accept | accept | accept | **reject** |
| `@final class Defaulted[T = object]` | syntax error | syntax error | syntax error | syntax error | syntax error |
| `@final class InvariantAttr[T]` + TYPE_CHECKING `_payload: T` | accept | accept | accept¹ | accept | **accept** |
| `class TokenKey` (non-generic) ← `@final class Based[T](TokenKey)` | accept | accept | accept | accept | **accept** |

¹ Basedpyright additionally reports
`reportUninitializedInstanceVariable` when the annotation is not inside
`if TYPE_CHECKING`.

```
$ uvx pyrefly@1.2.0 check --python-version 3.12 --preset strict p.py
ERROR p.py:37:19-27: Cannot set default type for a type parameter on Python 3.12 (syntax was added in Python 3.13) [invalid-syntax]
ERROR p.py:77:3-21: Argument `NonFinal[int]` is not assignable to parameter `k` with type `NonFinal[object]` in function `c`
ERROR p.py:78:3-22: Argument `Defaulted[int]` is not assignable to parameter `k` with type `Defaulted` in function `d`
```

Findings:

1. **`@final` does not alter inference.** `NonFinal` and the `@final` phantom
   `Token` are rejected identically by Pyrefly. `@final` is not a lever.
2. **PEP 696 defaults are unavailable on 3.12**, all five agree.
3. **A non-generic base class works on all five** without touching `T`.
4. **Any covariant use site works on all five**, whether it is a method, a
   property, or a bare attribute annotation.

## C.2 Which use sites actually pin variance — `probe1/p2.py`

| Use site (inside a `@final` phantom class) | mypy | Pyright | Basedpyright | ty | Pyrefly |
| --- | --- | --- | --- | --- | --- |
| `if TYPE_CHECKING: _payload: T` | accept | accept | accept | accept | accept |
| `_payload: T` (unguarded) | accept | accept | accept | accept | accept |
| `if TYPE_CHECKING: def _payload(self, v: T) -> T` | **reject** | **reject** | **reject** | **reject** | **reject** |
| `if TYPE_CHECKING: def _accept(self, v: T) -> None` | **reject** | **reject** | **reject** | **reject** | **reject** |

```
$ uvx mypy@2.3.1 --strict --python-version 3.12 p2.py
p2.py:56: error: Argument 1 to "c" has incompatible type "InvMethod[int]"; expected "InvMethod[object]"  [arg-type]
p2.py:57: error: Argument 1 to "d" has incompatible type "ContraTC[int]"; expected "ContraTC[object]"  [arg-type]
```

**A bare attribute annotation pins nothing in any of the five** — surprising,
since a mutable attribute is textbook-invariant, but unanimous and therefore
usable. **A method parameter of type `T` pins invariance on all five.** That
second row is the lever that fixes `n03` (section E).

## C.3 Signature spellings for the false negatives — `probe1/p3.py`, `p4.py`

`def value_bounded[T, V: T](key: type[T] | Token[T], v: V)` — a second type
parameter bounded by the first — is **rejected as illegal by all five**:

```
mypy         p3.py:23: error: Name "T" is not defined  [name-defined]
pyright      p3.py:23:25 - error: TypeVar constraint type cannot be generic
basedpyright p3.py:23:25 - error: TypeVar constraint type cannot be generic
ty           p3.py:23:25: error[invalid-type-variable-bound] TypeVar upper bound cannot be generic
pyrefly      p3.py:23:25-26: Type variable bounds and constraints must be concrete
```

`typing_extensions` 4.16 (the version in the extras venv) exports no `NoInfer`:

```
$ grep -n "NoInfer" .venv-extras/lib/python3.12/site-packages/typing_extensions.py
(no output)
```

**Python's type system has no non-inference marker.** The only spelling that
pins `T` to the key is to consume the key in one call and the value in the next
(`p4.py`, measured in section E.3).

---

# D. Remedies measured end-to-end

Every row is a real wheel, built from the worktree and force-installed into both
consumer venvs. Counts are diagnostics, not files.

## D.1 Consumer corpus (installed wheel, 21 files)

| Remedy | mypy | Pyright | Basedpyright | ty | Pyrefly (core) | Pyrefly (extras) |
| --- | --- | --- | --- | --- | --- | --- |
| **R0** unchanged | 0 | 0 | 0 | 3 | **3** | **6** |
| **R1** TYPE_CHECKING method `-> T` | 0 | 0 | 0 | 3 | 0 | 0 |
| **R1b** TYPE_CHECKING property `-> T` | 0 | 0 | 0 | 3 | 0 | 0 |
| **R1d** TYPE_CHECKING `_payload: T` | 0 | 0 | 0 | 3 | 0 | 0 |
| **R2** legacy `TypeVar(covariant=True)` | 0 | 0 | 0 | 3 | 0 | 0 |
| **R3** `ProviderKey` → structural Protocol | 0 | 0 | 0 | 3 | 0 | 0 |
| **R4** non-generic base `TokenKey` | 0 | 0 | 0 | 3 | 0 | 0 |
| **R5** R4 + invariant `payload(self, value: T) -> T` | 0 | 0 | 0 | 3 | 0 | 0 |

ty's 3 are the two `assert-type-unspellable-subtype` and one
`type-assertion-failure` the baseline classified as oracle/representation
artefacts (Disagreements 2 and 3). No remedy touches them, and none should:
they are fixed by re-spelling three assertions in the corpus.

## D.2 Repository source gates (`depin tests examples`)

| Remedy | ruff | Basedpyright | mypy | Pyright | ty | Pyrefly | pytest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **R0** | pass | 0 | 0 | 0 | 32 | **17** | 1081 passed |
| **R1** | pass | **1 FAIL** | 0 | 0 | 32 | 3 | 1081 passed |
| **R1b** | pass | **1 FAIL** | 0 | 0 | 32 | 3 | 1081 passed |
| **R1d** | pass | 0 | 0 | 0 | 32 | 3 | 1081 passed |
| **R2** | **1 FAIL** | 0 | 0 | 0 | 32 | 3 | 1081 passed |
| **R3** | pass | 0 | 0 | 0 | 32 | 3 | 1081 passed |
| **R4** | pass | 0 | 0 | 0 | 32 | 3 | 1081 passed |
| **R5** | pass | 0 | 0 | 0 | 32 | 3 | 1081 passed |

The Pyrefly 17 → 3 drop is the whole variance cluster: 14 of the 17 baseline
errors were one root cause. The surviving 3 are unrelated and were already
documented as such:

```
ERROR depin/_core/graph.py:88:50-52: Type of lambda parameter `kv` is unknown [implicit-any-lambda]
ERROR depin/_core/typeguards.py:26:43-48: Cannot determine the type parameter `T` for generic class `Token[T]` [implicit-any-type-argument]
ERROR tests/unit/test_graph_properties.py:298:41-45: Type of lambda parameter `case` is unknown [implicit-any-lambda]
```

ty's 32 are unchanged by every remedy; 25 of them are the suppression-spelling
artefacts the baseline itemised in B.4.

## D.3 The two gate failures, in full

**R1 / R1b — Basedpyright rejects a private, checker-only member:**

```
$ uv run basedpyright
depin/_core/markers.py:52:13 - error: Function "_payload" is not accessed (reportUnusedFunction)
1 error, 0 warnings, 0 notes
```

Identical for the `@property` form (`R1b`, line 53). `reportUnusedFunction`
fires on any underscore-prefixed callable that nothing in the package calls, and
a `TYPE_CHECKING`-only stub is by construction never called. Suppressing it is
barred by AGENTS.md. The only escapes are to rename the member into the public
namespace — which is exactly the "real cost" the brief anticipated — or to drop
the callable form, which is R1d.

**R2 — ruff rejects the legacy spelling as an enforced lint, not a convention:**

```
$ uv run ruff check
UP046 Generic class `Token` uses `Generic` subclass instead of type parameters
  --> depin/_core/markers.py:16:13
   |
15 | @final
16 | class Token(Generic[T_co]):
   |             ^^^^^^^^^^^^^
help: Use type parameters
Found 1 error.
```

**R2 is barred.** AGENTS.md forbids mixing `TypeVar(...)` with PEP 695 syntax in
one module; independently, the project's own `ruff` configuration enforces
`UP046` and fails the first command of the commit gate. Its typing result is
otherwise identical to R1: Pyrefly's 6 consumer errors go to 0, and the `n03`
catch is lost. The measurable cost of the AGENTS.md rule here is therefore
**zero** — the rule bars nothing that any other remedy does not also deliver.

---

# E. The two known false negatives

`n03` = `Container().value(Token[int]('port'), 'not-an-int')`
`n05` = `di.override(Config, Other())`

## E.1 Result per remedy

| Remedy | `n03` mypy | Pyright | Basedpyright | ty | Pyrefly | `n05` (all five) |
| --- | --- | --- | --- | --- | --- | --- |
| **R0** | accept | accept | accept | accept | **reject** | accept |
| **R1** | accept | accept | accept | accept | accept ⚠ | accept |
| **R1b** | accept | accept | accept | accept | accept ⚠ | accept |
| **R1d** | accept | accept | accept | accept | accept ⚠ | accept |
| **R2** | accept | accept | accept | accept | accept ⚠ | accept |
| **R3** | accept | accept | accept | accept | **reject** | accept |
| **R4** | accept | accept | accept | accept | **reject** | accept |
| **R5** | **reject** | **reject** | **reject** | **reject** | **reject** | accept |

⚠ **R1, R1b, R1d and R2 are trades, not wins.** Each fixes Pyrefly's variance
divergence by declaring `T` covariant, and Pyrefly's catch on `n03` existed
*only* because it read `T` as invariant. Buying six green diagnostics with a lost
true-positive is a net loss of signal: it converts the last checker that caught
a real public-API defect into one that does not.

**R3 and R4 are neutral on `n03`**: they remove the assignability requirement
without asserting a variance, so Pyrefly keeps reading `T` as invariant and
keeps the catch, while the other four keep reading it as covariant and keep
missing it. Four-of-five is exactly the baseline state.

**R5 is the only remedy that improves it.** Giving `T` a genuine invariant use
site makes all five agree on invariance, and all five then reject `n03`:

```
$ bash run-all.sh    # R5, neg/n03_token_value_type_mismatch.py
--- mypy ---
neg/n03_token_value_type_mismatch.py:9: error: Cannot infer value of type parameter "T" of "value" of "BindingCollector"  [misc]
exit=1
--- pyright ---
  neg/n03_token_value_type_mismatch.py:9:33 - error: Argument of type "Literal['not-an-int']" cannot be assigned to
    parameter "value" of type "T@value" in function "value"
    "Literal['not-an-int']" is not assignable to "int" (reportArgumentType)
exit=1
--- basedpyright ---
  (identical to pyright)                                                     exit=1
--- ty ---
neg/n03_token_value_type_mismatch.py:9:27: error[invalid-argument-type] Argument to bound method
  `BindingCollector.value` is incorrect: Expected `Token[int | Literal["not-an-int"]]`, found `Token[int]`
exit=1
--- pyrefly ---
ERROR neg/n03_token_value_type_mismatch.py:9:33-45: Argument `Literal['not-an-int']` is not assignable to
  parameter `value` with type `int` in function `depin._core.bindings.BindingCollector.value` [bad-argument-type]
exit=1
```

Note that mypy's message names the symptom (`Cannot infer T`) rather than the
mismatch, and ty reports it as a key-side error. Both reject; a negative harness
keyed on message text would be brittle here, which is the same conclusion the
baseline reached in Disagreement 3.

## E.2 `n05` is not a variance problem

No remedy touches it, and none can. Reduced to nine lines with no `depin`
import (`probe1/p4.py`, line 45):

```python
def override[T](self, key: type[T] | Token[T], replacement: T) -> Self: ...


c.override(A, Unrelated())  # accepted by all five, R0 through R5
```

`T` is solved from both parameters and widened to the join `A | Unrelated`;
`type[A]` is assignable to `type[A | Unrelated]` because `type[...]` is
covariant **by construction in the spec**, not by inference. Making `Token`
invariant fixes the token branch and leaves the class branch untouched. This is
why R5 fixes `n03` and not `n05`.

## E.3 Proposal for both, measured but not implemented

Pin `T` to the key by consuming the key and the value in **separate calls**, so
only one call site can drive inference:

```python
@final
class _Override[T]:
    __slots__ = ()

    def using(self, replacement: T) -> None: ...


def override[T](key: type[T] | Token[T]) -> _Override[T]: ...
```

```
$ bash probe1/run.sh p4.py
=== mypy ===
p4.py:42: error: Argument 1 to "using" of "_Override" has incompatible type "Unrelated"; expected "A"  [arg-type]
p4.py:44: error: Argument 1 to "using" of "_Override" has incompatible type "str"; expected "int"  [arg-type]
=== pyright ===
  p4.py:42:27 - error: Argument of type "Unrelated" cannot be assigned to parameter "replacement" of type "A"
  p4.py:44:41 - error: Argument of type "Literal['no']" cannot be assigned to parameter "replacement" of type "int"
=== basedpyright ===  (identical)
=== ty ===
p4.py:42:27: error[invalid-argument-type] Argument to bound method `_Override.using` is incorrect: Expected `A`, found `Unrelated`
p4.py:44:41: error[invalid-argument-type] Argument to bound method `_Override.using` is incorrect: Expected `int`, found `Literal["no"]`
=== pyrefly ===
ERROR p4.py:42:27-38: Argument `Unrelated` is not assignable to parameter `replacement` with type `A` [bad-argument-type]
ERROR p4.py:44:41-45: Argument `Literal['no']` is not assignable to parameter `replacement` with type `int` [bad-argument-type]
```

**All five reject both invalid calls**, and the legitimate widening
`override_twostep(A).using(B())` where `B(A)` is still accepted (line 43, no
diagnostic anywhere). The same file confirms the one-step form
`c.override(A, Unrelated())` on line 45 stays accepted by all five.

Cost: `override` changes shape, which is a breaking public-API change and does
not fit the `with di.override(...)` context-manager spelling without a second
object. Two spellings were ruled out first, both empirically:
`[T, V: T]` is illegal in all five (C.3), and Python has no `NoInfer` (C.3).

---

# F. Precision: what each widening actually costs

`R3` widens `ProviderKey` structurally. The probe
(`/tmp/typing-baseline/remedy/precision/pk.py`) is an ordinary dataclass that is
not a token and has nothing to do with dependency injection:

```python
@dataclass
class Person:
    name: str


di = Container().bind(Repo).freeze()
di.explain(Person('ada'))
```

Under **R3**, every checker accepts it:

```
=== mypy ===     (no output)
=== pyright ===  (no diagnostics)
=== ty ===       All checks passed!
=== pyrefly ===  (no output)
```

Under **R4 / R5**, every checker rejects it:

```
=== mypy ===
pk.py:17: error: Argument 1 to "explain" of "FrozenContainer" has incompatible type "Person";
  expected "type[object] | TokenKey | str | GenericAlias | Underlying"  [arg-type]
=== pyright ===
  "Argument of type \"Person\" cannot be assigned to parameter \"key\" of type \"ProviderKey\" …
   \"Person\" is not assignable to \"TokenKey\" …"
=== ty ===
pk.py:17:12: error[invalid-argument-type] Argument to bound method `FrozenContainer.explain` is incorrect:
  Expected `ProviderKey`, found `Person`
=== pyrefly ===
ERROR pk.py:17:12-25: Argument `Person` is not assignable to parameter `key` with type
  `GenericAlias | TokenKey | Underlying | str | type[object]` [bad-argument-type]
```

**R3's precision loss is real and reaches the public API.** Every signature that
takes a key — `alias`, `collect`, `decorate`, `explain`, `DependencyGraph.find`
/ `node`, `Named(...)`, and the `seed` return type in `ext.asgi`, `ext.wsgi`,
`ext.cli` — silently accepts any object carrying a `name: str` attribute, and
fails at runtime instead. R4 and R5 lose nothing: `Token[int]` is assignable to
`TokenKey` by inheritance, and nothing else is.

---

# G. What R5 changes, exactly

Three files, 48 insertions / 26 deletions. Nothing else in the repository was
touched.

```
$ git diff --stat
 depin/_core/introspect.py | 12 +++++-----
 depin/_core/markers.py    | 56 +++++++++++++++++++++++++++++++++--------------
 depin/_core/spec.py       |  6 ++---
 3 files changed, 48 insertions(+), 26 deletions(-)
```

1. `markers.py` gains a non-generic `TokenKey` carrying `__slots__ = ('name',)`,
   `__init__`, `__repr__`, `__eq__`, `__hash__`. `Token[T]` becomes
   `@final class Token[T](TokenKey)` with `__slots__ = ()` and one new method.
   `__eq__` narrows on `TokenKey` rather than `Token`.
2. The eight `Token[object]` annotations become `TokenKey`
   (`spec.ProviderKey`, `spec.FrameBinding.key`, `markers.Named.key`,
   `markers._InjectMarker.key`, `introspect.AnnotatedMeta.token` / `.named`
   × 2, `introspect.is_object_token`'s `TypeGuard`).
3. `Token` gains one public method:

```python
    def payload(self, value: T) -> T:
        """Return ``value`` unchanged, checked against the token's payload type.

        Pins the type parameter to a single use site, so a checker treats two
        tokens with different payload types as unrelated rather than widening
        one to the other.
        """
        return value
```

## G.1 Runtime behaviour is unchanged

Equality and hashing are still by `name` only — the hash seed string
`'depin.Token'` is unchanged, so hashes are stable across the change.
`__slots__` is preserved (moved to the base; the subclass declares an empty
tuple, so no `__dict__` appears). The docstring's doctest still passes, with one
line added for the new method:

```
$ uv run pytest -q --timeout 300
1081 passed, 6 skipped, 5 warnings in 51.02s
```

`pytest` runs with `--doctest-modules` over `depin`, so this is the doctest
result, not a separate claim.

```
$ uv run --group docs mkdocs build --strict
INFO    -  Documentation built in 8.90 seconds
```

## G.2 The costs, stated plainly

1. **`payload` is a new public member on `Token`.** It carries a docstring and
   is genuinely callable — it is not a `TYPE_CHECKING` fiction that would raise
   `AttributeError` if a consumer used it — but it exists to pin variance, and
   every reader of `Token` will now ask what it is for. This is the single
   largest cost and it is not free.
2. **`T` becomes invariant.** `Token[Derived]` is no longer usable where
   `Token[Base]` is expected. Nothing in the 1062-line consumer corpus, the
   1081-test suite or `tests/typing` relies on that, but it is a real narrowing
   of the public contract and belongs in a release note.
3. **`TokenKey` appears in the public `ProviderKey` alias but is not exported
   from `depin/__init__.py`.** A consumer who reads a diagnostic naming
   `TokenKey` cannot `from depin import TokenKey`. Either export it (with the
   docstring the public API requires) or accept the asymmetry — this is an open
   design decision the experiment did not settle.
4. **`TokenKey` is not `@final`.** A consumer can subclass it and pass the
   result where a key is expected. `Token` stays `@final`.
5. **Basedpyright's `reportUnusedFunction` dictates the shape.** A private
   `_payload` fails the commit gate (D.3), so the member must be public. R5's
   design is a consequence of that measurement, not a preference.

If cost 1 or 2 is unacceptable, **R4 is the fallback**: identical on every
checker in every mode, no new member on `Token`, `T` stays phantom, and the only
loss relative to R5 is that `n03` stays a four-of-five false negative — which is
the baseline's state, not a regression.

---

# H. Verdicts

## H.1 Remedy × checker, consolidated

`C` = consumer corpus (extras mode, the strictest); `S` = repository source
gates. Cell = diagnostics; `FAIL` = a commit-gate command exits non-zero.

| Remedy | mypy C/S | Pyright C/S | Basedpyright C/S | ty C/S | Pyrefly C/S | `n03` | `n05` | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0 unchanged | 0/0 | 0/0 | 0/0 | 3/32 | **6/17** | 1 of 5 | 0 of 5 | baseline |
| R1 TC method | 0/0 | 0/0 | 0/**FAIL** | 3/32 | 0/3 | **0 of 5** | 0 of 5 | rejected — breaks the gate, loses `n03` |
| R1b TC property | 0/0 | 0/0 | 0/**FAIL** | 3/32 | 0/3 | **0 of 5** | 0 of 5 | rejected — same |
| R1d TC attribute | 0/0 | 0/0 | 0/0 | 3/32 | 0/3 | **0 of 5** | 0 of 5 | trade — passes gates, loses `n03`, declares a member that never exists |
| R2 legacy TypeVar | 0/0 | 0/0 | 0/0 | 3/32 | 0/3 | **0 of 5** | 0 of 5 | **barred** — `ruff UP046` FAIL + AGENTS.md; and it is a trade anyway |
| R3 Protocol widening | 0/0 | 0/0 | 0/0 | 3/32 | 0/3 | 1 of 5 | 0 of 5 | rejected — silently accepts any `name: str` object as a key (F) |
| **R4 base class** | 0/0 | 0/0 | 0/0 | 3/32 | 0/3 | 1 of 5 | 0 of 5 | **acceptable fallback** |
| **R5 base class + invariance** | 0/0 | 0/0 | 0/0 | 3/32 | 0/3 | **5 of 5** | 0 of 5 | **recommended** |

## H.2 Is "all five blocking on the consumer contract" reachable?

**Yes, and the Pyrefly half of it is now free.** After R4 or R5, Pyrefly reports
zero diagnostics over the whole consumer corpus in both modes, and drops from 17
to 3 over the repository source — the 3 being `implicit-any-lambda` ×2 and one
`implicit-any-type-argument`, all fixable by ordinary annotation work with no
design question attached.

The residual blocker is **ty, and it is not about variance**: 3 consumer
diagnostics (two oracle spellings that should be assignability, one
indistinguishable-in-output representation choice) and 32 source diagnostics, 25
of which are suppression-spelling artefacts. That is exactly what the baseline
recorded, unchanged by every remedy. The price of "all five blocking" is
therefore: adopt R4 or R5, re-spell three corpus assertions, and settle ty's
suppression-comment policy — none of which is a design decision about `Token`.

## H.3 The false negatives

- **`n05` survives every remedy.** It is not a variance defect. `type[T]` is
  covariant by construction, so no change to `Token` can reach it. The two-step
  `override` in E.3 fixes it on all five and is a breaking API change; that is a
  separate decision the design specification must take on its own terms.
- **`n03` is the discriminator between remedies.** R1 / R1b / R1d / R2 lose it;
  R3 / R4 hold it at four-of-five; R5 fixes it on all five.

## H.4 Is documenting a permanent Pyrefly exception a legitimate outcome here?

**No — it is no longer necessary, and it would be the wrong call.** The baseline
was right that every remedy it could see had a cost. The measurement adds one it
did not: a **non-generic supertype in the key positions** sidesteps variance
entirely rather than asserting one, passes all five checkers and every commit
gate, changes no runtime behaviour, and — unlike every covariance-asserting
remedy — does not surrender Pyrefly's catch on `value`. Pyrefly 1.2.0 is still
non-conformant with the spec's auto-variance algorithm (section A) and that
should be reported upstream, but `depin` does not have to wait for it.

---

# Repository state

```
$ git status --porcelain
 M depin/_core/introspect.py
 M depin/_core/markers.py
 M depin/_core/spec.py
```

The working tree carries **R5**, unstaged and uncommitted, exactly as described
in section G. No commit was made. `pyproject.toml`, `depin/__init__.py`,
`depin/ext/`, `tests/`, `examples/`, `docs/` and `.github/` are untouched. To
return to R0: `cp /tmp/typing-baseline/remedy/orig/*.py depin/_core/`.

Side effects outside the worktree: `/tmp/typing-baseline/remedy/` (scripts,
eight wheels, logs, probes) and the two consumer venvs, which now hold the R5
wheel rather than the baseline's `0.16.2`. Reinstalling
`/tmp/typing-baseline/dist/pydepin-0.16.2-py3-none-any.whl` restores them.

## Reproduction artifacts

```
/tmp/typing-baseline/remedy/
├── build-install.sh              # uv build + force-reinstall + hash proof
├── run-all.sh                    # consumer corpus, five checkers, both modes, + n03/n05
├── run-repo.sh                   # AGENTS.md gate + pyright/ty/pyrefly over the source
├── pyrightconfig-src.json        # stock Pyright, source corpus, worktree venv
├── apply_r3.py apply_r4.py apply_r5_class.py
├── orig/                         # pristine copies of the five files touched
├── dist/{R0,R1,R1b,R1d,R2,R3,R4,R5,R5v}/*.whl
├── probe1/{p,p2,p3,p4}.py run.sh # standalone probes, no depin import
├── precision/{pk.py,run.sh}      # the R3 precision loss
└── {R0,R1,R1b,R1d,R2,R3,R4,R5}{,-repo}.log
```
