"""The three text renderings of a dependency graph."""

import os
import subprocess
import sys
from collections.abc import Generator
from typing import Annotated

import pytest

from depin._core.container import Container
from depin._core.diagnostics import DependencyGraph, GraphEdge, GraphNode, build_graph
from depin._core.graph import build_plan, format_missing
from depin._core.markers import Tag, Token, provides
from depin._core.render import render_tree
from depin._core.scope import Scope
from depin._core.spec import ProviderShape, fmt_key
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


class MultiCandidateTarget:
    """Undecorated key looked up by `test_the_absent_message_joins_multiple_candidates_with_comma_space`."""


@provides(MultiCandidateTarget)
class MultiCandidateA(MultiCandidateTarget):
    """Module-level by necessity: `suggest_candidates` walks `sys.modules`, so a function-local class is invisible."""


@provides(MultiCandidateTarget)
class MultiCandidateB(MultiCandidateTarget):
    """The second `@provides` match, so the render joins two candidates rather than one."""


def build() -> DependencyGraph:
    return build_graph(build_plan(Container().bind(Config).bind(Store).bind(Service).records()))


def test_a_leaf_renders_as_one_annotated_line() -> None:
    assert render_tree(build(), Config, None) == 'Config  [singleton, class]'


def test_a_tree_indents_each_level_by_two_spaces() -> None:
    assert render_tree(build(), Store, None) == ('Store  [singleton, class]\n  config: Config  [singleton, class]')


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
    assert render_tree(graph, Session, None) == (
        'test_an_async_provider_is_annotated_as_async.<locals>.Session  [singleton, async function, async]'
    )


def test_a_scoped_generator_reports_its_shape() -> None:
    class Connection:
        pass

    def connection() -> Generator[Connection]:
        yield Connection()

    graph = build_graph(build_plan(Container().bind(connection, scope=Scope.SCOPED).records()))
    assert render_tree(graph, Connection, None) == (
        'test_a_scoped_generator_reports_its_shape.<locals>.Connection  [scoped, generator]'
    )


def test_a_tag_is_reported_in_the_annotations() -> None:
    graph = build_graph(build_plan(Container().bind(Config, tag='primary').records()))
    assert render_tree(graph, Config, 'primary') == "Config  [singleton, class, tag='primary']"


def test_an_unbound_default_renders_as_a_leaf() -> None:
    class Client:
        def __init__(self, timeout: float = 5.0) -> None:
            self.timeout = timeout

    graph = build_graph(build_plan(Container().bind(Client).records()))
    assert render_tree(graph, Client, None) == (
        'test_an_unbound_default_renders_as_a_leaf.<locals>.Client  [singleton, class]\n'
        '  timeout: float  (unbound, default)'
    )


def test_a_token_key_renders_by_its_repr() -> None:
    port = Token[int]('port')
    graph = build_graph(build_plan(Container().value(port, 8080).records()))
    assert render_tree(graph, port, None) == "Token('port')  [singleton, value]"


def test_an_unregistered_key_that_nothing_requires_reports_the_lookup_wording() -> None:
    class Absent:
        pass

    assert render_tree(build(), Absent, None) == (
        'no provider for test_an_unregistered_key_that_nothing_requires_reports_the_lookup_wording'
        '.<locals>.Absent (tag=None)'
    )


