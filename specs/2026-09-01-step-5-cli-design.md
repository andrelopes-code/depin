# Step 5, cycle 4 — the command and message hosts: design

Date: 2026-09-01
Baseline: 0.15.0 at `79b28a1`
Target: 0.16.0
Status: approved, pending implementation plan

## Goal

Ship the last two integrations of the curated set — Click/Typer and Taskiq —
and close Step 5.

Cycle 3 shipped the request/response hosts. These two are the other shape: a
command invocation and a queue message. Neither has a request, both open a scope
per unit of work, and the roadmap predicted both would "expose lifecycle hooks as
a pair rather than as a block — the case the contract's context managers are
entered and exited by hand".

**That prediction was half wrong, and the measurements say so.** Click does have
a block seam, so nothing is entered and exited by hand there. Taskiq genuinely
does not, and pairing it correctly turns out to be the one hard problem in this
cycle.

## Measurements

Everything below was run against the published `pydepin==0.15.0` in a throwaway
environment, not assumed.

**Click has a block seam.** `click.Context.with_resource(cm)` enters a context
manager and exits it when the Click context closes — after the command body, and
after a group's `result_callback`. Teardown was observed running on a normal
return, on `ctx.exit()`, on `Abort`, on `UsageError`, and on a raising body. So
`Host.scope()` fits Click directly, with no manual pairing.

**Typer no longer is Click.** Up to typer 0.25.1 `typer.Context` *was*
`click.Context`. **0.26.0 is the first release that dropped the `click`
dependency** and vendored click 8.3.1 as `typer._click`; from there
`typer.Context is not click.Context`, `TyperGroup` is not a `click.Group`, and
`get_command()` returns a non-Click object. The full PyPI release list confirms
nothing sits between 0.25.1 and 0.26.0.

This is the opposite of the FastAPI/Starlette result cycle 3 relied on. There,
one identity let one middleware serve two frameworks. Here, an upstream split
means a class-based integration would have to import `typer._click.core.Context`
— a private name in a third-party package, which depin forbids anyone doing to
*it* and should not do to someone else.

**A structural protocol removes the problem entirely.** `with_resource` is
present on every typer release tested, 0.15.4 through 0.27.2, and on
`click.Context`. Declared as a `Protocol`, it is satisfied by both — the same
`install()` source drove a real Click group and a real Typer app, on
click-backed typer (0.15.4, 0.19.2, 0.25.1) and vendored typer (0.26.0, 0.27.2),
on the success and the raising path, with the teardown running after the command
returned and the publication undone afterwards.

**Taskiq's hooks pair, and the pairing is where the bug would live.**
`TaskiqMiddleware.pre_execute` / `post_execute` pair reliably — sync or async,
on a raising task, on a cancelled task, and for sync task bodies in the executor.
`pre_execute` runs in registration order and `post_execute` in reverse.
`contextvars` survive from `pre_execute` through the task body to
`post_execute`, because all three share one asyncio Task and therefore one
Context; the value does not leak back to the caller, and concurrent messages are
isolated.

**Where the `AsyncExitStack` lives is the whole design.** A `TaskiqMiddleware`
instance is shared across every message. Holding the stack as an instance
attribute was measured with three interleaved messages: every `post_execute`
received the *last* stack created, message C's — a real cross-message leak that
closes the wrong scope. Held in a module-level `ContextVar`, each `post_execute`
received its own.

**One hook-ordering hazard.** A middleware registered *after* depin's that
raises in its own `pre_execute` skips depin's `post_execute` and leaks the
scope. Register depin's last.

**`InMemoryBroker` skips middleware lifecycle hooks.** Its `startup()` overrides
the base and never calls middleware `startup`/`shutdown`. Relevant to tests, not
to the integration.

**`Host.activated()` cannot span `startup`/`shutdown`.** They run in different
tasks, so resetting the `ContextVar` token raises `ValueError: Token was created
in a different Context`. There is no process-wide publication story here, and the
integration does not attempt one.

## Public surface

One framework-free module and three specialisations.

| Symbol | Role |
| --- | --- |
| `depin.ext.cli.CommandContext` | The structural seam: anything with `with_resource`. |
| `depin.ext.cli.install` | Opens a scope bound to the command context's lifetime; returns the frame. |
| `depin.ext.click.install` | `cli.install`, seeding `click.Context`. |
| `depin.ext.typer.install` | `cli.install`, seeding nothing. |
| `depin.ext.taskiq.MessageScope` | Middleware: a scope per message, seeding `TaskiqMessage`. |

