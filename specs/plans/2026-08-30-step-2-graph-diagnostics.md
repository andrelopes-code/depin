# Step 2 — Graph diagnostics: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the validated `ResolutionPlan` as a public, immutable graph view and render it three ways — an indented resolution tree for one key, a Graphviz `dot` document, and a Mermaid `graph` document — for the 0.7.0 milestone.

**Architecture:** Two new `_core` modules. `diagnostics.py` turns a `ResolutionPlan` into `DependencyGraph`/`GraphNode`/`GraphEdge` and indexes it by `(key, tag)`. `render.py` walks that view iteratively and emits the three text forms, reusing the missing-provider formatter that `graph.py` already raises with, so a diagnostic and an error never disagree. `FrozenContainer` gains two delegating methods and nothing else changes.

**Tech Stack:** Python 3.12–3.14, free-threaded CPython 3.13t/3.14t, pytest, Hypothesis, mutmut 3.7, pytest-benchmark, mkdocs-material with mkdocstrings, uv.

**Spec:** `specs/2026-08-30-step-2-graph-diagnostics-design.md`

## Global constraints

Every task inherits these requirements from `AGENTS.md`, the approved roadmap, and the spec.

- The core keeps zero runtime dependencies. Nothing in this step adds a package to `[project.dependencies]` or to any dependency group.
- Use PEP 695 syntax. Do not introduce `TypeVar`, `typing.Any`, `typing.cast`, `# type: ignore`, or `# pyright: ignore`.
- Data structures are `@dataclass(frozen=True, slots=True)`. `DependencyGraph` is the single documented exception: it derives an index in `__init__`, and populating a derived field on a frozen dataclass requires `object.__setattr__`, which this codebase does not use.
- Every renderer walks `DependencyGraph.nodes` in order and each node's `dependencies` in order. No renderer iterates a `set`, and no renderer depends on the iteration order of a `dict` it did not build itself in walk order.
- Output is ASCII. No box-drawing characters, no non-breaking spaces.
- Tests exercise the real `Container` / `FrozenContainer`. Do not mock the DI machinery.
- Public API additions carry Google-style docstrings that omit types and include a doctest `Example:`. Doctests run in the default `pytest` invocation.
- Coverage over `depin/` stays at or above 95%; it is 98.32% on 3.12 at the 0.6.0 baseline. The mutation gate stays at 95% killed, and `[tool.mutmut] only_mutate = ["depin/_core/*.py"]` already covers both new modules.
- Before every commit, run in this exact order:

  ```bash
  uv run ruff format
  uv run ruff check
  uv run basedpyright
  uv run mypy
  uv run pytest
  ```

- Any commit that changes prose also runs `uv run --group docs mkdocs build --strict` after the five gates.
- Commits are focused, conventional, at most 72 characters in the subject, and contain no attribution or automation language.

## File structure

| Path | Responsibility | Task |
| --- | --- | --- |
| `depin/_core/spec.py` | Adds `fmt_chain`, the single join used by every rendered resolution path. | 1 |
| `depin/_core/graph.py` | Shares its missing-provider formatter and candidate scan with the renderer. | 1 |
| `tests/unit/test_spec.py` | Covers `fmt_chain`. | 1 |
| `tests/unit/test_graph_validation.py` | Comment reference follows the rename. | 1 |
| `depin/_core/diagnostics.py` | `GraphEdge`, `GraphNode`, `DependencyGraph`, and `build_graph`. | 2, 4 |
| `tests/unit/test_graph_view.py` | Construction of the view: nodes, edges, `satisfied`, `roots`, `node`, `find`. | 2 |
| `depin/_core/render.py` | The three renderers and the absent-key line. | 3, 4 |
| `tests/unit/test_graph_render.py` | The three renderers, elision, escaping, determinism. | 3, 4 |
| `depin/_core/frozen.py` | `FrozenContainer.graph()` and `FrozenContainer.explain()`. | 5 |
| `depin/__init__.py` | Exports the five new public symbols. | 5 |
| `tests/unit/test_public_api.py` | Pins the new `__all__`. | 5 |
| `tests/typing/test_conformance.py` | `assert_type` over the new surface. | 5 |
| `tests/integration/test_fastapi_ext.py` | Exercises the new surface through the extension. | 5 |
| `tests/unit/test_graph_properties.py` | Generative invariants over the view and the renderers. | 6 |
| `benchmarks/test_diagnostics.py` | `explain()` and `dot()` over a 1000-node graph. | 6 |
| `docs/reference/diagnostics.md` | Generated reference for the new symbols. | 7 |
| `docs/guide/diagnostics.md` | Narrative guide, with `pycon` doctests. | 7 |
| `mkdocs.yml` | Nav entries for both pages. | 7 |
| `examples/graph_diagnostics/__init__.py` | Makes the example a package. | 7 |
| `examples/graph_diagnostics/main.py` | Runnable program for the concept. | 7 |
| `examples/README.md` | Lists the new example. | 7 |
| `tests/integration/test_examples.py` | Executes the new example. | 7 |
| `AGENTS.md` | Adds the two modules to the `_core` map. | 7 |

---

### Task 1: Share the missing-provider formatter

`explain()` must name the same chain `MissingProviderError` names. That holds by construction only if both call one formatter. This task moves the formatter and the candidate scan out of `graph.py`'s private namespace and makes the formatter take keys, so a caller holding a `GraphNode` can reach it.

**Files:**

- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/graph.py`
- Modify: `tests/unit/test_spec.py`
- Modify: `tests/unit/test_graph_validation.py:32`

**Interfaces:**

- Produces: `fmt_chain(keys: Iterable[object]) -> str` in `depin._core.spec`.
- Produces: `format_missing(key: ProviderKey, chain: tuple[ProviderKey, ...], owner: ProviderKey, param_name: str) -> str` in `depin._core.graph`, renamed from `_format_missing` and taking keys rather than `ProviderSpec` values.
- Produces: `suggest_candidates(target: object) -> list[str]` in `depin._core.graph`, renamed from `_suggest_candidates`.

- [ ] **Step 1: Write the failing test for `fmt_chain`**

Append to `tests/unit/test_spec.py`:

```python
def test_fmt_chain_joins_keys_with_arrows() -> None:
    class First: ...

    class Second: ...

    assert fmt_chain([First, Second]) == f'{fmt_key(First)} -> {fmt_key(Second)}'


def test_fmt_chain_of_one_key_has_no_arrow() -> None:
    class Only: ...

    assert fmt_chain([Only]) == fmt_key(Only)


def test_fmt_chain_of_nothing_is_empty() -> None:
    assert fmt_chain([]) == ''
```

Add `fmt_chain` to the existing `from depin._core.spec import ...` line at the top of that file, keeping the names alphabetically sorted as `ruff`'s isort rules require.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_spec.py -k fmt_chain`
Expected: FAIL, `ImportError: cannot import name 'fmt_chain'`.

- [ ] **Step 3: Add `fmt_chain`**

Append to `depin/_core/spec.py`, directly below `fmt_key`:

```python
def fmt_chain(keys: Iterable[object]) -> str:
    """Render a resolution path as ``A -> B -> C``, in walk order.

    Every rendered path in the library goes through here, so an error message
    and a diagnostic can never disagree about how a chain is spelled.
    """
    return ' -> '.join(fmt_key(key) for key in keys)
```

