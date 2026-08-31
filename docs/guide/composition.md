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

## Where to freeze

Freeze once, at the composition root — the entry point that knows the whole
application. Everything below it receives what it needs and never touches a
container. In practice that means a `build()` or `create_app()` function rather
than a module-level global, which also lets a test build a different graph
without patching anything.
