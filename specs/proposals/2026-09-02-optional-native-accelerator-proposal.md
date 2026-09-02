# Proposal: evidence-gated optional native accelerator

Date: 2026-09-02
Status: proposed for investigation after the compiled Python runtime and FastAPI recalibration
Scope: Rust feasibility, Python/native boundary, packaging, semantic parity, and adoption thresholds

## Nature of this document

This proposal authorizes a bounded Rust experiment, not a native rewrite. Native
code enters the product only after the optimized pure-Python runtime is measured
and only if the experiment passes explicit application, portability, and
maintenance gates.

## Executive summary

Rust can reduce interpreter dispatch, cache bookkeeping, and graph traversal, but
only when a sufficiently large unit of work remains native. Moving individual
helpers across the Python boundary is unlikely to matter and may regress due to
argument conversion, reference counting, and repeated Python calls.

Dependency providers remain Python objects in the normal use case. A useful
accelerator must therefore own an entire immutable execution program, retain
provider and cache references, traverse the program natively, and call Python
providers only at construction edges using the fastest supported call protocol.

The accelerator must be optional. The pure-Python engine remains complete,
correct, supported, and automatically selected when no compatible native wheel is
present. A native wheel must never be required to install or use core `depin` on
a supported platform.

## Why Rust is not first

The preliminary comparison found pure-Python Dishka and Wireup far ahead of the
current `depin` interpreter on transient and scoped graphs. That demonstrates a
large architectural opportunity before native code.

Measuring Rust against today's runtime would conflate two gains:

- compiling repeated resolution decisions; and
- executing residual bookkeeping outside the Python interpreter.

The experiment begins only after the Python proposal has made the first gain. It
then answers the useful question: whether native execution materially improves
the best maintainable Python design.

## Goals

- Measure a native execution-program boundary rather than isolated helper ports.
- Preserve the complete public API and automatically fall back to Python.
- Prove value in recurring core work and representative applications.
- Preserve lifecycle, errors, overrides, concurrency, cancellation, teardown,
  diagnostics, and static typing exactly.
- Support the project's interpreter and operating-system policy without making
  source compilation a consumer requirement.
- Make acceptance and removal decisions from reproducible evidence.

## Non-goals

- Rewriting provider functions, user services, FastAPI, or asyncio in Rust.
- Making the public API expose native object types.
- Requiring a Rust toolchain for normal installation.
- Keeping a native implementation because it is technically interesting when its
  application gain is negligible.
- Using native code to bypass validation or weaken free-threading guarantees.

## Candidate native boundary

The experiment receives the immutable executable plan produced by `freeze()`.
The native side may own:

- compact operation and dependency arrays;
- stable references to provider callables and cache slots;
- iterative graph traversal;
- argument-vector assembly;
- lifetime dispatch already fixed by the compiled program;
- cache state transitions and owner/joiner coordination; and
- construction and teardown-record bookkeeping.

It returns normal Python objects and raises the same public Python exceptions.
Provider invocation uses vectorcall or the equivalent fastest stable API when
available. Async providers return to Python's event loop at an explicit boundary;
the native layer must not implement a second scheduler.

Ports of key formatting, `ContextVar.get()`, individual dictionary lookups, or
one-provider wrappers are excluded from the primary prototype. They cross the
boundary too frequently to test the intended hypothesis.

## Engine selection and fallback

The public API never exposes an engine choice. Import selects the native engine
only when a compatible module is installed and has passed an internal ABI and
feature check; otherwise the same frozen container uses Python.

For testing and diagnosis, a private environment-controlled selection may force
either engine. It is not a supported application configuration and must not
change public behavior.

Failure to import the optional module because it is absent is a normal fallback.
A present but incompatible or corrupt module produces an actionable installation
diagnostic rather than silently changing engines. The design phase decides the
package boundary and error policy before distribution.

## Semantic parity

Python is the behavioral reference. Both engines consume the same immutable
execution model and must agree on:

- values and identity by lifetime;
- provider construction order;
- context-local override visibility;
- single-flight ownership and joining;
- circular dependency and circular wait errors;
- cancellation and retry after failed construction;
- teardown registration, reverse ordering, and grouped failures;
- dependency-chain formatting and exception types; and
- diagnostics derived from the declarative plan.

No native-only provider shape or reduced-semantics fast mode is allowed.

## Performance adoption threshold

The experiment runs against the optimized Python engine, direct Python, and the
current eligible competitors. Native adoption requires all of the following:

- at least a 30% reduction in incremental core time on two recurring workloads,
  one of which constructs a multi-provider graph;
- at least a 20% reduction in DI-attributable CPU or latency on one representative
  application workload after framework baseline subtraction;
