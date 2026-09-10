# FastAPI minimum-overhead design

Date: 2026-09-09
Status: accepted for implementation
Source proposal: `specs/proposals/2026-09-02-fastapi-minimum-overhead-proposal.md`
Baseline revision: `086adf98459773e3175f4723b2b64e3f47306e42`
Baseline evidence: `benchmarks/results/2026-09-09-competitive-rebaseline/`

## Decision

The optimized FastAPI integration adds one public setup operation:

```python
from fastapi import FastAPI

from depin import FrozenContainer
from depin.ext.fastapi import install


def install(app: FastAPI, container: FrozenContainer) -> None: ...
```

Applications register path operations and included routers, then call `install`
once before the application starts. `install` compiles direct `Inject[...]`
parameters already present on HTTP path operations and installs request state
that opens a depin scope lazily. The handler annotation remains unchanged:

```python
app = FastAPI()


@app.get('/users/{user_id}')
async def user(user_id: int, service: Inject[UserService]) -> User:
    return await service.get(user_id)


install(app, container)
```

The existing `app.add_middleware(RequestScope, container=container)` setup
remains the compatibility path. It retains eager request scope behavior and the
current `Inject[...]` resolver. It is not removed or silently changed by this
work.

## Scope

This specification covers only:

- direct FastAPI endpoint compilation for `Inject[...]` parameters;
- lazy request scope activation and lazy framework-request seeding;
- the public `install` operation and its compatibility diagnostics;
- lifecycle, concurrency, typing, validation, OpenAPI, and benchmark evidence
  required to prove equivalence and the performance outcome.

It does not cover provider discovery, native or Rust acceleration, changes to
the general resolution runtime, replacement of FastAPI dependency injection,
or optimization of framework integrations other than FastAPI.

## Baseline and measurable outcome

The accepted 2026-09-09 measurements are the comparison oracle. Their median
repetition-level totals are:

| Workload | depin p50/p95/p99 | Direct p50 | DI-attributable p50 |
| --- | ---: | ---: | ---: |
| CPU-light endpoint | 525.6/710.5/930.5 us | 464.9 us | 60.7 us |
| Async resource teardown | 614.3/919.3/1352.7 us | 463.7 us | 150.6 us |
| Request-scoped graph | 592.4/1154.7/2570.2 us | 458.3 us | 134.1 us |
| Application startup | 2.693/4.741/6.199 ms | 1.717 ms | 0.976 ms |

Independent percentile subtraction is not DI attribution. The performance
decision uses paired observations and the confidence interval produced by the
repository harness.

The implementation is accepted only when all of the following hold:

- the upper 95% confidence bound of the relative change in paired,
  DI-attributable CPU-light p50 overhead is at most `-25%` against revision
  `086adf9`;
- the point estimate targets `-30%` or better;
- FastAPI p95 and p99 total latency do not regress by more than `5%`;
- the route with no depin injection remains within its calibrated noise
  allowance;
- retained memory, peak memory, allocation count, application startup, and
  contention remain within their existing calibrated noise allowances or
  authored budgets; and
- every measured pair validates equivalent response and lifecycle semantics
  before its samples are admitted.

## Public surface

### `Inject[T]`

`Inject[T]` remains statically identical to `T` and requires no default value.
At runtime it continues to expand to an `Annotated` FastAPI dependency. The
dependency callable becomes a project-owned immutable resolver object carrying
the depin key. That object has two roles:

- the compatibility path resolves its single key through the hosted container;
- the compiler recognizes it without parsing annotations or depending on
  parameter names.

The callable accepts FastAPI's existing `Request` object. It registers that
object as a lazy seed before resolution, so a provider asking for `Request`
receives the same object FastAPI created rather than a duplicate.

### `install(app, container)`

`install` is called after HTTP routes and included routers are registered and
before startup. It:

1. validates the supported FastAPI route shape;
2. scans the application's existing `APIRoute` instances;
3. compiles each route containing direct `Inject[...]` dependencies;
4. leaves routes without `Inject[...]` untouched;
5. installs one project-owned pure-ASGI lazy request-state middleware; and
6. records the container identity so repeated installation is deterministic.

A second call with the same container is idempotent and compiles any routes
added since the first call. A second call with another container raises an
actionable `FastAPIIntegrationError`. Calling after the Starlette middleware
stack has been built raises the same depin error and tells the caller to install
before startup.

Routes added after the final call remain on the compatibility dependency path.
The guide states that `install` must follow route registration so performance
does not depend on router construction order.

### Compatibility error

