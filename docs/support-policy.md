# Support policy

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

The public API is verified under `basedpyright --strict` and `mypy --strict`, and
a conformance suite asserts the inferred type of the public call sites it covers.
Neither checker is treated as authoritative over the other: a change must
satisfy both.

Astral's `ty` runs in CI over the same code, advisorily: its job is allowed to
fail without blocking a merge. `ty` is pre-1.0 on `0.0.x` versioning, and its
own documentation warns that diagnostics can change between any two releases,
so it is not yet part of the support commitment above.
