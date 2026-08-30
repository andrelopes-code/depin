# Step 2 — Graph diagnostics: design

Date: 2026-08-30
Baseline: 0.6.0 at `5cf6989`
Target: 0.7.0
Status: approved, pending implementation plan

## Goal

Make the validated dependency graph inspectable. `ResolutionPlan` already holds
every fact a diagnostic needs — key, tag, scope, shape, async propagation, and
each provider's parameters in declaration order. Step 2 exposes that data as a
public, immutable view and renders it in three forms: an indented tree for a
single key, a Graphviz `dot` document, and a Mermaid `graph` document.

Nothing about resolution, validation, or lifetimes changes. The step adds
read-only surface over a structure that is already built and already frozen.

## Public surface

Five symbols are added to `depin/__init__.py` and to `__all__`.

| Symbol | Role |
| --- | --- |
| `DependencyGraph` | The immutable view of a `ResolutionPlan`. |
| `GraphNode` | One provider in that view. |
| `GraphEdge` | One provider parameter and the identity it resolves to. |
| `ProviderShape` | The provider-shape enum, promoted from `_core/spec.py`. |
| `ProviderKey` | The key type alias, promoted from `_core/spec.py`. |

Two methods are added to `FrozenContainer`.

```python
def explain(self, key: ProviderKey, *, tag: str | None = None) -> str: ...
def graph(self) -> DependencyGraph: ...
```

`ProviderShape` is promoted rather than mirrored as a `Literal` alias: a second
vocabulary for the same nine values would need to be kept in step with the enum
by hand, and `AGENTS.md` requires the narrowest type that states the contract.
Promotion freezes the nine members at 1.0; adding a shape after that becomes a
public-surface change, which is the correct classification for it.

`ProviderKey` is promoted because a consumer writing a function over
`GraphNode.key` needs to name its type. Step 3 widens the alias to admit
parameterised generics; widening a union is compatible with every consumer
already written against it.

## Data model

```python
@dataclass(frozen=True, slots=True)
class GraphEdge:
    parameter: str
    key: ProviderKey
    tag: str | None
    satisfied: bool


@dataclass(frozen=True, slots=True)
class GraphNode:
    key: ProviderKey
    tag: str | None
    scope: Scope
    shape: ProviderShape
    needs_async: bool
    dependencies: tuple[GraphEdge, ...]


class DependencyGraph:
    __slots__ = ('_index', '_nodes')

    def __init__(self, nodes: tuple[GraphNode, ...]) -> None: ...
    @property
    def nodes(self) -> tuple[GraphNode, ...]: ...
    @property
    def roots(self) -> tuple[GraphNode, ...]: ...
    def node(self, key: ProviderKey, tag: str | None = None) -> GraphNode: ...
    def find(self, key: ProviderKey, tag: str | None = None) -> GraphNode | None: ...
    def dot(self) -> str: ...
    def mermaid(self) -> str: ...
```

`GraphNode` and `GraphEdge` are frozen dataclasses; `DependencyGraph` is not.
It holds an identity index built once in `__init__`, and a frozen dataclass can
only populate a derived field through `object.__setattr__`, which the codebase
does not use. A slotted class with read-only properties and a structural
`__eq__` over `nodes` gives the same immutability without that. Rebuilding the
index on every lookup instead would make `explain()` quadratic in the node
count.

`nodes` holds every provider in `ResolutionPlan.order`, which is topological:
a node never precedes one it depends on. `roots` is the subset no other node
depends on.

An edge carries an identity, `(key, tag)`, rather than a reference to a
`GraphNode`. A recursive object graph of frozen dataclasses can only be built
through `object.__setattr__`, which the codebase does not otherwise use, and the
identity form makes node equality structural and the render order independent of
object identity. `DependencyGraph.node` resolves an identity in constant time
against an index built once at construction.

`satisfied` is `False` for a parameter that has a default and no binding. That
is the only unsatisfied edge a frozen container can hold: `freeze()` rejects
every unsatisfied parameter that has no default.

`GraphEdge` carries no `Scope`: the scope belongs to the target node, and
duplicating it would allow the two to disagree.