`FastAPIIntegrationError` lives in `depin/errors.py`, inherits `DepinError` and
`RuntimeError`, and is re-exported with the other public exceptions. It is used
only for integration setup or compatibility failures. Its message names the
incompatible route or application state, the detected FastAPI version, and the
supported recovery: upgrade to a tested version or use `RequestScope`.

## Endpoint compilation

### Recognition

FastAPI has already produced a dependency graph for every `APIRoute` when
`install` runs. The compiler examines only direct dependency nodes of the route
handler. A node belongs to depin when its callable is the private immutable
`_InjectResolver`. Native `Depends`, security, body, query, header, cookie, and
path nodes are never classified by name or annotation shape and remain exactly
where FastAPI put them.

Nested FastAPI dependency functions that themselves use `Inject[...]` remain on
the compatibility path in this version. Compiling those graphs would expand the
scope into replacing FastAPI's dependency system and is explicitly deferred.

### Program

For a route containing one or more direct injections, the compiler creates one
immutable `_EndpointProgram` containing ordered `(parameter_name, key)` entries
and the frozen container. It replaces the per-parameter depin dependency nodes
with one program node. The program:

1. receives FastAPI's existing `Request`;
2. makes it available to the lazy request state without opening a frame;
3. resolves every key through the frozen container in declaration order;
4. returns the resolved keyword arguments as one result; and
5. is executed once per request regardless of injection count.

The route call target becomes a wrapper that combines FastAPI's already
validated keyword arguments with the program result and invokes the original
handler. Async handlers are awaited directly. Sync handlers retain FastAPI's
threadpool behavior and context propagation. The original route endpoint,
signature, response model, name, operation ID inputs, and documentation metadata
remain the source of static tooling and OpenAPI information.

The program uses the container's existing generated, instruction, or iterative
executor selected at freeze time. This work adds no second resolution engine.

### FastAPI compatibility boundary

`APIRoute` and custom route handlers are documented FastAPI extension points.
Removing already-built depin nodes and rebuilding the route ASGI callable
requires a small set of FastAPI/Starlette route attributes that are not a stable
cross-version protocol. That compatibility boundary is contained in the private
FastAPI compiler module and nowhere else.

Before mutation, `install` structurally verifies every attribute it will use and
performs no partial compilation when the shape is incompatible. The supported
matrix exercises the declared FastAPI floor (`0.133`) with Starlette `1.1` and
the latest allowed pair. An incompatible future shape fails at setup with
`FastAPIIntegrationError`; it never silently runs a partially compiled route.
The documented `RequestScope` path remains available without the compiler.

## Lazy request state

### State machine

Every HTTP or WebSocket connection installed by `install` gets one context-local
lazy state with these states:

```text
inactive -> hosted -> frame-open -> drained
```

- `inactive`: no depin request state exists.
- `hosted`: the root container and lazy seed registry are published, but no
  `ScopeFrame`, teardown list, or framework `Request` seed has been allocated.
- `frame-open`: the first scoped read, request seed read, or request-owned
  teardown registration created and pushed exactly one frame.
- `drained`: the downstream ASGI application ended and the opened frame, if any,
  was drained exactly once before all context-local publications were restored.

The state transition is idempotent within one context. It is not shared between
requests. Child tasks inherit the same request context according to normal
`contextvars` rules, while concurrent requests receive independent state and
frames.

### Activation triggers

The root resolution path continues without consulting a frame for singleton and
ordinary transient graphs that own no request teardown. A frame opens only when
existing runtime behavior requires one:

- a scoped provider reads or writes the active frame;
- a `scope_value` binding reads a lazy seed;
- a non-singleton resource registers request-owned teardown; or
- application code dynamically resolves one of those shapes through
  `hosted_container()`.

Outside a lazy-host context, the same operations continue to raise
`OutsideScopeError`. The lazy hook is therefore inert for ordinary container
resolution and for every non-FastAPI integration.

### Request seeds

The lazy state stores seeds by depin identity without applying them. A seed is
written into the frame only when its `scope_value` binding is first read. A
compiled or compatibility resolver registers the actual FastAPI `Request`
object. The middleware retains a metadata-only factory only for dynamic hosted
resolution that occurs without an endpoint resolver; that fallback is not
materialized unless `Request` is requested.

WebSockets get lazy hosting and frame lifetime but no HTTP `Request` fallback.
WebSocket injection continues through FastAPI's compatibility dependency path.

### Teardown and failures

The lazy implementation reuses the same scope draining primitive as
`FrozenContainer.ascope()` rather than duplicating teardown logic. If no frame
opened, exit performs no drain. If a frame opened, teardown runs after the final
HTTP response event, streaming body, background task, or WebSocket session and
before host publication is restored.

