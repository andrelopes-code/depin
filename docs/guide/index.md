# Guide

Six pages, in the order most projects need them.

- **[Lifetimes and scopes](lifetimes.md)** — how long a value lives, when it is
  rebuilt, and when its teardown runs. Read this first; almost every question
  about depin is really a question about lifetimes.
- **[Composing bindings](composition.md)** — registries, containers built from
  several sources, tags, protocols, tokens, and aliases.
- **[Resolution semantics](resolution.md)** — optional dependencies and
  collection injection: what a `T | None` parameter and a `list[T]` parameter
  mean, and when each resolves to `None` or to every registered provider.
- **[Testing](testing.md)** — replacing a dependency without rebuilding the
  graph, and wiring test functions with `@inject`.
- **[Inspecting the graph](diagnostics.md)** — the resolution tree, `dot` and
  `mermaid` renderings, and how `freeze()` and `explain()` report the same
  chain.
- **[FastAPI](fastapi.md)** — the optional ASGI integration: one scope per
  request, `Inject[T]`, and shutdown.

## The three stages

| Stage | Object | What it does |
| --- | --- | --- |
| Declare | `Container` | Mutable builder. Collects bindings; validates nothing. |
| Validate | `Container.freeze()` | Runs every static check, then returns the runtime. |
| Resolve | `FrozenContainer` | Immutable. Builds and caches values, opens scopes, injects. |

`freeze()` is the gate, and it is deliberately strict. It rejects:

- a dependency with no provider, naming the resolution chain that needed it;
- a cycle in the graph;
- two bindings that resolve to the same key and tag;
- a singleton that depends on a scoped provider (it would capture one scope's
  instance forever);
- a factory whose return type cannot be inferred, or a parameter with neither an
  annotation nor a default;
- a generator or context-manager provider bound as transient, which would leave
  its teardown unreachable.

Everything above is caught before a single value is constructed, so a graph that
freezes at start-up will not fail to wire itself under load.
