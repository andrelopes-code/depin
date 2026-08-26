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

!!! warning "Values built before the override are not replaced"

    A singleton resolved before the `with` block is already cached, and the
    override does not evict it. Override before the first resolution, or build a
    fresh container per test.

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
