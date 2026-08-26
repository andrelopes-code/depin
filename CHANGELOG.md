# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2](https://github.com/andrelopes-code/depin/compare/v0.4.1...v0.4.2) (2026-08-26)


### Bug Fixes

* stop a manual release run from forcing a PyPI publish ([#25](https://github.com/andrelopes-code/depin/issues/25)) ([9161b6a](https://github.com/andrelopes-code/depin/commit/9161b6a7773883ddd604012621686637a97435d3))

## [0.4.1](https://github.com/andrelopes-code/depin/compare/v0.4.0...v0.4.1) (2026-08-26)


### Bug Fixes

* keep uv.lock in step with the released version ([#23](https://github.com/andrelopes-code/depin/issues/23)) ([7575caf](https://github.com/andrelopes-code/depin/commit/7575caf5a8df150e86ff706a3a047b88ac28c864))

## [0.4.0](https://github.com/andrelopes-code/depin/compare/v0.3.0...v0.4.0) (2026-08-26)


### ⚠ BREAKING CHANGES

* `Container.from_`, `merge`, `frame_provides`, `ScopeFrame.put`, the `with_` keyword of `override` and the `HasRecords` protocol are removed. `freeze()` raises `InvalidProviderError` and `InvalidScopeError` instead of bare `TypeError` and `ValueError`, and teardown raises `TeardownError` instead of `RuntimeError`.

### Features

* rework the public API, error hierarchy and internals ([#16](https://github.com/andrelopes-code/depin/issues/16)) ([46effd2](https://github.com/andrelopes-code/depin/commit/46effd2fe438841142d9baae67469718f8569c87))

## [0.3.0](https://github.com/andrelopes-code/depin/compare/v0.2.0...v0.3.0) (2026-05-24)


### ⚠ BREAKING CHANGES

* require explicit injected() marker for @inject parameters
* reject captive singleton-on-scoped dependencies
* make RequestScope Request metadata-only and container context-scoped
* raise DuplicateProviderError on conflicting bindings
* switch Inject to type subscript form Inject[T]
* rewrite RequestScope as pure ASGI middleware
* simplify marker API for v0.2

### Features

* add cached signature/type-hints, shape detection, Annotated scanner ([78200e8](https://github.com/andrelopes-code/depin/commit/78200e8feefe60e9e8f773833d1bbda733835ea9))
* add Container builder mirroring Registry surface ([00fa2e7](https://github.com/andrelopes-code/depin/commit/00fa2e7330a11705ce1801b7785119c64c25c374))
* add depin error hierarchy ([3f83e03](https://github.com/andrelopes-code/depin/commit/3f83e03144c7a6acbbef837db81baffa180975b2))
* add fastapi extension with RequestScope, Inject, and frame_provides ([80b39f3](https://github.com/andrelopes-code/depin/commit/80b39f35a2d041ecbb70a217c4b2d1b1c724c342))
* add injected() marker for explicit [@inject](https://github.com/inject) parameters ([ab77f36](https://github.com/andrelopes-code/depin/commit/ab77f365fd9f273e4ac67a26cdcbd1857533a17d))
* add provider spec dataclasses ([4985083](https://github.com/andrelopes-code/depin/commit/498508364a95f9193524a7624e553bb5f73dbf11))
* add recursive check for async dependencies ([7504adb](https://github.com/andrelopes-code/depin/commit/7504adbe9aa7c0967511bf93ea16332dc01a02bc))
* add Registry with bind, value, scope decorators and merge ([427a9c2](https://github.com/andrelopes-code/depin/commit/427a9c26f203f444a749f68c9fc1ef6d5b6627e5))
* add resolver — build specs, validate graph, compute async paths ([1a30360](https://github.com/andrelopes-code/depin/commit/1a30360a7f699bb5494538ff9b0e898be850376d))
* add Scope enum ([fd24abc](https://github.com/andrelopes-code/depin/commit/fd24abc725c3bf006921181f0b6eff64ef5c10e6))
* add ScopeFrame and ContextVar-based active-frame tracking ([6a820f8](https://github.com/andrelopes-code/depin/commit/6a820f814e223c7a2cf754464c710675336ce2c0))
* add Token, Inject, Named, Tag markers and provides decorator ([920aa19](https://github.com/andrelopes-code/depin/commit/920aa1909f921f0660d7d62568af470ede0f3d34))
* async resolution path for sync and async providers ([2afb6c9](https://github.com/andrelopes-code/depin/commit/2afb6c9bbc6239e5456a6ac88553cb452ebcf737))
* enhance circular dependency error message ([5a01612](https://github.com/andrelopes-code/depin/commit/5a016122e6e8b3118a28eda4ece874d646b85c51))
* expose __version__ on the package root ([0a1d9f8](https://github.com/andrelopes-code/depin/commit/0a1d9f85f6953860ec63ca091221296e1a9251a1))
* expose public api from depin package root ([8229dfa](https://github.com/andrelopes-code/depin/commit/8229dfa9aa75c97c19d87ff21d7443cc27b0428b))
* improve example code and rename files and folders ([a9f3baf](https://github.com/andrelopes-code/depin/commit/a9f3bafa4332a1f82be6ffdebf8f4018e9ce11ee))
* include resolution chain and provides candidates in MissingProviderError ([7c04657](https://github.com/andrelopes-code/depin/commit/7c04657d61189df0ba7230839d47287082db1310))
* lifespan management for generators, context managers, and aclose ([71e445a](https://github.com/andrelopes-code/depin/commit/71e445a7e57dfde658963e0ab438e0ed6ce4f505))
* raise DuplicateProviderError on conflicting bindings ([b532236](https://github.com/andrelopes-code/depin/commit/b5322364df2f9533f1d872309ed8e9f30cf9ece4))
* re-export HasRecords from package root ([4bed4d1](https://github.com/andrelopes-code/depin/commit/4bed4d19d51d597694eea7f7f88a46215abf315a))
* reject captive singleton-on-scoped dependencies ([7f35885](https://github.com/andrelopes-code/depin/commit/7f358850fa0419eb12ea3db250266211b0bd5cf6))
* report every missing provider in one error ([2b953e5](https://github.com/andrelopes-code/depin/commit/2b953e5b61e2ab37cd9debabb367de4bcb323205))
* require explicit injected() marker for [@inject](https://github.com/inject) parameters ([50edc74](https://github.com/andrelopes-code/depin/commit/50edc74236f337b262056d48c211140f36c50b98))
* resolve singleton classes, functions and tokens via FrozenContainer ([b539f7e](https://github.com/andrelopes-code/depin/commit/b539f7e5cd0610492ab1e46bd9bb80451e7c1d79))
* simplify marker API for v0.2 ([e44d631](https://github.com/andrelopes-code/depin/commit/e44d631d38eea9dd208a7d4828ae8ebb36b3b0a0))
* start project ([618971b](https://github.com/andrelopes-code/depin/commit/618971b5d525e098d75a0a1f5c88a603e974e82a))
* support scoped and transient resolution via push_frame ([6835dd9](https://github.com/andrelopes-code/depin/commit/6835dd9f9a66c13416d542596af2b3364bdea939))
* switch Inject to type subscript form Inject[T] ([ce3d843](https://github.com/andrelopes-code/depin/commit/ce3d843f310dc699b39042ee527ec507f3060865))
* task-safe overrides via ContextVar frames ([5d5e9b9](https://github.com/andrelopes-code/depin/commit/5d5e9b9635ac6d6e2a44a44014f5ad0071afc748))
* transform individual methods to enter request scope into contextmanagers ([d1c2906](https://github.com/andrelopes-code/depin/commit/d1c2906dcc1809fcac420d62eacbc73d38edef19))
* type-preserving inject decorator (sync + async) ([5528721](https://github.com/andrelopes-code/depin/commit/5528721c657d132be7d2ad9bb74f95db0d024bc4))


### Bug Fixes

* apply override to nested dependencies ([b8e902c](https://github.com/andrelopes-code/depin/commit/b8e902c4abd1545f36b8983d0c49a953448e7016))
* build cached providers once under concurrent async resolution ([1931a0d](https://github.com/andrelopes-code/depin/commit/1931a0dc2efad4f99ac99bd2478672b13d0a2fb5))
* cache provider instances by identity, not spec object ([25ff9b1](https://github.com/andrelopes-code/depin/commit/25ff9b125aec8cc23627ee9bdc2b9ea5d2ae9230))
* error when recursive checking third party objects ([4bdf91f](https://github.com/andrelopes-code/depin/commit/4bdf91f7d1d05206b550084459b2afe4b7396f3f))
* exception bypass on context managers ([f06dd81](https://github.com/andrelopes-code/depin/commit/f06dd81d851dc6fe4dcc7eea2fed02f9f8f3ac40))
* internal package not included ([a31469d](https://github.com/andrelopes-code/depin/commit/a31469de4e2baeb6a463200f51414387347d4842))
* make RequestScope Request metadata-only and container context-scoped ([3729d6a](https://github.com/andrelopes-code/depin/commit/3729d6a6cda00f8643e90ff0d41515eb9f06d4ad))
* relative import on __init__ ([1ddadaf](https://github.com/andrelopes-code/depin/commit/1ddadaf1f6ea72629352585e9c7246f2de4d3024))
* remove usage of noqa: B008 ([f67c1f4](https://github.com/andrelopes-code/depin/commit/f67c1f4a625cd61cf5f197b06e603f97400db950))
* update fastapi version and adjust dependency specifications ([4b38948](https://github.com/andrelopes-code/depin/commit/4b389480fe848cc8af8e9f18d3382ff1b197e1da))


### Performance Improvements

* bound _suggest_candidates scan and result count ([0826ea1](https://github.com/andrelopes-code/depin/commit/0826ea1e866a47f78520371758859a25ed96ea81))


### Documentation

* add changelog ([5bc1800](https://github.com/andrelopes-code/depin/commit/5bc1800bfe91908ca2cf34b31eb5f222e8e3a177))
* add code of conduct ([20d36bc](https://github.com/andrelopes-code/depin/commit/20d36bc8adaa35ab069bf87e0a2485f81fcffdd2))
* add contributing guide ([c9bbc45](https://github.com/andrelopes-code/depin/commit/c9bbc45002629c09ef8f55561e2c33430a2ca4d9))
* add minimal_sync and fastapi_app examples ([c1b1015](https://github.com/andrelopes-code/depin/commit/c1b1015f1639aab4e3ba69d6e395640594912d8d))
* add module docstring to spec ([bb3e12c](https://github.com/andrelopes-code/depin/commit/bb3e12c275a20d02ca7f0c5c41828cd78b1a3bc9))
* add package docstring and mental-model example ([0696715](https://github.com/andrelopes-code/depin/commit/0696715c694a45de115972a390de0a55e051505a))
* add security policy ([319b4c8](https://github.com/andrelopes-code/depin/commit/319b4c8f57601b7843a5d012be0fd8f4728d66ed))
* add some documentation to methods ([9a9ef54](https://github.com/andrelopes-code/depin/commit/9a9ef5478cc9caca09b84bbdf87911926546ff1c))
* add status badges to README ([94d9967](https://github.com/andrelopes-code/depin/commit/94d9967b800490de56cabd58491cb2d7de128a1f))
* add v2 design, implementation plan, and contributor rules ([20e768c](https://github.com/andrelopes-code/depin/commit/20e768cca68023df1089d03f8fa82e8fe712c4b4))
* convert docstring cross-references to plain text ([f77ca75](https://github.com/andrelopes-code/depin/commit/f77ca75a51995fc2b474b75a978ed7fd3ec17903))
* document Container builder API ([28d7c54](https://github.com/andrelopes-code/depin/commit/28d7c54c872b732f70f4f7ca35a264cc37781be0))
* document FastAPI RequestScope and Inject ([9e9d5a9](https://github.com/andrelopes-code/depin/commit/9e9d5a99c4702d941e073fffb071d3aa53e72801))
* document FrozenContainer runtime API ([fdda83a](https://github.com/andrelopes-code/depin/commit/fdda83a002aac5ef714e47a86263c291c3c2851e))
* document injected() marker for [@inject](https://github.com/inject) ([f1a655a](https://github.com/andrelopes-code/depin/commit/f1a655a822569262a85d2d23e3a08d5c4cbab9fa))
* document lifecycle, nested-scope, and inject typing caveats ([ed1c1c2](https://github.com/andrelopes-code/depin/commit/ed1c1c280b04d7414c9c3b77544655ce25a73c98))
* document Registry and ScopeDecorator ([2af61f6](https://github.com/andrelopes-code/depin/commit/2af61f6c915f516f776c10c8b5bdc3e31dff8d63))
* document Scope lifetimes and ScopeFrame ([f9db561](https://github.com/andrelopes-code/depin/commit/f9db5618f53b1199cc7fda3be8c88fd425718c54))
* document the bootstrap release process ([f7ad5c2](https://github.com/andrelopes-code/depin/commit/f7ad5c2ec6b3f7e44aafb1ef4d97e92d70bb7650))
* document the public-API docstring convention ([6b03bcc](https://github.com/andrelopes-code/depin/commit/6b03bcc39f69c108cd8951fb96b19143347de9e8))
* document Token, Named, Tag, and provides markers ([c133e0b](https://github.com/andrelopes-code/depin/commit/c133e0b35e5c8cfeff927a4d0251ed762c31dfe8))
* expand exception docstrings with triggers and fixes ([eaaaab8](https://github.com/andrelopes-code/depin/commit/eaaaab863a2ccb6fc113558578d5c30944b09fbf))
* link governance docs from README ([5218850](https://github.com/andrelopes-code/depin/commit/52188509fe2ea1645ebe74906a1c44a2edbb9e7c))
* list TypeError and ValueError in Container.freeze Raises ([4e0330c](https://github.com/andrelopes-code/depin/commit/4e0330ca1e2127877750a058650605e9f05b0d8a))
* note lifetime check in build-time validation ([2c3f699](https://github.com/andrelopes-code/depin/commit/2c3f699a8979657d8396c81819543f4ef7492764))
* remove placeholder narrative pages, keep home and reference ([#5](https://github.com/andrelopes-code/depin/issues/5)) ([b3ff025](https://github.com/andrelopes-code/depin/commit/b3ff025fbbb470c22de46be03c59f3e100fb3000))
* render docstring examples as pycon code blocks ([48a1c5a](https://github.com/andrelopes-code/depin/commit/48a1c5a05d5819ab65c80c5ace7469c6eca30b0a))
* rewrite README for v2 ([fb649a7](https://github.com/andrelopes-code/depin/commit/fb649a71f3eb811712ba32233d23d2e3924ff49d))
* scaffold mkdocs site with generated reference ([610aac6](https://github.com/andrelopes-code/depin/commit/610aac6f68bdb1d4f565a6e828bd02cb379d50f7))


### Code Refactoring

* rewrite RequestScope as pure ASGI middleware ([86bf55a](https://github.com/andrelopes-code/depin/commit/86bf55a409a44e474f771cbbd8c087b9e026895d))

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