Normal return, handler failure, provider failure, response failure, cancellation,
and teardown failure follow the existing contract. When application work and
teardown both fail, both exceptions are retained in the existing exception-group
shape. No exception is swallowed or replaced by cleanup.

## Framework behavior invariants

The optimized and compatibility paths must be observably equivalent for:

- path, query, header, cookie, and body parsing;
- Pydantic validation errors, status codes, locations, and bodies;
- ordinary `Depends`, security dependencies, and their cache behavior;
- response models, exception handlers, background tasks, and middleware order;
- streaming without buffering and cancellation during streaming;
- WebSocket accept/send/receive/close lifetime;
- overrides and context propagation across async and sync handlers;
- OpenAPI schemas, operation IDs, request bodies, parameters, and responses; and
- construction identity, lifetime caching, reverse-order teardown, and grouped
  teardown failures.

Multiple injected parameters are resolved by one program and still share
singleton and scoped dependencies according to the container plan. Missing
providers, sync/async mismatches, absent hosting, and scope errors remain the
same `DepinError` subclasses with the same key and chain information.

## Test-first verification

Implementation proceeds in red-green-refactor cycles. The first production
change for each behavior follows a focused failing test that names the mutation
it catches.

### Core lazy-state tests

- singleton-only hosted resolution never constructs a `ScopeFrame`;
- scoped resolution constructs one frame on first use and reuses it;
- lazy seeds are materialized only when their key is requested;
- sync and async resource teardown drains once and in reverse order;
- body failure plus teardown failure preserves both exceptions;
- cancellation drains and restores the prior host/frame state;
- nested contexts restore enclosing publication without sharing request frames;
- barrier/event concurrency proves request isolation and single activation.

### FastAPI integration tests

Real `FastAPI` applications run through `httpx.AsyncClient` and cover:

- no injection, one warm singleton, transient, scoped, and async-resource routes;
- multiple direct injections sharing dependencies and one program invocation;
- mixed `Inject`, `Depends`, security, path, query, body, and request parameters;
- nested provider access to the exact FastAPI `Request` object;
- direct and included-router compilation;
- routes added around repeated same-container installation;
- different-container and incompatible-route setup errors;
- exact OpenAPI and validation-error equivalence with the compatibility app;
- async and sync handlers, custom exception handlers, and background tasks;
- streaming completion, streaming cancellation, WebSocket lifetime, and teardown
  failures; and
- concurrent requests, scopes, overrides, and context restoration synchronized
  by barriers or events rather than sleeps.

The FastAPI floor/latest jobs execute the same behavioral contract. Typing
fixtures prove that handler parameters remain the underlying service type and
that `install` accepts only `FastAPI` plus `FrozenContainer`.

### Performance tests and evidence

The existing six application workloads switch the depin deployment to
`install`. The inventory adds a no-injection pair and maintained component
measurements that isolate:

- minimal lazy host publication without frame activation;
- first lazy frame activation and drain;
- one compiled endpoint program with one and multiple injected values;
- request seed lookup; and
- resource teardown after activation.

Deterministic observations record Python calls, allocation count, allocated
bytes, peak bytes, retained bytes, startup, and validated lifecycle counts. The
accepted baseline and head run in isolated locked environments, in five
counterbalanced repetitions, through the repository's pair and gate harnesses.
Raw observations, environment metadata, gate output, and a concise before/after
analysis are stored under a dated `benchmarks/results/` directory.

## Alternatives rejected

### Keep one FastAPI dependency per injected parameter

This retains the measured traversal cost and cannot amortize multiple injected
values. It remains only as the compatibility mechanism.

### Replace endpoint signatures before route construction

This requires every router to opt into a custom route class before decorators
run and does not cover already-built or included routers with one application
setup call. It weakens migration ergonomics without removing the compatibility
boundary.

### Wrap only `APIRoute.get_route_handler`

That wrapper exits when a `Response` object is returned, before streaming bodies
and background tasks finish. It cannot own request teardown safely.

### Open a scope in the endpoint program unconditionally

This removes dependency-node overhead but retains empty frame allocation and
draining on the CPU-light route. It cannot meet the accepted attribution.

### Change core resolution or add native acceleration

Core resolution accounts for only a small part of the measured application
increment. Such work is outside this specification and would confound the
FastAPI attribution.

## Completion conditions

This design is complete only when behavior, typing, documentation, benchmark,
and repository gates pass; the before/after report demonstrates the accepted
confidence-bound reduction; an independent code review has no unresolved
load-bearing finding; and the pull request is merged without broadening the
scope above.
