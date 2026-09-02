# Proposal: minimum-overhead FastAPI integration

Date: 2026-09-02
Status: proposed; depends on the competitive baseline and should be recalibrated after the compiled runtime
Scope: `depin.ext.fastapi`, request hosting, scope activation, endpoint injection, and application benchmarks

## Nature of this document

This proposal defines an application-level performance outcome. It does not yet
choose a new public setup function, route class, or compatibility mechanism. Any
surface change must be designed and accepted before Step 8 freezes the API.

## Executive summary

The CPU-light FastAPI workload measured `depin` at 726.118 microseconds per
request against 646.634 microseconds for the direct route, a 79.484-microsecond
increment.
A diagnostic decomposition on the same application shape attributed only about
8 microseconds to `FrozenContainer.aresolve()`. Approximately 28 microseconds
came from traversing a FastAPI `Depends` node and approximately 40 microseconds
from publishing the `Host` and opening an async scope for every request.

Core optimization alone therefore cannot make the integration a leader.

The FastAPI path should preserve `service: Inject[Service]` while compiling
endpoint injection at setup, opening a real `ScopeFrame` only when the endpoint's
reachable graph requires one, and keeping the public ASGI middleware safe for
streaming responses and WebSockets. An optimized integration must use supported
FastAPI and Starlette extension points or carry an explicit compatibility policy;
it must not silently depend on unstable internals.

## Goals

- Preserve the existing one-annotation handler ergonomics.
- Remove one-FastAPI-dependency-per-injected-parameter from the optimized path.
- Avoid opening and draining a scope for singleton-only endpoints.
- Avoid eagerly constructing and seeding a framework `Request` unless a reachable
  provider needs it.
- Resolve all injected parameters through one endpoint execution program.
- Preserve async resources until the response, streaming body, or WebSocket
  session has actually ended.
- Make endpoints that do not use `depin` pay no integration overhead.
- Reach competitive leadership on semantically equivalent FastAPI workloads.

## Non-goals

- Replacing FastAPI's dependency system for non-`depin` parameters.
- Preventing handlers from mixing `Inject[...]` with ordinary `Depends(...)`.
- Buffering streaming responses to simplify teardown.
- Requiring users to call the container manually inside handlers.
- Moving FastAPI imports into the core.

## Proposed architecture

### Compatibility path and optimized path

The existing `Inject[T]` behavior through `Depends` remains a compatibility path
until the optimized path proves equivalent. The design phase selects the
smallest supported FastAPI integration surface that can compile `Inject`
parameters after routes are known.

Candidates include a public `APIRoute` subclass, an application setup function
that installs project-owned route handlers, or a documented combination of the
two. The selection experiment must test current supported FastAPI versions and
must preserve mixed native dependencies, validation errors, OpenAPI signatures,
exception handlers, background tasks, streaming, and WebSockets.

The ordinary user should still write one application setup operation and:

```python
@app.get('/users/{user_id}')
async def user(user_id: int, service: Inject[UserService]) -> User:
    return await service.get(user_id)
```

No performance mode flag appears at the handler call site.

### Endpoint injection program

At route setup, the integration records all `Inject` parameters and obtains their
compiled container executors. Per request, one integration entry point resolves
the complete set and calls the original handler with the resulting keyword
arguments. It does not ask FastAPI to traverse a separate `Depends` node for each
injected value.

FastAPI remains responsible for path, query, body, security, and ordinary
dependency parameters. The integration must preserve the handler signature used
for OpenAPI and static tooling.

### Lazy request state

The ASGI boundary creates only the minimal request-local state needed to locate
the hosted container. A `ScopeFrame` is opened lazily when the compiled endpoint
program or code reached during the request first requires a scoped value, a
resource-owning transient, or a framework request seed.

Singleton-only injection uses the root cache without constructing, entering, or
draining an empty scope. Once opened, the frame remains active through the entire
ASGI response lifecycle and drains exactly once on normal return, exception, or
cancellation.

The generic `depin.ext.asgi.RequestScope` remains the portable correctness
implementation. The FastAPI-specific path may specialize it, but must retain its
direct-ASGI behavior: no response buffering, no wrapping of lifespan events, and
correct WebSocket duration.

### Request injection