def test_a_cycle_in_a_manually_built_graph_does_not_loop_the_missing_search() -> None:
    """`Container.freeze()` rejects cycles before a graph is ever built.

    `_deepest_requirement`'s explicit-stack search still guards against one,
    since `GraphNode`/`GraphEdge`/`DependencyGraph` are public and constructible
    without going through `freeze()`. This builds a two-node cycle directly and
    checks the search terminates rather than looping forever.
    """

    class A:
        pass

    class B:
        pass

    class Missing:
        pass

    node_a = GraphNode(
        key=A,
        tag=None,
        scope=Scope.SINGLETON,
        shape=ProviderShape.CLASS,
        needs_async=False,
        dependencies=(GraphEdge(parameter='b', key=B, tag=None, satisfied=True, optional=False, has_default=False),),
    )
    node_b = GraphNode(
        key=B,
        tag=None,
        scope=Scope.SINGLETON,
        shape=ProviderShape.CLASS,
        needs_async=False,
        dependencies=(GraphEdge(parameter='a', key=A, tag=None, satisfied=True, optional=False, has_default=False),),
    )
    graph = DependencyGraph((node_a, node_b))
    assert render_tree(graph, Missing, None) == f'no provider for {fmt_key(Missing)} (tag=None)'


def test_a_cycle_does_not_stop_the_search_for_a_sibling_missing_edge() -> None:
    """The chain-membership guard in `_deepest_requirement` must not cut a node's later edges.

    `A` and `B` form a cycle; `B` also has a second edge to `Missing`. Walking from
    `A`, the guard fires on `B`'s edge back to `A` — that must skip only that one
    edge, not abandon the rest of `B`'s dependencies, or the longer chain through
    `A` is lost in favour of the shorter one found by starting at `B` directly.
    """

    class A:
        pass

    class B:
        pass

    class Missing:
        pass

    node_a = GraphNode(
        key=A,
        tag=None,
        scope=Scope.SINGLETON,
        shape=ProviderShape.CLASS,
        needs_async=False,
        dependencies=(GraphEdge(parameter='b', key=B, tag=None, satisfied=True, optional=False, has_default=False),),
    )
    node_b = GraphNode(
        key=B,
        tag=None,
        scope=Scope.SINGLETON,
        shape=ProviderShape.CLASS,
        needs_async=False,
        dependencies=(
            GraphEdge(parameter='a', key=A, tag=None, satisfied=True, optional=False, has_default=False),
            GraphEdge(parameter='missing', key=Missing, tag=None, satisfied=True, optional=False, has_default=False),
        ),
    )
    graph = DependencyGraph((node_a, node_b))
    assert render_tree(graph, Missing, None) == format_missing(Missing, (A, B), B, 'missing')


def test_an_unrelated_missing_edge_does_not_stop_the_search_for_the_real_one() -> None:
    other = type('Other', (), {})
    missing = type('Missing', (), {})
    outer = type('Outer', (), {})

    def make_outer(other_dep: object = None, missing_dep: object = None) -> object:
        del other_dep, missing_dep
        return outer()

    make_outer.__annotations__ = {'other_dep': other, 'missing_dep': missing, 'return': outer}

    graph = build_graph(build_plan(Container().bind(make_outer).records()))
    assert render_tree(graph, missing, None) == format_missing(missing, (outer,), outer, 'missing_dep')


def test_the_absent_message_uses_the_requested_tag() -> None:
    """Both the `render_tree` -> `_render_absent` and `_render_absent` -> `_deepest_requirement`

    handoffs must carry the caller's tag through unchanged, or a tagged requirement
    a few levels deep is missed entirely.
    """

    class Missing:
        pass

    class Inner:
        pass

    missing_default = Missing()

    def make_inner_required(dep: Annotated[Missing, Tag('special')]) -> Inner:
        del dep
        return Inner()

    def make_inner_defaulted(dep: Annotated[Missing, Tag('special')] = missing_default) -> Inner:
        del dep
        return Inner()

    with pytest.raises(MissingProviderError) as raised:
        _ = Container().bind(make_inner_required).freeze()

    graph = build_graph(build_plan(Container().bind(make_inner_defaulted).records()))
    assert render_tree(graph, Missing, 'special') == str(raised.value)


