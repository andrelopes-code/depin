import pytest

from benchmarks.comparison.shapes import chain, observation
from benchmarks.contracts import Observation
from benchmarks.harness import HarnessError


def test_chain_constructs_a_typed_five_node_observation() -> None:
    shared = chain(5)

    value: object = shared.factories[0]()
    for factory in shared.factories[1:]:
        value = factory(value)

    assert type(value) is shared.leaf
    assert observation(shared, value) == Observation(
        result='Node4', constructed=('Node0', 'Node1', 'Node2', 'Node3', 'Node4'), closed=()
    )
    assert tuple(factory.__annotations__ for factory in shared.factories) == (
        {'return': shared.nodes[0]},
        {'upstream': shared.nodes[0], 'return': shared.nodes[1]},
        {'upstream': shared.nodes[1], 'return': shared.nodes[2]},
        {'upstream': shared.nodes[2], 'return': shared.nodes[3]},
        {'upstream': shared.nodes[3], 'return': shared.nodes[4]},
    )


def test_caller_clears_chain_log_between_observations() -> None:
    shared = chain(1)

    first = shared.factories[0]()
    assert observation(shared, first).constructed == ('Node0',)
    shared.log.clear()

    second = shared.factories[0]()
    assert observation(shared, second).constructed == ('Node0',)


def test_chain_creates_fresh_nodes_and_an_isolated_log() -> None:
    first = chain(3)
    second = chain(3)

    identical_nodes = tuple(
        first_node is second_node for first_node, second_node in zip(first.nodes, second.nodes, strict=True)
    )
    assert identical_nodes == (False, False, False)

    value: object = first.factories[0]()
    for factory in first.factories[1:]:
        value = factory(value)

    assert type(value) is first.leaf
    assert first.log == ['Node0', 'Node1', 'Node2']
    assert second.log == []


@pytest.mark.parametrize('size', [0, -1])
def test_chain_rejects_a_non_positive_size(size: int) -> None:
    with pytest.raises(HarnessError, match='chain size must be at least one'):
        _ = chain(size)
