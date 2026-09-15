# Declarative provider discovery

Declarative discovery starts from objects named explicitly in Python code. A
module declares its own providers, closes them into an immutable `Catalog`, and
a composition root imports completed catalogues into a `Manifest`. depin never
walks a package, searches module globals, follows naming conventions, or imports
modules on the application's behalf.

## Declare providers in their owning module

`provider()` records one class or factory together with the module that declared
it. The resulting `Provider` is immutable. `configure()` returns a replacement
declaration, leaving the original unchanged, and stores metadata for later
processing.

```pycon
>>> from depin import Catalog, Scope, provider
>>> class Cache: ...
>>> declaration = provider(Cache)
>>> transient = declaration.configure(scope=Scope.TRANSIENT, tag='worker')
>>> providers = Catalog(__name__, transient)
>>> providers.providers == (transient,)
True
>>> declaration is transient
False

```

Construct `Catalog(__name__, ...)` in that same module after its declarations.
The first argument must identify the calling module, and every member must have
been declared there. Export the completed catalogue; do not export individual
declarations for another module to assemble. A catalogue contains only local
providers and deliberately is not a `Bindings` source.

## Compose explicit imports with a manifest

The import graph is the discovery graph. A provider module exports a completed
catalogue, and a composition module imports that object explicitly:

```python
# billing/providers.py
from depin import Catalog, provider


class BillingService: ...


billing = Catalog(__name__, provider(BillingService))
```

```python
# application.py
from depin import Manifest
from billing.providers import billing


application = Manifest(__name__, billing)
```

`Manifest` is owned by the module that constructs it, but its sources are the
completed `Catalog` and `Manifest` objects explicitly imported there. Nested
manifests let a package publish a larger boundary without hiding its imports.
Only the manifest satisfies `Bindings`, so pass it to a container and freeze the
ordinary dependency graph:

```pycon
>>> from depin import Catalog, Container, Manifest, provider
>>> class Settings: ...
>>> class Service:
...     def __init__(self, settings: Settings) -> None:
...         self.settings = settings
>>> local = Catalog(__name__, provider(Settings), provider(Service))
>>> application = Manifest(__name__, local)
>>> runtime = Container(application).freeze()
>>> isinstance(runtime[Service].settings, Settings)
True

```

There is no separate discovery runtime. `Container.include(application)` and
`Container(application)` ingest the same records, and `freeze()` validates them
with manually registered bindings as one graph.

## Interleave manifests and manual bindings

A manifest is a binding source, not a special container mode. Include it at the
exact point where its records belong among calls to `bind()`, `value()`,
`alias()`, and the other registration methods. Each source is appended as one
contiguous segment.

```pycon
>>> from depin import Catalog, Container, Manifest, provider
>>> class Before: ...
>>> class Imported: ...
>>> class After: ...
>>> imported = Manifest(__name__, Catalog(__name__, provider(Imported)))
>>> runtime = Container().bind(Before).include(imported).bind(After).freeze()
>>> isinstance(runtime[Before], Before)
True
>>> isinstance(runtime[Imported], Imported)
True
>>> isinstance(runtime[After], After)
True

```

Registration order is retained for diagnostics and deterministic composition;
dependency order is still derived from the validated graph at `freeze()`.

## Repetition remains a conflict

Manifest sources flatten from left to right. Nesting preserves that order, and
repeating a catalogue or manifest repeats every occurrence. Nothing silently
de-duplicates or gives the later declaration precedence, so repeated keys reach
the normal duplicate-provider validation.

```pycon
>>> from depin import Catalog, Container, Manifest, provider
>>> from depin.errors import DuplicateProviderError
>>> class Worker: ...
>>> workers = Catalog(__name__, provider(Worker))
>>> leaf = Manifest(__name__, workers)
>>> repeated = Manifest(__name__, leaf, leaf)
>>> try:
...     Container(repeated).freeze()
... except DuplicateProviderError:
...     print('duplicate rejected')
duplicate rejected

```

This makes conflicts visible at the composition root instead of allowing import
order to choose a winner.

## Reloads create new snapshots

Catalogues and manifests retain immutable tuples of the objects supplied at
construction. Reloading a provider module creates a new exported catalogue; it
does not mutate catalogues already imported or manifests already built. Re-import
the completed catalogue and rebuild the manifest when a reload should change the
application snapshot.

Rebinding a local name illustrates the same boundary:

```pycon
>>> from depin import Catalog, Container, Manifest, provider
>>> from depin.errors import MissingProviderError
>>> class First: ...
>>> class Replacement: ...
>>> exported = Catalog(__name__, provider(First))
>>> snapshot = Manifest(__name__, exported)
>>> exported = Catalog(__name__, provider(Replacement))
>>> runtime = Container(snapshot).freeze()
>>> isinstance(runtime[First], First)
True
>>> try:
...     runtime[Replacement]
... except MissingProviderError:
...     print('not in the snapshot')
not in the snapshot

```

## Declaration, freeze, and resolution stay separate

Declaring providers and composing snapshots calls neither conditions nor
factories. `freeze()` evaluates `when` conditions and validates only the active
records. Resolution constructs the selected provider; a health check, when
configured, runs only through the frozen container's health operations.

```pycon
>>> from depin import Catalog, Container, Manifest, provider
>>> events: list[str] = []
>>> class Service: ...
>>> def enabled() -> bool:
...     events.append('condition')
...     return True
>>> def build_service() -> Service:
...     events.append('factory')
...     return Service()
>>> declared = provider(build_service).configure(when=enabled)
>>> application = Manifest(__name__, Catalog(__name__, declared))
>>> events
[]
>>> runtime = Container(application).freeze()
>>> events
['condition']
>>> isinstance(runtime[Service], Service)
True
>>> events
['condition', 'factory']

```

An unlisted class or factory remains unlisted even when it shares a module,
package, annotation, or name with a declaration. The explicit objects in the
manifest are the complete discovery boundary.
