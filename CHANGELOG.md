# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-23

`0.2.0` is a clean break from the `0.1.x` line; migration is breaking.

### Changed
- `Container()` no longer resolves directly; call `.freeze()` to get a `FrozenContainer`.
- Injection uses the `@frozen.inject` decorator or `Inject[T]` (FastAPI extra) instead of `Inject(fn)` defaults.
- Dependency access is `frozen[X]` / `frozen.resolve(X)` / `Inject[T]` instead of `Container.Depends(X)`.
- `Scope.REQUEST` renamed to `Scope.SCOPED`.
- Request scoping is `frozen.scope()` / `frozen.ascope()`.

### Added
- Build-time validation on `freeze()`: missing providers, cycles, lifetime (captive-dependency) violations, and async/sync mismatches.
- `injected()` marker for explicit `@inject` parameters.
- Pure-ASGI `RequestScope` middleware for the FastAPI extra.