def test_the_search_follows_a_tagged_intermediate_to_a_deeper_missing_leaf() -> None:
    class Missing:
        pass

    class Middle:
        pass

    class Outer:
        pass

    missing_default = Missing()

    def make_middle_required(dep: Missing) -> Middle:
        del dep
        return Middle()

    def make_middle_defaulted(dep: Missing = missing_default) -> Middle:
        del dep
        return Middle()

    def make_outer(dep: Annotated[Middle, Tag('mid')]) -> Outer:
        del dep
        return Outer()

    with pytest.raises(MissingProviderError) as raised:
        _ = Container().bind(make_middle_required, tag='mid').bind(make_outer).freeze()

    graph = build_graph(build_plan(Container().bind(make_middle_defaulted, tag='mid').bind(make_outer).records()))
    assert render_tree(graph, Missing, None) == str(raised.value)


def test_an_unbound_leaf_does_not_truncate_the_remaining_siblings() -> None:
    missing = type('Missing', (), {})
    multi = type('Multi', (), {})

    def make_multi(missing_dep: object = None, config: object = None) -> object:
        del missing_dep, config
        return multi()

    make_multi.__annotations__ = {'missing_dep': missing, 'config': Config, 'return': multi}

    graph = build_graph(build_plan(Container().bind(Config).bind(make_multi).records()))
    assert render_tree(graph, multi, None) == (
        f'{fmt_key(multi)}  [singleton, function]\n'
        f'  missing_dep: {fmt_key(missing)}  (unbound, default)\n'
        '  config: Config  [singleton, class]'
    )


def test_a_repeated_node_does_not_truncate_the_remaining_siblings() -> None:
    class Multi:
        def __init__(self, a: Store, b: Store, c: Config) -> None:
            self.a = a
            self.b = b
            self.c = c

    graph = build_graph(build_plan(Container().bind(Config).bind(Store).bind(Multi).records()))
    assert render_tree(graph, Multi, None) == (
        f'{fmt_key(Multi)}  [singleton, class]\n'
        '  a: Store  [singleton, class]\n'
        '    config: Config  [singleton, class]\n'
        '  b: Store  [singleton, class]  (shown above)\n'
        '  c: Config  [singleton, class]  (shown above)'
    )


def test_a_tagged_dependency_is_found_by_its_required_tag() -> None:
    class Consumer:
        def __init__(self, store: Annotated[Store, Tag('primary')]) -> None:
            self.store = store

    graph = build_graph(build_plan(Container().bind(Config).bind(Store, tag='primary').bind(Consumer).records()))
    assert render_tree(graph, Consumer, None) == (
        f'{fmt_key(Consumer)}  [singleton, class]\n'
        "  store: Store  [singleton, class, tag='primary']\n"
        '    config: Config  [singleton, class]'
    )


def test_the_absent_message_joins_multiple_candidates_with_comma_space() -> None:
    names = sorted(f'{cls.__module__}.{cls.__qualname__}' for cls in (MultiCandidateA, MultiCandidateB))
    assert render_tree(build(), MultiCandidateTarget, None) == (
        f'no provider for {fmt_key(MultiCandidateTarget)} (tag=None); candidates: {", ".join(names)}'
    )


def test_a_repeated_unbound_target_does_not_hide_a_later_one() -> None:
    x_type = type('X', (), {})
    y_type = type('Y', (), {})
    root_type = type('Root', (), {})

    def make_root(a: object = None, b: object = None, c: object = None) -> object:
        del a, b, c
        return root_type()

    make_root.__annotations__ = {'a': x_type, 'b': x_type, 'c': y_type, 'return': root_type}

    graph = build_graph(build_plan(Container().bind(make_root).records()))
    dot = graph.dot()
    assert dot.count(', shape=box, style=dashed];') == 2
    assert f'{fmt_key(y_type)}\\nunbound' in dot


def test_a_backslash_in_a_key_is_escaped_in_dot() -> None:
    """Each single backslash survives ``repr()`` doubled, then `_dot_escape` doubles it again."""
    weird = Token[int]('a \\backslash\\ name')
    graph = build_graph(build_plan(Container().value(weird, 1).records()))
    assert ('\\' * 4 + 'backslash' + '\\' * 4) in graph.dot()


