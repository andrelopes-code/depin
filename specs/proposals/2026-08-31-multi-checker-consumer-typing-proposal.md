# Proposal: consumer typing compatibility across common type checkers

Date: 2026-08-31
Status: accepted and implemented in Step 6, released in 0.17.0
Scope: public typing contract, distribution artifact, and compatibility verification

## Outcome

Taken from the queue and closed by Step 6. The design is in
`specs/2026-09-01-step-6-consumer-typing-design.md`, the plan in
`specs/plans/2026-09-01-step-6-consumer-typing.md`, and the evidence — normal
results and fault injection — in
`specs/evidence/2026-09-01-step-6-consumer-typing.md`. The support policy the
proposal asked for is `docs/support-policy.md`.

Two items are routed onward rather than delivered, and the evidence report says
so item by item:

- The two false negatives this work discovered — `FrozenContainer.override`
  accepting a replacement of an unrelated type, and `Container.value` accepting
  a value the token does not carry — go to the Step 8 surface review, which is
  the last window in which a call shape may change. They are gated meanwhile as
  divergence fixtures, on each checker's verdict rather than on rejection.
- The request to test the oldest supported version of each stable checker line
  beside the current one is deferred to the weekly forward probe. Exactly one
  version of each checker has been measured, so naming a lower minimum today
  would be a support claim with no evidence behind it.

## Nature of this document

This document proposes a future body of work. It is deliberately not a design
specification and not an implementation plan. The agent that takes this proposal
from the queue must first investigate the current checker behavior, make the
remaining design decisions explicit, write a design specification, obtain review,
and only then produce an implementation plan.

The proposal is detailed enough to preserve the intended outcome and the reasons
behind it. File layout, scripts, job decomposition, and the order of code changes
belong in the later design and plan.

## Executive summary

`depin` is a type-first library. Its type annotations are part of the product, not
an optional developer aid. A valid consumer program should receive precise types
from the installed package without false diagnostics, loss of generic information,
or silent degradation to `Any` or an unknown type.

The project should establish a supported checker matrix consisting of:

- mypy;
- stock Pyright;
- Basedpyright;
- ty;
- Pyrefly.

Support should be measured from the perspective of a separate consumer that
installs the built wheel. All five checkers should be blocking gates for this
consumer contract. Mypy and Basedpyright should continue to check the complete
repository in strict mode. Broader source checks and forward-looking runs against
new checker releases may remain advisory when they test properties beyond the
consumer contract.

The future work must introduce static type tests that make inference observable.
Exact type assertions should protect types that are promised exactly; assignability
tests should protect semantic contracts where different but equivalent or narrower
representations are valid. Negative fixtures should prove that invalid uses remain
invalid. The suite must also prove that it is testing the wheel rather than the
source checkout and must be demonstrated to fail under representative mutations.

## Current position

At the time this proposal was written:

- Basedpyright and mypy check `depin`, `tests`, and `examples` as blocking CI
  gates. Both are configured in strict mode and run against the supported Python
  version matrix.
- The existing conformance module uses `typing.assert_type` to exercise many
  public call sites, but it runs inside the repository and therefore does not by
  itself prove the experience of an independently installed consumer.
- ty runs in an advisory CI job whose command always exits successfully. Its
  diagnostics do not block a merge.
- Stock Pyright is not run independently from Basedpyright.
- Pyrefly has no native project configuration and does not run in CI.
- The source tree contains `depin/py.typed`, and a locally built wheel was observed
  to contain the marker. A future artifact test should turn that observation into
  a permanent guarantee.

Point-in-time exploratory runs are encouraging but are not support evidence:

- Pyrefly 1.2.0 reported no active errors for the existing core and FastAPI public
  conformance modules when checked directly.
- ty 0.0.75 passed the FastAPI conformance module. It reported two diagnostics in
  the core module: one because it inferred a concrete coroutine subtype where the
  test asserted exact equality with `Awaitable[str]`, and one on an intentionally
  invalid call carrying suppressions written for mypy and Pyright.

