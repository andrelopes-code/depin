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


def build_chain(size: int, *, scope: Scope = Scope.SINGLETON) -> tuple[Container, type[object]]:
    """A linear chain of `size` providers, each depending on the one before it.

    Returns the unfrozen container and the key at the deep end of the chain, so a
    benchmark can time `freeze()` and resolution independently.
    """
    container = Container()
    previous: type[object] | None = None
    leaf: type[object] = object
    for index in range(size):
        leaf = type(f'Node{index}', (), {})
        container = container.bind(_provider(leaf, previous), provides=leaf, scope=scope)
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