```python
class CommandContext(Protocol):  # depin.ext.cli
    def with_resource[T](self, context_manager: AbstractContextManager[T], /) -> T: ...


def install[C: CommandContext](
    ctx: C,
    container: FrozenContainer,
    *,
    seed: Callable[[C], tuple[ProviderKey, object] | None] | None = None,
) -> ScopeFrame: ...
```

`install` is **generic over the context type**, and that is load-bearing rather
than decorative. With a non-generic `install(ctx: CommandContext, *, seed:
Callable[[CommandContext], ...])`, passing a `def seed_context(ctx:
click.Context)` is rejected by both checkers — the same contravariance failure
cycle 3 hit with the ASGI triple:

```
mypy: Argument "seed" to "install" has incompatible type "Callable[[Context], ...]";
      expected "Callable[[CommandContext], ...] | None"  [arg-type]
```

Generic, both checkers report zero diagnostics over the protocol, the Click
callbacks and the Typer callbacks, with no suppression, no `Any`, and no private
import.

`install` **returns the `ScopeFrame`**, unlike cycle 3's middlewares, which
return nothing because they have no caller. Here the caller is the user's own
command callback, and the frame is how they seed their own values — a tenant, a
correlation id read off an option — before anything resolves.

`depin/ext/cli.py` imports **no third-party package**, exactly as
`depin/ext/asgi.py` and `depin/ext/wsgi.py` do not. It therefore works for any
command framework whose context can hold a resource, not only the two shipped.

## Semantics

| Operation | Guarantee |
| --- | --- |
| `cli.install(ctx, di)` | Publishes the container and opens one sync scope, bound to the Click/Typer context's lifetime. Teardowns run when that context closes — after the command body, and after a group's `result_callback`. |
| A command that raises | The scope drains and the publication is undone; the exception propagates. Observed for `Abort`, `UsageError`, `ctx.exit()` and an arbitrary exception. |
| Nested group and command scopes | Safe but redundant: the inner scope resolves the outer frame's cached instance. Documented, not prevented. |
| `--help` | Opens no scope. |
| `taskiq` `pre_execute` | Enters `Host.ascope()` on an `AsyncExitStack` held in a `ContextVar`, seeds the `TaskiqMessage`, and returns the message it was given — the receiver threads the return value onward. |
| `taskiq` `post_execute` | Clears the `ContextVar`, then closes the stack. Teardowns run, then the publication is undone. |
| Concurrent messages | Isolated. Each message's `pre_execute`, task body and `post_execute` share one asyncio Context. |

## Sync and async

**Click and Typer are sync, and that is the honest answer rather than a
limitation to work around.** Neither awaits a coroutine callback — both return it
unawaited. An async provider resolved in a sync scope raises
`AsyncInSyncContextError`; calling `aresolve` inside `Host.scope()` raises an
`ExceptionGroup` wrapping `TeardownError` **and leaks the provider**. The guide
says so and points async CLI users at driving `asyncio.run` themselves around
`Host.ascope()`.

**Taskiq is async throughout.**

## Errors

No new exception type. `ContainerNotBoundError` covers the unhosted case, and
each integration's own message names its own setup step.

## Module layout

| Module | Change |
| --- | --- |
| `depin/ext/cli.py` | **New.** The `CommandContext` protocol and generic `install`. No third-party import. |
| `depin/ext/click.py` | **New.** `install` seeding `click.Context`. |
| `depin/ext/typer.py` | **New.** `install` seeding nothing, and why. |
| `depin/ext/taskiq.py` | **New.** `MessageScope`, and the `ContextVar` that makes it correct. |
| `pyproject.toml` | `click`, `typer`, `taskiq` extras with declared floors. |

## Declared floors

- `click>=8.2` — `with_resource` predates it; 8.2 is where `Group` absorbed
  `MultiCommand`, and it is the tidier supported floor.
