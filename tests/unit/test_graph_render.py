"""The three text renderings of a dependency graph."""

import os
import subprocess
import sys
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


def test_the_tree_is_identical_on_two_calls() -> None:
    graph = build()
    assert render_tree(graph, Service, None) == render_tree(graph, Service, None)


def _set_dynamic_attribute(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


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
        _set_dynamic_attribute(factory, '__annotations__', {'dep': missing, 'return': inner})
    _set_dynamic_attribute(make_outer, '__annotations__', {'dep': inner, 'return': outer})

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
        _set_dynamic_attribute(factory, '__annotations__', {'dep': missing, 'return': inner_a})
    for factory in (make_inner_b_required, make_inner_b_defaulted):
        _set_dynamic_attribute(factory, '__annotations__', {'dep': missing, 'return': inner_b})
    _set_dynamic_attribute(make_outer_a, '__annotations__', {'dep': inner_a, 'return': outer_a})
    _set_dynamic_attribute(make_outer_b, '__annotations__', {'dep': inner_b, 'return': outer_b})

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
