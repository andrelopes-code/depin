"""depin — type-first dependency injection for Python.

Declare providers locally with `provider()`, collect each module's declarations
in an immutable `Catalog`, and explicitly compose catalogues in a `Manifest`.
Pass that manifest or manual bindings to a mutable `Container`, call
`Container.freeze()` to validate the dependency graph, and resolve values from
the immutable `FrozenContainer` it returns. Resolution is driven by type hints;
``Protocol`` and ``Annotated`` are first-class. The core has zero runtime
dependencies; the optional FastAPI integration lives in ``depin.ext.fastapi``.

Example:
    ```pycon
    >>> from depin import Catalog, Container, Manifest, provider
    >>> class Config:
    ...     value = 42
    >>> config = provider(Config)
    >>> providers = Catalog(__name__, config)
    >>> manifest = Manifest(__name__, providers)
    >>> di = Container(manifest).freeze()
    >>> di[Config].value
    42

    ```
"""

from importlib.metadata import PackageNotFoundError, version

from depin._core.bindings import ScopeDecorator
from depin._core.container import Container
from depin._core.diagnostics import DependencyGraph, GraphEdge, GraphNode
from depin._core.discovery import Catalog, Manifest, Provider, provider
from depin._core.frozen import FrozenContainer, ProviderOverride
from depin._core.health import HealthCheck, HealthReport, HealthResult
from depin._core.hosting import (
    CONTRACT_VERSION,
    ContractVersion,
    Host,
    hosted_container,
    optional_hosted_container,
)
from depin._core.markers import Named, Tag, Token, injected, provides
from depin._core.registry import Registry
from depin._core.scope import Scope, ScopeFrame
from depin._core.seeds import ScopeSeed, ScopeSeeder
from depin._core.spec import Bindings, Condition, ProviderKey, ProviderShape, Underlying, render_key
from depin._core.warmup import WarmupReport
from depin.errors import AsyncInSyncContextError, ContainerClosedError, ContainerLifecycleError, FastAPIIntegrationError

try:
    __version__ = version('pydepin')
except PackageNotFoundError:
    # Running from a source tree or vendored copy, with no installed
    # distribution metadata to read the version from.
    __version__ = '0.0.0+unknown'

__all__ = (
    'CONTRACT_VERSION',
    'AsyncInSyncContextError',
    'Bindings',
    'Catalog',
    'Condition',
    'Container',
    'ContainerClosedError',
    'ContainerLifecycleError',
    'ContractVersion',
    'DependencyGraph',
    'FastAPIIntegrationError',
    'FrozenContainer',
    'GraphEdge',
    'GraphNode',
    'HealthCheck',
    'HealthReport',
    'HealthResult',
    'Host',
    'Manifest',
    'Named',
    'Provider',
    'ProviderKey',
    'ProviderOverride',
    'ProviderShape',
    'Registry',
    'Scope',
    'ScopeDecorator',
    'ScopeFrame',
    'ScopeSeed',
    'ScopeSeeder',
    'Tag',
    'Token',
    'Underlying',
    'WarmupReport',
    'hosted_container',
    'injected',
    'optional_hosted_container',
    'provider',
    'provides',
    'render_key',
)