`Iterable` is already imported at the top of that module.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_spec.py -k fmt_chain`
Expected: PASS, 3 tests.

- [ ] **Step 5: Rename and re-sign the formatter in `graph.py`**

Replace the existing `_format_missing` definition with:

```python
def format_missing(
    key: ProviderKey,
    chain: tuple[ProviderKey, ...],
    owner: ProviderKey,
    param_name: str,
) -> str:
    """The message `build_plan` raises for an unsatisfied parameter.

    Also used by `depin._core.render` for a key that `explain()` is asked about
    and no binding provides, so the two paths report one chain in one wording.
    """
    suggestions = suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    return (
        f'no provider for {fmt_key(key)} '
        f'(required by {fmt_key(owner)}.{param_name}; '
        f'resolution chain: {fmt_chain((*chain, key))}){extra}'
    )
```

Update the call site inside `_check_missing`:

```python
    lines = [
        format_missing(ident[0], tuple(spec.key for spec in chain), owner.key, param_name)
        for ident, (chain, owner, param_name) in ordered
    ]
```

Rename `_suggest_candidates` to `suggest_candidates` at its definition and at the reference inside the `_loaded_modules` docstring. Extend the import from `depin._core.spec` on line 15 to include `fmt_chain`.

- [ ] **Step 6: Follow the rename in the test comment**

In `tests/unit/test_graph_validation.py`, line 32 reads ``Module-level by necessity: `_suggest_candidates` finds classes by walking``. Change `_suggest_candidates` to `suggest_candidates`.

- [ ] **Step 7: Run the five gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass. The message text is unchanged, so every existing assertion on `MissingProviderError` still holds.

- [ ] **Step 8: Commit**

```bash
git add depin/_core/spec.py depin/_core/graph.py tests/unit/test_spec.py tests/unit/test_graph_validation.py
git commit -m "refactor: share the missing-provider formatter"
```

---

### Task 2: Build the graph view

**Files:**

- Create: `depin/_core/diagnostics.py`
- Create: `tests/unit/test_graph_view.py`

**Interfaces:**

- Consumes: `ProviderKey`, `ProviderShape`, `ProviderSpec`, `ResolutionPlan`, `fmt_key` from `depin._core.spec`; `Scope` from `depin._core.scope`; `MissingProviderError` from `depin.errors`.
- Produces: `GraphEdge(parameter: str, key: ProviderKey, tag: str | None, satisfied: bool)`.
- Produces: `GraphNode(key: ProviderKey, tag: str | None, scope: Scope, shape: ProviderShape, needs_async: bool, dependencies: tuple[GraphEdge, ...])`.
- Produces: `DependencyGraph(nodes: tuple[GraphNode, ...])` with `nodes`, `roots`, `node(key, tag=None)`, `find(key, tag=None)`, and — added in Task 4 — `dot()` and `mermaid()`.
- Produces: `build_graph(plan: ResolutionPlan) -> DependencyGraph`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_graph_view.py`:

```python
"""The immutable view a frozen container exposes over its validated plan."""

import pytest

from depin._core.container import Container
from depin._core.diagnostics import DependencyGraph, GraphNode, build_graph
from depin._core.graph import build_plan
from depin._core.scope import Scope
from depin._core.spec import ProviderShape
from depin.errors import MissingProviderError


class Config:
    pass


class Store:
    def __init__(self, config: Config) -> None:
        self.config = config


class Service:
    def __init__(self, store: Store, config: Config) -> None:
        self.store = store
        self.config = config


def build() -> DependencyGraph:
    plan = build_plan(Container().bind(Config).bind(Store).bind(Service).records())
    return build_graph(plan)


def test_every_provider_becomes_one_node() -> None:
    graph = build()
    assert len(graph.nodes) == 3
    assert {node.key for node in graph.nodes} == {Config, Store, Service}


def test_nodes_are_in_resolution_order() -> None:
    graph = build()
    keys = [node.key for node in graph.nodes]
    assert keys.index(Config) < keys.index(Store) < keys.index(Service)


def test_a_node_carries_its_scope_shape_and_tag() -> None:
    graph = build()
    node = graph.node(Config)
    assert node.scope is Scope.SINGLETON
    assert node.shape is ProviderShape.CLASS
    assert node.tag is None
    assert node.needs_async is False


def test_edges_follow_the_parameter_order_of_the_provider() -> None:
    graph = build()
    node = graph.node(Service)
    assert [edge.parameter for edge in node.dependencies] == ['store', 'config']
    assert [edge.key for edge in node.dependencies] == [Store, Config]
    assert all(edge.satisfied for edge in node.dependencies)


def test_a_defaulted_parameter_with_no_binding_is_an_unsatisfied_edge() -> None:
    class Timeout:
        pass

    class Client:
        def __init__(self, timeout: Timeout | None = None) -> None:
            self.timeout = timeout

    graph = build_graph(build_plan(Container().bind(Client).records()))
    edge = graph.node(Client).dependencies[0]
    assert edge.parameter == 'timeout'
    assert edge.satisfied is False


def test_roots_are_the_nodes_nothing_depends_on() -> None:
    graph = build()
    assert [node.key for node in graph.roots] == [Service]


def test_find_returns_none_for_an_unbound_key() -> None:
    assert build().find(Store, 'other') is None


def test_node_raises_for_an_unbound_key() -> None:
    with pytest.raises(MissingProviderError, match="no provider for Store \\(tag='other'\\)"):
        _ = build().node(Store, 'other')


def test_a_tagged_binding_keeps_its_tag_on_the_node() -> None:
    graph = build_graph(build_plan(Container().bind(Config, tag='primary').records()))
    assert graph.node(Config, 'primary').tag == 'primary'
    assert graph.find(Config) is None


def test_two_views_of_one_plan_are_equal() -> None:
    plan = build_plan(Container().bind(Config).bind(Store).records())
    assert build_graph(plan) == build_graph(plan)


def test_a_graph_is_not_equal_to_another_type() -> None:
    assert build() != 'not a graph'


def test_the_repr_reports_the_node_count() -> None:
    assert repr(build()) == 'DependencyGraph(3 nodes)'


def test_a_node_is_hashable_and_structural() -> None:
    first = build().node(Config)
    second = build().node(Config)
    assert first == second
    assert isinstance(first, GraphNode)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_graph_view.py`
Expected: FAIL at collection, `ModuleNotFoundError: No module named 'depin._core.diagnostics'`.

- [ ] **Step 3: Write the module**

Create `depin/_core/diagnostics.py`:

