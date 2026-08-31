# Step 5, cycle 3 — the request/response hosts: design

Date: 2026-08-31
Baseline: 0.14.0 at `495296a`
Target: 0.15.0
Status: approved, pending implementation plan

## Goal

Ship the three remaining web integrations — Starlette, Litestar, Flask — on the
contract cycle 1 published, and collapse the duplication doing so would
otherwise create.

Every one of them does the same four things per request: publish the container,
open a scope, seed the framework's own request object, resolve. Only two things
differ: the protocol (ASGI or WSGI) and which class the request object is. So
this cycle ships **two** middlewares, not four, and each framework module is the
key and the factory that specialise one of them.

`depin.ext.fastapi` is rewritten a second time — onto the shared ASGI
middleware — which is the same proof cycle 1 made, applied to the abstraction
rather than to the contract.

## What changes for an existing graph

| Before | After |
| --- | --- |
| `depin.ext.fastapi.RequestScope` is its own ASGI middleware. | It is the shared one, specialised. Same import path, same constructor, same behaviour. |
| Three frameworks have no integration. | Starlette, Litestar and Flask each have one. |

Nothing in `depin/` outside `ext/` changes. A FastAPI application upgrading
from 0.14.0 changes nothing.

## Measurements

Three questions were measured against the tree at `495296a` rather than assumed.

**`fastapi.Request` *is* `starlette.requests.Request`.** Confirmed by identity:
`fastapi.Request is starlette.requests.Request` returns `True`. FastAPI
re-exports the Starlette class rather than subclassing it, so one middleware
seeding that class serves a FastAPI provider and a Starlette provider under the
same key. `depin.ext.fastapi` therefore does not need its own middleware at
all — it needs Starlette's.

**Litestar accepts a plain ASGI middleware.** A three-line class implementing
`__call__(scope, receive, send)`, passed as `middleware=[Mw]`, ran and the route
returned 200. Litestar needs no adapter of its own beyond its request class.

**Flask hosts a WSGI middleware at `app.wsgi_app`.** Wrapping it with a class
implementing `__call__(environ, start_response)` saw the request path and the
route still returned its body. That is the whole WSGI seam, and it is a `with`
block, so `Host.scope()` fits it directly.

## Public surface

Two middlewares and three modules.

| Symbol | Role |
| --- | --- |
| `depin.ext.asgi.RequestScope` | ASGI middleware: a scope per request, seeding whatever the caller names. |
| `depin.ext.wsgi.RequestScope` | The WSGI counterpart. |
| `depin.ext.starlette.RequestScope` | The ASGI one, seeding `starlette.requests.Request`. |
| `depin.ext.litestar.RequestScope` | The ASGI one, seeding `litestar.Request`. |
| `depin.ext.flask.RequestScope` | The WSGI one, seeding `flask.Request`. |
| `depin.ext.fastapi.RequestScope` | Now `depin.ext.starlette`'s, re-exported. `Inject[T]` is unchanged. |

```python
class RequestScope:  # depin.ext.asgi
    def __init__(
        self,
        app: ASGIApp,
        container: FrozenContainer,
        *,
        seed: Callable[[ASGIScope], tuple[ProviderKey, object] | None] | None = None,
    ) -> None: ...
```

`seed` returns the key and value to place in the frame, or `None` to seed
nothing. It is called once per request, before anything resolves.

`depin/ext/asgi.py` and `depin/ext/wsgi.py` import **no** third-party package:
the ASGI and WSGI protocols are structural, and their types are declared with
`Protocol` locally. So they work with no extra installed, and a fourth-party
framework can use them directly.

## Data model

None. Each middleware holds an app, a `Host`, and a `seed` callable.

## Semantics

| Operation | Guarantee |
| --- | --- |
| ASGI, `scope['type']` not `http` or `websocket` | Forwarded untouched. No scope opened, no container published. Lifespan is the case that matters. |
| ASGI, `http` or `websocket` | `Host.ascope()`; the seed is applied for `http` only; the downstream app is called inside the scope. |
| WSGI | `Host.scope()`; the seed is applied; the downstream app is called inside. Teardowns run before the response iterable is consumed, so a streaming WSGI response must not depend on a scoped value. |
| Any | An exception from downstream propagates after the scope drains and the container is unpublished. |

The WSGI row is a real limitation, not an oversight: WSGI's `start_response`
contract returns an iterable the server consumes after the application returns,
by which time the `with` block has exited. Documented, and the guide says to
materialise a streaming body inside the request if it needs a scoped value.

## Errors

No new exception type. `ContainerNotBoundError` already covers the unhosted
case, and each integration's own message names its own setup step.

## Module layout

| Module | Change |
| --- | --- |
| `depin/ext/asgi.py` | **New.** The ASGI middleware and the protocol types. No third-party import. |
| `depin/ext/wsgi.py` | **New.** The WSGI counterpart. No third-party import. |
| `depin/ext/starlette.py` | **New.** Seeds `starlette.requests.Request`. |
| `depin/ext/litestar.py` | **New.** Seeds `litestar.Request`. |
| `depin/ext/flask.py` | **New.** Seeds `flask.Request`. |
| `depin/ext/fastapi.py` | `RequestScope` re-exported from `depin.ext.starlette`; `Inject[T]` unchanged. |
| `pyproject.toml` | `starlette`, `litestar`, `flask` extras with declared floors. |

The shared middleware is extracted now rather than in cycle 1 because this is
the cycle that gives it a second and third consumer. Cycle 1 said so.

## Verification

- **Unit.** `tests/unit/test_asgi_wsgi.py`: the middlewares driven against
  hand-written ASGI and WSGI applications, with no framework installed —
  non-HTTP scopes forwarded untouched, the seed applied and skipped, the scope
  drained on an exception, nothing published afterwards.
- **Integration.** One file per framework, each against that framework's real
  test client: a scoped provider resolved per request, its teardown run, two
  requests getting independent instances, and `hosted_container()` reachable
  from a handler.
- **Contract.** The existing `tests/unit/test_integration_contract.py` covers
  all five new modules automatically and is what keeps them off `depin._core`.
- **FastAPI.** Its two existing integration suites must pass unedited. That is
  the proof the extraction is behaviour-preserving.
- **Examples.** One example, not three: `examples/starlette_app/`. The other
  two are the same four operations against a different import, and three
  examples would be three copies of one idea.
- **Docs.** `docs/guide/integrations.md` gains a section naming which module to
  use per framework; `docs/reference/` gains a page for the two middlewares.

## Acceptance criteria

- `depin.ext.fastapi`'s two integration suites pass with no edit.
- `depin/ext/asgi.py` and `depin/ext/wsgi.py` import no third-party package,
  proven by a test that imports them with the extras uninstalled — or, failing
  that, by the contract test's import scan.
- All five new modules import nothing from `depin._core`.
- Coverage over `depin/` stays at or above 95%; the mutation gate is unaffected
  because nothing under `depin/_core/` changes.
- `depin/` still carries exactly three suppressions.
- `minimum-versions` and `latest-versions` exercise every new extra at both ends.

## Out of scope

| Item | Reason |
| --- | --- |
| An `Inject[T]` equivalent for Starlette or Litestar | `Inject[T]` exists because FastAPI has a parameter-injection system to hook into. Starlette has none, and Litestar's is its own DI, which a second one would fight. Both get `hosted_container()`. |
| Django | Not in the roadmap's curated set. The contract is what serves it. |
| A streaming-safe WSGI scope | Would mean holding the scope open past the application's return, which WSGI gives no hook for. Documented as a limitation instead. |
| Three examples | One demonstrates the shape; the other two differ only in an import. |