Those results show that the current test harness itself is not fully portable.
They do not demonstrate a consumer-facing defect in those two cases, and they do
not protect future changes.

## Problem statement

The current policy can allow a merge that preserves mypy and Basedpyright while
degrading another common checker. A consumer may then experience one or more of
the following:

- a generic result becomes `Any`, unknown, or `object`;
- an overload that should match a valid call is rejected;
- a decorator loses the wrapped callable's parameters or return type;
- a `Token[T]`, protocol key, generic alias, or collection loses `T`;
- valid synchronous or asynchronous injection produces a false diagnostic;
- an optional integration exposes less precise types than the core API;
- a checker reports diagnostics originating from normal use of the installed
  package;
- an invalid call is accepted because an annotation became too broad.

These failures are especially damaging for `depin` because precise dependency
types are a central reason to adopt the library. Runtime tests cannot detect them.
Checking the implementation with one or two tools also cannot prove how every
supported checker interprets the installed public surface.

## Proposed support contract

A checker is supported only when all of the following are true for the checker
versions named by the project's published support policy:

1. A clean consumer project can install the released wheel and discover its inline
   types through standard packaging metadata.
2. Valid representative uses of every public API area produce no diagnostics.
3. Values returned from type-dependent APIs preserve their promised concrete or
   generic types.
4. Public decorators and wrappers preserve callable parameters, sync/async
   behavior, and return types.
5. APIs that promise an interface by assignability remain assignable even if a
   checker chooses a valid narrower representation.
6. Representative invalid calls are rejected rather than accepted through
   `Any`, unknown types, or an over-broad overload.
7. The checker is a required CI gate for the consumer contract; a job that uses
   `continue-on-error`, discards the exit status, or unconditionally exits zero
   does not establish support.
8. The tested checker and Python language-target versions are recorded and
   reproducible.

The support statement must not claim compatibility with every past and future
release of every tool. Type checkers evolve independently and do not all provide
the same stability guarantees. The policy should name a bounded, tested version
line and define how it advances.

## Goals

- Make consumer-visible type inference a tested public contract.
- Provide blocking compatibility coverage for mypy, Pyright, Basedpyright, ty,
  and Pyrefly.
- Exercise the artifact that users install rather than relying exclusively on
  imports from the source checkout.
- Detect both false positives on valid code and false negatives on invalid code.
- Prevent silent erasure to `Any`, unknown types, or an unjustifiably broad type.
- Cover the core package and the FastAPI integration without introducing runtime
  dependencies into the core.
- Keep checker-specific mechanics in runners and configuration while preserving
  one semantic contract for the public API.
- Define an honest version and upgrade policy that offers reproducibility and
  early warning of upstream changes.
- Give contributors a local command that reproduces each required CI result.

## Non-goals

- Requiring every checker to produce identical diagnostic wording or error codes.
- Requiring every checker to print the same internal representation when the
  representations are semantically equivalent under the documented contract.
- Promising support for every Python type checker in existence.
- Promising support for checker releases that the project has never tested.
- Making all five tools authoritative over every private implementation detail.
- Adding duplicate `.pyi` stubs merely to avoid maintaining the inline public
  annotations. A separate stub surface should require a compelling design reason.
- Silencing incompatibilities with broad exclusions, `Any`, casts, or unexplained
  checker-specific ignores.
- Replacing runtime, doctest, integration, or documentation verification with
  static tests.

## Recommended verification model

The recommended model has three complementary layers.

### Layer 1: implementation quality gates

Mypy and Basedpyright should continue to check the complete repository in strict
mode as required gates. This preserves the existing discipline over private code,
tests, examples, and public annotations.

The future design may decide whether stock Pyright can also be a complete-source
gate without duplicating Basedpyright's signal excessively. That decision must not
weaken its required consumer-contract gate.

