# Step 5, cycle 2 — the pytest plugin and singleton eviction: design

Date: 2026-08-31
Baseline: 0.13.0 at `5a186db`
Target: 0.14.0
Status: approved, pending implementation plan

## Goal

Ship the `pytest` integration, and the one core seam it cannot work without.

**Eviction.** `FrozenContainer.reset()` and `await areset()` drain the singleton
cache and drop it, so the next resolution rebuilds. Nothing public does this
today, and no amount of cleverness in an integration can substitute: the
contract test this repository ships forbids `depin/ext/` from importing
`depin._core`, so the seam must be public or the plugin cannot exist. That
constraint is not an obstacle to route around — it is the contract working.

**The plugin.** `depin.ext.pytest`, registered on the `pytest11` entry point.
Five fixtures: the container the suite under test supplies, an evicting override
in both a sync and an async form, and a scope in both forms, opened through the
`Host` cycle 1 published.

**The caveat.** The README's "overrides do not evict caches" goes, replaced by
an accurate statement and a fixture that removes the reason for it.

## What changes for an existing graph

| Before | After |
| --- | --- |
| Nothing drops a built singleton. | `reset()` / `areset()` drain and drop the whole singleton cache. |
| `pytest` sees depin as an ordinary library. | Installing `pydepin` registers a plugin that adds five fixtures and nothing else. |

Both are additions. No existing method changes behaviour, and a suite that
requests none of the fixtures behaves exactly as it did at 0.13.0.

## Measurements

Five questions were measured against the tree at `5a186db` rather than assumed.

**The README's caveat is wrong about which value survives.** It says a singleton
resolved before the block "is already built, and the override does not replace
it". Measured: `di.override(Clock, FakeClock())` *does* replace `Clock` even
when `Clock` was already built, because `_lookup_optional` consults overrides
before the plan and returns a `TRANSIENT` spec that never reads the cache. What
survives is a **consumer**: a `Report` singleton built before the block keeps
the real `Clock` it was constructed with, so `di[Report].render()` returns
`'real'` inside the block while `di[Clock].now()` returns `'fake'`. The caveat
names the wrong object, and the correction is part of this cycle.

**Eviction is what fixes it, and the fix is small.** Prototyped by draining the
root frame's teardowns and clearing its cache under one lock: after the drop,
the same override reaches the previously-built consumer — `di[Report].render()`
returns `'fake'` — and after a second drop the real graph is back. The
generator singleton's teardown ran exactly once, in the drop, and the value it
owned was not rebuilt until something asked for it.

**`close()` is not the seam, and must not become it.** `close()` drains
teardowns and leaves the cache populated, so `di.close()` followed by
`di[Pool]` hands back the *same, already-torn-down* object. Making `close()`
clear the cache would fix that, and would give the plugin its seam for free —
but it would also make a stray resolution after shutdown construct a fresh
resource that nothing will ever close, which is worse than the dead object it
replaces. `close()` therefore keeps its meaning, `reset()` gets its own, and
the dead-object behaviour is routed to Step 6 rather than half-fixed here.

**A module named `pytest` inside a package is a valid plugin.** A package
module at `depinx/ext/pytest.py`, loaded with `-p depinx.ext.pytest`, resolved
`import pytest` to the installed distribution — absolute imports, as expected —
and its fixtures were injected into an unrelated test file. `depin/ext/pytest.py`
is therefore free to take the obvious name.

**Nothing in the suite resolves after `close()`.** Thirty-one call sites across
`tests/`, `examples/`, and `docs/`; none follows `close()` with a resolution.
So the decision above costs nothing today and closes no door.

## Public surface

Two methods, five fixtures, one extra, one entry point.

| Symbol | Role |
| --- | --- |
| `FrozenContainer.reset` / `areset` | Drain the singleton cache and drop it, so the next resolution rebuilds. |
| `depin_container` *(fixture)* | The frozen container the suite under test supplies. |
| `depin_override` / `depin_aoverride` *(fixtures)* | Override a key with the cache evicted around the block. |
| `depin_scope` / `depin_ascope` *(fixtures)* | A scope for the test, opened through `Host`, yielding its `ScopeFrame`. |

```python
def reset(self) -> None: ...
async def areset(self) -> None: ...
```

`reset` adds no name to `depin.__all__`: both are methods on a type that is
already exported. The plugin exports nothing importable at all — a fixture is
reached by requesting it, not by importing it.

## Data model

None. `reset()` holds no state and returns nothing; the plugin holds none
either. The eviction is one operation on the root `ScopeFrame`, which already
owns both the cache and the teardown list it has to take atomically.

## Semantics