```python
"""The immutable, navigable view of a validated `ResolutionPlan`."""

from collections.abc import Mapping
from dataclasses import dataclass

from depin._core.scope import Scope
from depin._core.spec import ProviderKey, ProviderShape, ProviderSpec, ResolutionPlan, fmt_key
from depin.errors import MissingProviderError

type _Ident = tuple[ProviderKey, str | None]


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """One provider parameter and the binding identity it resolves to.

    ``satisfied`` is false only for a parameter that carries a default and that
    no binding provides. `Container.freeze()` rejects every other unsatisfied
    parameter, so a frozen graph holds no other kind.
    """

    parameter: str
    key: ProviderKey
    tag: str | None
    satisfied: bool


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One provider in the validated graph.

    ``dependencies`` is in the provider's own parameter order, which is what
    makes every rendering of the graph reproducible.
    """

    key: ProviderKey
    tag: str | None
    scope: Scope
    shape: ProviderShape
    needs_async: bool
    dependencies: tuple[GraphEdge, ...]


class DependencyGraph:
    """The validated dependency graph, as data.

    Returned by `FrozenContainer.graph()`. Nodes come in resolution order: a
    node never precedes one it depends on. The view describes the plan
    `Container.freeze()` validated, so an active `FrozenContainer.override`
    does not change it.
    """

    __slots__ = ('_index', '_nodes')

    def __init__(self, nodes: tuple[GraphNode, ...]) -> None:
        self._nodes = nodes
        self._index: Mapping[_Ident, GraphNode] = {(node.key, node.tag): node for node in nodes}

    @property
    def nodes(self) -> tuple[GraphNode, ...]:
        """Every provider in the graph, in resolution order."""
        return self._nodes

    @property
    def roots(self) -> tuple[GraphNode, ...]:
        """The nodes no other node depends on, in resolution order."""
        depended = {(edge.key, edge.tag) for node in self._nodes for edge in node.dependencies if edge.satisfied}
        return tuple(node for node in self._nodes if (node.key, node.tag) not in depended)

    def node(self, key: ProviderKey, tag: str | None = None) -> GraphNode:
        """Return the node bound under ``key`` and ``tag``.

        Raises:
            MissingProviderError: Nothing is bound under that key and tag. Use
                `find` to ask without raising.
        """
        found = self.find(key, tag)
        if found is None:
            raise MissingProviderError(f'no provider for {fmt_key(key)} (tag={tag!r})')
        return found

    def find(self, key: ProviderKey, tag: str | None = None) -> GraphNode | None:
        """Return the node bound under ``key`` and ``tag``, or None when nothing is."""
        return self._index.get((key, tag))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DependencyGraph):
            return NotImplemented
        return self._nodes == other._nodes

    def __repr__(self) -> str:
        return f'DependencyGraph({len(self._nodes)} nodes)'


def build_graph(plan: ResolutionPlan) -> DependencyGraph:
    """Project a validated plan into the public view."""
    return DependencyGraph(tuple(_node_for(spec, plan) for spec in plan.order))


def _node_for(spec: ProviderSpec, plan: ResolutionPlan) -> GraphNode:
    edges = tuple(
        GraphEdge(
            parameter=param.name,
            key=param.key,
            tag=param.tag,
            satisfied=(param.key, param.tag) in plan.by_key,
        )
        for param in spec.params
    )
    return GraphNode(
        key=spec.key,
        tag=spec.tag,
        scope=spec.scope,
        shape=spec.shape,
        needs_async=spec.needs_async,
        dependencies=edges,
    )
```

Defining `__eq__` sets `__hash__` to None, so `DependencyGraph` is unhashable. Nothing hashes it; `GraphNode` and `GraphEdge` stay hashable because they are frozen dataclasses.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_graph_view.py`
Expected: PASS, 13 tests.

- [ ] **Step 5: Run the five gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add depin/_core/diagnostics.py tests/unit/test_graph_view.py
git commit -m "feat: project the resolution plan into a graph view"
```

---

### Task 3: Render the resolution tree

**Files:**

- Create: `depin/_core/render.py`
- Create: `tests/unit/test_graph_render.py`

**Interfaces:**

- Consumes: `DependencyGraph`, `GraphNode` from `depin._core.diagnostics`; `format_missing`, `suggest_candidates` from `depin._core.graph`; `ProviderKey`, `ProviderShape`, `fmt_key` from `depin._core.spec`.
- Produces: `render_tree(graph: DependencyGraph, key: ProviderKey, tag: str | None) -> str`.
- Produces: `annotation_parts(node: GraphNode) -> list[str]`, the scope/shape/async/tag fragments both the tree and the exports label nodes with.

The import direction is one way: `render` imports `graph`, and `graph` imports nothing from `render`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_graph_render.py`:

```python
"""The three text renderings of a dependency graph."""

from collections.abc import Generator

import pytest

from depin._core.container import Container
from depin._core.diagnostics import DependencyGraph, build_graph
from depin._core.graph import build_plan
from depin._core.markers import Token
from depin._core.render import render_tree
from depin._core.scope import Scope
from depin.errors import MissingProviderError


class Config:
    pass


class Store:
    def __init__(self, config: Config) -> None:
        self.config = config


class Service:
    def __init__(self, store: Store, config: Config) -> None:
        self.store = store
        self.config = config


def build() -> DependencyGraph:
    return build_graph(build_plan(Container().bind(Config).bind(Store).bind(Service).records()))


def test_a_leaf_renders_as_one_annotated_line() -> None:
    assert render_tree(build(), Config, None) == 'Config  [singleton, class]'


def test_a_tree_indents_each_level_by_two_spaces() -> None:
    assert render_tree(build(), Store, None) == (
        'Store  [singleton, class]\n  config: Config  [singleton, class]'
    )


def test_a_repeated_subtree_is_rendered_once() -> None:
    assert render_tree(build(), Service, None) == (
        'Service  [singleton, class]\n'
        '  store: Store  [singleton, class]\n'
        '    config: Config  [singleton, class]\n'
        '  config: Config  [singleton, class]  (shown above)'
    )


def test_an_async_provider_is_annotated_as_async() -> None:
    class Session:
        pass

    async def session() -> Session:
        return Session()

    graph = build_graph(build_plan(Container().bind(session).records()))
    assert render_tree(graph, Session, None) == 'Session  [singleton, async function, async]'


def test_a_scoped_generator_reports_its_shape() -> None:
    class Connection:
        pass

    def connection() -> 'Generator[Connection]':
        yield Connection()

    graph = build_graph(build_plan(Container().bind(connection, scope=Scope.SCOPED).records()))
    assert render_tree(graph, Connection, None) == 'Connection  [scoped, generator]'


def test_a_tag_is_reported_in_the_annotations() -> None:
    graph = build_graph(build_plan(Container().bind(Config, tag='primary').records()))
    assert render_tree(graph, Config, 'primary') == "Config  [singleton, class, tag='primary']"


def test_an_unbound_default_renders_as_a_leaf() -> None:
    class Timeout:
        pass

    class Client:
        def __init__(self, timeout: Timeout | None = None) -> None:
            self.timeout = timeout

    graph = build_graph(build_plan(Container().bind(Client).records()))
    assert render_tree(graph, Client, None) == (
        'Client  [singleton, class]\n  timeout: Timeout | None  (unbound, default)'
    )


def test_a_token_key_renders_by_its_repr() -> None:
    port = Token[int]('port')
    graph = build_graph(build_plan(Container().value(port, 8080).records()))
    assert render_tree(graph, port, None) == "Token('port')  [singleton, value]"


def test_an_unregistered_key_that_nothing_requires_reports_the_lookup_wording() -> None:
    class Absent:
        pass

    assert render_tree(build(), Absent, None) == 'no provider for Absent (tag=None)'


def test_the_tree_is_identical_on_two_calls() -> None:
    graph = build()
    assert render_tree(graph, Service, None) == render_tree(graph, Service, None)
```

Write the `Generator` return annotation directly, without quotes: the import is already at the top of the file.

Confirm the exact spelling `Timeout | None` matches what `fmt_key` produces for that parameter's key before locking the assertion: run `uv run python -c "from depin._core.spec import fmt_key; print(fmt_key(int | None))"`. If the union renders differently, bind a non-optional defaulted parameter instead — `def __init__(self, timeout: Timeout = Timeout()) -> None` — and assert `timeout: Timeout  (unbound, default)`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_graph_render.py`
Expected: FAIL at collection, `ModuleNotFoundError: No module named 'depin._core.render'`.

- [ ] **Step 3: Write the renderer**

Create `depin/_core/render.py`:

```python
"""Text renderings of a `DependencyGraph`: a resolution tree, Graphviz, and Mermaid."""

from depin._core.diagnostics import DependencyGraph, GraphNode
from depin._core.graph import format_missing, suggest_candidates
from depin._core.spec import ProviderKey, ProviderShape, fmt_key

type _Ident = tuple[ProviderKey, str | None]

_SHAPE_NAMES: dict[ProviderShape, str] = {
    ProviderShape.CLASS: 'class',
    ProviderShape.FUNCTION: 'function',
    ProviderShape.ASYNC_FUNCTION: 'async function',
    ProviderShape.GENERATOR: 'generator',
    ProviderShape.ASYNC_GENERATOR: 'async generator',
    ProviderShape.CONTEXT_MANAGER: 'context manager',
    ProviderShape.ASYNC_CONTEXT_MANAGER: 'async context manager',
    ProviderShape.VALUE: 'value',
    ProviderShape.FRAME: 'frame',
}


def annotation_parts(node: GraphNode) -> list[str]:
    """The scope, shape, async flag and tag fragments, in the order every renderer uses."""
    parts = [node.scope.value, _SHAPE_NAMES[node.shape]]
    if node.needs_async:
        parts.append('async')
    if node.tag is not None:
        parts.append(f'tag={node.tag!r}')
    return parts


def render_tree(graph: DependencyGraph, key: ProviderKey, tag: str | None) -> str:
    """The resolution tree below ``(key, tag)``, or the missing-provider line for it."""
    root = graph.find(key, tag)
    if root is None:
        return _render_absent(graph, key, tag)

    lines: list[str] = []
    expanded: set[_Ident] = set()
    # Explicit stack rather than recursion: a chain of a thousand providers is a
    # supported graph, and CPython's recursion limit is well below that.
    stack: list[tuple[int, str, GraphNode | ProviderKey]] = [(0, '', root)]
    while stack:
        depth, label, target = stack.pop()
        indent = '  ' * depth
        if not isinstance(target, GraphNode):
            lines.append(f'{indent}{label}{fmt_key(target)}  (unbound, default)')
            continue
        annotations = f'[{", ".join(annotation_parts(target))}]'
        ident = (target.key, target.tag)
        if ident in expanded:
            lines.append(f'{indent}{label}{fmt_key(target.key)}  {annotations}  (shown above)')
            continue
        expanded.add(ident)
        lines.append(f'{indent}{label}{fmt_key(target.key)}  {annotations}')
        for edge in reversed(target.dependencies):
            child = graph.find(edge.key, edge.tag)
            stack.append((depth + 1, f'{edge.parameter}: ', edge.key if child is None else child))
    return '\n'.join(lines)


def _render_absent(graph: DependencyGraph, key: ProviderKey, tag: str | None) -> str:
    required = _deepest_requirement(graph, key, tag)
    if required is not None:
        chain, owner, parameter = required
        return format_missing(key, chain, owner, parameter)
    suggestions = suggest_candidates(key)
    extra = f'; candidates: {", ".join(suggestions)}' if suggestions else ''
    return f'no provider for {fmt_key(key)} (tag={tag!r}){extra}'


def _deepest_requirement(
    graph: DependencyGraph,
    key: ProviderKey,
    tag: str | None,
) -> tuple[tuple[ProviderKey, ...], ProviderKey, str] | None:
    """The longest chain reaching an unsatisfied parameter bound for ``(key, tag)``.

    Picks the chain the way `depin._core.graph._collect_missing` picks it, so the
    line `explain` returns for a required-but-unbound key is the line `freeze()`
    would have raised had that parameter carried no default. It inherits that
    walk's cost on a dense graph; the roadmap routes that to Step 6.
    """
    best: tuple[tuple[ProviderKey, ...], ProviderKey, str] | None = None
    for root in graph.nodes:
        stack: list[tuple[GraphNode, tuple[_Ident, ...]]] = [(root, ((root.key, root.tag),))]
        while stack:
            node, chain = stack.pop()
            for edge in node.dependencies:
                child = graph.find(edge.key, edge.tag)
                if child is None:
                    if (edge.key, edge.tag) == (key, tag) and (best is None or len(chain) > len(best[0])):
                        best = (tuple(ident[0] for ident in chain), node.key, edge.parameter)
                    continue
                if (child.key, child.tag) in chain:
                    continue
                stack.append((child, (*chain, (child.key, child.tag))))
    return best
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_graph_render.py`
Expected: PASS, 10 tests.

- [ ] **Step 5: Write the chain-consistency test**

This is the roadmap's acceptance criterion. Both variants must share one owner,
one parameter name and one chain, so the two containers are built over one set
of classes with assigned annotations — the technique `benchmarks/graphs.py`
already uses. Append to `tests/unit/test_graph_render.py`:

```python
def _chain_with_unbound_leaf() -> tuple[Container, Container, type[object]]:
    """Two containers over one set of classes: leaf required, then leaf defaulted.

    Annotations are assigned rather than written so both variants agree on the
    parameter name, the owner and the chain. The only difference between them is
    whether that parameter carries a default.
    """
    missing = type('Missing', (), {})
    inner = type('Inner', (), {})
    outer = type('Outer', (), {})

    def make_inner_required(dep: object) -> object:
        del dep
        return inner()

    def make_inner_defaulted(dep: object = None) -> object:
        del dep
        return inner()

    def make_outer(dep: object) -> object:
        del dep
        return outer()

    for factory in (make_inner_required, make_inner_defaulted):
        factory.__annotations__ = {'dep': missing, 'return': inner}
    make_outer.__annotations__ = {'dep': inner, 'return': outer}

    required = Container().bind(make_inner_required).bind(make_outer)
    defaulted = Container().bind(make_inner_defaulted).bind(make_outer)
    return required, defaulted, missing


def test_explain_names_the_chain_the_freeze_error_names() -> None:
    required, defaulted, missing = _chain_with_unbound_leaf()

    with pytest.raises(MissingProviderError) as raised:
        _ = required.freeze()

    graph = build_graph(build_plan(defaulted.records()))

    assert render_tree(graph, missing, None) == str(raised.value)
```

Assigning `__annotations__` on a function needs the `_set_dynamic_attribute`
shape `tests/unit/test_graph_properties.py` uses if `basedpyright` rejects the
direct assignment; copy that helper into this file rather than suppressing the
diagnostic.

- [ ] **Step 6: Run the acceptance test**

Run: `uv run pytest tests/unit/test_graph_render.py::test_explain_names_the_chain_the_freeze_error_names -v`
Expected: PASS. If the two strings differ, the difference is in `format_missing`'s inputs, not in its body — fix the caller that builds the chain, never by special-casing the text.

- [ ] **Step 7: Run the five gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add depin/_core/render.py tests/unit/test_graph_render.py
git commit -m "feat: render the resolution tree for a key"
```

---

### Task 4: Render Graphviz and Mermaid

**Files:**

- Modify: `depin/_core/render.py`
- Modify: `depin/_core/diagnostics.py`
- Modify: `tests/unit/test_graph_render.py`

**Interfaces:**

- Produces: `render_dot(graph: DependencyGraph) -> str` and `render_mermaid(graph: DependencyGraph) -> str` in `depin._core.render`.
- Produces: `DependencyGraph.dot() -> str` and `DependencyGraph.mermaid() -> str`, each delegating to the matching function.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_graph_render.py`:

