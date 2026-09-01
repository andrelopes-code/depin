"""The graph view, the renderings, and the warmup and health reports.

`GraphNode.shape` and `GraphNode.scope` are asserted as the enum *types* they
are declared at, which is exact: the dishonest form is the other one, a member
access such as ``Scope.SINGLETON`` that every checker narrows to its own literal
member type. Member expressions of `ProviderShape` therefore take a witness
here, as `Scope`'s do in `c06_lifetimes.py`.
"""

from typing import Protocol, assert_type

from depin import (
    Container,
    DependencyGraph,
    FrozenContainer,
    GraphEdge,
    GraphNode,
    HealthCheck,
    HealthReport,
    HealthResult,
    ProviderKey,
    ProviderShape,
    Scope,
    Token,
    WarmupReport,
)


class Config:
    def __init__(self) -> None:
        self.dsn = 'sqlite://'


class Repository:
    def __init__(self, config: Config) -> None:
        self.config = config


class Service:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository


class Store(Protocol):
    def get(self) -> str: ...


class Database:
    def __init__(self) -> None:
        self.connected = True


port = Token[int]('port')


def ping(database: Database) -> bool:
    return database.connected


def build() -> FrozenContainer:
    return Container().bind(Config).bind(Repository).bind(Service).value(port, 8080).freeze()


def graph_returns_the_graph_view() -> None:
    di = build()
    assert_type(di.graph(), DependencyGraph)


def the_graph_exposes_its_nodes_and_its_roots() -> None:
    graph = build().graph()
    assert_type(graph.nodes, tuple[GraphNode, ...])
    assert_type(graph.roots, tuple[GraphNode, ...])


def a_node_is_found_by_key() -> None:
    graph = build().graph()
    assert_type(graph.node(Service), GraphNode)
    assert_type(graph.node(port), GraphNode)
    assert_type(graph.find(Service), GraphNode | None)
    assert_type(graph.find(Store), GraphNode | None)
    assert_type(graph.node(Service, tag=None), GraphNode)


def a_node_reports_its_key_lifetime_and_shape() -> None:
    node = build().graph().node(Service)
    _key: ProviderKey = node.key
    assert_type(node.tag, str | None)
    assert_type(node.scope, Scope)
    assert_type(node.shape, ProviderShape)
    assert_type(node.needs_async, bool)


def a_node_reports_its_dependencies_as_edges() -> None:
    node = build().graph().node(Service)
    assert_type(node.dependencies, tuple[GraphEdge, ...])


def an_edge_reports_the_parameter_it_stands_for() -> None:
    edge = build().graph().node(Service).dependencies[0]
    assert_type(edge.parameter, str)
    _key: ProviderKey = edge.key
    assert_type(edge.tag, str | None)
    assert_type(edge.satisfied, bool)
    assert_type(edge.optional, bool)
    assert_type(edge.has_default, bool)


def every_provider_shape_is_a_provider_shape() -> None:
    _class_shape: ProviderShape = ProviderShape.CLASS
    _function_shape: ProviderShape = ProviderShape.FUNCTION
    _value_shape: ProviderShape = ProviderShape.VALUE
    _alias_shape: ProviderShape = ProviderShape.ALIAS
    _collection_shape: ProviderShape = ProviderShape.COLLECTION


def the_graph_renders_to_both_formats() -> None:
    graph = build().graph()
    assert_type(graph.dot(), str)
    assert_type(graph.mermaid(), str)


def explain_renders_one_resolution_tree() -> None:
    di = build()
    assert_type(di.explain(Service), str)
    assert_type(di.explain(port), str)
    assert_type(di.explain(Service, tag='primary'), str)


def warmup_reports_what_it_constructed() -> None:
    di = build()
    report = di.warmup()
    assert_type(report, WarmupReport)
    assert_type(report.constructed, tuple[GraphNode, ...])
    assert_type(report.cached, tuple[GraphNode, ...])


async def awarmup_reports_the_same_shape() -> None:
    di = build()
    report = await di.awarmup()
    assert_type(report, WarmupReport)
    assert_type(report.constructed, tuple[GraphNode, ...])


def checks_reports_the_declared_health_checks() -> None:
    di = Container().bind(Database, check=ping).freeze()
    checks = di.checks()
    assert_type(checks, tuple[HealthCheck, ...])
    _key: ProviderKey = checks[0].key
    assert_type(checks[0].tag, str | None)
    assert_type(checks[0].needs_async, bool)


def health_reports_one_result_per_check() -> None:
    di = Container().bind(Database, check=ping).freeze()
    report = di.health()
    assert_type(report, HealthReport)
    assert_type(report.healthy, bool)
    assert_type(report.results, tuple[HealthResult, ...])


def a_health_result_carries_the_failure_that_produced_it() -> None:
    di = Container().bind(Database, check=ping).freeze()
    result = di.health().results[0]
    assert_type(result, HealthResult)
    _key: ProviderKey = result.key
    assert_type(result.tag, str | None)
    assert_type(result.healthy, bool)
    assert_type(result.error, Exception | None)


async def ahealth_reports_the_same_shape() -> None:
    di = Container().bind(Database, check=ping).freeze()
    report = await di.ahealth()
    assert_type(report, HealthReport)
    assert_type(report.results, tuple[HealthResult, ...])