## Overrides

`graph()` and `explain()` read `ResolutionPlan` directly. They do not consult
`overrides.active`, so an active `FrozenContainer.override` block does not change
their output.

Three consequences follow, and all three are intended:

- The export is deterministic across runs, which the acceptance criteria
  require. Overrides live in a `ContextVar`, so any read of them makes the
  output a function of the calling context.
- The view is what `freeze()` validated. The roadmap defines `graph()` as a view
  of the plan, and a substituted provider is not in the plan.
- Inside an `override` block, `explain()` describes the original provider. This
  is stated in one sentence of each method's docstring.

Annotating a substituted node instead was rejected: it puts a context-dependent
field inside `GraphNode`, which breaks the structural identity of a node and
forces the export to exclude that field to stay deterministic. It pays the cost
of reading the override state without gaining the property that reading it would
give.

## Rendering

All three renderers walk `nodes` in plan order and each node's `dependencies` in
parameter order. No renderer iterates a `set` or the keys of an unordered
`dict`. Output is ASCII.

### `explain(key)`

An indented tree, two spaces per level. The root line carries no parameter
prefix; every other line is prefixed by the parameter that requires it.

```
Service  [singleton, class]
  config: Config  [singleton, class]
    dsn: str  [transient, value]
  store: Store  [scoped, async generator, async]
    conn: Connection  [scoped, context manager, async]
  timeout: float  (unbound, default)
```

The bracketed annotations appear in this order: scope, shape, `async` when
`needs_async` is set, and `tag='...'` when the node carries a tag. An unsatisfied
edge renders as `(unbound, default)` and has no children.

A node whose subtree was already printed renders as
`Config  [singleton, class]  (shown above)` with no children. Without the
elision, a diamond-shaped graph prints the shared subtree once per path.

An unregistered key returns a single line, in one of the two wordings
`MissingProviderError` uses. When some node declares an unsatisfied parameter
for that identity, the line is the freeze-time wording, produced by the same
`format_missing` that `build_plan` raises with — the same `required by`, the
same resolution chain, and the same candidate scan:

```
no provider for float (required by Service.timeout; resolution chain: Service -> float)
```

The chain reported is the deepest one that reaches the parameter, chosen the way
`_collect_missing` chooses it. When nothing requires the key, the line is the
resolution-time wording, plus the candidate scan:

```
no provider for Store (tag=None); candidates: app.store.PostgresStore
```

### `dot()`

```
digraph depin {
  rankdir=LR;
  n0 [label="Service\nsingleton, class", shape=box];
  n1 [label="Config\nsingleton, class", shape=box];
  u0 [label="float\nunbound", shape=box, style=dashed];
  n0 -> n1 [label="config"];
  n0 -> u0 [label="timeout", style=dashed];
}
```

### `mermaid()`

```
graph LR
  n0["Service<br/>singleton, class"]
  n1["Config<br/>singleton, class"]
  u0["float<br/>unbound"]
  n0 -->|config| n1
  n0 -.->|timeout| u0
```

Both formats identify a bound node as `n<index in plan order>` and an unbound
target as `u<index in first-encounter order>`. An index is stable across runs,
is a valid Mermaid identifier without escaping, and keeps a key containing a
quote or a bracket out of the identifier position. In a `dot` label a quotation
mark and a backslash are escaped with a backslash; in a Mermaid label a
quotation mark becomes `#quot;`. An edge label is a Python parameter name, so it
can contain neither format's delimiter.

An unsatisfied edge produces a dashed edge to a dashed node labelled with the
unbound key, so a graph that resolves a default is visible as such rather than
silently absent.

## Errors

No exception type is added to `depin/errors.py`.

| Call | Behaviour |
| --- | --- |
| `graph()`, `dot()`, `mermaid()` | Never raise. |
| `DependencyGraph.node` | Raises `MissingProviderError` for an unregistered identity, in the wording `FrozenContainer._lookup` uses. |
| `DependencyGraph.find` | Returns `None` for an unregistered identity. |
| `explain` | Returns text for an unregistered key. Raises `MissingProviderError` for a value that is not a valid key type. |