### Layer 2: installed-consumer contract gates

All five supported checkers should run the same semantic consumer corpus against
an installed wheel. These jobs are the authoritative compatibility guarantee and
must block merges.

The environment must ensure that:

- the wheel is built before the checks;
- the wheel contains `depin/py.typed` and the expected package metadata;
- the consumer is located outside the repository source path;
- the wheel, not an editable install or checkout import, supplies `depin`;
- `PYTHONPATH`, the current directory, and test configuration cannot accidentally
  resolve the source checkout;
- each checker uses an explicit native configuration rather than silently
  importing another checker's configuration;
- core-only checks do not gain optional framework dependencies accidentally;
- FastAPI checks install and exercise the declared optional extra.

### Layer 3: forward and implementation diagnostics

Advisory jobs may run additional full-source checks with stock Pyright, ty, and
Pyrefly, and may probe the newest available checker releases. Their purpose is to
find future incompatibilities before a supported version is advanced.

An advisory job must remain visible and actionable. It should preserve the real
exit status in its report, and recurring failures should be tracked. Advisory
coverage must not be described as supported coverage and must not substitute for
the blocking consumer matrix.

## Static type-test semantics

The future test corpus should distinguish several kinds of promise instead of
using one assertion mechanism indiscriminately.

### Exact inference

Use `typing.assert_type` when the public API promises an exact result, especially
where an input type determines an output type. Examples include resolving
`Token[int]` as `int`, resolving `Repo[User]` as `Repo[User]`, and preserving the
return type of a decorated provider.

These assertions should fail if the result becomes `Any`, unknown, `object`, an
incorrect union, or a generic with the wrong argument.

### Assignability and valid narrowing

Use typed assignments, protocol witnesses, or typed helper parameters when the
contract is assignability rather than identical internal representation. For
example, a checker may infer a concrete coroutine type that is a valid subtype of
`Awaitable[str]`. Rejecting that result because its printed type is narrower would
test the checker, not `depin`.

The later design specification must classify each case as exact or assignable and
must document why. A difference is acceptable only when it preserves every
operation promised by the public signature.

### Anti-erasure checks

The suite must explicitly guard against `Any` and unknown types. Strict checker
settings, exact assertions, generic member access, and targeted checker-native
diagnostics may all contribute. Passing an assignment alone is insufficient
because `Any` can satisfy assignments in both directions.

No supported positive fixture may depend on a checker-specific suppression to
hide an erased type.

### Negative conformance

Separate fixtures should contain representative invalid calls and must fail for
the intended semantic reason. Each fixture should isolate a small misuse so that
an unrelated diagnostic cannot make the test pass accidentally.

The harness should verify the checker exit status and the location or diagnostic
category needed to identify the intended failure. It should avoid brittle
snapshots of complete human-readable messages.

Negative cases should include wrong provider signatures, incompatible health
checks, invalid decorator relationships, incompatible aliases or collection
members, and incorrect injection call shapes where the public annotations promise
rejection.

### Zero-diagnostic positive fixtures

Valid consumer fixtures must complete with zero diagnostics. Filtering known
errors out of their output is not compatibility. If a checker has a genuine bug,
the version policy and upstream-issue process should handle it rather than hiding
the error in the consumer corpus.

## Required public-surface coverage

The future design should inventory every symbol re-exported from `depin`, every
public exception surface whose typing affects control flow, and
`depin.ext.fastapi`. It should maintain a coverage map so that a new public symbol
cannot be added without an explicit type-test decision.

At minimum, the corpus should cover the following areas:

| Area | Consumer contracts to protect |
| --- | --- |
| Container construction | Fluent builder return types, registry composition, and `freeze()` |
| Keys | Class keys, `Protocol` keys, `Token[T]`, tags, generic aliases, and `Underlying` |
| Providers | Classes, functions, callable instances, sync and async generators, values, and resources |
| Resolution | `resolve`, `aresolve`, subscription, scoped resolution, and generic preservation |
| Injection | Sync wrappers, async wrappers, parameter preservation, explicit arguments, and `injected()` |
| Lifetimes | Scope context managers, async scopes, overrides, and frame types |
| Registration features | `provides`, aliases, decoration, conditions, collections, and optional dependencies |
| Diagnostics and operations | Graph views, renderers, explanation, warmup, checks, and health reports |
| FastAPI | `Inject[T]`, route parameter inference, async endpoints, and optional-extra isolation |

The inventory should include both ordinary classes and structural protocols, as
these often expose differences in overload selection and variance among checkers.

## Shared corpus and checker adapters

The preferred architecture is one semantic corpus with thin checker-specific
drivers or configurations. Duplicating entire fixtures per checker would allow
the declared contracts to drift.

Small checker-specific adaptations are acceptable only for tool invocation,
configuration syntax, or expressing an oracle that has no portable spelling.
They must not weaken the expected public type. Any unavoidable semantic divergence
must be documented in the support policy and justified in the future design.

The corpus should be ordinary consumer code. It should import only documented
public modules and must never depend on `depin._core`.

## Version and Python-target policy

The future design must define exact initial versions from fresh evidence rather
than copying the exploratory versions in this proposal blindly.

The policy should provide two complementary properties:

- **Reproducible gates:** required CI and local commands use recorded versions so
  that the same commit produces the same compatibility result.
- **Forward detection:** scheduled or dependency-update jobs probe newer releases
  and surface incompatibilities before the supported set advances.

For stable checker lines, the design should evaluate testing both the oldest
supported version and the current supported version. For a pre-stable line such as
ty, the guarantee may need to name a narrower tested version set. Before a `depin`
release, the latest-probe results must be reviewed: the project should either make
the new release green, retain and document the supported ceiling, or document a
verified upstream blocker.

The consumer contract should be evaluated for every supported Python language
target that can change annotation interpretation. Free-threaded and ordinary
interpreters with the same language version need not duplicate static checks
unless a checker demonstrably treats them differently. The future design may
optimize the CI matrix, but it must show that the optimization does not omit a
meaningful language target.

## CI and contributor experience

Required jobs should identify the checker and target clearly. They must fail on an
unexpected diagnostic, a missing expected negative diagnostic, a packaging error,
or accidental import from the checkout.

The future implementation should provide:

- a documented local entry point for the complete consumer compatibility suite;
- a focused local command for each checker;
- CI summaries that retain enough diagnostic context to reproduce failures;
- a PR checklist that reflects all required type gates;
- support-policy documentation naming the checker and Python target versions;
- release-process guidance for advancing checker versions.

CI convenience must not make an advisory result look required or a required
result look optional.

## Failure classification and remediation principles

When a checker disagrees with the contract, the implementation team should
classify the failure before changing annotations:

1. **Public annotation defect:** improve the overload, protocol, generic shape, or
   API so the real contract is expressed naturally.
2. **Invalid test oracle:** replace exact equality with assignability, or vice
   versa, based on the documented API promise.
3. **Harness or packaging defect:** correct isolation, configuration, wheel
   contents, or the expected negative failure.
4. **Checker defect:** reduce the behavior to a minimal external reproducer,
   report or link the upstream issue, and use the version policy rather than a
   broad suppression to retain an honest support statement.
5. **Intentional checker divergence:** document why both results satisfy the same
   semantic contract and encode that contract without weakening it.

The repository's existing prohibition on `Any`, blanket ignores, casts used as
silencers, and unexplained suppressions applies to this work. Supporting more
checkers must improve the public model rather than accumulate checker-specific
debt.

## Acceptance criteria for the future implementation

The future design may refine mechanics, but a completed implementation should not
claim success until all of the following are demonstrated:

- A wheel-built, isolated consumer compatibility suite is a required CI gate.
- Mypy, stock Pyright, Basedpyright, ty, and Pyrefly all pass the positive consumer
  corpus with zero diagnostics.
