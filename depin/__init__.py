"""depin — type-first dependency injection for Python.

Declare bindings on a mutable :class:`Container`, call :meth:`Container.freeze`
to validate the dependency graph, and resolve values from the immutable
:class:`FrozenContainer` it returns. Resolution is driven by type hints;
``Protocol`` and ``Annotated`` are first-class. The core has zero runtime
dependencies; the optional FastAPI integration lives in ``depin.ext.fastapi``.

Example:
    >>> from depin import Container
    >>> class Config:
    ...     value = 42
    >>> class Service:
    ...     def __init__(self, config: Config) -> None:
    ...         self.config = config
    >>> di = Container().bind(Config).bind(Service).freeze()
    >>> di[Service].config.value
    42
"""

from importlib.metadata import version

from depin._core.container import Container
from depin._core.frozen import FrozenContainer
from depin._core.markers import Named, Tag, Token, injected, provides
from depin._core.registry import Registry
from depin._core.scope import Scope
from depin._core.spec import HasRecords

__version__ = version('pydepin')

__all__ = (
    'Container',
    'FrozenContainer',
    'HasRecords',
    'Named',
    'Registry',
    'Scope',
    'Tag',
    'Token',
    'injected',
    'provides',
)