```python
def test_dot_declares_every_node_and_edge_in_plan_order() -> None:
    assert build().dot() == (
        'digraph depin {\n'
        '  rankdir=LR;\n'
        '  n0 [label="Config\\nsingleton, class", shape=box];\n'
        '  n1 [label="Store\\nsingleton, class", shape=box];\n'
        '  n2 [label="Service\\nsingleton, class", shape=box];\n'
        '  n1 -> n0 [label="config"];\n'
        '  n2 -> n1 [label="store"];\n'
        '  n2 -> n0 [label="config"];\n'
        '}'
    )


def test_mermaid_declares_every_node_and_edge_in_plan_order() -> None:
    assert build().mermaid() == (
        'graph LR\n'
        '  n0["Config<br/>singleton, class"]\n'
        '  n1["Store<br/>singleton, class"]\n'
        '  n2["Service<br/>singleton, class"]\n'
        '  n1 -->|config| n0\n'
        '  n2 -->|store| n1\n'
        '  n2 -->|config| n0'
    )


def test_an_unbound_default_becomes_a_dashed_node_in_both_formats() -> None:
    class Timeout:
        pass

    class Client:
        def __init__(self, timeout: Timeout = Timeout()) -> None:
            self.timeout = timeout

    graph = build_graph(build_plan(Container().bind(Client).records()))
    assert '  u0 [label="Timeout\\nunbound", shape=box, style=dashed];' in graph.dot()
    assert '  n0 -> u0 [label="timeout", style=dashed];' in graph.dot()
    assert '  u0["Timeout<br/>unbound"]' in graph.mermaid()
    assert '  n0 -.->|timeout| u0' in graph.mermaid()


def test_a_quote_in_a_key_is_escaped_per_format() -> None:
    weird = Token[int]('a "quoted" name')
    graph = build_graph(build_plan(Container().value(weird, 1).records()))
    assert '\\"quoted\\"' in graph.dot()
    assert '#quot;quoted#quot;' in graph.mermaid()


def test_both_exports_are_identical_on_two_calls() -> None:
    graph = build()
    assert graph.dot() == graph.dot()
    assert graph.mermaid() == graph.mermaid()


def test_both_exports_declare_one_node_per_provider() -> None:
    graph = build()
    assert graph.dot().count('shape=box];') == len(graph.nodes)
    assert graph.mermaid().count('["') == len(graph.nodes)
```

The escaping test's expected substrings assume `fmt_key` renders a `Token` as `Token('a "quoted" name')`. Verify with `uv run python -c "from depin._core.markers import Token; from depin._core.spec import fmt_key; print(fmt_key(Token[int]('a \"q\" name')))"` before locking the assertion.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_graph_render.py -k "dot or mermaid or escaped"`
Expected: FAIL, `AttributeError: 'DependencyGraph' object has no attribute 'dot'`.

- [ ] **Step 3: Write the exporters**

Append to `depin/_core/render.py`:

```python
def render_dot(graph: DependencyGraph) -> str:
    """The graph as a Graphviz ``digraph`` document."""
    bound, unbound = _identifiers(graph)
    lines = ['digraph depin {', '  rankdir=LR;']
    for node in graph.nodes:
        label = f'{_dot_escape(fmt_key(node.key))}\\n{_dot_escape(", ".join(annotation_parts(node)))}'
        lines.append(f'  {bound[(node.key, node.tag)]} [label="{label}", shape=box];')
    for ident, name in unbound.items():
        lines.append(f'  {name} [label="{_dot_escape(fmt_key(ident[0]))}\\nunbound", shape=box, style=dashed];')
    for node in graph.nodes:
        source = bound[(node.key, node.tag)]
        for edge in node.dependencies:
            ident = (edge.key, edge.tag)
            if ident in bound:
                lines.append(f'  {source} -> {bound[ident]} [label="{edge.parameter}"];')
            else:
                lines.append(f'  {source} -> {unbound[ident]} [label="{edge.parameter}", style=dashed];')
    lines.append('}')
    return '\n'.join(lines)


def render_mermaid(graph: DependencyGraph) -> str:
    """The graph as a Mermaid ``graph LR`` document."""
    bound, unbound = _identifiers(graph)
    lines = ['graph LR']
    for node in graph.nodes:
        label = f'{_mermaid_escape(fmt_key(node.key))}<br/>{_mermaid_escape(", ".join(annotation_parts(node)))}'
        lines.append(f'  {bound[(node.key, node.tag)]}["{label}"]')
    for ident, name in unbound.items():
        lines.append(f'  {name}["{_mermaid_escape(fmt_key(ident[0]))}<br/>unbound"]')
    for node in graph.nodes:
        source = bound[(node.key, node.tag)]
        for edge in node.dependencies:
            ident = (edge.key, edge.tag)
            if ident in bound:
                lines.append(f'  {source} -->|{edge.parameter}| {bound[ident]}')
            else:
                lines.append(f'  {source} -.->|{edge.parameter}| {unbound[ident]}')
    return '\n'.join(lines)


def _identifiers(graph: DependencyGraph) -> tuple[dict[_Ident, str], dict[_Ident, str]]:
    """Stable identifiers: ``n<plan index>`` for a bound node, ``u<n>`` for an unbound target.

    An index keeps a key containing a quote or a bracket out of the identifier
    position in both formats, and both dictionaries are built in walk order, so
    iterating them is deterministic.
    """
    bound = {(node.key, node.tag): f'n{index}' for index, node in enumerate(graph.nodes)}
    unbound: dict[_Ident, str] = {}
    for node in graph.nodes:
        for edge in node.dependencies:
            ident = (edge.key, edge.tag)
            if ident in bound or ident in unbound:
                continue
            unbound[ident] = f'u{len(unbound)}'
    return bound, unbound


def _dot_escape(text: str) -> str:
    return text.replace('\\', '\\\\').replace('"', '\\"')


def _mermaid_escape(text: str) -> str:
    return text.replace('"', '#quot;')
```

An edge label is a Python parameter name, so it can contain neither `"` nor `|` and needs no escaping.

- [ ] **Step 4: Add the two methods to `DependencyGraph`**

In `depin/_core/diagnostics.py`, insert directly above `__eq__`:

```python
    def dot(self) -> str:
        """Render the graph as a Graphviz ``digraph`` document."""
        from depin._core import render

        return render.render_dot(self)

    def mermaid(self) -> str:
        """Render the graph as a Mermaid ``graph LR`` document."""
        from depin._core import render

        return render.render_mermaid(self)
```

The import is deferred to call time on purpose: `render` imports the node types from this module, so a module-level import here would be circular.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_graph_render.py`
Expected: PASS, 16 tests.

- [ ] **Step 6: Add the cross-process determinism test**

Append to `tests/unit/test_graph_render.py`:

```python
def test_the_exports_do_not_depend_on_the_hash_seed() -> None:
    program = (
        'from depin import Container\n'
        'class Config: ...\n'
        'class Store:\n'
        '    def __init__(self, config: Config) -> None: ...\n'
        'class Service:\n'
        '    def __init__(self, store: Store, config: Config) -> None: ...\n'
        'di = Container().bind(Config).bind(Store).bind(Service).freeze()\n'
        'print(di.graph().dot())\n'
        'print(di.graph().mermaid())\n'
        'print(di.explain(Service))\n'
    )
    outputs = [
        subprocess.run(  # noqa: S603
            [sys.executable, '-c', program],
            capture_output=True,
            check=True,
            text=True,
            env={**os.environ, 'PYTHONHASHSEED': seed},
        ).stdout
        for seed in ('0', '1', '12345')
    ]
    assert outputs[0] == outputs[1] == outputs[2]
```

Add `import os`, `import subprocess`, `import sys` to the file's imports. This test depends on `FrozenContainer.graph()` and `FrozenContainer.explain()`, which Task 5 adds, so mark it `@pytest.mark.skip(reason='enabled in Task 5')` when committing this task and remove the marker in Task 5. The `noqa` is only needed if `ruff check` flags the subprocess call; the repository does not select `S`, so drop it unless the linter asks for it.

- [ ] **Step 7: Run the five gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add depin/_core/render.py depin/_core/diagnostics.py tests/unit/test_graph_render.py
git commit -m "feat: export the graph as dot and mermaid"
```

---

### Task 5: Publish the surface

**Files:**

- Modify: `depin/_core/frozen.py`
- Modify: `depin/_core/spec.py`
- Modify: `depin/_core/diagnostics.py`
- Modify: `depin/__init__.py`
- Modify: `tests/unit/test_public_api.py`
- Modify: `tests/unit/test_graph_render.py`
- Modify: `tests/typing/test_conformance.py`
- Modify: `tests/integration/test_fastapi_ext.py`

**Interfaces:**