- Every checker preserves the exact or assignable types classified by the corpus,
  including generic arguments and callable signatures.
- Every checker rejects the required negative fixtures for the intended reasons.
- The suite detects `Any` or unknown leakage at type-dependent public call sites.
- Core and FastAPI consumer scenarios are covered without violating the zero
  runtime-dependency rule for the core.
- The built wheel is proven to contain `depin/py.typed`, and the consumer is proven
  to import from that wheel.
- Stock Pyright is executed independently; a Basedpyright result is not counted as
  a stock Pyright result.
- ty and Pyrefly consumer jobs propagate their real exit status and cannot pass
  unconditionally.
- No positive conformance case relies on a checker-specific suppression.
- The public API inventory has an explicit type-test coverage decision for every
  exported symbol or API family.
- Contributor documentation and the support policy describe the same matrix that
  CI enforces.
- Checker versions and Python language targets are recorded reproducibly.
- Representative fault injection proves the suite is sensitive. At minimum, the
  evidence should show that degrading a type-dependent overload or generic return
  makes all relevant checker jobs fail, and that removing the wheel's typing
  marker makes the artifact/consumer guard fail.
- The ordinary repository gate remains green after the compatibility work.

## Alternatives considered

### Make all five tools blocking over the complete repository

This offers maximal internal cross-checking but conflates consumer compatibility
with private implementation differences. It is likely to create maintenance work
that does not improve a user's experience, especially while some checkers evolve
quickly. Additional full-source coverage is valuable as an advisory signal, not as
the primary definition of support.

### Check only the public modules inside the source checkout

This is inexpensive and resembles the current conformance module, but it can miss
packaging mistakes, a missing typing marker, accidental private imports, and path
or configuration leakage. It should remain a fast developer aid, not the complete
support proof.

### Publish separate stubs for checker compatibility

This creates two public type surfaces that can drift and weakens the type-first
discipline of the implementation. It should be considered only if a future design
proves that correct inline annotations cannot express the contract portably.

## Questions the future design specification must resolve

The proposal fixes the outcome but intentionally leaves these implementation
choices to the design phase:

- How should the shared consumer corpus and the negative fixtures be organized?
- Which current checker releases establish the initial minimum and current tested
  versions?
- Which checker/Python-target combinations must run on every pull request, and
  which can run on a scheduled cadence without weakening the guarantee?
- How should the harness prove wheel import isolation on every platform?
- Which current `assert_type` cases promise exact equality, and which promise only
  assignability?
- What checker-native settings are the closest honest equivalent of strict
  consumer checking for ty and Pyrefly?
- How should expected negative diagnostics be identified without brittle message
  snapshots?
- Should stock Pyright also become a complete-source gate, or remain authoritative
  only for the consumer contract?
- How should automated checker-version updates report an upstream regression and
  prevent an unsupported release claim?

The design specification should answer these with current experiments and cite
the relevant checker documentation. It should not assume that behavior observed
on 2026-08-31 remains unchanged.

## Expected handoff artifacts

The agent that accepts this proposal from the queue should produce, in order:

1. a fresh baseline report for all five checkers against both the source corpus
   and an installed wheel;
2. a reviewed design specification resolving the questions above;
3. an implementation plan derived from that approved design;
4. the implementation and required documentation changes;
5. an evidence report containing normal gate results and fault-injection results.

The proposal should not be treated as permission to skip the design review or to
turn the acceptance criteria into a checklist without investigating checker
semantics first.

## Decision recorded by this proposal

The project intends to support mypy, stock Pyright, Basedpyright, ty, and Pyrefly
as common consumer type checkers. Consumer-visible inference is part of the public
compatibility contract. The recommended path is the hybrid model: strict internal
authority remains with mypy and Basedpyright, while all five tools become blocking
authorities over a wheel-installed consumer conformance suite.
