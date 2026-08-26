"""The mutable builder: register bindings, then ``freeze()`` into a runtime view."""

from depin._core.bindings import BindingCollector
from depin._core.frozen import FrozenContainer
from depin._core.graph import build_plan
from depin._core.spec import Bindings


class Container(BindingCollector):
    """Mutable builder for a dependency graph.

    Collect bindings with `bind()`, `value()`, `scope_value()`, and the
    `singleton()` / `scoped()` / `transient()` decorators, then call `freeze()`
    to validate the graph and obtain an immutable `FrozenContainer`. A
    ``Container`` performs no resolution itself; nothing is constructed until you
    resolve from the frozen view. Registration order does not matter — providers
    are matched by key and ordered at `freeze()` time.

    Args:
        *sources: Binding sources to load up front — `Registry` instances, other
            containers, anything satisfying `Bindings`. Equivalent to calling
            `include()` with the same arguments.

    Example:
        ```pycon
        >>> from depin import Container
        >>> class Config:
        ...     value = 42
        >>> class Service:
        ...     def __init__(self, config: Config) -> None:
        ...         self.config = config
        >>> di = Container().bind(Config).bind(Service).freeze()
        >>> di[Service].config.value
        42

        ```
    """

    __slots__ = ()

    def __init__(self, *sources: Bindings) -> None:
        super().__init__()
        _ = self.include(*sources)

    def freeze(self) -> FrozenContainer:
        """Validate the dependency graph and return an immutable runtime view.

        All static checks happen here, before anything is constructed: every
        required provider exists, the graph is acyclic, no key is bound twice, no
        singleton depends on a scoped provider it would capture for life, and
        every factory exposes enough type information to infer its key and
        parameters. The frozen container also pre-computes which providers need
        async resolution, so `FrozenContainer.resolve()` can reject async
        providers up front instead of blocking an event loop.

        Raises:
            MissingProviderError: A required dependency has no provider.
            CircularDependencyError: The dependency graph contains a cycle.
            DuplicateProviderError: Two bindings resolve to the same key and tag.
            CaptiveDependencyError: A singleton depends on a scoped provider.
            InvalidProviderError: A factory lacks a return annotation (and no
                ``provides=``), a parameter has no type annotation and no
                default, or a binding is neither a class nor a callable.
            InvalidScopeError: A generator or context-manager provider is bound
                as transient.

        Example:
            ```pycon
            >>> from depin import Container, Scope
            >>> from depin.errors import CaptiveDependencyError
            >>> class Session: ...
            >>> class Repo:
            ...     def __init__(self, session: Session) -> None: ...
            >>> builder = (
            ...     Container()
            ...     .bind(Session, scope=Scope.SCOPED)
            ...     .bind(Repo, scope=Scope.SINGLETON)
            ... )
            >>> try:
            ...     builder.freeze()
            ... except CaptiveDependencyError:
            ...     print('rejected')
            rejected

            ```
        """
        return FrozenContainer(build_plan(self.records()))
