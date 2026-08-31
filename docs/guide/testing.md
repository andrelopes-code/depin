# Testing

The point of wiring by type is that a test can substitute any node of the graph
without the code under test noticing.

## Overriding a provider

`override()` replaces a key for the duration of a block, everywhere it appears —
including deep in the graph, as a dependency of something else:

```pycon
>>> from depin import Container
>>> class Clock:
...     def now(self) -> str:
...         return 'real'
>>> class Report:
...     def __init__(self, clock: Clock) -> None:
...         self.clock = clock
...
...     def render(self) -> str:
...         return f'at {self.clock.now()}'
>>> class FrozenClock:
...     def now(self) -> str:
...         return '2026-01-01'
>>> di = Container().bind(Clock).bind(Report).freeze()
>>> with di.override(Clock, FrozenClock()):
...     di[Report].render()
'at 2026-01-01'

```

Three details worth knowing:

- If the replacement is a callable that is not a class, it is treated as a
  factory and invoked per resolution. Anything else is returned as-is.
- The override is bound to the current `contextvars.Context`, so concurrent
  tests do not leak into each other.
- Overrides nest, innermost wins, and a key that was never bound at all can be
  overridden — useful for a dependency you only stub.

!!! note "What survives an override"

    `override()` replaces the key immediately, even for a singleton already
    built. What survives is a *consumer* — a value built before the block
    keeps the instance it was constructed with, because a provider's arguments
    are resolved once, at construction time:

    ```pycon
    >>> di = Container().bind(Clock).bind(Report).freeze()
    >>> _ = di[Report]
    >>> with di.override(Clock, FrozenClock()):
    ...     di[Clock].now()
    ...     di[Report].render()
    '2026-01-01'
    'at real'

    ```

    `reset()` drops every built singleton's cache, so the next resolution of
    `Report` rebuilds it and picks up the override that is active at that
    point:

    ```pycon
    >>> di.reset()
    >>> with di.override(Clock, FrozenClock()):
    ...     di.reset()
    ...     di[Report].render()
    'at 2026-01-01'
    >>> di.reset()
    >>> di[Report].render()
    'at real'

    ```

    The `depin.ext.pytest` fixtures below call `reset()` on both edges of the
    block, so a test never has to reason about which *singletons in the root
    cache* were built first. A scoped value already cached in an open
    `depin_scope` frame is outside that cache: neither edge evicts it, so it
    keeps the dependency it was built with for as long as the scope stays
    open.

## A pytest fixture

Freezing is cheap and gives every test an isolated cache:

```python
import pytest

from myapp.wiring import build


@pytest.fixture
def di():
    container = build()
    yield container
    container.close()


def test_report_uses_the_clock(di):
    with di.override(Clock, FrozenClock()):
        assert di[Report].render() == 'at 2026-01-01'
```

For an async graph use `aclose()` in the teardown half of the fixture.

## The pytest plugin

`depin.ext.pytest` is registered on the `pytest11` entry point by the
distribution, so installing `pydepin` at all makes its fixtures available in
any suite with no `conftest.py` import. The `pytest` extra adds nothing to
that: it only states the pytest floor the plugin is tested against.

```bash
uv add pydepin                # the fixtures are already available
uv add 'pydepin[pytest]'      # and the tested pytest floor is enforced
```

The plugin defines `depin_container` itself, but only to raise: a suite that
never hands it a container gets a `ContainerNotBoundError` naming the fixture
to define. Add one to your own `conftest.py`; every other fixture builds on
whatever it returns:

```python
import pytest

from depin import FrozenContainer

from myapp.wiring import build


@pytest.fixture
def depin_container() -> FrozenContainer:
    return build()
```

`depin_override` is `depin_container`'s `override()` with the fix from the
note above already applied — it calls `reset()` before entering the block and
again on exit:

```python
def test_report_uses_the_fake_clock(depin_container, depin_override) -> None:
    # Report is a singleton and is already built here, before the override.
    real = depin_container[Report]

    with depin_override(Clock, FrozenClock()) as di:
        assert di[Report].render() == 'at 2026-01-01'

    # Report is a singleton in the root cache, so reset() on exit rebuilds it
    # against the real Clock the next time it is resolved.
    assert depin_container[Report].render() == 'at real'
```

Use `depin_aoverride` — the same shape, built on `areset()` — when a
singleton on the overridden path is constructed by an async provider;
`reset()` raises for that case rather than leaving it half torn down.

`depin_scope` opens one synchronous scope around the test and yields its
`ScopeFrame`, so a `Container.scope_value` key can be seeded before anything
resolves through it:

```python
def test_job_sees_the_seeded_value(depin_container, depin_scope) -> None:
    depin_scope.provide(job, 'reindex')
    assert depin_container.resolve(job) == 'reindex'
```

`depin_ascope` is its async counterpart, built on `Host.ascope()`.

One test may request `depin_scope` and `depin_override` together. Both edges
of the override block reach the root cache only, so a scoped value already
built inside the open scope is untouched and keeps the dependency it was
constructed with.

`examples/eviction/` in the repository runs the same eviction without pytest,
as a plain module.

## Replacing bindings instead of overriding them

When a whole subsystem differs in tests — an in-memory store instead of a
database — swap the registry rather than each provider:

```python
from depin import Container

from myapp.wiring import services
from tests.fakes import fake_infra


def build_test_container():
    return Container(fake_infra, services).freeze()
```

This keeps the production graph untouched and still exercises the real
`Container` / `FrozenContainer`, which is what you want a wiring test to prove.

## Wiring a function under test

`@inject` fills only the parameters whose default is `injected(...)`, and leaves
everything else to the caller — including those same parameters, if the caller
passes them:

```pycon
>>> from depin import Container, injected
>>> class Repo:
...     def count(self) -> int:
...         return 3
>>> class FakeRepo:
...     def count(self) -> int:
...         return 99
>>> di = Container().bind(Repo).freeze()
>>> @di.inject
... def summary(label: str, repo: Repo = injected(Repo)) -> str:
...     return f'{label}={repo.count()}'
>>> summary(label='n')
'n=3'
>>> summary(label='n', repo=FakeRepo())
'n=99'

```

Injected keys are validated when the decorator runs, not when the function is
called: decorating a function that asks for an unregistered key raises
`MissingProviderError` immediately, at import time, instead of on the first
request.
