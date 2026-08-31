# Composing bindings

A container is built from binding sources. A `Registry` is one; another
container is one; so is anything implementing `Bindings`.

## Registries

A registry is a catalogue you declare once, at module level, and reuse:

```python
from depin import Registry

infra = Registry('infra')
services = Registry('services')


@infra.singleton()
def load_settings() -> Settings:
    return Settings()


@services.scoped()
class UserService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
```

A registry validates nothing and resolves nothing. It only records bindings, so
importing one has no side effect beyond that record.

Registries combine with `|`, and a container takes any number of sources at
construction:

```pycon
>>> from depin import Container, Registry
>>> class Logger: ...
>>> class Metrics: ...
>>> infra = Registry('infra').bind(Logger)
>>> obs = Registry('obs').bind(Metrics)
>>> di = Container(infra | obs).freeze()
>>> isinstance(di[Logger], Logger)
True

```

`Container(a, b)` and `Container().include(a, b)` are the same thing. Records are
concatenated, never de-duplicated: if two sources bind the same key, `freeze()`
raises `DuplicateProviderError` rather than letting one silently win.

## Keys

The provider key is what you resolve by. It is inferred from the binding:

| Binding | Key |
| --- | --- |
| `bind(Cls)` | `Cls`, or its `@provides(...)` target |
| `bind(factory)` | the factory's return annotation |
| `bind(gen_factory)` | the yielded type, unwrapped from `Generator[T]` |
| `bind(x, provides=Abstract)` | `Abstract` |
| `value(token, v)` | `token` |

### Protocols

To bind an implementation against an interface, decorate it:

```pycon
>>> from typing import Protocol
>>> from depin import Container, provides
>>> class Store(Protocol):
...     def get(self) -> str: ...
>>> @provides(Store)
... class MemStore:
...     def get(self) -> str:
...         return 'mem'
>>> di = Container().bind(MemStore).freeze()
>>> di.resolve(Store).get()
'mem'

```

`bind(MemStore, provides=Store)` does the same thing at the call site instead of
on the class. Use the decorator when the class always implements that interface,
the argument when the choice belongs to the composition root.

### Tokens

Values that have no type of their own — a URL, a timeout, a feature flag — get a
`Token`. Two tokens are equal when their names are equal, so the same token can
be declared in more than one module:

```pycon
>>> from typing import Annotated
>>> from depin import Container, Token
>>> db_url = Token[str]('db.url')
>>> class Database:
...     def __init__(self, url: str) -> None:
...         self.url = url
>>> def open_db(url: Annotated[str, db_url]) -> Database:
...     return Database(url)
>>> di = Container().value(db_url, 'postgres://…').bind(open_db).freeze()
>>> di[Database].url
'postgres://…'

```

The `Annotated[str, db_url]` on the parameter is what points at the token; the
bare `str` alone would look for a provider of `str`.

### Tags

When several implementations share one key, tag them apart:

```pycon
>>> from typing import Annotated
>>> from depin import Container, Tag
>>> class Cache:
...     def __init__(self, label: str = '') -> None:
...         self.label = label
>>> def primary() -> Cache:
...     return Cache('primary')
>>> def backup() -> Cache:
...     return Cache('backup')
>>> di = Container().bind(primary, provides=Cache, tag='primary').bind(backup, provides=Cache, tag='backup').freeze()
>>> di.resolve(Cache, tag='primary').label
'primary'

```

Inside a provider, select the tagged one with `Annotated[Cache, Tag('primary')]`.

## Aliases

`provides=` and `@provides` register a class *under* another key. An alias goes
the other way: it adds a second name to a binding that already exists.

```pycon
>>> from typing import Protocol
>>> from depin import Container
>>> class Store(Protocol):
...     def get(self) -> str: ...
>>> class PostgresStore:
...     def get(self) -> str:
...         return 'pg'
>>> di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
>>> di.resolve(Store) is di[PostgresStore]
True

```

Both names reach one instance. The target keeps its lifetime, its cache entry,
and its teardown, so a singleton is still built once and closed once no matter
which name asked for it.

The alias itself is a transient indirection, and `explain()` says so:

```pycon
>>> print(di.explain(Store))
Store  [transient, alias]
  target: PostgresStore  [singleton, class]

```

`transient` describes the alias node, which caches nothing — not the target,
which is the singleton on the line below it. Because the alias is a real node,
it participates in validation like any other: an unbound target, a duplicate
name, a cycle, and a singleton that reaches a scoped provider through an alias
are all rejected by `freeze()`.

depin does not verify that the target satisfies the alias key. A `Protocol` that
is not `runtime_checkable` cannot be checked at runtime, and a structural alias
between two unrelated classes is a legitimate thing to write.

## Decoration

