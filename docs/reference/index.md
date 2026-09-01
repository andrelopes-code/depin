# API reference

Generated from the source docstrings — signatures and types are read from the code,
never retyped by hand.

- [Container & Registry](container.md) — building and composing the dependency graph.
- [FrozenContainer](frozen.md) — resolving, scoping, injecting, overriding.
- [Scope](scope.md) — provider lifetimes and the scope frame.
- [Markers](markers.md) — `Token`, `Named`, `Tag`, `injected`, `provides`.
- [Errors](errors.md) — the exception hierarchy, all rooted at `DepinError`.
- [Graph diagnostics](diagnostics.md) — the data behind `graph()` and `explain()`.
- [Warmup and health](operations.md) — the data behind `warmup()`, `checks()`, and `health()`.
- [Integration contract](hosting.md) — `Host` and the ambient container.
- [ASGI request scope](asgi.md) — the framework-free ASGI middleware, no extra required.
- [WSGI request scope](wsgi.md) — the framework-free WSGI middleware, no extra required.
- [Starlette](starlette.md) — the ASGI middleware seeded with a `starlette.requests.Request`.
- [FastAPI](fastapi.md) — `Inject[T]`, plus the Starlette middleware under its own name.
- [Litestar](litestar.md) — the ASGI middleware seeded with a `litestar.Request`.
- [Flask](flask.md) — the WSGI middleware seeded with a `flask.Request`.
- [pytest](pytest.md) — the callables the plugin's override fixtures return.

Looking for prose instead? Start with the [guide](../guide/index.md).
