# Multi-checker consumer typing: fresh baseline measurement

Handoff artifact 1 of 5 for
`specs/proposals/2026-08-31-multi-checker-consumer-typing-proposal.md`.

Date measured: 2026-09-01
Repository: `/home/dreco/dev/depin`, branch `step-6-consumer-typing`
Distribution version measured: `pydepin 0.16.2`
Host: Linux 6.8.0-138-generic, x86_64, CPython 3.12.13 (uv-managed)

No tracked file in the repository was modified to produce this report. Every
experiment ran under `/tmp/typing-baseline/`. Two repository-state notes are
recorded in the closing section.

This document reports measurements only. Nothing was fixed.

---

## Scope correction: the proposal is stale

The proposal (2026-08-31) scopes the work to "the core package and the FastAPI
integration". That is no longer the surface.

```
$ ls depin/ext/
asgi.py  cli.py  click.py  fastapi.py  flask.py  __init__.py
litestar.py  pytest.py  starlette.py  taskiq.py  typer.py  wsgi.py
```

```
$ python3 -c "import zipfile; z=zipfile.ZipFile('dist/pydepin-0.16.2-py3-none-any.whl'); print('\n'.join(l for l in z.read('pydepin-0.16.2.dist-info/METADATA').decode().splitlines() if l.startswith('Provides-Extra')))"
Provides-Extra: click
Provides-Extra: fastapi
Provides-Extra: flask
Provides-Extra: litestar
Provides-Extra: pytest
Provides-Extra: starlette
Provides-Extra: taskiq
Provides-Extra: typer
```

Twelve `depin.ext` modules, eight declared extras. Four of the twelve carry
PEP 695 constructs on the consumer-facing surface — `asgi.RequestScope`,
`wsgi.RequestScope`, `cli.install` / `cli.CommandContext.with_resource`, and
`fastapi.Inject`. All four are measured in sections C and D. The design
specification must widen its coverage table from one integration to eight
extras, and its CI matrix from one optional install to at least two
(core-only, all-extras).

---

# A. Tooling reality

Every checker was run at the newest version published on PyPI on the
measurement date. The two versions the repository pins in `[dependency-groups]
dev` happen to be those newest versions.

```
$ for p in mypy basedpyright pyright ty pyrefly; do
    v=$(curl -s "https://pypi.org/pypi/$p/json" | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])")
    echo "$p latest on PyPI: $v"; done
mypy latest on PyPI: 2.3.1
basedpyright latest on PyPI: 1.39.10
pyright latest on PyPI: 1.1.411
ty latest on PyPI: 0.0.77
pyrefly latest on PyPI: 1.2.0
```

```
$ uv --version
uv 0.11.13 (x86_64-unknown-linux-gnu)
$ uv run python -V
Python 3.12.3
$ uv run mypy --version
mypy 2.3.1 (compiled: yes)
$ uv run basedpyright --version
basedpyright 1.39.10
based on pyright 1.1.412
$ uvx ty --version
ty 0.0.77
$ uvx pyrefly --version
pyrefly 1.2.0
$ uvx pyright --version
pyright 1.1.411
```

Note the version skew inside Basedpyright: `basedpyright 1.39.10` is built on
`pyright 1.1.412`, one patch ahead of the newest stock `pyright` on PyPI
(1.1.411). A Basedpyright result is therefore never a stock-Pyright result even
when both report zero, which is the proposal's acceptance criterion "Stock
Pyright is executed independently".

## A.1 Native project configuration present in the repository

```
$ grep -n "^\[tool\." pyproject.toml
157:[tool.basedpyright]
167:[tool.mypy]
176:[tool.ty.src]
(plus hatch, ruff, pytest, coverage, mutmut)
$ ls -a | grep -iE "pyright|pyrefly|mypy|setup.cfg"
.mypy_cache
```

| Checker | Native config in repo | Section read | Notes |
| --- | --- | --- | --- |
| mypy | yes | `[tool.mypy]` | `strict`, `warn_unreachable`, four extra error codes, `files = ["depin","tests","examples"]` |
| Basedpyright | yes | `[tool.basedpyright]` | `typeCheckingMode = "strict"`, `reportImplicitOverride = true`, same file list |
| Stock Pyright | **no** | `[tool.pyright]` absent, no `pyrightconfig.json` | AGENTS.md forbids reintroducing `pyrightconfig.json` |
| ty | yes (advisory) | `[tool.ty.src]` | file list only; no severity configuration |
| Pyrefly | **no** | `[tool.pyrefly]` absent, no `pyrefly.toml` | falls back to `basic` preset, which is near-silent (A.4) |

Stock Pyright silently reads nothing from this repository. It does **not** read
`[tool.basedpyright]`. Run with no arguments in the repo root it would use its
own defaults (`typeCheckingMode` = `standard`), not the project's strict
settings.

## A.2 How each checker was invoked

Configuration files written for this baseline live in `/tmp/typing-baseline/`
and `/tmp/typing-baseline/consumer/`; none was placed inside the repository.

**mypy** — repository gate as CI runs it:

```
$ uv run mypy
Success: no issues found in 139 source files
```

For the consumer corpus, mypy is pointed at the consumer's interpreter so it
resolves `depin` from the wheel:

```
$ uvx mypy@2.3.1 --strict --warn-unreachable --python-version 3.12 \
    --python-executable .venv-extras/bin/python --no-incremental core ext
```

**Basedpyright** — repository gate as CI runs it (`uv run basedpyright`); for
the consumer corpus, `-p <config>.json`.

**Stock Pyright** — needs a config written from scratch. Two mechanical facts
were established by experiment:

```
$ uvx pyright@1.1.411 -p /tmp/typing-baseline/pyrightconfig-src.json
Ignoring path "/home/dreco/dev/depin/depin" in "include" array because it is not relative.
Ignoring path "/home/dreco/dev/depin/tests" in "include" array because it is not relative.
Ignoring path "/home/dreco/dev/depin/examples" in "include" array because it is not relative.
Config contains unrecognized setting "pythonPath".
0 errors, 0 warnings, 0 informations
```

- `include` entries must be relative to the config file's directory; absolute
  paths are dropped, and the run then reports zero having checked nothing.
- `pythonPath` is not a recognised stock-Pyright config key. `venvPath` +
  `venv` is.

Both traps produce a green run that checked no files, which is exactly the kind
of silent pass the proposal's acceptance criteria must forbid. The working form
passes the paths on the command line, which overrides `include`:

```json
// /tmp/typing-baseline/pyrightconfig-src.json
{
  "typeCheckingMode": "strict",
  "pythonVersion": "3.12",
  "venvPath": "/home/dreco/dev/depin",
  "venv": ".venv",
  "reportMissingTypeStubs": false,
  "reportImplicitOverride": true
}
```

```
$ uvx pyright@1.1.411 -p /tmp/typing-baseline/pyrightconfig-src.json --stats depin tests examples
Found 139 source files
pyright 1.1.411
0 errors, 0 warnings, 0 informations
Completed in 19.707sec
Total files checked: 139
```

`Total files checked: 139` matches mypy's `139 source files`; the two checkers
saw the same corpus. **A file count assertion belongs in the future CI job.**

**ty** — `uvx ty@0.0.77 check` reads `[tool.ty.src]`. For the consumer corpus a
standalone config was written:

```toml
# /tmp/typing-baseline/consumer/ty-extras.toml
[environment]
python = "/tmp/typing-baseline/consumer/.venv-extras"
python-version = "3.12"
[src]
include = ["core", "ext"]
```

```
$ uvx ty@0.0.77 check --config-file ty-extras.toml --error all --output-format concise
```

**Pyrefly** — needs a config written from scratch:

```toml
# /tmp/typing-baseline/consumer/pyrefly-extras.toml
python-interpreter = "/tmp/typing-baseline/consumer/.venv-extras/bin/python"
python-version = "3.12"
project-includes = ["core", "ext"]
```

```
$ uvx pyrefly@1.2.0 check -c pyrefly-extras.toml --preset strict \
    --output-format min-text --progress-bar no --summary=none
```

Running `pyrefly check <file>` with no config prints, on every invocation:

```
No `pyrefly.toml` found — using preset `basic`.
Run `pyrefly init` to continue setting up Pyrefly.
```

## A.3 Closest honest equivalent of "strict consumer checking"

| Checker | Chosen setting | Why |
| --- | --- | --- |
| mypy | `--strict --warn-unreachable` | mirrors `[tool.mypy]`. `--disallow-any-expr` measured separately (A.5); unusable with extras installed |
| Stock Pyright | `typeCheckingMode: "strict"`, `useLibraryCodeForTypes: false`, `reportMissingTypeStubs: true` | strict is Pyright's own maximum named mode. `useLibraryCodeForTypes: false` forces reliance on `py.typed` inline types rather than inferred library code — the property the consumer contract is about |
| Basedpyright | same, plus `reportImplicitOverride: true` | mirrors `[tool.basedpyright]`. `reportAny` / `reportExplicitAny` measured separately (A.5) |
| ty | `--error all` | ty has no strict mode and no preset system. `--error all` promotes every rule to error severity; `--error-on-warning` additionally fails on warnings. Verified below to change nothing on this corpus, so it costs nothing to adopt |
| Pyrefly | `--preset strict` | measured against every preset below |