`decorate(key, wrapper)` wraps a binding that already exists. Every consumer of
`key` receives what `wrapper` returns; the binding that was registered keeps
its own lifetime, cache entry, and teardown, reachable at `Underlying(key, 0)`.

```pycon
>>> from depin import Container
>>> class Store:
...     def get(self) -> str:
...         return 'row'
>>> class Cached:
...     def __init__(self, inner: Store) -> None:
...         self.inner = inner
...         self.hits = 0
...
...     def get(self) -> str:
...         self.hits += 1
...         return self.inner.get()
>>> di = Container().bind(Store).decorate(Store, Cached).freeze()
>>> di[Store].get()
'row'

```

`wrapper` declares exactly one parameter whose key and tag are the decorated
ones — `inner` above — which receives the undecorated value. Any further
parameter is an ordinary dependency, resolved from the graph like any other:

```pycon
>>> class Prefix:
...     text = '>> '
>>> class Verbose:
...     def __init__(self, inner: Store, prefix: Prefix) -> None:
...         self.inner = inner
...         self.prefix = prefix
...
...     def get(self) -> str:
...         return f'{self.prefix.text}{self.inner.get()}'
>>> di = Container().bind(Prefix).bind(Store).decorate(Store, Verbose).freeze()
>>> di[Store].get()
'>> row'

```

Two decorators over one key both apply, the last registered wrapping the
first:

```pycon
>>> class Upper:
...     def __init__(self, inner: Store) -> None:
...         self.inner = inner
...
...     def get(self) -> str:
...         return self.inner.get().upper()
>>> class Bracket:
...     def __init__(self, inner: Store) -> None:
...         self.inner = inner
...
...     def get(self) -> str:
...         return f'[{self.inner.get()}]'
>>> di = Container().bind(Store).decorate(Store, Upper).decorate(Store, Bracket).freeze()
>>> di[Store].get()
'[ROW]'
>>> print(di.explain(Store))
Store  [singleton, class]
  inner: Store (decorated x1)  [singleton, class]
    inner: Store (undecorated)  [singleton, class]

```

`explain()` reads outward to inward: the outermost wrapper on the public key,
each further wrapper under `Store (decorated x`*n*`)`, and the registered
binding itself under `Store (undecorated)`. A decorator is a real node, so it
participates in validation like any other: an unbound key, a cycle through the
wrapper's own dependencies, and an async wrapper over a sync binding are all
checked the way an ordinary provider's would be.

A `scope_value` binding cannot be decorated. A value supplied by whoever opens
the scope is read from the active frame before the plan is consulted, so a
parameter would receive the undecorated value while `resolve()` returned the
decorated one; `freeze()` rejects the decorator with `InvalidProviderError`
rather than leave it half-working.

## Conditional bindings

`when=` keeps a binding out of the plan unless a condition holds. It is
accepted by `bind`, `value`, `scope_value`, `alias`, `collect`, `decorate`, and
the `singleton` / `scoped` / `transient` decorators.

```pycon
>>> from depin import Container
>>> class Store: ...
>>> class Postgres(Store): ...
>>> class Memory(Store): ...
>>> production = False
>>> di = (
...     Container()
...     .bind(Postgres, provides=Store, when=lambda: production)
...     .bind(Memory, provides=Store, when=lambda: not production)
...     .freeze()
... )
>>> isinstance(di.resolve(Store), Memory)
True

```

A `bool` is read at the call that appends the record. A callable is called
once inside `freeze()`, with no arguments, and again on every later freeze of
the same builder — a container is a builder, and two freezes may legitimately
differ. Either way, the condition is settled before anything else is
validated: an inactive binding contributes no node, appears in no plan, and is
never introspected for its shape or its parameters. Two bindings for one key,
with exactly one condition active, is the deployment switch shown above; two
active at once still raises `DuplicateProviderError`.

A parameter that requires an inactive binding is unsatisfied, exactly as an
unbound key is — it escapes only through a default or a `T | None`
annotation:

```pycon
>>> class Cache: ...
>>> class Service:
...     def __init__(self, cache: Cache | None = None) -> None:
...         self.cache = cache
>>> di = Container().bind(Cache, when=False).bind(Service).freeze()
>>> di[Service].cache is None
True

```

`MissingProviderError` and `explain()` both name the cause: a key only an
inactive binding declares gets `registered but inactive` appended after the
chain, instead of being reported as unbound outright.

A decorator over an inactive binding needs the same condition. Decorating a
key that no active binding occupies raises `MissingProviderError`, because the
decoration has nothing to wrap; give `decorate(..., when=...)` the identical
predicate so the wrapper disappears along with what it wraps.

## Where to freeze

Freeze once, at the composition root — the entry point that knows the whole
application. Everything below it receives what it needs and never touches a
container. In practice that means a `build()` or `create_app()` function rather
than a module-level global, which also lets a test build a different graph
without patching anything.
