"""Synthetic provider graphs of a controlled size."""

from collections.abc import Callable
from types import GenericAlias

from depin import Container, Scope


def _provider(node: type[object], dependency: type[object] | None) -> Callable[..., object]:
    """Return a factory for `node`, annotated so depin resolves `dependency` into it.

    The annotations are assigned rather than written, because the graph's size is
    a parameter of the benchmark and the node types do not exist until runtime.
    """
    if dependency is None:

        def make() -> object:
            return node()

        make.__annotations__ = {'return': node}
        return make

    def make_with_dependency(upstream: object) -> object:
        del upstream
        return node()

    make_with_dependency.__annotations__ = {'upstream': dependency, 'return': node}
    return make_with_dependency


def chain_types(size: int) -> tuple[type[object], ...]:
    """The node classes `build_chain` binds, in dependency order.

    Exposed because a direct-Python baseline has to construct the same classes
    for its `Observation` to be comparable with the container's: the observation
    names what was built, and two runs naming different classes are not doing the
    same work.
    """
    return tuple(type(f'Node{index}', (), {}) for index in range(size))


def build_chain(size: int, *, scope: Scope = Scope.SINGLETON) -> tuple[Container, type[object]]:
    """A linear chain of `size` providers, each depending on the one before it.

    Returns the unfrozen container and the key at the deep end of the chain, so a
    benchmark can time `freeze()` and resolution independently.
    """
    container = Container()
    previous: type[object] | None = None
    leaf: type[object] = object
    for node in chain_types(size):
        leaf = node
        container = container.bind(_provider(leaf, previous), provides=leaf, scope=scope)
        previous = leaf
    return container, leaf


def _decorator(node: type[object]) -> Callable[..., object]:
    """A pass-through decorator over `node`, annotated the way `_provider` is.

    The wrapper's single parameter must be annotated with the exact key it
    decorates, which — like every node type here — does not exist until the
    benchmark picks a size.
    """

    def wrap(inner: object) -> object:
        return inner

    wrap.__annotations__ = {'inner': node, 'return': node}
    return wrap


def build_decorated_chain(size: int, *, scope: Scope = Scope.SINGLETON) -> tuple[Container, type[object]]:
    """`build_chain`, with one pass-through decorator applied to every node.

    Isolates what `depin._core.decoration`'s fold costs `freeze()`, against the
    plain chain `build_chain` produces at the same size.
    """
    container = Container()
    previous: type[object] | None = None
    leaf: type[object] = object
    for index in range(size):
        leaf = type(f'DecoratedNode{index}', (), {})
        container = container.bind(_provider(leaf, previous), provides=leaf, scope=scope).decorate(
            leaf, _decorator(leaf)
        )
        previous = leaf
    return container, leaf


class GenericWrapper[T]:
    """The one generic origin `build_generic_chain` parameterises over.

    A node class is created dynamically, so subscripting a generic with it
    (`GenericWrapper[node]`) is a runtime-only type argument — exactly the shape
    the design spec's Measurements section shows both checkers reject when built
    through the origin's own `__getitem__`. `types.GenericAlias(GenericWrapper,
    (node,))` builds the identical canonical key without going through a subscript
    expression at all.
    """


def _generic_key(node: type[object]) -> GenericAlias:
    return GenericAlias(GenericWrapper, (node,))


def _generic_provider(key: object, dependency: object | None) -> Callable[..., object]:
    """The `_provider` counterpart for `build_generic_chain`: same shape, generic keys."""
    if dependency is None:

        def make() -> object:
            return object()

        make.__annotations__ = {'return': key}
        return make

    def make_with_dependency(upstream: object) -> object:
        del upstream
        return object()

    make_with_dependency.__annotations__ = {'upstream': dependency, 'return': key}
    return make_with_dependency


class Unbound:
    """The key no builder in this module binds.

    Both error-path builders point an edge at it, so a graph carrying it is one
    `freeze()` rejects and `explain()` has to walk for.
    """


def _fanin_provider(node: type[object], first: type[object], second: type[object]) -> Callable[..., object]:
    """A factory for `node` taking two upstream nodes, annotated the way `_provider` is."""

    def make_with_dependencies(first_upstream: object, second_upstream: object) -> object:
        del first_upstream, second_upstream
        return node()

    make_with_dependencies.__annotations__ = {
        'first_upstream': first,
        'second_upstream': second,
        'return': node,
    }
    return make_with_dependencies


def build_layered_dag(size: int, *, scope: Scope = Scope.SINGLETON) -> tuple[Container, type[object]]:
    """`size` providers where node `i` depends on both `i - 1` and `i - 2`.

    A chain reaches every node once; this shape reaches most of them twice, which
    is what a diamond costs the two walks that expand per path — `render_tree`'s
    subtree elision and `render._deepest_requirement`. The number of simple paths
    from the deepest node is Fibonacci in `size`, so the missing-key walk's cost
    is exponential over it while the rendered tree stays linear.
    """
    container = Container()
    nodes: list[type[object]] = []
    for index in range(size):
        node = type(f'LayerNode{index}', (), {})
        if index == 0:
            provider = _provider(node, None)
        elif index == 1:
            provider = _provider(node, nodes[0])
        else:
            provider = _fanin_provider(node, nodes[index - 1], nodes[index - 2])
        container = container.bind(provider, provides=node, scope=scope)
        nodes.append(node)
    return container, nodes[-1]


def build_chain_missing_a_provider(size: int) -> tuple[Container, type[object]]:
    """`build_chain`, with the deepest node requiring `Unbound`.

    `freeze()` raises `MissingProviderError` over this graph, and the chain the
    message names runs the whole `size` nodes, so the walk that finds it is
    exercised at its full depth rather than at the first node it touches.
    """
    container = Container()
    previous: type[object] | None = None
    leaf: type[object] = object
    for index in range(size):
        leaf = type(f'IncompleteNode{index}', (), {})
        dependency = Unbound if index == 0 else previous
        container = container.bind(_provider(leaf, dependency), provides=leaf)
        previous = leaf
    return container, leaf


def build_generic_chain(size: int, *, scope: Scope = Scope.SINGLETON) -> tuple[Container, object]:
    """`build_chain`, with every key a parameterised generic instead of a bare class.

    Isolates the canonical-form check's cost on the freeze path: `as_provider_key`
    takes the `get_origin` branch for every provider here, rather than skipping it.
    """
    container = Container()
    previous: object | None = None
    leaf: object = object
    for index in range(size):
        node = type(f'GenericNode{index}', (), {})
        key = _generic_key(node)
        container = container.bind(_generic_provider(key, previous), scope=scope)
        previous = key
        leaf = key
    return container, leaf
