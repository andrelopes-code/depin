"""depin — type-first dependency injection for Python.

Declare bindings on a mutable `Container`, call `Container.freeze()`
to validate the dependency graph, and resolve values from the immutable
`FrozenContainer` it returns. Resolution is driven by type hints;
``Protocol`` and ``Annotated`` are first-class. The core has zero runtime
dependencies; the optional FastAPI integration lives in ``depin.ext.fastapi``.

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

from importlib.metadata import PackageNotFoundError, version

from depin._core.bindings import ScopeDecorator
from depin._core.container import Container
from depin._core.diagnostics import DependencyGraph, GraphEdge, GraphNode
from depin._core.frozen import FrozenContainer
from depin._core.health import HealthCheck, HealthReport, HealthResult
from depin._core.hosting import (
    CONTRACT_VERSION,
    ContractVersion,
    Host,
    hosted_container,
    optional_hosted_container,
)
from depin._core.markers import Named, Tag, Token, TokenKey, injected, provides
from depin._core.registry import Registry
from depin._core.scope import Scope, ScopeFrame
from depin._core.spec import Bindings, Condition, ProviderKey, ProviderShape, Underlying
from depin._core.warmup import WarmupReport

try:
    __version__ = version('pydepin')
except PackageNotFoundError:
    # Running from a source tree or vendored copy, with no installed
    # distribution metadata to read the version from.
    __version__ = '0.0.0+unknown'

__all__ = (
    'CONTRACT_VERSION',
    'Bindings',
    'Condition',
    'Container',
    'ContractVersion',
    'DependencyGraph',
    'FrozenContainer',
    'GraphEdge',
    'GraphNode',
    'HealthCheck',
    'HealthReport',
    'HealthResult',
    'Host',
    'Named',
    'ProviderKey',
    'ProviderShape',
    'Registry',
    'Scope',
    'ScopeDecorator',
    'ScopeFrame',
    'Tag',
    'Token',
    'TokenKey',
    'Underlying',
    'WarmupReport',
    'hosted_container',
    'injected',
    'optional_hosted_container',
    'provides',
)
