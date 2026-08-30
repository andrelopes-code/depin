"""The immutable view a frozen container exposes over its validated plan."""

from typing import Annotated

import pytest

from depin._core.container import Container
from depin._core.diagnostics import DependencyGraph, GraphNode, build_graph
from depin._core.graph import build_plan
from depin._core.markers import Tag
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


def test_an_edge_records_the_tag_its_parameter_requires() -> None:
    class TaggedConsumer:
        def __init__(self, store: Annotated[Store, Tag('primary')]) -> None:
            self.store = store

    graph = build_graph(build_plan(Container().bind(Config).bind(Store, tag='primary').bind(TaggedConsumer).records()))
    edge = graph.node(TaggedConsumer).dependencies[0]
    assert edge.tag == 'primary'
    assert graph.find(edge.key, tag=edge.tag) == graph.node(Store, tag='primary')


def test_a_defaulted_parameter_with_no_binding_is_an_unsatisfied_edge() -> None:
    class Client:
        def __init__(self, timeout: float = 5.0) -> None:
            self.timeout = timeout

    graph = build_graph(build_plan(Container().bind(Client).records()))
    edge = graph.node(Client).dependencies[0]
    assert edge.parameter == 'timeout'
    assert edge.key is float
    assert edge.satisfied is False


def test_roots_are_the_nodes_nothing_depends_on() -> None:
    graph = build()
    assert [node.key for node in graph.roots] == [Service]


def test_find_returns_none_for_an_unbound_key() -> None:
    assert build().find(Store, tag='other') is None


def test_node_raises_for_an_unbound_key() -> None:
    with pytest.raises(MissingProviderError, match="no provider for Store \\(tag='other'\\)"):
        _ = build().node(Store, tag='other')


def test_a_tagged_binding_keeps_its_tag_on_the_node() -> None:
    graph = build_graph(build_plan(Container().bind(Config, tag='primary').records()))
    assert graph.node(Config, tag='primary').tag == 'primary'
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
    assert hash(first) == hash(second)
    assert isinstance(first, GraphNode)
