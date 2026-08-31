# Warmup and health

`FrozenContainer` reads a validated plan two more ways: `warmup()` builds every
singleton before the first request, and `health()` runs the checks a binding
declared. Neither alters the plan; both are optional operations a deployment
wires in where it needs them.

## Warmup

A singleton is normally built on first resolution. `warmup()` builds every
singleton immediately, in resolution order, so a provider that fails to
construct fails at startup — where a deployment can roll back — instead of on
the first request that needs it.

```pycon
>>> from depin import Container, Scope
>>> class Config:
...     def __init__(self) -> None:
...         print('building Config')
>>> class Service:
...     def __init__(self, config: Config) -> None:
...         print('building Service')
...         self.config = config
>>> class Session:
...     def __init__(self) -> None:
...         print('building Session')
>>> di = Container().bind(Config).bind(Service).bind(Session, scope=Scope.SCOPED).freeze()
>>> report = di.warmup()
building Config
building Service
>>> [node.key.__qualname__ for node in report.constructed]
['Config', 'Service']

```

`Session` is scoped, and warmup never printed `building Session`: a scoped
value belongs to a scope that has not opened yet, and a transient value is
never cached, so neither has a boot-time instance to build. Only singletons are
touched.

`WarmupReport` carries two tuples, both in resolution order and both holding
the same `GraphNode` the graph view already exposes: `constructed` is what this
call built, `cached` is what was already built. Calling `warmup()` again builds
nothing — everything reports under `cached` instead:

```pycon
>>> report = di.warmup()
>>> report.constructed
()
>>> [node.key.__qualname__ for node in report.cached]
['Config', 'Service']

```

### The async rule

A singleton that needs async resolution cannot be built by `warmup()`.
Rather than build every sync singleton and stop partway through the async one,
`warmup()` checks every singleton it would touch first and refuses before
constructing anything:

```pycon
>>> class Pool: ...
>>> async def make_pool() -> Pool:
...     return Pool()
>>> di = Container().bind(make_pool, provides=Pool).freeze()
>>> di.warmup()
Traceback (most recent call last):
    ...
depin.errors.AsyncInSyncContextError: warmup() cannot construct Pool: they require async resolution. Call awarmup() instead.

```

`awarmup()` is the counterpart an ASGI lifespan calls; it drives async and sync
singletons alike and returns the same report.

### A failure aborts startup

A singleton whose construction raises propagates the exception unchanged.
Warmup does not catch it and does not report a partial result — a container
with some singletons built and one failed is a startup to abort, not a state
to report:

```pycon
>>> class Broken:
...     def __init__(self) -> None:
...         raise RuntimeError('cannot reach the database')
>>> di = Container().bind(Broken).freeze()
>>> di.warmup()
Traceback (most recent call last):
    ...
RuntimeError: cannot reach the database

```

## Health checks

`bind(Database, check=ping)` declares how to verify the value that binding
produces. The check is not run at bind time, or by `freeze()`, or by
`warmup()` — only `health()` and `ahealth()` run it, and only when asked.

```pycon
>>> from depin import Container
>>> class Database:
...     def __init__(self) -> None:
...         self.connected = True
>>> def ping(db: Database) -> bool:
...     return db.connected
>>> di = Container().bind(Database, check=ping).freeze()
>>> report = di.health()
>>> report.healthy
True
>>> report.results[0].key.__qualname__, report.results[0].error
('Database', None)

```

A check receives the value its provider produced — `ping` above is called
with the `Database` instance, not with the class. It is healthy unless it
raises or returns exactly `False`; a `0` or an empty string is a value the
check returned, not a verdict, so it does not count as a failure.

`checks()` returns the declared checks as data, in resolution order, and runs
nothing:

```pycon
>>> [check.key.__qualname__ for check in di.checks()]
['Database']

```

### Every check runs

One check failing never stops another from running. `health()` calls every
declared check and collects every result, even after the first one fails:

```pycon
>>> class Cache:
...     def __init__(self) -> None:
...         self.up = False
>>> def cache_ping(cache: Cache) -> bool:
...     return cache.up
>>> di = Container().bind(Database, check=ping).bind(Cache, check=cache_ping).freeze()
>>> report = di.health()
>>> report.healthy
False
>>> [(result.key.__qualname__, result.healthy) for result in report.results]
[('Database', True), ('Cache', False)]

```

A check that raises is caught, and the exception is carried on
`HealthResult.error` rather than propagating:

```pycon
>>> def failing_ping(db: Database) -> bool:
...     raise ConnectionError('connection refused')
>>> di = Container().bind(Database, check=failing_ping).freeze()
>>> result = di.health().results[0]
>>> result.healthy, result.error
(False, ConnectionError('connection refused'))

```

### The async rule

A check on an async provider, or an `async def` check itself, needs an event
loop. `health()` checks every declared check first and refuses before running
any of them, the same rule `warmup()` applies to construction:

```pycon
>>> async def make_pool() -> Pool:
...     return Pool()
>>> async def aping(pool: Pool) -> bool:
...     return True
>>> di = Container().bind(make_pool, provides=Pool, check=aping).freeze()
>>> di.health()
Traceback (most recent call last):
    ...
depin.errors.AsyncInSyncContextError: health() cannot run the checks for Pool: they require an event loop, because the provider is async or the check is. Call ahealth() instead.

```

`ahealth()` awaits both kinds.

### A resolution error propagates; a check's own error does not

`health()` distinguishes failing to build the value from the value failing its
check. A provider that raises while resolving is a container misused, and that
exception propagates like any other resolution failure — it is never turned
into a `HealthResult`:

```pycon
>>> class Unreachable:
...     def __init__(self) -> None:
...         raise RuntimeError('no route to host')
>>> def unreachable_check(value: object) -> bool:
...     return True
>>> di = Container().bind(Unreachable, check=unreachable_check).freeze()
>>> di.health()
Traceback (most recent call last):
    ...
RuntimeError: no route to host

```

Only once the value exists does its check run, and only a failure from *that*
call is reported on `HealthResult`.

### A check on a scoped binding needs a scope

Running a check resolves its provider exactly as any other resolution would.
A check on a `Scope.SCOPED` binding therefore needs an active scope, and
raises `OutsideScopeError` without one:

```pycon
>>> from depin import Scope
>>> from depin.errors import OutsideScopeError
>>> class Session:
...     def __init__(self) -> None:
...         self.ok = True
>>> def session_check(session: Session) -> bool:
...     return session.ok
>>> di = Container().bind(Session, scope=Scope.SCOPED, check=session_check).freeze()
>>> try:
...     di.health()
... except OutsideScopeError as exc:
...     print(type(exc).__name__)
OutsideScopeError
>>> with di.scope():
...     di.health().healthy
True

```

### A check on a decorated binding verifies the undecorated value

A check stays with the binding it was declared on. `decorate()` moves the
registered binding to `Underlying(key, 0)` and puts the wrapper on the public
key, and a check declared on the registered binding rides with it — it
verifies the value before decoration, not after, and `HealthCheck.key` names
the underlying key:

```pycon
>>> from depin import Underlying
>>> class Store:
...     def __init__(self) -> None:
...         self.ok = True
>>> def store_check(store: Store) -> bool:
...     return store.ok
>>> class Logged:
...     def __init__(self, inner: Store) -> None:
...         self.inner = inner
>>> di = Container().bind(Store, check=store_check).decorate(Store, Logged).freeze()
>>> di.checks()[0].key == Underlying(Store, 0)
True

```

A decorator that wants its own check declares one on itself, the same way any
other binding does.