Pyrefly preset comparison on the same consumer corpus:

```
$ for p in basic default strict all; do
    n=$(uvx pyrefly@1.2.0 check -c pyrefly-extras.toml --preset $p \
        --output-format min-text --progress-bar no --summary=none 2>&1 | grep -c '^ERROR')
    echo "pyrefly --preset $p : $n errors"; done
pyrefly --preset basic : 0 errors
pyrefly --preset default : 6 errors
pyrefly --preset strict : 6 errors
pyrefly --preset all : 7 errors
```

The single error `all` adds over `strict` is a house-style rule, not a typing
contract:

```
$ diff <(pyrefly ... --preset strict) <(pyrefly ... --preset all)
> ERROR ext/e03_cli.py:35:25-36: Implicit conversion of `str | None` to `bool` is not allowed [implicit-bool]
```

`strict` is therefore the honest choice: `all` adds lint, `default` happens to
be equivalent here but is not a stability promise, and `basic` is the trap
described next.

ty `--error all` on the same corpus (compare with C.5, which used defaults):

```
$ uvx ty@0.0.77 check --config-file ty-extras.toml --error all --error-on-warning --output-format concise
core/c01_container.py:60:5: error[assert-type-unspellable-subtype] ...
core/c01_container.py:66:5: error[type-assertion-failure] ...
core/c07_registration.py:46:5: error[assert-type-unspellable-subtype] ...
Found 3 diagnostics
$ echo exit=$?    # measured without a pipe
exit=1
```

Identical to ty's default severities. ty propagates a real exit status; the
proposal's criterion "ty and Pyrefly consumer jobs propagate their real exit
status" is satisfiable today (the current advisory CI job's `exit 0` is a
deliberate choice, not a tool limitation).

## A.4 Pyrefly's default preset is a false-negative trap

```
$ cat q.py
def f(x: int) -> int:
    return x

e = f("none")
$ uvx pyrefly@1.2.0 check q.py
 INFO 0 errors
No `pyrefly.toml` found — using preset `basic`.
$ echo exit=$?
exit=0
$ uvx pyrefly@1.2.0 check --preset all q.py
ERROR Argument `Literal['none']` is not assignable to parameter `x` with type `int` in function `f` [bad-argument-type]
 INFO 1 error
exit=1
```

An unconfigured Pyrefly does not report `bad-argument-type` at all. **The
proposal's recorded observation that "Pyrefly 1.2.0 reported no active errors
for the existing core and FastAPI public conformance modules when checked
directly" is not evidence of compatibility if it was produced without a config**
— an unconfigured Pyrefly reports almost nothing. Section B re-measures with
`--preset strict`.

## A.5 Anti-erasure capability per checker

| Checker | Mechanism | Measured on consumer corpus |
| --- | --- | --- |
| mypy | `--disallow-any-expr` | core-only: clean. With extras: 7 errors, all from FastAPI's `DecoratedCallable` and Litestar's `Middleware` union — third-party `Any`, not depin's |
| Basedpyright | `reportAny`, `reportExplicitAny` (basedpyright-only) | `0 errors, 0 warnings, 0 notes` with both set to `error` |
| Stock Pyright | `reportUnknownVariableType`/`MemberType`/`ArgumentType` (in strict) | clean; fires on the negative fixtures (section D.7) |
| Pyrefly | `explicit-any`, `no-any-return-explicit`, `implicit-any-lambda`, `implicit-any-type-argument`, `unknown-argument-type` — only at `--preset all` | not enabled at `strict` |
| ty | no equivalent rule found in `ty check --help` | **cannot express this** |

```
$ uvx basedpyright@1.39.10 -p bpr-extras-any.json   # reportAny + reportExplicitAny = error
0 errors, 0 warnings, 0 notes
$ uvx mypy@2.3.1 --strict --disallow-any-expr --python-version 3.12 \
    --python-executable .venv-core/bin/python --no-incremental core
Success: no issues found in 9 source files
```

Both results are strong: no `Any` and no unknown type reaches any core public
call site in the consumer corpus.

## A.6 Suppression-comment semantics — a foundational divergence

```
$ cat p.py
def f(x: int) -> int:
    return x

a = f("bare")     # type: ignore
b = f("coded")    # type: ignore[arg-type]
c = f("pyright")  # pyright: ignore[reportArgumentType]
d = f("tyignore") # ty: ignore[invalid-argument-type]
e = f("none")

$ uvx ty@0.0.77 check --output-format concise p.py
p.py:5:7: error[invalid-argument-type] ... Literal["coded"]
p.py:6:7: error[invalid-argument-type] ... Literal["pyright"]
p.py:8:7: error[invalid-argument-type] ... Literal["none"]
Found 3 diagnostics

$ uvx pyrefly@1.2.0 check --preset all --output-format min-text p.py
ERROR p.py:6:7-16: ... Literal['pyright'] ... [bad-argument-type]
ERROR p.py:7:7-17: ... Literal['tyignore'] ... [bad-argument-type]
ERROR p.py:8:7-13: ... Literal['none'] ... [bad-argument-type]
 INFO 3 errors (2 suppressed)

$ uvx pyrefly@1.2.0 check --preset all --permissive-ignores --output-format min-text p.py
ERROR p.py:8:7-13: ... Literal['none'] ... [bad-argument-type]
 INFO 1 error (4 suppressed)
```

| Suppression spelling | mypy | Pyright / Basedpyright | ty 0.0.77 | Pyrefly 1.2.0 default | Pyrefly `--permissive-ignores` |
| --- | --- | --- | --- | --- | --- |
| `# type: ignore` | honoured | honoured | honoured | honoured | honoured |
| `# type: ignore[code]` | honoured | honoured | **not honoured** | honoured | honoured |
| `# pyright: ignore[...]` | ignored | honoured | **not honoured** | **not honoured** | honoured |
| `# ty: ignore[...]` | ignored | ignored | honoured | not honoured | honoured |

ty accepts a *bare* `# type: ignore` but not the mypy-coded form. The
repository's negative fixtures are all written as
`# type: ignore[code]  # pyright: ignore[code]`, which ty honours in neither
half. This single fact accounts for 25 of ty's 32 source-corpus diagnostics
(section B.4). Pyrefly's default `enabled-ignores` is `type,pyrefly`; the repo
never uses `# pyright: ignore` without a paired `# type: ignore`, so
`--permissive-ignores` changed nothing here (B.5).

---

# B. Source-corpus baseline

Corpus: `depin/`, `tests/`, `examples/` — the exact file list
`[tool.basedpyright] include` and `[tool.mypy] files` already share. 139 files.

## B.1 Summary

| Checker | `depin` + `tests` + `examples` | `tests/typing` only |
| --- | --- | --- |
| mypy 2.3.1 (`--strict`) | 0, exit 0 | 0 |
| stock Pyright 1.1.411 (strict) | 0, exit 0 | 0 |
| Basedpyright 1.39.10 (strict) | 0, exit 0 | 0 |
| ty 0.0.77 | **32 diagnostics**, exit 1 | **2** |
| Pyrefly 1.2.0 (`--preset strict`) | **17 errors** (32 suppressed), exit 1 | 0 |

The repository's own typing corpus is 80 `assert_type` cases:

```
$ grep -c "assert_type" tests/typing/test_conformance.py tests/typing/test_conformance_fastapi.py tests/typing/test_conformance_pytest.py
tests/typing/test_conformance.py:73
tests/typing/test_conformance_fastapi.py:3
tests/typing/test_conformance_pytest.py:4
```

## B.2 mypy and Basedpyright (the current blocking gates)

```
$ uv run mypy
Success: no issues found in 139 source files
$ uv run basedpyright
0 errors, 0 warnings, 0 notes
```

## B.3 Stock Pyright — first independent run

```
$ uvx pyright@1.1.411 -p /tmp/typing-baseline/pyrightconfig-src.json --stats depin tests examples
Found 139 source files
pyright 1.1.411
0 errors, 0 warnings, 0 informations
Completed in 19.707sec
Total files checked: 139
```

Stock Pyright 1.1.411 in strict mode is clean over the entire repository. It
could become a complete-source gate today at no annotation cost. The only
argument against it is duplicated signal against Basedpyright, and the one-patch
version skew (A) is the argument for keeping it separate.

## B.4 ty 0.0.77 — 32 diagnostics

```
$ uvx ty@0.0.77 check --output-format concise
```

By rule:

```
     11 error[invalid-argument-type]
      8 error[no-matching-overload]
      4 error[invalid-return-type]
      3 error[unknown-argument]
      2 error[unresolved-reference]
      1 error[unresolved-attribute]
      1 error[type-assertion-failure]
      1 error[invalid-assignment]
      1 error[call-top-callable]
Found 32 diagnostics
```

Classified by whether the reported line already carries a mypy/Pyright
suppression:

```
ty source diagnostics on a line carrying a mypy/pyright suppression: 25
ty source diagnostics NOT suppressed elsewhere: 7
```

### The 25 suppression-spelling artefacts

Every one of them sits on a line the repository has already declared an
intentional negative, e.g.

```python
# tests/unit/test_resolution.py:36
frozen.resolve(42)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType, reportUnusedCallResult]
```

```
tests/unit/test_resolution.py:36:24: error[invalid-argument-type] Argument to bound method
  `FrozenContainer.resolve` is incorrect: Expected `type[Unknown] | Token[Unknown]`, found `Literal[42]`
```

**Classification: harness portability problem, not a consumer-visible defect.**
These are ty *agreeing* with mypy and Pyright about invalid code and then being
unable to read the suppression. Remediation is a suppression spelling all four
tools honour, or moving intentional negatives out of the checked corpus into
per-file negative fixtures (which is what section D does).

### The 7 remaining, individually

```
depin/_core/typeguards.py:194:16: error[invalid-return-type] Return type does not match returned value:
  expected `(object, /) -> object`, found `Top[(...) -> object]`
tests/unit/test_wsgi.py:140:9: error[call-top-callable] Object of type `Top[(...) -> object]`
  is not safe to call; its signature is not known
```

**Classification: checker limitation.** ty models `Callable[..., object]` as a
gradual "top callable" and refuses to narrow or call it. Private code
(`_core.typeguards`) and a unit test; no public signature involved. Both are
outside the consumer contract.

```
tests/integration/test_taskiq_ext.py:246:35  error[unknown-argument] `is_err` ... `PydanticRecursiveRef.__call__`
tests/integration/test_taskiq_ext.py:246:49  error[unknown-argument] `return_value` ...
tests/integration/test_taskiq_ext.py:246:68  error[unknown-argument] `execution_time` ...
tests/integration/test_taskiq_ext.py:248:44  error[invalid-argument-type] ... found `BaseModel | None | Any`
```

**Classification: third-party.** ty resolves `taskiq.TaskiqResult` through
pydantic's `PydanticRecursiveRef` rather than the generic model. Nothing in
`depin` is involved.

```
tests/typing/test_conformance.py:82:9: error[type-assertion-failure]
  Type `CoroutineType[Any, Any, str]` does not match asserted type `Awaitable[str]`
```

**Classification: invalid test oracle.** This is the case the proposal named,
still present at 0.0.77. Full analysis in section E.3.

Note what is *not* in ty's list: the four `invalid-return-type` diagnostics at
`frozen.py:127`, `frozen.py:150`, `markers.py:132` and `typeguards.py:194` are
in the 32 but three of them are on lines that carry the library's own
documented `# type: ignore[return-value]  # pyright: ignore[reportReturnType]`
widenings — the same suppression-spelling problem, on `depin` source rather than
tests:

```
depin/_core/frozen.py:127:16: error[invalid-return-type] expected `T@resolve`, found `object`
depin/_core/frozen.py:150:16: error[invalid-return-type] expected `T@aresolve`, found `object`
depin/_core/markers.py:132:12: error[invalid-return-type] expected `T@injected`, found `_InjectMarker`
```

These are the three deliberate, documented widenings at the plan-erasure
boundary. They are invisible to a consumer; both `resolve` and `injected`
return the promised `T` at every call site measured in section D.

## B.5 Pyrefly 1.2.0 (`--preset strict`) — 17 errors

```
$ uvx pyrefly@1.2.0 check --python-interpreter-path /home/dreco/dev/depin/.venv/bin/python \
    --python-version 3.12 --preset strict --output-format min-text --progress-bar no \
    depin tests examples
 INFO 17 errors (32 suppressed)
```

`--permissive-ignores` produces the identical 17: the repository never writes a
`# pyright: ignore` without a paired `# type: ignore`.

Fourteen of the seventeen are one root cause:

```
ERROR depin/_core/bindings.py:301:44-47: Argument `Token[T] | type[T]` is not assignable to parameter
  `key` with type `Token[object] | type[object]` in function `depin._core.spec.FrameBinding.__init__` [bad-argument-type]
ERROR tests/unit/test_alias.py:101:48-53: Argument `Token[PostgresStore]` is not assignable to parameter
  `key` with type `GenericAlias | Token[object] | Underlying | str | type[object]` in function `...alias`
ERROR tests/unit/test_conditional.py:257:56-60: Argument `Token[int]` ... in function `FrozenContainer.explain`
ERROR tests/unit/test_decoration.py:249:47-51: Argument `Token[int]` ... in function `BindingCollector.decorate`
ERROR tests/unit/test_graph_render.py:124:31-35: Argument `Token[int]` ... in function `render_tree`
ERROR tests/unit/test_health.py:452:48-52: Argument `Token[int]` ... in function `HealthResult.__init__`
ERROR tests/unit/test_health_declaration.py:31:65-69: Argument `Token[int]` ... in function `_spec`
ERROR tests/unit/test_markers.py:41:15-18: Argument `Token[str]` ... in function `Named.__init__`
ERROR tests/unit/test_providers.py:462:64-67: Argument `Token[int]` ... in function `AnnotatedMeta.__init__`
ERROR tests/unit/test_asgi.py:55:12-31: Returned type `tuple[Token[str], str]` is not assignable to
  declared return type `tuple[ProviderKey, object]` [bad-return]
ERROR tests/unit/test_asgi.py:178:16-43: (same)
ERROR tests/unit/test_cli.py:69:12-27: (same)
ERROR tests/unit/test_wsgi.py:56:12-31: (same)
ERROR tests/unit/test_wsgi.py:90:16-55: (same)
```

**Root cause, isolated to a nine-line reproducer with no `depin` import:**

```python
# /tmp/typing-baseline/probe-variance/v.py
class Token[T]:
    __slots__ = ('name',)

    def __init__(self, name: str) -> None:
        self.name = name


def takes(key: Token[object]) -> None: ...


t: Token[int] = Token('n')
takes(t)
```

```
$ uvx mypy@2.3.1 --strict --python-version 3.12 v.py
Success: no issues found in 1 source file
$ uvx pyright@1.1.411 v.py            → 0 diagnostics
$ uvx ty@0.0.77 check v.py            → All checks passed!
$ uvx pyrefly@1.2.0 check --preset strict v.py
ERROR v.py:9:7-8: Argument `Token[int]` is not assignable to parameter `key` with type `Token[object]`
  in function `takes` [bad-argument-type]
```

