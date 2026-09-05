# Stability and compatibility

## Before 1.0

Until the commit tagged exactly `1.0.0`, depin is pre-1.0 software. Public APIs
may change, including in a minor release, without a deprecation period. Release
notes will describe material changes, but users who need a fixed contract should
pin an exact version.

## The V1 contract

The commit tagged exactly `1.0.0` begins depin's Semantic Versioning commitment.
After that commit, a compatible public API is not removed or changed incompatibly
outside a major release, except for the security and correctness boundaries below.

The public surface is:

- Names in `depin.__all__`.
- The documented modules under `depin.ext` and their documented public members.
- Documented command-line and plugin surfaces.

Everything else is private implementation detail, including `depin._core`,
undocumented modules and members, and names beginning with an underscore. Private
surfaces may change without notice.

## Python and typing support

The supported Python versions and platform commitments are maintained in the
[support policy](support-policy.md). A supported Python version is removed only
in the first minor release after upstream end of life, with notice in the prior
release notes.

Typing compatibility is part of the public contract. depin supports mypy, stock
Pyright, Basedpyright, ty, and Pyrefly for the documented consumer surface. The
published wheel must type check with zero diagnostics against the consumer corpus
on each checker at its documented version. Source-level policy and known checker
limitations are recorded in the support policy.

The previously blocking ty outcome is closed: ty now gates source diagnostics
against its explicit, reviewed register rather than an advisory `exit 0` job.
Consumer compatibility remains a zero-diagnostic requirement for ty, as it does
for the other four checkers.

## Deprecations after V1

After `1.0.0`, a public API removal must first emit `DeprecationWarning` and name
the affected symbol, replacement or required action, introduction version, and
removal version. The normal window is at least one minor release; removals happen
only in the announced removal version or a later major release. A removal is
checked against the package version, never a wall-clock date.

Experimental APIs are not part of V1. New public APIs follow the ordinary V1
contract unless a future release explicitly introduces and documents an
experimental policy before exposing such an API.

## Security and correctness exceptions

depin may make a narrowly scoped incompatible change in a patch release when it
is necessary to fix a security vulnerability, data-corruption risk, or a defect
that violates the documented safety contract. The release notes will identify the
boundary, describe the impact, and provide migration guidance where practical.