- Consumes: `build_graph`, `DependencyGraph` from `depin._core.diagnostics`; `render_tree` from `depin._core.render`; `is_provider_key` from `depin._core.typeguards`, already imported in `frozen.py`.
- Produces: `FrozenContainer.graph() -> DependencyGraph` and `FrozenContainer.explain(key: ProviderKey, *, tag: str | None = None) -> str`.
- Produces: `depin.__all__` extended with `DependencyGraph`, `GraphEdge`, `GraphNode`, `ProviderKey`, `ProviderShape`.

- [ ] **Step 1: Write the failing tests**

Update `EXPECTED_EXPORTS` in `tests/unit/test_public_api.py` to:

```python
EXPECTED_EXPORTS = (
    'Bindings',
    'Container',
    'DependencyGraph',
    'FrozenContainer',
    'GraphEdge',
    'GraphNode',
    'Named',
    'ProviderKey',
    'ProviderShape',
    'Registry',
    'Scope',
    'ScopeDecorator',
    'ScopeFrame',
    'Tag',
    'Token',
    'injected',
    'provides',
)
```

Append to `tests/unit/test_graph_render.py`:

```python
def test_explain_delegates_to_the_tree_renderer() -> None:
    container = Container().bind(Config).bind(Store).bind(Service)
    graph = build_graph(build_plan(container.records()))
    assert container.freeze().explain(Service) == render_tree(graph, Service, None)


def test_explain_accepts_a_tag() -> None:
    di = Container().bind(Config, tag='primary').freeze()
    assert di.explain(Config, tag='primary') == "Config  [singleton, class, tag='primary']"


def test_explain_rejects_a_value_that_is_not_a_key() -> None:
    di = Container().bind(Config).freeze()
    with pytest.raises(MissingProviderError, match='not a valid key type'):
        _ = di.explain(42)  # pyright: ignore[reportArgumentType]


def test_explain_describes_the_plan_not_an_active_override() -> None:
    container = Container().bind(Config).bind(Store)
    di = container.freeze()
    expected = render_tree(build_graph(build_plan(container.records())), Store, None)
    with di.override(Config, Config()):
        assert di.explain(Store) == expected


def test_graph_returns_a_view_of_the_plan() -> None:
    container = Container().bind(Config).bind(Store)
    assert container.freeze().graph() == build_graph(build_plan(container.records()))
```

`test_explain_rejects_a_value_that_is_not_a_key` passes an `int` on purpose, which is the one place in this step where a checker suppression is correct: the runtime guard exists for callers with no type checking, and the narrowest form names the rule. Keep the comment on the same line.

Remove the `@pytest.mark.skip` marker from `test_the_exports_do_not_depend_on_the_hash_seed`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_public_api.py tests/unit/test_graph_render.py`
Expected: FAIL — `assert depin.__all__ == EXPECTED_EXPORTS` and `AttributeError: 'FrozenContainer' object has no attribute 'explain'`.

- [ ] **Step 3: Add the two methods**

In `depin/_core/frozen.py`, extend the imports:

```python
from depin._core.diagnostics import DependencyGraph, build_graph
from depin._core.render import render_tree
```

Insert both methods after `override`, before `_is_registered`:

```python
    def graph(self) -> DependencyGraph:
        """Return the validated dependency graph as data.

        The view describes the plan `Container.freeze()` validated. An active
        `override()` does not change it, so the graph and both of its exports
        are the same on every call and in every context.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Config: ...
            >>> class Service:
            ...     def __init__(self, config: Config) -> None: ...
            >>> di = Container().bind(Config).bind(Service).freeze()
            >>> len(di.graph().nodes)
            2
            >>> di.graph().node(Service).dependencies[0].parameter
            'config'

            ```
        """
        return build_graph(self._plan)

    def explain(self, key: ProviderKey, *, tag: str | None = None) -> str:
        """Return the resolution tree below a key, as text.

        Each line names the parameter that requires the node, the node's key,
        its scope and provider shape, `async` when the node needs asynchronous
        resolution, and its tag when it has one. A subtree already shown is
        marked rather than repeated. A parameter with a default that nothing
        provides is marked ``(unbound, default)``.

        A key no binding provides returns the line `MissingProviderError`
        carries for it, including the resolution chain when some provider
        requires that key. Like `graph()`, the output describes the validated
        plan, not an active `override()`.

        Raises:
            MissingProviderError: The value cannot be a provider key at all.
                An unregistered key of a valid type is described in the
                returned text instead.

        Example:
            ```pycon
            >>> from depin import Container
            >>> class Config: ...
            >>> class Service:
            ...     def __init__(self, config: Config) -> None: ...
            >>> di = Container().bind(Config).bind(Service).freeze()
            >>> print(di.explain(Service))
            Service  [singleton, class]
              config: Config  [singleton, class]

            ```
        """
        if not is_provider_key(key):
            raise MissingProviderError(f'cannot look up provider for {key!r}: not a valid key type')
        return render_tree(self.graph(), key, tag)
```

- [ ] **Step 4: Document `ProviderShape` for the public API**

Replace the bare `ProviderShape` definition in `depin/_core/spec.py` with a documented one. Do not change the members or their order.

```python
class ProviderShape(Enum):
    """How a provider produces its value, and whether it owns a teardown.

    Reported by `GraphNode.shape`. `Container.freeze()` infers it from the
    binding: a class, a factory's kind, or a value.

    Attributes:
        CLASS: A class, instantiated with its resolved constructor arguments.
        FUNCTION: A synchronous factory, called with its resolved arguments.
        ASYNC_FUNCTION: A coroutine factory, awaited. Requires `aresolve`.
        GENERATOR: A generator factory that yields once and resumes at
            teardown. Cannot be transient.
        ASYNC_GENERATOR: An async generator factory that yields once and
            resumes at teardown. Requires `aresolve` and cannot be transient.
        CONTEXT_MANAGER: A factory returning a context manager, entered on
            construction and exited at teardown. Cannot be transient.
        ASYNC_CONTEXT_MANAGER: A factory returning an async context manager.
            Requires `aresolve` and cannot be transient.
        VALUE: A value bound directly with `Container.value`; nothing is called.
        FRAME: A value the active scope frame supplies, bound with
            `Container.scope_value`; nothing is called.
    """
```

Add a docstring line under the `ProviderKey` alias so the reference page can quote it:

```python
type ProviderKey = type[object] | Token[object] | str
"""What a provider can be bound and resolved under: a class, a `Token`, or a name."""
```

- [ ] **Step 5: Export the five symbols**

In `depin/__init__.py`, add:

```python
from depin._core.diagnostics import DependencyGraph, GraphEdge, GraphNode
from depin._core.spec import Bindings, ProviderKey, ProviderShape
```

replacing the existing `from depin._core.spec import Bindings` line, and extend `__all__` to the sorted tuple asserted in Step 1.

- [ ] **Step 6: Add `Example:` blocks to the four new public symbols**

Each doctest must stand alone; none may rely on another's names. In `depin/_core/diagnostics.py`, append an `Example:` section to `GraphEdge`, `GraphNode` and `DependencyGraph`:

```python
    Example:
        ```pycon
        >>> from depin import Container
        >>> class Config: ...
        >>> class Service:
        ...     def __init__(self, config: Config) -> None: ...
        >>> di = Container().bind(Config).bind(Service).freeze()
        >>> edge = di.graph().node(Service).dependencies[0]
        >>> edge.parameter, edge.satisfied
        ('config', True)

        ```
```

for `GraphEdge`;

```python
    Example:
        ```pycon
        >>> from depin import Container, ProviderShape
        >>> class Config: ...
        >>> di = Container().bind(Config).freeze()
        >>> node = di.graph().node(Config)
        >>> node.scope.value, node.shape is ProviderShape.CLASS
        ('singleton', True)

        ```