def test_the_tree_is_identical_on_two_calls() -> None:
    graph = build()
    assert render_tree(graph, Service, None) == render_tree(graph, Service, None)


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


def _two_equal_chains_to_one_unbound_leaf() -> tuple[Container, Container, type[object]]:
    """Two independent, equal-length chains reaching one shared unbound leaf.

    Mirrors `_chain_with_unbound_leaf`'s technique, doubled: two owner/dependent
    pairs, each two levels deep, both requiring the same missing type. Both
    chains have the same length, so `_collect_missing` and `_deepest_requirement`
    must break the tie the same way for the two renderings to agree.
    """
    missing = type('Missing', (), {})
    inner_a = type('InnerA', (), {})
    outer_a = type('OuterA', (), {})
    inner_b = type('InnerB', (), {})
    outer_b = type('OuterB', (), {})

    def make_inner_a_required(dep: object) -> object:
        del dep
        return inner_a()

    def make_inner_a_defaulted(dep: object = None) -> object:
        del dep
        return inner_a()

    def make_outer_a(dep: object) -> object:
        del dep
        return outer_a()

    def make_inner_b_required(dep: object) -> object:
        del dep
        return inner_b()

    def make_inner_b_defaulted(dep: object = None) -> object:
        del dep
        return inner_b()

    def make_outer_b(dep: object) -> object:
        del dep
        return outer_b()

    for factory in (make_inner_a_required, make_inner_a_defaulted):
        factory.__annotations__ = {'dep': missing, 'return': inner_a}
    for factory in (make_inner_b_required, make_inner_b_defaulted):
        factory.__annotations__ = {'dep': missing, 'return': inner_b}
    make_outer_a.__annotations__ = {'dep': inner_a, 'return': outer_a}
    make_outer_b.__annotations__ = {'dep': inner_b, 'return': outer_b}

    required = Container().bind(make_inner_a_required).bind(make_outer_a).bind(make_inner_b_required).bind(make_outer_b)
    defaulted = (
        Container().bind(make_inner_a_defaulted).bind(make_outer_a).bind(make_inner_b_defaulted).bind(make_outer_b)
    )
    return required, defaulted, missing


def test_a_tie_between_equal_length_chains_matches_the_freeze_error() -> None:
    required, defaulted, missing = _two_equal_chains_to_one_unbound_leaf()

    with pytest.raises(MissingProviderError) as raised:
        _ = required.freeze()

    graph = build_graph(build_plan(defaulted.records()))

    assert render_tree(graph, missing, None) == str(raised.value)


def _two_equal_sibling_chains_to_one_unbound_leaf() -> tuple[Container, Container, type[object]]:
    """One root with two branches, each two levels deep, both requiring one shared missing type.

    Unlike `_two_equal_chains_to_one_unbound_leaf`, the tie is not between two
    roots but between two siblings under one root: root -> branch_a -> missing
    and root -> branch_b -> missing are both length-two chains.
    """
    missing = type('Missing', (), {})
    branch_a = type('BranchA', (), {})
    branch_b = type('BranchB', (), {})
    root_type = type('Root', (), {})

    def make_branch_a_required(dep: object) -> object:
        del dep
        return branch_a()

    def make_branch_a_defaulted(dep: object = None) -> object:
        del dep
        return branch_a()

    def make_branch_b_required(dep: object) -> object:
        del dep
        return branch_b()

    def make_branch_b_defaulted(dep: object = None) -> object:
        del dep
        return branch_b()

    def make_root(a: object, b: object) -> object:
        del a, b
        return root_type()

    for factory in (make_branch_a_required, make_branch_a_defaulted):
        factory.__annotations__ = {'dep': missing, 'return': branch_a}
    for factory in (make_branch_b_required, make_branch_b_defaulted):
        factory.__annotations__ = {'dep': missing, 'return': branch_b}
    make_root.__annotations__ = {'a': branch_a, 'b': branch_b, 'return': root_type}

    required = Container().bind(make_branch_a_required).bind(make_branch_b_required).bind(make_root)
    defaulted = Container().bind(make_branch_a_defaulted).bind(make_branch_b_defaulted).bind(make_root)
    return required, defaulted, missing