| Operation | Guarantee |
| --- | --- |
| `reset()` | Takes the root frame's teardowns and clears its cache under one lock, then runs the teardowns outside the lock, newest first. Failures collect into an `ExceptionGroup`; one teardown failing never hides another or leaves the cache half-dropped. |
| `areset()` | The same, awaiting async teardowns. Required when any singleton is an async provider. |
| Both | Scoped and transient providers are untouched: a scoped value belongs to a scope, and a transient one is never cached. An active scope's frame is not the root frame and is not dropped. |
| Both | Idempotent. Calling twice with nothing built drains nothing and drops nothing. |
| `depin_container` | Supplied by the suite under test, by overriding the fixture. The plugin's own definition raises with the wording that says so. |
| `depin_override` | Evicts, enters `override()`, yields the container, exits, evicts again. Values built against the replacement do not survive the block, and values built before it do not survive into it. |
| `depin_scope` | Opens `Host(container).scope()`, so `hosted_container()` reaches the container from inside the test, and yields the frame for seeding. |

The cache is dropped on **both** edges of `depin_override`, not only the first.
Dropping only on entry would leave the block's fakes cached for whatever runs
next in the same container.

## Errors

| Trigger | Exception | Message |
| --- | --- | --- |
| A teardown fails during `reset()` | `ExceptionGroup` | `depin teardown errors`, as `close()` already raises |
| An async teardown is drained by `reset()` | `TeardownError` | the existing wording, naming `areset()` as the fix |
| `depin_container` not supplied by the suite | `ContainerNotBoundError` | names the fixture to define and shows its shape |

No new exception type. `ContainerNotBoundError` already means "no container is
available here", which is exactly the condition.

## Module layout

| Module | Change |
| --- | --- |
| `depin/_core/scope.py` | A module-level `drop_sync` / `drop_async` over a frame: the cache and the teardown list are private to this module, so the operation belongs here rather than reaching in from `frozen.py`. |
| `depin/_core/frozen.py` | `reset`, `areset`. |
| `depin/ext/pytest.py` | **New.** The five fixtures. Imports `depin` and `pytest`, nothing else. |
| `pyproject.toml` | A `pytest` extra with a declared floor, and the `pytest11` entry point. |
| `README.md` | The caveat corrected and shortened. |

The plugin registers unconditionally, not behind the extra: an entry point is
declared by the distribution, not by an extra, and a plugin that adds five
fixtures and no hooks costs a suite that ignores it one import. The extra
exists so `pydepin[pytest]` states the floor the plugin is tested against.

## Verification

- **Unit.** `tests/unit/test_reset.py`: a built singleton is dropped and
  rebuilt; its teardown runs exactly once, in the drop; several failing
  teardowns collect into an `ExceptionGroup` and the cache is still dropped; an
  async singleton is refused by `reset()` and drained by `areset()`; an active
  scope's values survive; the operation is idempotent.
- **The caveat.** A test that fails on `main`: a consumer singleton built
  before an override sees the replacement once the cache is evicted around it.
- **Plugin.** `tests/integration/test_pytest_plugin.py`, driven with pytest's
  own `pytester` fixture so the plugin is exercised as a plugin — loaded by
  entry point, in a subprocess suite — rather than by importing its functions.
  Cases: the fixtures are available without a `conftest` import; a suite that
  does not define `depin_container` fails with the message that names it; the
  evicting override reaches a pre-built consumer; the async forms drive an
  async provider; `hosted_container()` works inside `depin_scope`.
- **Contract.** The existing `tests/unit/test_integration_contract.py` covers
  the new module automatically, and is what forces `reset` to be public.
- **Example.** `examples/pytest_plugin/` — a small suite plus the container it
  tests, executed like every other example.
- **Docs.** `docs/guide/testing.md` gains the plugin; `docs/reference/frozen.md`
  picks up the two methods.

## Acceptance criteria

- A consumer singleton built before an override sees the replacement inside a
  `depin_override` block, and the test proving it fails without the eviction.
- The plugin is exercised through `pytester`, not by calling its fixtures
  directly.
- `depin/ext/pytest.py` imports nothing from `depin._core`, enforced by the
  existing contract test.
- The README carries no claim about overrides that the measurements contradict.
- Coverage over `depin/` stays at or above 95%; the mutation gate stays at or
  above 95% killed.
- `depin/` still carries exactly three suppressions.
- No benchmark regression: `reset` is not on any resolution path.

## Out of scope

| Item | Reason |
| --- | --- |
| Evicting only the overridden key's consumers | Needs reverse reachability over the plan and per-key teardown records. The whole cache is what the roadmap specifies, it is what a test wants, and it needs neither. |
| Making `close()` clear the cache | Measured above: it would make a post-shutdown resolution construct a resource nothing will close. Routed to Step 6 with the measurement. |
| A `depin_freeze` fixture that builds the container | The suite under test owns its wiring. A fixture that guessed at it would be a second, worse `Container`. |
| Auto-use fixtures | A plugin that changes behaviour without being requested is the opposite of what this library is for. |