```

for `GraphNode`; and

```python
    Example:
        ```pycon
        >>> from depin import Container
        >>> class Config: ...
        >>> class Service:
        ...     def __init__(self, config: Config) -> None: ...
        >>> di = Container().bind(Config).bind(Service).freeze()
        >>> print(di.graph().mermaid())
        graph LR
          n0["Config<br/>singleton, class"]
          n1["Service<br/>singleton, class"]
          n1 -->|config| n0

        ```
```

for `DependencyGraph`. Append to the `ProviderShape` docstring in `depin/_core/spec.py`:

```python
    Example:
        ```pycon
        >>> from depin import Container, ProviderShape
        >>> class Config: ...
        >>> di = Container().bind(Config).freeze()
        >>> di.graph().node(Config).shape is ProviderShape.CLASS
        True

        ```
```

- [ ] **Step 7: Add the conformance cases**

Append to `tests/typing/test_conformance.py`, extending its `from depin import ...` line with `DependencyGraph`, `GraphEdge`, `GraphNode`, `ProviderShape`:

```python
def test_graph_diagnostics_keep_their_types() -> None:
    di = Container().bind(Config).bind(Service).freeze()
    assert_type(di.graph(), DependencyGraph)
    assert_type(di.graph().nodes, tuple[GraphNode, ...])
    assert_type(di.graph().roots, tuple[GraphNode, ...])
    assert_type(di.graph().node(Service), GraphNode)
    assert_type(di.graph().find(Service), GraphNode | None)
    assert_type(di.graph().node(Service).dependencies, tuple[GraphEdge, ...])
    assert_type(di.graph().node(Service).shape, ProviderShape)
    assert_type(di.graph().dot(), str)
    assert_type(di.graph().mermaid(), str)
    assert_type(di.explain(Service), str)
    assert_type(di.explain(Service, tag='primary'), str)