The framework `Request` object is materialized and provided only when the
reachable provider graph requests it or an ordinary FastAPI feature has already
created it. The optimized integration reuses a request object available from
FastAPI rather than constructing a duplicate.

Graph analysis determines whether a known endpoint requires request scope. A
dynamic call to `hosted_container()` outside the declared endpoint graph remains
correct by activating lazy request state before application code runs; it may
trigger scope creation on first scoped resolution.

## Error and teardown behavior

Resolving `Inject[...]` without a correctly installed host continues to raise an
actionable `NoActiveHostError`. Missing providers and sync/async mismatches remain
the same `DepinError` subclasses with the same key and chain information.

If the handler fails and teardown also fails, neither failure is swallowed. The
design must state how Python's exception grouping exposes both while preserving
the existing public teardown contract.

Teardowns run after the last response event or WebSocket close, not merely after
the handler returns. Cancellation during streaming must still drain every
constructed resource and restore every context-local publication.

## Verification strategy

Integration tests use a real `FastAPI` application and `httpx.AsyncClient`. The
matrix covers:

- no injection, singleton-only, transient, scoped, and async-resource routes;
- multiple injected parameters sharing dependencies;
- mixed `Inject`, `Depends`, path, query, body, and security parameters;
- request injection into nested services;
- OpenAPI generation and validation-error compatibility;
- handler, provider, response-stream, cancellation, and teardown failures;
- background tasks and WebSocket lifetime;
- concurrent requests with isolated frames and overrides; and
- every supported FastAPI and Starlette dependency floor.

Each lifecycle test compares construction and closure logs with the generic ASGI
path. Concurrency tests use barriers or events, never sleeps.

## Performance evidence

The accepted application suite reports total latency, incremental DI overhead,
CPU time, throughput, p50, p95, p99, memory, and allocations. At minimum it
contains:

- a route with no `depin` usage;
- one warm singleton;
- several singleton and transient values;
- a request-scoped shared DAG;
- synchronous and asynchronous resource teardown; and
- representative handler work that shows the fraction of request cost due to DI.

The diagnostic decomposition becomes a maintained component workload so future
regressions can be assigned to FastAPI traversal, host publication, frame
lifecycle, core resolution, or teardown.

## Acceptance criteria

- The ordinary handler remains `parameter: Inject[Type]`; no manual `resolve()` or
  explicit scope is added.
- A route with no `Inject` has no measurable integration regression beyond the
  calibrated noise allowance.
- A singleton-only route does not allocate or drain a `ScopeFrame`.
- Multiple injected parameters enter the integration once and reuse shared
  dependencies according to their lifetimes.
- Streaming, WebSocket, background-task, cancellation, and failure teardown
  semantics remain correct.
- The optimized path reaches the leadership criterion against equivalent current
  FastAPI integrations.
- The compatibility path remains available for a documented transition window
  if a public setup change is accepted.
- Core remains free of framework imports and runtime dependencies.

## Stop conditions

The optimized integration is rejected or redesigned if it:

- relies on an undocumented FastAPI internal with no compatibility containment;
- changes OpenAPI or request validation for unrelated parameters;
- closes resources before response consumption ends;
- requires a different injection annotation for fast routes;
- imposes measurable overhead on routes with no injection; or
- can win only by excluding request scope or teardown that competitors perform.

## Alternatives considered

### Optimize only `aresolve()`

Rejected. The diagnostic decomposition shows that most minimal-route overhead is
outside core resolution.

### Keep one `Depends` resolver per value

Retained as compatibility, rejected as the leadership path. FastAPI traversal is
a material recurring cost even when the value is already cached.

### Open a scope for every request unconditionally

Retained in the generic ASGI implementation, rejected for an optimized FastAPI
singleton-only route. Empty lifecycle work is avoidable.

### Replace FastAPI dependency injection entirely

Rejected. `depin` owns only its parameters and must coexist with the framework's
validation, security, and dependency facilities.

## Expected handoff artifacts

- a supported-API compatibility study across the FastAPI version matrix;
- measured prototypes for route setup and lazy request state;
- an accepted public-surface design before Step 8 closes;
- lifecycle-equivalence and application-performance evidence; and
- migration documentation if setup behavior changes.

## Decision requested

Accept endpoint compilation and lazy request scope as the FastAPI performance
direction, provided the selected integration point preserves framework behavior
and the current injection call site.