- no required workload regression beyond five percent or its smaller calibrated
  noise budget;
- no material p95 or p99 tail regression under contention;
- peak memory and allocation changes inside explicit accepted budgets; and
- enough improvement to change or secure `depin`'s competitive position.

If the native engine improves only a sub-microsecond isolated lookup while leaving
application overhead statistically unchanged, the proposal is closed without
shipping it.

## Packaging and support requirements

Before adoption, CI builds and tests wheels for every platform/interpreter
combination the project declares supported for the accelerator. At minimum the
design evaluates Linux, macOS, and Windows on the architectures covered by the
release policy, CPython 3.12 and newer, debug behavior, and free-threaded builds.

Unsupported or newly released combinations fall back automatically to Python.
The project publishes which combinations are accelerated without implying that
the fallback is second-class.

The source distribution installs a complete pure-Python package without Rust.
Build dependencies remain build-time only. Reproducible wheel builds, license
inventory, vulnerability review, provenance, and Trusted Publishing remain part
of the release chain.

The implementation must define how native crashes, panics, and poisoned internal
state are prevented from crossing as process aborts. User-originated provider
exceptions remain ordinary Python exceptions.

## Verification strategy

Every behavioral test that can select an engine is parameterized over Python and
native execution. Differential property tests generate provider graphs and
compare values, logs, exceptions, and teardown.

The native-specific matrix includes:

- repeated create/destroy cycles and reference-leak checks;
- provider exceptions and panics at every boundary;
- cancellation during Python and native portions;
- synchronized threaded and async contention;
- free-threaded execution and sanitizer-capable jobs where supported;
- wheel installation in clean environments without a Rust toolchain;
- pure-Python fallback with the native module absent; and
- benchmark runs from installed wheels, not only a development build.

Rust linting, formatting, dependency auditing, and unsafe-code review become
commit gates if the accelerator ships. Every `unsafe` block must state the
invariant it relies on and have a focused test where practical.

## Maintenance and removal policy

The proposal must account for two engines in release cost. A native accelerator
may be removed in a later release if it repeatedly blocks supported Python
versions, lacks wheels, diverges semantically, or falls below the performance
threshold after Python improves.

The fallback prevents removal from becoming a public API migration. Performance
documentation records whether each published dataset used Python or native
execution.

## Acceptance criteria

- The prototype owns an end-to-end execution program and does not consist of
  helper-by-helper ports.
- It runs the same accepted workload contracts as Python from an installed wheel.
- Semantic, error, teardown, concurrency, and reference-lifetime parity pass.
- The adoption thresholds pass on repeated clean-host measurements.
- Packaging covers the declared accelerated matrix and fallback covers the full
  project support matrix.
- The public API, inferred types, and common call sites remain unchanged.
- A written cost assessment justifies ongoing Rust and wheel maintenance.

## Stop conditions

The experiment closes without product adoption if:

- it misses either the core or application performance threshold;
- most time remains in Python/native boundary crossings;
- it requires users to compile Rust for a supported installation;
- it weakens free-threading, exception, cancellation, or teardown behavior;
- it creates public engine-specific behavior; or
- its wheel and release burden is disproportionate to the measured gain.

Closing the experiment under a stop condition is a successful evidence result,
not a failed implementation.

## Alternatives considered

### Mandatory native core

Rejected. It would revoke the pure-Python installation guarantee and make wheel
availability part of basic correctness.

### Port small hot helpers first

Rejected as the primary experiment. PyO3 guidance and Python's object model favor
fewer, larger boundary crossings; isolated helpers do not test the credible gain.

### Cython instead of Rust

Retained as a prototype alternative only if the design evidence shows it better
fits the selected execution boundary. Rust is preferred for an explicit native
core and memory-safety tooling, but language choice does not override measured
performance, packaging, or maintenance results.

### Ship native code for any measurable win

Rejected. Statistical significance does not imply user relevance, and dual-engine
maintenance needs a deliberately high adoption threshold.

## Expected handoff artifacts

- a boundary and packaging design based on the optimized Python profile;
- an installed-wheel Rust prototype and pure-Python fallback;
- differential correctness, concurrency, leak, and failure evidence;
- accepted core and application performance datasets; and
- a written adopt-or-close decision against the thresholds above.

## Primary references

- [PyO3 performance guide](https://pyo3.rs/main/performance.html)
- [PyO3: calling Python from Rust](https://pyo3.rs/main/python-from-rust)
- [Dependency Injector installation and compiled
  modules](https://python-dependency-injector.ets-labs.org/introduction/installation.html)

## Decision requested

Authorize a bounded optional-native experiment after Python optimization, with
shipping contingent on semantic parity, broad fallback, and material application
gain.