- `typer>=0.16` — **corrected from `>=0.15` after the resolver disagreed with the
  measurement.** The seam was measured working on 0.15.4, but
  `--resolution lowest-direct` never selects that release: 0.15.4 caps Click below
  8.2, and depin declares `click>=8.2`, so the resolver picks typer **0.15.0**,
  which declares only `click>=8.0.0` and therefore accepts a Click it cannot run.
  On that pair `--help` raises `TypeError: Parameter.make_metavar() missing 1
  required positional argument: 'ctx'`, because Click 8.2 gave `make_metavar()` a
  context and Typer passes one only from 0.16. The two extras resolve together, so
  depin's own Click floor is the Click that Typer gets. 0.16.0 is the first
  release that works, verified against PyPI metadata and real installs rather than
  chosen conservatively.

  Still **deliberately far below `>=0.26`**, the release that vendored click: the
  protocol removes the vendoring problem, so a floor at the split would invent a
  constraint the design does not have. 0.16.0 declares `click>=8.0.0` and is
  click-backed, so the `minimum declared versions` job exercises `CommandContext`
  against click-backed Typer and the `latest released versions` job against
  vendored Typer — the protocol is proven across the split at both CI ends.
- `taskiq>=0.11` — the middleware contract is identical on 0.11.0, 0.11.18 and
  0.12.6.

## What Typer does not get

`depin.ext.typer.install` seeds **nothing**, and the omission is deliberate.
Seeding under the key `typer.Context` would be a lie: measured on 0.27.2, the
value handed to a callback annotated `typer.Context` is a
`typer._click.core.Context`, and `isinstance(value, typer.Context)` is `False`.
depin keys on the annotation as written, so the binding would resolve and hand
back an object that is not an instance of its own key.

Seeding under the private class instead would make depin depend on a third-party
private name. Between a lie and a private import, the module ships neither and
documents the gap: a Typer user who wants the context in the graph seeds it
themselves through the returned frame, under a key they own.

## Verification

- **Unit.** `tests/unit/test_cli.py`: `install` driven against a hand-written
  object satisfying `CommandContext`, with no framework installed — the scope
  opened, the seed applied and skipped, the frame returned, the scope drained
  when the context closes and on a raising body. This suite runs on the
  free-threaded and pre-release CI jobs, which install no framework, and is
  therefore the proof that `cli.py` needs no extra.
- **Integration.** One file per framework against its real runner:
  `click.testing.CliRunner`, Typer's runner, and Taskiq's `InMemoryBroker`.
- **The Taskiq concurrency proof.** A test that interleaves three messages and
  asserts each `post_execute` closed its own scope. **It must be shown to fail
  when the `ContextVar` is replaced by an instance attribute** — a test that
  stays green under that substitution proves nothing, and this is the one bug
  the module exists to avoid.
- **Contract.** `tests/unit/test_integration_contract.py` covers all four new
  modules automatically.
- **Docs.** `docs/guide/integrations.md` gains the command and message hosts;
  `docs/reference/` gains a page per new module.
- **Examples.** One, `examples/click_app/`. Typer and Taskiq differ from it by
  an import and a decorator.

## Acceptance criteria

- `depin/ext/cli.py` imports no third-party package, proven by `tests/unit`
  passing on the framework-free CI jobs.
- All four new modules import nothing from depin's private package.
- The same `install` is exercised against both a click-backed and a vendored
  Typer, and against Click.
- The Taskiq concurrency test fails when the `ContextVar` becomes an instance
  attribute.
- No suppression is added: `depin/` still carries exactly three, all
  pre-existing.
- Coverage over `depin/` stays at or above 95%.
- `minimum-versions` and `latest-versions` exercise every new extra at both ends.
- The mutation gate stays green; nothing under `depin/_core/` changes.

## Out of scope

| Item | Reason |
| --- | --- |
| A class-based Click integration (`ScopedGroup`, `ScopedCommand`) | Measured and working, but it buys a user one line and costs a second public shape per framework. `install` in a callback covers a bare command, a group, chained subcommands and a command tree the user cannot re-class. |
| Anything under `depin/ext/typer.py` beyond `install` | Every richer shape needs `typer._click`. |
| An async Click command runner | Click does not await a callback. Documented, with the two-line `asyncio.run` + `ascope()` pattern in the guide. |
| Holding a container across Taskiq `startup`/`shutdown` | Measured impossible: the hooks run in different tasks, so the `ContextVar` token cannot be reset. |
| Django, Celery, APScheduler | Not in the roadmap's curated set. The contract is what serves them. |