def test_a_tie_between_sibling_chains_matches_the_freeze_error() -> None:
    required, defaulted, missing = _two_equal_sibling_chains_to_one_unbound_leaf()

    with pytest.raises(MissingProviderError) as raised:
        _ = required.freeze()

    graph = build_graph(build_plan(defaulted.records()))

    assert render_tree(graph, missing, None) == str(raised.value)


def _chain_through_a_bound_and_defaulted_intermediate() -> tuple[Container, Container, type[object]]:
    """The same chain, with the outer provider's bound parameter also carrying a default.

    `_collect_missing` used to skip such a parameter for traversal as well as for
    reporting, so the freeze error named a shorter chain than `explain()` did.
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

    def make_outer(dep: object = None) -> object:
        del dep
        return outer()

    for factory in (make_inner_required, make_inner_defaulted):
        factory.__annotations__ = {'dep': missing, 'return': inner}
    make_outer.__annotations__ = {'dep': inner, 'return': outer}

    required = Container().bind(make_inner_required).bind(make_outer)
    defaulted = Container().bind(make_inner_defaulted).bind(make_outer)
    return required, defaulted, missing


def test_a_bound_and_defaulted_intermediate_does_not_shorten_the_chain() -> None:
    required, defaulted, missing = _chain_through_a_bound_and_defaulted_intermediate()

    with pytest.raises(MissingProviderError) as raised:
        _ = required.freeze()

    graph = build_graph(build_plan(defaulted.records()))

    assert 'Outer' in str(raised.value)
    assert render_tree(graph, missing, None) == str(raised.value)


def test_an_optional_only_dependency_reports_the_no_chain_wording() -> None:
    """A key only an optional parameter admits must not borrow the required wording.

    The other side of `_chain_through_a_bound_and_defaulted_intermediate`'s
    regression: `_collect_missing` excuses an optional parameter from `freeze()`'s
    missing-provider check, so `freeze()` succeeds here. `_deepest_requirement`
    must excuse the same edge, or `explain()` reports a chain `freeze()` never raises.
    """
    missing = type('Missing', (), {})
    owner = type('Owner', (), {})

    def make_owner(dep: object) -> object:
        del dep
        return owner()

    make_owner.__annotations__ = {'dep': missing | None, 'return': owner}

    graph = build_graph(build_plan(Container().bind(make_owner).records()))

    assert render_tree(graph, missing, None) == f'no provider for {fmt_key(missing)} (tag=None)'


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
    class Client:
        def __init__(self, timeout: float = 5.0) -> None:
            self.timeout = timeout

    graph = build_graph(build_plan(Container().bind(Client).records()))
    assert '  u0 [label="float\\nunbound", shape=box, style=dashed];' in graph.dot()
    assert '  n0 -> u0 [label="timeout", style=dashed];' in graph.dot()
    assert '  u0["float<br/>unbound"]' in graph.mermaid()
    assert '  n0 -.->|timeout| u0' in graph.mermaid()


def test_a_quote_in_a_key_is_escaped_per_format() -> None:
    weird = Token[int]('a "quoted" name')
    graph = build_graph(build_plan(Container().value(weird, 1).records()))
    assert '\\"quoted\\"' in graph.dot()
    assert '#quot;quoted#quot;' in graph.mermaid()


def test_angle_brackets_and_a_hash_in_a_key_are_escaped_in_mermaid_only() -> None:
    """Mermaid parses label text as HTML, so an unescaped `<` would swallow the rest of the label."""
    weird = Token[int]('a <tag> #1')
    graph = build_graph(build_plan(Container().value(weird, 1).records()))
    assert "Token('a <tag> #1')" in graph.dot()
    assert "Token('a #lt;tag#gt; #35;1')" in graph.mermaid()


def test_both_exports_are_identical_on_two_calls() -> None:
    graph = build()
    assert graph.dot() == graph.dot()
    assert graph.mermaid() == graph.mermaid()


def test_both_exports_declare_one_node_per_provider() -> None:
    graph = build()
    assert graph.dot().count('shape=box];') == len(graph.nodes)
    assert graph.mermaid().count('["') == len(graph.nodes)


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
        subprocess.run(
            [sys.executable, '-c', program],
            capture_output=True,
            check=True,
            text=True,
            env={**os.environ, 'PYTHONHASHSEED': seed},
        ).stdout
        for seed in ('0', '1', '12345')
    ]
    assert outputs[0] == outputs[1] == outputs[2]


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
        _ = di.explain(42)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def test_explain_describes_the_plan_not_an_active_override() -> None:
    container = Container().bind(Config).bind(Store)
    di = container.freeze()
    expected = render_tree(build_graph(build_plan(container.records())), Store, None)
    with di.override(Config, Config()):
        assert di.explain(Store) == expected


def test_graph_returns_a_view_of_the_plan() -> None:
    container = Container().bind(Config).bind(Store)
    assert container.freeze().graph() == build_graph(build_plan(container.records()))


def test_explain_renders_an_alias_and_its_target() -> None:
    class Store: ...

    class PostgresStore: ...

    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
    prefix = 'test_explain_renders_an_alias_and_its_target.<locals>.'
    assert di.explain(Store).replace(prefix, '') == (
        'Store  [transient, alias]\n  target: PostgresStore  [singleton, class]'
    )


def test_the_exports_carry_the_alias_edge() -> None:
    class Store: ...

    class PostgresStore: ...

    di = Container().bind(PostgresStore).alias(Store, to=PostgresStore).freeze()
    assert '[label="target"]' in di.graph().dot()
    assert '-->|target|' in di.graph().mermaid()
    assert 'transient, alias' in di.graph().mermaid()


def test_explain_marks_an_unbound_optional() -> None:
    class Cache: ...

    class Service:
        def __init__(self, cache: Cache | None) -> None:
            del cache

    prefix = 'test_explain_marks_an_unbound_optional.<locals>.'
    tree = Container().bind(Service).freeze().explain(Service).replace(prefix, '')
    assert tree == 'Service  [singleton, class]\n  cache: Cache  (unbound, optional)'


def test_an_unbound_optional_with_a_default_still_renders_as_default() -> None:
    """A parameter that is both optional and defaulted pins `has_default` as the deciding branch."""

    class Cache: ...

    default_cache = Cache()

    class Service:
        def __init__(self, cache: Cache | None = default_cache) -> None:
            del cache

    prefix = 'test_an_unbound_optional_with_a_default_still_renders_as_default.<locals>.'
    tree = Container().bind(Service).freeze().explain(Service).replace(prefix, '')
    assert tree == 'Service  [singleton, class]\n  cache: Cache  (unbound, default)'


def test_explain_renders_a_collection_and_its_members() -> None:
    class Handler: ...

    class First: ...

    class Second: ...

    di = Container().bind(First).bind(Second).collect(Handler, [First, Second]).freeze()
    prefix = 'test_explain_renders_a_collection_and_its_members.<locals>.'
    assert di.explain(list[Handler]).replace(prefix, '') == (
        'list[Handler]  [transient, collection]\n'
        '  member_0: First  [singleton, class]\n'
        '  member_1: Second  [singleton, class]'
    )


def test_the_exports_carry_the_collection_edges() -> None:
    class Handler: ...

    class First: ...

    di = Container().bind(First).collect(Handler, [First]).freeze()
    assert '[label="member_0"]' in di.graph().dot()
    assert '-->|member_0|' in di.graph().mermaid()
    assert 'transient, collection' in di.graph().mermaid()