`explain` does not raise on an unregistered key because that is the question it
exists to answer; a diagnostic that fails when asked about an absent key fails in
the case that motivates the call. An invalid key type is a defect at the call
site, not a question about the graph, so it raises as `_lookup` does.

## Chain consistency

The acceptance criterion requires `explain()` and `MissingProviderError` to name
the same chain. They share the formatter rather than reimplementing it:
`graph._format_missing` and `graph._suggest_candidates` lose their leading
underscore and become `format_missing` and `suggest_candidates`, which
`_core/render.py` imports. `format_missing` takes keys instead of
`ProviderSpec` values, so a caller holding a `GraphNode` can reach it, and joins
its chain through a new `fmt_chain(keys) -> str` in `_core/spec.py`, next to
`fmt_key`. The dependency runs one way: `render` imports `graph`, and `graph`
imports nothing from `render`.

The test drives both paths from one set of bindings in two variants. With the
parameter declared without a default, `freeze()` raises and the error names a
chain. With a default added, `freeze()` succeeds and `explain()` prints a path.
The test asserts the two strings are equal.

## Module layout

`_core/graph.py` is 340 lines and owns validation. Diagnostics is a separate
responsibility, so it lands in two new modules rather than in that file.

| Module | Responsibility |
| --- | --- |
| `_core/diagnostics.py` | `DependencyGraph`, `GraphNode`, `GraphEdge`, and their construction from a `ResolutionPlan`. |
| `_core/render.py` | The three text renderers: the `explain` tree, `dot`, and `mermaid`. |

`frozen.py` gains the two public signatures and their docstrings, and delegates
the work. The `_core` map in `AGENTS.md` gains the two rows.

## Verification

- `tests/unit/test_graph_view.py`: construction of the view from a plan —
  node set, edge order, `satisfied`, `roots`, `node`, `find`.
- `tests/unit/test_graph_render.py`: the three renderers, including subtree elision,
  the unregistered-key line, tag annotation, async annotation, and label
  escaping.
- Determinism: each renderer produces identical output on two calls in one
  process, and across subprocesses run with different `PYTHONHASHSEED` values.
- Chain consistency, as described above.
- Property-based checks with Hypothesis, reusing the graph model in
  `tests/unit/test_graph_properties.py`: every spec in the plan appears as
  exactly one node; every edge either indexes a node or has `satisfied=False`;
  `explain()` names every key reachable from its root; each export emits exactly
  `len(nodes)` node declarations.
- `tests/typing/test_conformance.py` gains `assert_type` cases for `explain`,
  `graph`, `DependencyGraph.node`, and `DependencyGraph.find`.
- The mutation gate at 95% covers both new modules.
- `benchmarks/`: `explain()` and `dot()` over a 1000-node graph, guarding the
  elision path against a regression to per-path expansion.
- `examples/graph_diagnostics/main.py`, listed in `examples/README.md` and
  executed by `tests/integration/test_examples.py`.
- `tests/integration/test_fastapi_ext.py` exercises `explain` and `graph`
  against the extension's container, per the roadmap's cross-cutting rule.
- `docs/reference/diagnostics.md` and `docs/guide/diagnostics.md`, with `pycon`
  blocks run as doctests, and both added to the `mkdocs.yml` nav.

## Acceptance criteria

- `explain()` output for a missing key names the same chain the corresponding
  `MissingProviderError` names.
- Export output is deterministic across runs, so it is diffable in a test.
- The five gates and `mkdocs build --strict` pass with no warnings or waivers.
- No regression against the benchmark baseline.

## Out of scope

| Item | Reason |
| --- | --- |
| `Container.explain()` before `freeze()` | The freeze-time errors already print the chain and the candidate scan. A second pre-freeze renderer would restate them. |
| Reflecting active overrides | Makes the output context-dependent, defeating the determinism criterion. |
| Image rendering | `dot` and `mermaid` are text. Rendering them is the consumer's toolchain, and a renderer would be the core's first runtime dependency. |
| A JSON export | No consumer is identified. `nodes` is public and structural, so a consumer can serialise it without depin shipping a format. |