```

- [ ] **Step 8: Exercise the surface through the FastAPI extension**

The roadmap requires every new feature to go through `depin.ext.fastapi` before it counts as complete. Append to `tests/integration/test_fastapi_ext.py`:

```python
@pytest.mark.asyncio
async def test_the_graph_describes_a_request_scoped_binding() -> None:
    class Session:
        pass

    frozen = Container().bind(Session, scope=Scope.SCOPED).freeze()

    app = FastAPI()
    app.add_middleware(RequestScope, container=frozen)

    @app.get('/explain')
    async def _explain(session: Inject[Session]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        del session
        return {'tree': frozen.explain(Session), 'dot': frozen.graph().dot()}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://t') as client:
        body = (await client.get('/explain')).json()

    assert body['tree'] == 'Session  [scoped, class]'
    assert 'digraph depin {' in body['dot']
    assert frozen.graph().node(Session).scope is Scope.SCOPED
```

- [ ] **Step 9: Run the gates plus the docs build**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Expected: all pass. The doctests in the new `Example:` blocks run as part of `pytest`; a mismatch there is a real difference in rendered output, so fix the expected text against what the renderer produces, never by loosening the example.

- [ ] **Step 10: Commit**

```bash
git add depin tests
git commit -m "feat: expose explain() and graph() on FrozenContainer"
```

---

### Task 6: Generative invariants and the benchmark

**Files:**

- Modify: `tests/unit/test_graph_properties.py`
- Create: `benchmarks/test_diagnostics.py`

**Interfaces:**

- Consumes: `GraphCase`, `_materialize` and the existing strategies in `tests/unit/test_graph_properties.py`; `build_chain` from `benchmarks.graphs`; the `Benchmark` protocol declared in `benchmarks/test_resolution.py`.

- [ ] **Step 1: Write the property tests**

Append to `tests/unit/test_graph_properties.py`. The module already defines `GraphCase`, the `_graphs()` strategy, `_materialize`, and `_frozen_plan`; reuse all four rather than writing new ones.

```python
@given(case=_graphs())
def test_every_planned_provider_appears_as_exactly_one_node(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        frozen = container.freeze()
    except DepinError:
        return
    graph = frozen.graph()
    idents = [(node.key, node.tag) for node in graph.nodes]
    assert len(idents) == len(set(idents))
    assert len(idents) == len(_frozen_plan(frozen).order)


@given(case=_graphs())
def test_every_edge_either_indexes_a_node_or_is_unsatisfied(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        graph = container.freeze().graph()
    except DepinError:
        return
    for node in graph.nodes:
        for edge in node.dependencies:
            assert edge.satisfied is (graph.find(edge.key, edge.tag) is not None)


@given(case=_graphs())
def test_each_export_declares_one_entry_per_node(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        graph = container.freeze().graph()
    except DepinError:
        return
    assert graph.dot().count('shape=box];') >= len(graph.nodes)
    assert graph.mermaid().count('["') >= len(graph.nodes)


@given(case=_graphs())
def test_explain_names_every_key_reachable_from_its_root(case: GraphCase) -> None:
    container = _materialize(case)
    try:
        frozen = container.freeze()
    except DepinError:
        return
    graph = frozen.graph()
    for root in graph.roots:
        text = frozen.explain(root.key, tag=root.tag)
        reachable: set[tuple[object, str | None]] = set()
        pending = [root]
        while pending:
            node = pending.pop()
            if (node.key, node.tag) in reachable:
                continue
            reachable.add((node.key, node.tag))
            for edge in node.dependencies:
                child = graph.find(edge.key, edge.tag)
                if child is not None:
                    pending.append(child)
        for key, _tag in reachable:
            assert fmt_key(key) in text
```

Extend that file's imports with `from depin._core.spec import fmt_key`; `DepinError` is already imported there. The `>=` in the export test allows for unbound targets, which add declarations beyond the node count.

- [ ] **Step 2: Run the property tests**

Run: `uv run pytest tests/unit/test_graph_properties.py`
Expected: PASS.

- [ ] **Step 3: Show a property test failing against a broken renderer**

The roadmap's Step 1 rule stands: a generative test that cannot fail proves nothing. Temporarily change `render_tree` so it stops descending — replace the `for edge in reversed(target.dependencies):` loop body with `pass` — and run:

Run: `uv run pytest tests/unit/test_graph_properties.py::test_explain_names_every_key_reachable_from_its_root`
Expected: FAIL. Restore the loop and rerun; expected: PASS. Record both commands and their last output line in the commit body.

- [ ] **Step 4: Write the benchmark**

Create `benchmarks/test_diagnostics.py`:

```python
"""Diagnostics over a large graph: the view, the tree, and the exports."""

from collections.abc import Callable
from typing import Protocol

from benchmarks.graphs import build_chain


class Benchmark(Protocol):
    """The subset of pytest-benchmark's fixture these cases use.

    Declared locally so the benchmarks do not depend on the plugin shipping
    accurate type information.
    """

    def __call__[T](self, function: Callable[[], T]) -> T: ...


def test_build_the_graph_view(benchmark: Benchmark) -> None:
    container, _ = build_chain(1000)
    frozen = container.freeze()
    _ = benchmark(frozen.graph)


def test_explain_a_deep_chain(benchmark: Benchmark) -> None:
    container, leaf = build_chain(1000)
    frozen = container.freeze()

    def explain() -> str:
        return frozen.explain(leaf)

    _ = benchmark(explain)


def test_export_a_large_graph_as_dot(benchmark: Benchmark) -> None:
    container, _ = build_chain(1000)
    graph = container.freeze().graph()
    _ = benchmark(graph.dot)
```

- [ ] **Step 5: Run the benchmark suite**

Run: `uv run --group bench pytest benchmarks --benchmark-only`
Expected: PASS, with the three new cases reported. Record the mean of each in the commit body; they are the first measurements of these paths, so there is nothing to compare against yet.

- [ ] **Step 6: Run the five gates**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_graph_properties.py benchmarks/test_diagnostics.py
git commit -m "test: check graph diagnostics generatively and under load"
```

---

### Task 7: Documentation, example, and the module map

**Files:**

- Create: `docs/reference/diagnostics.md`
- Create: `docs/guide/diagnostics.md`
- Modify: `mkdocs.yml`
- Create: `examples/graph_diagnostics/__init__.py`
- Create: `examples/graph_diagnostics/main.py`
- Modify: `examples/README.md`
- Modify: `tests/integration/test_examples.py`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write the example**

Create `examples/graph_diagnostics/__init__.py` as an empty file, and `examples/graph_diagnostics/main.py`:

```python
"""Inspecting a validated graph: the resolution tree and the two exports.

Run with ``python -m examples.graph_diagnostics.main``.
"""

from collections.abc import Generator

from depin import Container, FrozenContainer, Scope


class Settings:
    def __init__(self) -> None:
        self.dsn = 'postgres://example'


class Pool:
    def __init__(self, settings: Settings) -> None:
        self.dsn = settings.dsn


class Connection:
    def __init__(self, pool: Pool) -> None:
        self.pool = pool


def connection(pool: Pool) -> Generator[Connection]:
    conn = Connection(pool)
    yield conn


class Repo:
    def __init__(self, connection: Connection, settings: Settings) -> None:
        self.connection = connection
        self.settings = settings


def build() -> FrozenContainer:
    return (
        Container()
        .bind(Settings)
        .bind(Pool)
        .bind(connection, scope=Scope.SCOPED)
        .bind(Repo, scope=Scope.SCOPED)
        .freeze()
    )


def main() -> None:
    di = build()
    print(di.explain(Repo))
    print()
    print(di.graph().mermaid())


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run the example**

Run: `uv run python -m examples.graph_diagnostics.main`
Expected: a tree rooted at `Repo` with `Connection` and `Settings` beneath it, then a Mermaid document. Copy the exact tree text into the next step.

- [ ] **Step 3: Test the example**

Append to `tests/integration/test_examples.py`, and add `from examples.graph_diagnostics.main import Repo, Settings` and `from examples.graph_diagnostics.main import build as build_diagnostics` to its imports, keeping them sorted:

```python
def test_graph_diagnostics_example_explains_and_exports_its_graph() -> None:
    di = build_diagnostics()
    tree = di.explain(Repo)

    assert tree.splitlines()[0] == 'Repo  [scoped, class]'
    assert '(shown above)' in tree
    assert di.graph().node(Settings).scope.value == 'singleton'
    assert di.graph().mermaid().startswith('graph LR')
    assert di.graph().dot().startswith('digraph depin {')
```

Replace the first assertion with the exact first line printed in Step 2 if it differs.

- [ ] **Step 4: List the example**

Add a row to the table in `examples/README.md`, after the `testing` row:

```markdown
| [`graph_diagnostics`](graph_diagnostics/main.py) | `python -m examples.graph_diagnostics.main` | `explain()` for one key, and the `mermaid` export of the whole graph. |
```

- [ ] **Step 5: Write the reference page**

Create `docs/reference/diagnostics.md`:

```markdown
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
```

- [ ] **Step 6: Write the guide page**

Create `docs/guide/diagnostics.md`. Every `pycon` block is executed by `pytest`, so the expected output must be exact — run each block before committing.

```markdown
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
```

The `node.key.__name__` access in the second block works because those keys are
classes; mention nothing about it in the prose.

- [ ] **Step 7: Add both pages to the nav**

In `mkdocs.yml`, add `- Inspecting the graph: guide/diagnostics.md` after the `Testing` entry under `Guide`, and `- Graph diagnostics: reference/diagnostics.md` after the `Errors` entry under `Reference`.

- [ ] **Step 8: Add the two modules to the `_core` map**

In `AGENTS.md`, add two rows to the table under "Code organisation", after the `graph.py` row:

```markdown
| `diagnostics.py` | The public graph view over a validated plan. |
| `render.py` | The resolution tree, `dot`, and `mermaid` renderings of that view. |
```

- [ ] **Step 9: Run the gates plus the docs build**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Expected: all pass. The guide's `pycon` blocks are doctests; a mismatch means the documented output is wrong, so correct the document against the renderer.

- [ ] **Step 10: Commit**

```bash
git add docs mkdocs.yml examples tests/integration/test_examples.py AGENTS.md
git commit -m "docs: document and demonstrate graph diagnostics"
```

---

### Task 8: Final verification and the pull request

**Files:**

- Create: `specs/evidence/2026-08-30-step-2-diagnostics.md`

- [ ] **Step 1: Run the full gate sequence from a clean tree**

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run mypy
uv run pytest
uv run --group docs mkdocs build --strict
```

Expected: all pass with no warnings.

- [ ] **Step 2: Measure coverage**

Run: `uv run pytest --cov=depin --cov-report=term-missing`
Expected: at or above 95% over `depin/`, and no uncovered branch in `depin/_core/diagnostics.py` or `depin/_core/render.py`. Cover any gap with a test rather than lowering the bar.

- [ ] **Step 3: Run the mutation gate over the new modules**

```bash
uv run mutmut run
uv run python -m scripts.check_mutation_threshold
```

Expected: at least 95% killed, zero inconclusive. A survivor in the new modules is a missing assertion; add the test that kills it.

- [ ] **Step 4: Run the benchmarks**

Run: `uv run --group bench pytest benchmarks --benchmark-only`
Expected: the pre-existing cases within noise of the 0.6.0 baseline, and the three new cases reported.

- [ ] **Step 5: Record the evidence**

Create `specs/evidence/2026-08-30-step-2-diagnostics.md` in the shape of `specs/evidence/2026-08-30-step-1-verification.md`: the exact commands from Steps 1 to 4, their relevant output, the coverage figure per interpreter that CI reports, the mutation score, and the benchmark means for the three new cases. Include the red/green pair from Task 6 Step 3.

- [ ] **Step 6: Commit and open the pull request**

```bash
git add specs/evidence/2026-08-30-step-2-diagnostics.md
git commit -m "docs: record Step 2 verification evidence"
git push -u origin feat/step-2-graph-diagnostics
```

Open the pull request with the title `feat: make the validated graph inspectable` and a body in the shape the repository's recent pull requests use: a Summary of three or four bullets, a Verification list of every command run, and the checklist from the pull-request template with each box ticked.

- [ ] **Step 7: Confirm CI is green**

Run: `gh pr checks --watch`
Expected: every required check passes on 3.12, 3.13, 3.14, 3.13t, and 3.14t.

## Self-review

**Spec coverage.** Public surface — Task 5. Data model — Task 2. Overrides — Task 5 Step 1 (`test_explain_describes_the_plan_not_an_active_override`). Rendering: tree — Task 3; `dot` and `mermaid` — Task 4. Errors — Tasks 2 and 5. Chain consistency — Tasks 1 and 3. Module layout — Tasks 2, 3, 4 and 7 Step 8. Verification — Tasks 2 to 8. Acceptance criteria — Task 3 Step 6, Task 4 Step 6, Task 8.

**Type consistency.** `build_graph`, `render_tree`, `render_dot`, `render_mermaid`, `annotation_parts`, `format_missing`, `suggest_candidates` and `fmt_chain` are spelled the same in every task that uses them. `GraphNode.dependencies`, `GraphEdge.parameter` and `GraphEdge.satisfied` match between the module, the tests, the doctests and the guide.

**Known verification points.** Three assertions in Tasks 3, 4 and 7 depend on exact rendered text — the union spelling for an optional parameter, the `Token` repr, and the example's first line. Each carries a step that prints the real value before the assertion is locked.
