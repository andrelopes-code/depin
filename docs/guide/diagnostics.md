# Inspecting the graph

`Container.freeze()` validates the whole dependency graph before a single value
is constructed. `FrozenContainer` exposes that validated graph two ways: as text
for one key, and as data for the whole container.

## The resolution tree

```pycon
>>> from depin import Container, Scope
>>> class Settings: ...
>>> class Pool:
...     def __init__(self, settings: Settings) -> None: ...
>>> class Repo:
...     def __init__(self, pool: Pool, settings: Settings) -> None: ...
>>> di = Container().bind(Settings).bind(Pool).bind(Repo).freeze()
>>> print(di.explain(Repo))
Repo  [singleton, class]
  pool: Pool  [singleton, class]
    settings: Settings  [singleton, class]
  settings: Settings  [singleton, class]  (shown above)

```

Each line carries the parameter that requires the node, the node's key, and its
lifetime and provider shape. A subtree that has already been printed is marked
rather than repeated, so a diamond-shaped graph stays as small as it is.

A key nothing provides is described rather than raised:

```pycon
>>> class Absent: ...
>>> print(di.explain(Absent))
no provider for Absent (tag=None)

```

## The graph as data

`graph()` returns an immutable view. Nodes come in resolution order, so a node
never precedes one it depends on.

```pycon
>>> [node.key.__name__ for node in di.graph().nodes]
['Settings', 'Pool', 'Repo']
>>> [node.key.__name__ for node in di.graph().roots]
['Repo']

```

## Exports

```pycon
>>> print(di.graph().mermaid())
graph LR
  n0["Settings<br/>singleton, class"]
  n1["Pool<br/>singleton, class"]
  n2["Repo<br/>singleton, class"]
  n1 -->|settings| n0
  n2 -->|pool| n1
  n2 -->|settings| n0

```

`dot()` produces the Graphviz equivalent. Both are deterministic: the same
container renders the same document on every run, so an export can be committed
and diffed.

## What the view does not show

Both methods describe the plan `freeze()` validated. An active `override()`
substitutes a provider for resolution only; inside an `override` block,
`explain()` still describes the binding the container was frozen with.
