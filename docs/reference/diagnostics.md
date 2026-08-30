# Graph diagnostics

The data behind `FrozenContainer.graph()` and `FrozenContainer.explain()`.

A key is anything a provider can be bound and resolved under:

```python
type ProviderKey = type[object] | Token[object] | str
```

::: depin.DependencyGraph

::: depin.GraphNode

::: depin.GraphEdge

::: depin.ProviderShape
