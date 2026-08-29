"""Synthetic provider graphs of a controlled size."""

from collections.abc import Callable

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