`depin.Token[T]` declares `T` as a documented phantom parameter ("The type
parameter is phantom — it exists only for the static checker"). Under PEP 695
auto-variance, mypy, Pyright, Basedpyright and ty all infer an unused type
parameter as **covariant**; Pyrefly 1.2.0 infers it as **invariant**.

Second probe, narrowing the divergence to the unused case only:

```python
class Phantom[T]:  # T never appears in the body
    def __init__(self, name: str) -> None:
        self.name = name


class Used[T]:  # T appears in a return position
    def __init__(self, name: str) -> None:
        self.name = name

    def get(self) -> T: ...


T_co = TypeVar('T_co', covariant=True)


class Explicit(Generic[T_co]):
    def __init__(self, name: str) -> None:
        self.name = name


takes_phantom(Phantom[int]('a'))  # line 22
takes_used(Used[int]('b'))  # line 23
takes_explicit(Explicit[int]('c'))  # line 24
```

```
$ uvx pyrefly@1.2.0 check --preset strict v2.py
ERROR v2.py:22:15-32: Argument `Phantom[int]` is not assignable to parameter `k` with type `Phantom[object]`
```

Lines 23 and 24 pass. Pyrefly accepts the covariant relation when `T` is used
covariantly, and when the variance is declared explicitly with a legacy
`TypeVar(covariant=True)`. It rejects it only for the phantom parameter.

**Classification: checker divergence with real consumer impact.** It is
consumer-visible, not test-only: `ProviderKey` is a public alias containing
`Token[object]`, and every public API that takes a key — `alias`, `collect`,
`decorate`, `explain`, `DependencyGraph.find`/`node`, `Named(...)`, and the
`seed` return type in `ext.asgi`, `ext.wsgi`, `ext.cli` — rejects a
`Token[int]` under Pyrefly. Section C.5 reproduces it in ordinary consumer code
that imports only the public API. Note that PEP 695 offers no syntax to declare
variance explicitly, and AGENTS.md forbids mixing `TypeVar(...)` with PEP 695
syntax in the same module, so the design phase has a genuine decision here.

The remaining three Pyrefly errors are private-code diagnostics with no
consumer surface:

```
ERROR depin/_core/graph.py:88:50-52: Type of lambda parameter `kv` is unknown [implicit-any-lambda]
ERROR depin/_core/typeguards.py:26:43-48: Cannot determine the type parameter `T` for generic class `Token[T]` [implicit-any-type-argument]
ERROR tests/unit/test_graph_properties.py:298:41-45: Type of lambda parameter `case` is unknown [implicit-any-lambda]
```

## B.6 `tests/typing` alone

```
$ uvx mypy@2.3.1 --strict --warn-unreachable --python-executable .venv/bin/python tests/typing
(no output — clean)
$ uvx pyright@1.1.411 -p ... tests/typing
0 errors, 0 warnings, 0 informations
$ uvx basedpyright@1.39.10 -p ... tests/typing
0 errors, 0 warnings, 0 notes
$ uvx ty@0.0.77 check --output-format concise tests/typing
tests/typing/test_conformance.py:82:9: error[type-assertion-failure] Type `CoroutineType[Any, Any, str]`
  does not match asserted type `Awaitable[str]`
tests/typing/test_conformance.py:304:9: error[no-matching-overload] No overload of bound method
  `BindingCollector.bind` matches arguments
Found 2 diagnostics
$ uvx pyrefly@1.2.0 check --preset strict ... tests/typing
(no output — clean)
```

Exactly the two diagnostics the proposal recorded on 2026-08-31, unchanged at
ty 0.0.77. Line 304 is the intentional-negative suppression case; line 82 is
the exact-vs-assignability case.

Pyrefly is clean on `tests/typing` because the existing corpus never passes a
`Token[T]` where a `ProviderKey` is expected. That is a coverage gap, not
compatibility: section C's consumer corpus does, and Pyrefly fails there.

---

# C. Installed-wheel consumer baseline

## C.1 Build and wheel verification

Built outside the repository so nothing lands in the checkout's `dist/`:

```
$ git status --porcelain     # empty before building
$ uv build -o /tmp/typing-baseline/dist
Successfully built /tmp/typing-baseline/dist/pydepin-0.16.2.tar.gz
Successfully built /tmp/typing-baseline/dist/pydepin-0.16.2-py3-none-any.whl
```

Marker and contents verified by reading the zip's central directory directly,
not by importing the package:

```
$ python3 -c "
import zipfile
z = zipfile.ZipFile('dist/pydepin-0.16.2-py3-none-any.whl')
names = z.namelist()
print('depin/py.typed' in names, [n for n in names if 'py.typed' in n])
print('ext modules:', sorted(n for n in names if n.startswith('depin/ext/')))
print('total entries:', len(names))"
True ['depin/py.typed']
ext modules: ['depin/ext/__init__.py', 'depin/ext/asgi.py', 'depin/ext/cli.py',
 'depin/ext/fastapi.py', 'depin/ext/flask.py', 'depin/ext/litestar.py',
 'depin/ext/pytest.py', 'depin/ext/starlette.py', 'depin/ext/taskiq.py',
 'depin/ext/typer.py', 'depin/ext/wsgi.py']
total entries: 42

$ unzip -l dist/pydepin-0.16.2-py3-none-any.whl | grep -E "py.typed|RECORD|WHEEL"
        0  2020-02-02 00:00   depin/py.typed
       87  2020-02-02 00:00   pydepin-0.16.2.dist-info/WHEEL
     3283  2020-02-02 00:00   pydepin-0.16.2.dist-info/RECORD
```

Metadata:

```
Metadata-Version: 2.5
Name: pydepin
Version: 0.16.2
Requires-Python: >=3.12
Classifier: Typing :: Typed
Provides-Extra: click | fastapi | flask | litestar | pytest | starlette | taskiq | typer
entry_points.txt:
[pytest11]
depin = depin.ext.pytest
```

`py.typed` is present, has zero bytes (correct — it is a marker), is listed in
`RECORD`, and the distribution carries the `Typing :: Typed` classifier. A
`.dist-info/RECORD` membership assertion is the permanent guarantee the
proposal asks for; a plain `namelist()` check would miss a wheel whose RECORD
and payload disagree.

## C.2 Clean consumer project

Two virtual environments, both outside the repository, both fed the wheel file
rather than the checkout:

```
$ uv venv --python 3.12 consumer/.venv-core
$ uv pip install --python consumer/.venv-core/bin/python \
    /tmp/typing-baseline/dist/pydepin-0.16.2-py3-none-any.whl

$ uv venv --python 3.12 consumer/.venv-extras
$ uv pip install --python consumer/.venv-extras/bin/python \
    "pydepin[fastapi,click,typer,flask,litestar,starlette,taskiq,pytest] @ /tmp/typing-baseline/dist/pydepin-0.16.2-py3-none-any.whl"
```

Note: `uv pip install "<wheelpath>[extra]"` is a parse error
(`Expected package name starting with an alphanumeric character, found '['`);
the `name[extras] @ <path>` form is required. That is a real CI-script trap.

Extras environment resolved:

```
click 8.5.0 · fastapi 0.141.1 · flask 3.1.3 · litestar 2.24.0 · pytest 9.1.1
starlette 1.6.0 · taskiq 0.12.6 · typer 0.27.2 · pydepin 0.16.2
```

## C.3 Proof of isolation

Four independent proofs. The fourth is the decisive one.

**(1) Runtime resolution.**

```
$ echo "PYTHONPATH=[${PYTHONPATH-<unset>}] MYPYPATH=[${MYPYPATH-<unset>}]"
PYTHONPATH=[<unset>] MYPYPATH=[<unset>]

$ .venv-core/bin/python -c "
import depin, sys, os
print('depin.__file__ =', depin.__file__)
print('inside venv    =', depin.__file__.startswith(os.path.abspath('.venv-core')))
print('repo on sys.path:', [p for p in sys.path if 'dev/depin' in p])
print('sys.path =', sys.path)"
depin.__file__ = /tmp/typing-baseline/consumer/.venv-core/lib/python3.12/site-packages/depin/__init__.py
inside venv    = True
repo on sys.path: []
sys.path = ['', '.../cpython-3.12.13.../lib/python312.zip', '.../lib/python3.12',
            '.../lib-dynload', '/tmp/typing-baseline/consumer/.venv-core/lib/python3.12/site-packages']
```

**(2) The install is a wheel archive, not an editable or directory install.**

```
$ cat .venv-core/lib/python3.12/site-packages/pydepin-0.16.2.dist-info/direct_url.json
{"url":"file:///tmp/typing-baseline/dist/pydepin-0.16.2-py3-none-any.whl","archive_info":{}}
$ cat .venv-core/lib/python3.12/site-packages/pydepin-0.16.2.dist-info/INSTALLER
uv
```

`archive_info` — not `dir_info: {"editable": true}`. An editable install would
show the latter and a `__editable__*.pth` file. There is none:

```
$ find .venv-core/lib/python3.12/site-packages -name '*.pth' -exec sh -c 'echo "== {}"; cat {}' \;
== .venv-core/lib/python3.12/site-packages/_virtualenv.pth
import _virtualenv
$ ls .venv-core/lib/python3.12/site-packages/
depin  __pycache__  pydepin-0.16.2.dist-info  _virtualenv.pth  _virtualenv.py
$ ls -l .venv-core/lib/python3.12/site-packages/depin/py.typed
-rw-rw-r-- 3 dreco dreco 0 Sep  1 12:24 .../depin/py.typed
```

**(3) The consumer corpus reaches nothing private.**

```
$ grep -rn "depin\._core\|from depin import _" core ext neg
(none)
```

**(4) Negative control: remove `depin` and every checker must lose it.** A
third venv with nothing installed, checked with the same commands:

```
$ uv venv --python 3.12 .venv-empty

$ uvx mypy@2.3.1 --strict --python-executable .venv-empty/bin/python core/c01_container.py
core/c01_container.py:6: error: Cannot find implementation or library stub for module named "depin"  [import-not-found]

$ uvx pyright@1.1.411 -p pyright-empty.json
  core/c01_container.py:6:6 - error: Import "depin" could not be resolved (reportMissingImports)

$ uvx basedpyright@1.39.10 -p pyright-empty.json
  core/c01_container.py:6:6 - error: Import "depin" could not be resolved (reportMissingImports)

$ uvx ty@0.0.77 check --python .venv-empty core/c01_container.py
core/c01_container.py:6:6: error[unresolved-import] Cannot resolve imported module `depin`

$ uvx pyrefly@1.2.0 check --python-interpreter-path .venv-empty/bin/python --preset strict core/c01_container.py
ERROR core/c01_container.py:6:1-88: Cannot find module `depin` [missing-import]
```

**All five lose `depin` entirely.** Neither `PYTHONPATH`, nor the working
directory, nor any config file reaches `/home/dreco/dev/depin`. When the wheel
venv supplies `depin`, that venv is the only possible source.

**Answer to the proposal's open question "How should the harness prove wheel
import isolation on every platform?": run the identical checker commands against
an empty venv and require every one of them to report an unresolved-import
diagnostic.** It is a positive assertion about behaviour rather than an
enumeration of environment variables, so it is portable, and it catches any
future leak — a stray `.pth`, an `extraPaths` entry, a `conftest.py`, a
`MYPYPATH` — regardless of how it was introduced. Pair it with the
`direct_url.json` `archive_info` assertion from proof (2), which distinguishes a
wheel install from an editable one on every platform.

## C.4 Consumer corpus

`/tmp/typing-baseline/consumer/`, 1062 lines across 21 files, importing only
`depin`, `depin.errors`, and `depin.ext.*`:

| File | Proposal coverage area |
| --- | --- |
| `core/c01_container.py` | Container construction: fluent builder returns, `Registry` `|` composition, `Bindings` protocol, `singleton`/`scoped`/`transient` decorators, `include`, `freeze()` |
| `core/c02_keys.py` | Class keys, `Protocol` keys, `Token[T]`, tags, generic aliases, `Underlying`, `ProviderKey` |
| `core/c03_providers.py` | Classes, functions, callable instances, sync/async generators, sync/async context managers, awaitables, `value`, `scope_value`, `check=` |
| `core/c04_resolution.py` | `resolve`, `aresolve`, `__getitem__`, scoped resolution, generic preservation |
| `core/c05_injection.py` | Sync/async `@inject`, parameter preservation, explicit arguments, `injected()` |
| `core/c06_lifetimes.py` | `scope`, `ascope`, `override`, `ScopeFrame`, `Scope`, `close`/`reset`/`aclose` |
| `core/c07_registration.py` | `provides`, `alias`, `decorate`, `Condition`, `collect`, optional dependencies |
| `core/c08_diagnostics.py` | `graph()`, `nodes`/`roots`/`node`/`find`, `dot`, `mermaid`, `explain`, `warmup`/`awarmup`, `checks`, `health`/`ahealth` |
| `core/c09_hosting.py` | `Host`, `hosted_container`, `optional_hosted_container`, `CONTRACT_VERSION`, `depin.errors` |
| `ext/e01_fastapi.py` | `Inject[T]` on sync and async routes, mixed with ordinary FastAPI parameters |
| `ext/e02_asgi_wsgi.py` | `asgi.RequestScope[ScopeT, ReceiveT, SendT]`, `wsgi.RequestScope[EnvironT, StartResponseT]`, both `ASGIApp`/`WSGIApp` protocols, both `seed` callbacks |
| `ext/e03_cli.py` | `install[C: CommandContext]` with `click.Context`, `typer.Context` and a consumer's own structural context; `CommandContext.with_resource[T]` |
| `ext/e04_frameworks.py` | Flask/Litestar/Starlette middleware, `taskiq.MessageScope`, pytest `OverrideFactory`/`AsyncOverrideFactory` |
| `neg/n01`–`n08` | Negative fixtures, section D.7 |

Three assertions in the corpus were written as `assert_type` first and demoted
to assignability after measurement showed the exact form was dishonest. They
are annotated in place and analysed in E.3.

## C.5 Results

```
$ bash run-positives.sh
================ CORE-ONLY (wheel, no extras) ================
--- mypy ---         Success: no issues found in 9 source files          exit=0
--- pyright ---      0 errors, 0 warnings, 0 informations                exit=0
--- basedpyright --- 0 errors, 0 warnings, 0 notes                       exit=0
--- ty ---
core/c01_container.py:60:5: error[assert-type-unspellable-subtype] Type `<class 'Repo'>` does not match asserted type `type[Repo]`
core/c01_container.py:66:5: error[type-assertion-failure] Type `() -> Cache` does not match asserted type `() -> Cache`
core/c07_registration.py:46:5: error[assert-type-unspellable-subtype] Type `<class 'MemoryStore'>` does not match asserted type `type[MemoryStore]`
Found 3 diagnostics                                                      exit=1
--- pyrefly ---
ERROR core/c02_keys.py:39:36-40: Argument `Token[int]` is not assignable to parameter `key` with type
  `GenericAlias | Token[object] | Underlying | str | type[object]` in function `token_is_a_provider_key` [bad-argument-type]
ERROR core/c07_registration.py:51:48-54: Argument `Token[str]` ... in function `BindingCollector.alias`
ERROR core/c07_registration.py:51:59-65: Argument `Token[str]` ... in function `BindingCollector.alias`
                                                                         exit=1

================ EXTRAS (wheel + all 8 extras) ================
--- mypy ---         Success: no issues found in 13 source files         exit=0
--- pyright ---      0 errors, 0 warnings, 0 informations                exit=0
--- basedpyright --- 0 errors, 0 warnings, 0 notes                       exit=0
--- ty ---           (same 3 diagnostics as core-only)                   exit=1
--- pyrefly ---      (same 3, plus)
ERROR ext/e02_asgi_wsgi.py:33:16-51: Returned type `tuple[Token[str], str]` is not assignable to
  declared return type `tuple[ProviderKey, object] | None` [bad-return]
ERROR ext/e02_asgi_wsgi.py:55:16-58: (same, wsgi seed)
ERROR ext/e03_cli.py:35:16-43: (same, cli seed)
                                                                         exit=1
```

### Who is right, disagreement by disagreement

**Disagreement 1 — Pyrefly, 6 diagnostics, 1 root cause: `Token[T]` variance.**
`depin` writes `ProviderKey = ... | Token[object] | ...` and a consumer writes
`Token[int]`. The relevant consumer code is as ordinary as it gets:

```python
LEGACY = Token[str]('legacy')
MODERN = Token[str]('modern')
di = Container().value(MODERN, 'v2').alias(LEGACY, to=MODERN).freeze()
```

```python
def seed(scope: ASGIScope) -> tuple[ProviderKey, object] | None:
    return (TRACE, str(scope.get('path', '')))
```

**Pyrefly is wrong about the intended contract and right about the letter of
the annotation.** The typing spec's auto-variance algorithm tests covariance
before invariance, and four of five checkers conclude covariant for an unused
parameter; Pyrefly concludes invariant. But the divergence is only possible
*because* `Token[T]`'s `T` is phantom — a type parameter with no use site has no
variance the annotation actually pins down. Under the proposal's failure
taxonomy this is (4) checker defect and (1) public annotation defect at the same
time, and only the second is actionable inside `depin`. Impact if unresolved:
Pyrefly cannot be a blocking consumer gate.

**Disagreement 2 — ty, 2 × `assert-type-unspellable-subtype`.**

```python
@c.singleton()
class Repo: ...


assert_type(Repo, type[Repo])
```

ty infers `<class 'Repo'>` — a class-literal type that is a strict subtype of
`type[Repo]` — and says so in the rule name. **ty is right and the oracle is
wrong.** `ScopeDecorator.__call__` promises `type[T]`, and a class-literal
satisfies every operation `type[Repo]` promises. Exact equality is not the
honest promise here; `type[Repo]` assignability is. Same for
`assert_type(MemoryStore, type[MemoryStore])` after `@provides(Store)`.

**Disagreement 3 — ty, 1 × `type-assertion-failure` printing both sides
identically.**

```
core/c01_container.py:66:5: error[type-assertion-failure] Type `() -> Cache` does not match asserted type `() -> Cache`
```

from `assert_type(make_cache, Callable[[], Cache])` after `@c.transient()`.
ty distinguishes a function's own type from the `Callable` protocol, prints both
as `() -> Cache`, and rejects. **This is a ty limitation** — an
indistinguishable-in-output diagnostic is not actionable, and the two types are
mutually assignable. It is also the strongest argument in this report against
brittle message snapshots in the negative harness.

No disagreement anywhere in the corpus is a defect in `depin`'s consumer types
in the false-positive direction. Every false-positive disagreement is either an
oracle that should be assignability, a checker representation choice, or the
phantom-typevar variance question. The defects this baseline *did* find are all
in the false-negative direction (section D.7).

---

# D. Targeted probes

Probe file `/tmp/typing-baseline/probes/d_probe.py`, run in the extras venv.
Every row is a `reveal_type` at the named line.

## D.1 `Inject[T]` on a FastAPI route parameter

```python
@app.get('/p')
async def route(svc: Inject[Config], n: int = 1) -> int:
    reveal_type(svc)
    reveal_type(svc.value)
    reveal_type(n)
```

| Checker | `svc` | `svc.value` | `n` |
| --- | --- | --- | --- |
| mypy 2.3.1 | `d_probe.Config` | `int` | `int` |
| Pyright 1.1.411 | `Config` | `int` | `int` |
| Basedpyright 1.39.10 | `Config` | `int` | `int` |
| ty 0.0.77 | `Config` | `int` | `int` |
| Pyrefly 1.2.0 | `Config` | `int` | `int` |

**All five see `T`.** The most checker-sensitive construct in the library —
a `TYPE_CHECKING` PEP 695 alias `type Inject[T] = T` shadowing a runtime class
with `__class_getitem__` — is unanimous. `ext/e01_fastapi.py` also passes
`assert_type(svc, UserService)` under all five for sync routes, async routes,
`Inject[int]` over a `Token`, and routes mixing `Inject` with ordinary FastAPI
query and default parameters.

One cosmetic divergence, visible only in diagnostics: Pyright and Basedpyright
print the *alias* in error messages —

```
neg/n08:24:16 - error: Cannot access attribute "value" for class "Inject[UserService]"
```

— whereas ty says `Object of type Inject[UserService] has no attribute value`
and Pyrefly says `Object of class UserService has no attribute value`. All three
reject; only the rendering differs. A negative harness that matched on the type
name would be brittle here.

## D.2 `Token[T]` round trip

```python
PORT = Token[int]('port')
reveal_type(PORT)
reveal_type(di[PORT])
reveal_type(di.resolve(PORT))
reveal_type(di.aresolve(PORT))
reveal_type(di[Config])
```

| Checker | `PORT` | `di[PORT]` | `di.resolve(PORT)` | `di.aresolve(PORT)` | `di[Config]` |
| --- | --- | --- | --- | --- | --- |
| mypy | `Token[int]` | `int` | `int` | `Coroutine[Any, Any, int]` | `Config` |
| Pyright | `Token[int]` | `int` | `int` | `CoroutineType[Any, Any, int]` | `Config` |
| Basedpyright | `Token[int]` | `int` | `int` | `CoroutineType[Any, Any, int]` | `Config` |
| ty | `Token[int]` | `int` | `int` | `CoroutineType[Any, Any, int]` | `Config` |
| Pyrefly | `Token[int]` | `int` | `int` | `Coroutine[Unknown, Unknown, int]` | `Config` |

**`T` is preserved by all five through subscript, `resolve` and `aresolve`.** No
erasure to `Any`, unknown or `object` anywhere. `aresolve` differs only in the
awaitable's printed spelling; all four spellings are assignable to
`Awaitable[int]`, and `await di.aresolve(PORT)` is `int` under all five.

## D.3 The `@inject` decorator

```python
@di.inject
def handler(label: str, config: Config = injected(Config)) -> str: ...
@di.inject
async def ahandler(label: str, config: Config = injected(Config)) -> str: ...
```

| Checker | sync wrapper | `handler('a')` | async wrapper | `ahandler('a')` |
| --- | --- | --- | --- | --- |
| mypy | `def (label: str, config: Config =) -> str` | `str` | `def (label: str, config: Config =) -> Awaitable[str]` | `Awaitable[str]` |
| Pyright | `(label: str, config: Config = injected(Config)) -> str` | `str` | `... -> Awaitable[str]` | `Awaitable[str]` |
| Basedpyright | identical to Pyright | `str` | identical to Pyright | `Awaitable[str]` |
| ty | `(label: str, config: Config = ...) -> str` | `str` | `... -> CoroutineType[Any, Any, str]` | `CoroutineType[Any, Any, str]` |
| Pyrefly | `(label: str, config: Config = ...) -> str` | `str` | `... -> Awaitable[str]` | `Awaitable[str]` |

**Parameters and return type are preserved by all five, sync and async.** One
divergence: for an `async def`, `inject`'s two overloads

```python
@overload
def inject[**P, R](self, fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]: ...
@overload
def inject[**P, R](self, fn: Callable[P, R]) -> Callable[P, R]: ...
```

both match. mypy, Pyright, Basedpyright and Pyrefly select the first;
**ty selects the second**, so its result is `CoroutineType[Any, Any, str]`
rather than `Awaitable[str]`. Both are correct — `CoroutineType[Any, Any, str]`
is a `Awaitable[str]` — and this is the sole cause of the standing
`tests/typing/test_conformance.py:82` failure.

The wrapper keeps the injected parameter in its signature (with its marker
default). That is why `assert_type(handler, Callable[[str, int], str])` fails
under mypy with `Expression is of type "Callable[[str, int, Config], str]"`, and
why the consumer corpus asserts the *call site* instead.

## D.4 `bind`'s seven overloads

```python
reveal_type(Container().bind(Config))  # type[T]
reveal_type(Container().bind(cls_provider))  # Callable[..., T]
reveal_type(Container().bind(gen_provider))  # Callable[..., Generator[T]]
reveal_type(Container().bind(coro_provider))  # Callable[..., Awaitable[T]]
```

All five: `Container` for all four. **Every checker selects an overload whose
return is `Self`, so the observable result is identical.** The overloads differ
only in the accepted `source` shape, and all return `Self`; overload *selection*
is therefore not observable at the call site for `bind`. That is a design
finding in itself: a corpus cannot detect an overload-selection regression on
`bind` from the return type alone. The `check=` parameter is where selection
becomes observable, and `neg/n02` exercises it (D.7).

## D.5 Fluent-builder chaining and `freeze()`

```python
reveal_type(Container())
reveal_type(Container().bind(Config))
reveal_type(Container().bind(Config).value(PORT, 1))
reveal_type(Container().bind(Config).freeze())
reveal_type(Container().bind(Config).freeze().scope())
```

| Checker | `Container()` … `.value(...)` | `.freeze()` | `.scope()` |
| --- | --- | --- | --- |
| mypy | `Container` ×3 | `FrozenContainer` | `contextlib._GeneratorContextManager[ScopeFrame, None, None]` |
| Pyright / Basedpyright | `Container` ×3 | `FrozenContainer` | `_GeneratorContextManager[ScopeFrame, None, None]` |
| ty | `Container` ×3 | `FrozenContainer` | `_GeneratorContextManager[ScopeFrame, None, None]` |
| Pyrefly | `Container` ×3 | `FrozenContainer` | `_GeneratorContextManager[ScopeFrame]` |

Unanimous. `Self` on `BindingCollector` returns `Container` (not
`BindingCollector`) in every checker, so the fluent builder is safe. Pyrefly
prints `_GeneratorContextManager` with one argument; the class is generic in
three with defaults, so this is a rendering difference only. **A consumer corpus
must not `assert_type` on `_GeneratorContextManager[...]` — the spelling is not
portable.** Assert the `with`-bound value instead, which the corpus does
(`assert_type(frame, ScopeFrame)`, unanimous).

## D.6 Generic `RequestScope` and `install[C: CommandContext]`

```python
mw = ASGIRequestScope(d6_downstream, di)
reveal_type(mw)
reveal_type(ASGIRequestScope(d6_downstream, di, seed=seed))
reveal_type(install(ctx, di))
reveal_type(install)
reveal_type(ctx.with_resource(cm))  # ctx: CommandContext, cm: AbstractContextManager[int]
```

| Probe | mypy | Pyright / Basedpyright | ty | Pyrefly |
| --- | --- | --- | --- | --- |
| `mw` | `RequestScope[Mapping[str, object], object, object]` | same | same | same |
| with `seed=` | same | same | same | same |
| `install(ctx, di)` | `ScopeFrame` | `ScopeFrame` | `ScopeFrame` | `ScopeFrame` |
| `ctx.with_resource(cm)` | `int` | `int` | `int` | `int` |

`install`'s own type, rendered:

- mypy: `def [C <: depin.ext.cli.CommandContext] (ctx: C, container: FrozenContainer, *, seed: (def (C) -> tuple[...] | None) | None =) -> ScopeFrame`
- Pyright: `(ctx: C@install, container: FrozenContainer, *, seed: ((C@install) -> ...) | None = None) -> ScopeFrame`
- ty: `def install[C](ctx: C, container: FrozenContainer, *, seed: ((C, /) -> tuple[ProviderKey, object] | None) | None = None) -> ScopeFrame`
- Pyrefly: `[C: CommandContext](ctx: C, container: FrozenContainer, *, seed: ((C) -> tuple[ProviderKey, object] | None) | None = None) -> ScopeFrame`

**Yes — a consumer can annotate both without a suppression, under all five.**
`ext/e03_cli.py` binds `C` to `click.Context`, `typer.Context` and a consumer's
own class implementing `with_resource[T]` structurally, and asserts inside each
`seed` callback that the parameter arrives as the concrete context type
(`assert_type(c, click.Context)`, `assert_type(c, OwnContext)`) — unanimous.
`ext/e02_asgi_wsgi.py` does the same for `ASGIScope` (`Mapping[str, object]`)
and `Environ` (`MutableMapping[str, object]`).

The only failures on these files are Pyrefly's three `bad-return` diagnostics on
the `seed` return type, which are the `Token[T]` variance issue from B.5 again,
not a generics problem.

## D.7 Negative fixtures

Eight fixtures, one misuse each, no suppressions, run one file at a time.
`n01`–`n07` in the core-only venv, `n08` in the extras venv.

| Fixture | Misuse | mypy | Pyright | Basedpyright | ty | Pyrefly |
| --- | --- | --- | --- | --- | --- | --- |
| n01 | `di.resolve(42)` | reject | reject | reject | reject | reject |
| n02 | `bind(Database, check=ping)` where `ping(cache: Cache)` | reject | reject | reject | reject | reject |
| n03 | `Container().value(Token[int], 'not-an-int')` | **ACCEPT** | **ACCEPT** | **ACCEPT** | **ACCEPT** | reject |
| n04 | `di[Token[int]].upper()` | reject | reject | reject | reject | reject |
| n05 | `di.override(Config, Other())` | **ACCEPT** | **ACCEPT** | **ACCEPT** | **ACCEPT** | **ACCEPT** |
| n06 | `@inject`-wrapped `handler(123)` where `label: str` | reject | reject | reject | reject | reject |
| n07 | `Repo[User]` resolution returned as `Repo[Order]` | reject | reject | reject | reject | reject |
| n08 | `Inject[UserService]` used as if it had `.value` | reject | reject | reject | reject | reject |

Six of eight are unanimously rejected, each for the intended semantic reason —
`arg-type`/`reportArgumentType`/`invalid-argument-type`/`bad-argument-type` for
n01, n06; overload failure for n02; attribute access for n04, n08; return-type
for n07. Two are not.

### n05 — accepted by all five. Real public-annotation defect.

```python
# neg/n05_override_replacement_mismatch.py
di = Container().bind(Config).freeze()
with di.override(Config, Other()):  # Other has nothing to do with Config
    pass
```

```
--- mypy ---         exit=0
--- pyright ---      0 errors, 0 warnings, 0 informations    exit=0
--- basedpyright --- 0 errors, 0 warnings, 0 notes           exit=0
--- ty ---           All checks passed!                      exit=0
--- pyrefly ---                                              exit=0
```

### n03 — accepted by four of five. Same root cause.

```python
PORT = Token[int]('port')
Container().value(PORT, 'not-an-int')
```

```
--- mypy ---  exit=0     --- pyright --- exit=0     --- basedpyright --- exit=0
--- ty ---    All checks passed!   exit=0
--- pyrefly ---
ERROR neg/n03:9:33-45: Argument `Literal['not-an-int']` is not assignable to parameter `value`
  with type `int` in function `depin._core.bindings.BindingCollector.value` [bad-argument-type]
exit=1
```

**Mechanism, reduced to a 13-line reproducer with no `depin` import:**

```python
# /tmp/typing-baseline/probe-solve2/m.py
class Token[T]:
    def __init__(self, name: str) -> None:
        self.name = name


class A: ...


class B: ...


def override[T](key: type[T] | Token[T], replacement: T) -> None: ...
def value[T](token: Token[T], v: T) -> None: ...


override(A, B())  # line 12
value(Token[int]('p'), 'no')  # line 13
```

```
$ uvx mypy@2.3.1 --strict --python-version 3.12 m.py       (no output)
$ uvx pyright@1.1.411 m.py                                 (none)
$ uvx basedpyright@1.39.10 --level error m.py              0 errors, 0 warnings, 0 notes
$ uvx ty@0.0.77 check m.py                                 All checks passed!
$ uvx pyrefly@1.2.0 check --preset strict m.py
ERROR m.py:13:24-28: Argument `Literal['no']` is not assignable to parameter `v` with type `int`
  in function `value` [bad-argument-type]
```

`T` appears in both the key parameter and the value parameter, so the solver is
free to widen it to the join of the two arguments. For `override(A, B())` the
solver takes `T = A | B`, and `type[A]` is assignable to `type[A | B]` because
`type[...]` is covariant. Every checker accepts. For
`value(Token[int]('p'), 'no')` the same widening to `T = int | str` requires
`Token[int]` to be assignable to `Token[int | str]` — which is true under the
covariant reading four checkers use, and false under Pyrefly's invariant
reading. **Pyrefly catches the bug precisely because of the variance divergence
that makes it fail everywhere else.**

**Classification: (1) public annotation defect.** `Container.value` and
`FrozenContainer.override` promise that the replacement matches the key's type
and do not enforce it. This is a false negative in the public API, and the
proposal says explicitly that "an invalid call is accepted because an annotation
became too broad" is one of the failures the work exists to prevent. Not fixed
here, per instruction. Any fix must pin `T` to the key alone — the usual
spelling is a second, defaulted type parameter or a non-inferring position for
the value — and its correctness must be re-measured against all five, because
Pyrefly and the other four will disagree about whether it worked.

---

# E. Feasibility findings

## E.1 Which checker/Python-target combinations are worth running

The consumer corpus was re-run at every supported language target.

```
$ for v in 3.12 3.13 3.14; do uvx mypy@2.3.1 --strict --warn-unreachable --python-version $v \
    --python-executable .venv-extras/bin/python --no-incremental core ext; done
(3.12) Success  (3.13) Success  (3.14) Success

$ uvx pyright@1.1.411 -p pyright-extras.json --pythonversion 3.13   → 0 errors
$ uvx pyright@1.1.411 -p pyright-extras.json --pythonversion 3.14   → 0 errors
$ uvx ty@0.0.77 check --config-file ty-extras.toml --python-version 3.13  → same 3 diagnostics
$ uvx ty@0.0.77 check --config-file ty-extras.toml --python-version 3.14  → same 3 diagnostics
$ uvx pyrefly@1.2.0 check -c pyrefly-extras.toml --preset strict --python-version 3.13  → 6 errors
$ uvx pyrefly@1.2.0 check -c pyrefly-extras.toml --preset strict --python-version 3.14  → 6 errors
```

**Byte-identical results at 3.12, 3.13 and 3.14 for every checker.** The
language-target axis is redundant for the consumer contract at the current
corpus: `depin` targets `>=3.12`, uses PEP 695 throughout, and reaches for
nothing whose typeshed definition is version-gated. The meaningful axis is
`{5 checkers} × {core-only, all-extras}` = 10 jobs at one Python target, not 30.
The design should keep a single scheduled multi-target run as a regression
detector and justify dropping the per-PR target matrix with a re-run of this
measurement.

Redundancy that does **not** hold: stock Pyright vs Basedpyright. They agreed on
every `reveal_type` in section D —

```
$ diff d-pyright.txt d-bpr.txt
IDENTICAL to stock pyright
```

— but Basedpyright 1.39.10 is built on pyright 1.1.412 while stock is 1.1.411,
and Basedpyright's `reportAny`/`reportExplicitAny` have no stock equivalent.
They are the same engine at different commits with different rule sets. Running
both costs ~5 s and is the only way to satisfy the proposal's stock-Pyright
criterion.

## E.2 What a checker cannot express

| Capability | mypy | Pyright | Basedpyright | ty | Pyrefly |
| --- | --- | --- | --- | --- | --- |
| Reject `Any` leakage at a call site | `--disallow-any-expr` (all-or-nothing, unusable with third-party extras) | `reportUnknown*` in strict | `reportAny`, `reportExplicitAny` — the most precise of the five | **no equivalent** | `explicit-any`, `implicit-any-*` — only at `--preset all`, which also enables lint |
| Named strict mode | `--strict` | `typeCheckingMode: strict` | same | **none** — per-rule severity only (`--error all`) | `--preset strict` |
| Honour the repo's existing `# type: ignore[code]` | yes | yes | yes | **no** | yes |
| Honour `# pyright: ignore[...]` | n/a | yes | yes | **no** | only with `--permissive-ignores` |
| Distinguish a class-literal from `type[X]` in `assert_type` | no | no | no | yes (`assert-type-unspellable-subtype`) | no |
| Stable release line | yes (2.x) | yes (1.1.x) | yes (1.x) | **no — 0.0.x, no stable API** | yes (1.x), 8 months old |
| Config discoverable from `pyproject.toml` today | yes | **no section exists** | yes | yes | **no section exists** |

`ty` cannot express anti-`Any` checking, and this matters: the proposal requires
"The suite detects `Any` or unknown leakage at type-dependent public call sites."
ty can contribute exact `assert_type` oracles but cannot contribute an
anti-erasure rule. Basedpyright and mypy must carry that requirement.

`ty` is also the only checker with no stable release line. Its own CI job in
this repository already records that: "ty is still on 0.0.x versioning with no
stable API, and its own docs warn that diagnostics can change between any two
releases."

## E.3 Exact vs assignability — the proposal's open question

**Answer for the existing corpus: exactly one of the repository's 80
`assert_type` cases promises exact equality where only assignability is honest.**

```
$ grep -n "assert_type(.*Awaitable\|assert_type(.*Coroutine" tests/typing/*.py
tests/typing/test_conformance.py:82:        assert_type(handler(label='n'), Awaitable[str])
$ grep -n "assert_type(.*type\[" tests/typing/*.py        → (none)
$ grep -n "assert_type(.*Callable" tests/typing/*.py      → (none)
$ grep -n "assert_type(.*ContextManager\|assert_type(.*Generator" tests/typing/*.py  → (none)
```

`test_conformance.py:82` is the only one. It fails under ty and passes under the
other four, for the overload-selection reason in D.3. `CoroutineType[Any, Any, str]`
preserves every operation `Awaitable[str]` promises, so ty's result satisfies the
documented contract and the oracle is wrong, not the annotation.
**Correct form: an assignability witness —**

```python
pending: Awaitable[str] = handler('n')
```

Everything else in the existing corpus is honestly exact. The near-miss is
`test_conformance.py:166`, `assert_type(di.graph().node(Service).shape, ProviderShape)`,
which is safe because it reads a *declared attribute* of `GraphNode` rather than
an enum member expression. The unsafe form is
`assert_type(Scope.SINGLETON, Scope)` — every checker narrows a member access to
its literal member type:

```
core/c06_lifetimes.py:47: error: Expression is of type "Literal[Scope.SINGLETON]", not "Scope"  [assert-type]
```

The repository does not contain that form. It must not acquire one.

Three further categories were discovered while authoring the consumer corpus.
Each was written as `assert_type` first and demoted after measurement; the
design specification should classify them as assignability up front:

1. **Decorator-returned classes.** `assert_type(Repo, type[Repo])` after
   `@c.singleton()` — ty infers the class-literal `<class 'Repo'>`. Assignable
   to `type[Repo]`; not equal.
2. **Decorator-returned functions.** `assert_type(make_cache, Callable[[], Cache])`
   after `@c.transient()` — ty distinguishes the function type from the
   `Callable` protocol and prints both identically.
3. **`@inject` wrapper signatures.** `assert_type(handler, Callable[[str, int], str])`
   is false under every checker: the wrapper's real type is
   `Callable[[str, int, Config], str]`, because the injected parameter survives
   with its marker default. The honest contract is *call-site* preservation
   (`assert_type(handler('a', 1), str)`), not signature identity.
4. **Context-manager spellings.** `_GeneratorContextManager[ScopeFrame, None, None]`
   (mypy/Pyright/ty) vs `_GeneratorContextManager[ScopeFrame]` (Pyrefly). Assert
   the `with`-bound value, never the manager.
5. **Awaitables from `aresolve`.** `Coroutine[Any, Any, T]` /
   `CoroutineType[Any, Any, T]` / `Coroutine[Unknown, Unknown, T]`. Assert
   `await`-ed results, or use an `Awaitable[T]` witness assignment.

The rule that falls out: **`assert_type` is honest for a nominal class, a
`Protocol`, a parameterised generic of a `depin` type, a builtin, `None`, and a
union of those. It is dishonest for anything a decorator returned, anything
awaitable, any context manager, and any enum member expression.** Those five
categories need typed-assignment witnesses.

## E.4 Wall-clock cost

Every timing is total wall clock including `uvx` resolution against a warm uv
cache, on the host named at the top. Both figures are cold (no incremental
cache) — the realistic CI cost.

**Repository source, 139 files:**

| Checker | Wall clock |
| --- | --- |
| mypy 2.3.1 | 22.3 s |
| stock Pyright 1.1.411 | 13.7 s |
| Basedpyright 1.39.10 | 14.9 s |
| ty 0.0.77 | **1.1 s** |
| Pyrefly 1.2.0 | **1.9 s** |

**Consumer corpus, 13 files / 1062 lines, extras venv:**

| Checker | Wall clock |
| --- | --- |
| mypy 2.3.1 | 14.8 s |
| stock Pyright 1.1.411 | 4.9 s |
| Basedpyright 1.39.10 | 4.8 s |
| ty 0.0.77 | **0.5 s** |
| Pyrefly 1.2.0 | **0.8 s** |

Five blocking consumer gates across two install modes cost roughly
`2 × (14.8 + 4.9 + 4.8 + 0.5 + 0.8) ≈ 50 s` of checker time, plus wheel build
and two `uv pip install` runs. The dominant cost is mypy's cold start on a
13-file corpus (14.8 s), which is startup, not analysis. Adding stock Pyright to
the *source* gate costs 13.7 s on top of the existing 37 s. **Five blocking
consumer gates are affordable; the Python-target matrix (E.1) is what would make
them expensive, and E.1 shows it buys nothing.**

## E.5 Feasibility verdict per checker

| Checker | Blocking consumer gate today? | What blocks it |
| --- | --- | --- |
| mypy 2.3.1 | **yes** | nothing. Zero diagnostics, both modes, three targets |
| stock Pyright 1.1.411 | **yes**, once a config is written | no `[tool.pyright]` section exists; the config must avoid the two traps in A.2 (absolute `include`, `pythonPath`) |
| Basedpyright 1.39.10 | **yes** | nothing. Already the repo gate; `reportAny` also clean on the consumer corpus |
| ty 0.0.77 | **no, today** | 3 corpus diagnostics, all oracle/representation; fixable by re-spelling three assertions as assignability. Then the blocker is policy, not behaviour: 0.0.x with no stable API and no anti-`Any` rule |
| Pyrefly 1.2.0 | **no** | 6 consumer diagnostics from one unresolved question — phantom `Token[T]` variance. Requires either a `depin` annotation change or an accepted upstream divergence |

## E.6 Does anything make the proposal's goal impossible?

No. Two things make it harder than the proposal assumes.

1. **The `Token[T]` phantom parameter has no portable variance.** PEP 695 gives
   no syntax to declare variance, so `depin` cannot state the intent that four
   checkers infer and one does not. Every available remedy has a cost: reverting
   `Token` to `TypeVar(covariant=True)` violates AGENTS.md's ban on mixing the
   two forms in one module; giving `T` a covariant use site (e.g. a
   `TYPE_CHECKING`-only method returning `T`) adds a member the class does not
   want; widening the public `ProviderKey` alias to accept any `Token[...]`
   weakens the annotation. Until this is decided, "all five blocking" is
   unreachable, and this is the single decision the design specification most
   needs to make.
2. **The corpus proved two false negatives in the public API before a single
   line of the compatibility suite was written** (D.7, n03 and n05). The
   proposal's acceptance criterion "Every checker rejects the required negative
   fixtures for the intended reasons" cannot be met by adding checkers; it
   requires changing `Container.value` and `FrozenContainer.override`. That is
   implementation work the proposal did not anticipate, and it must land before
   the negative corpus can be green.

Everything else the proposal asks for is demonstrably reachable today: the wheel
carries `py.typed`, isolation is provable by a portable method, `Inject[T]`
survives all five checkers, generics are preserved through every public
type-dependent call, and no `Any` reaches any core public call site.

---

# Repository state

```
$ git status --porcelain
?? .superpowers/
$ git diff --stat
(empty)
```

No tracked file is modified. Two notes:

1. **The branch advanced by one commit during this session, from a concurrent
   process, not from this baseline.** Midway through the work
   `git status --porcelain` briefly showed
   ` M specs/2026-08-28-roadmap-1.0-design.md` (mtime `2026-09-01 12:43:34`);
   it is now committed as `07c0743 docs: sequence the two proposals ahead of the
   freeze`, authored by André Lopes, touching that one file and nothing else.
   No file under `depin/`, `tests/` or `examples/` changed, so every measurement
   in this report remains valid for the current HEAD.
2. **`.superpowers/typing-baseline.md` — this file — is not covered by any
   ignore rule.** `git check-ignore -v .superpowers/typing-baseline.md` exits 1.
   The only ignore rule under that tree is `.superpowers/sdd/.gitignore`
   containing `*`, which covers `.superpowers/sdd/` and nothing above it.
   Writing this report at the requested path therefore adds `?? .superpowers/`
   to `git status`. No `.gitignore` was edited to hide it.

Nothing under `depin/`, `tests/`, `examples/`, `docs/`, `pyproject.toml` or
`.github/` was written by this baseline. Every experiment ran under
`/tmp/typing-baseline/`. The one repository-local side effect is `.mypy_cache/`,
written by `uv run mypy` and already covered by `.gitignore`.

## Reproduction artifacts

```
/tmp/typing-baseline/
├── dist/pydepin-0.16.2-py3-none-any.whl      # the wheel under test
├── pyrightconfig-src.json                     # stock Pyright, source corpus
├── consumer/
│   ├── .venv-core   .venv-extras   .venv-empty
│   ├── core/c01..c09*.py   ext/e01..e04*.py   neg/n01..n08*.py
│   ├── pyright-{core,extras,neg-core,neg-extras}.json
│   ├── bpr-{core,extras,neg-core,neg-extras,extras-any}.json
│   ├── ty-{core,extras}.toml   pyrefly-{core,extras}.toml
│   └── run-positives.sh   run-negatives.sh
├── probes/d_probe.py                          # section D reveal_type probes
├── probe-ignore/p.py                          # suppression semantics (A.6)
├── probe-variance/v.py  v2.py                 # Token variance (B.5)
├── probe-solve2/m.py                          # bidirectional solve (D.7)
└── logs/                                      # raw output of every run above
```
