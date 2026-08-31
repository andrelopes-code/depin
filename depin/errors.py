"""Exceptions raised by depin, all rooted at `DepinError`.

Every failure depin raises inherits `DepinError`, so a single ``except
DepinError`` handles the library uniformly. Errors that a caller might
reasonably want to catch as a standard Python exception also inherit the
matching builtin — `InvalidProviderError` is a ``TypeError``,
`InvalidScopeError` is a ``ValueError``, `TeardownError` is a ``RuntimeError``.
"""


class DepinError(Exception):
    """Base class for every error raised by depin.

    Catch this to handle any depin failure uniformly; catch a subclass for a
    specific cause. No depin code path raises an exception outside this
    hierarchy.
    """


class MissingProviderError(DepinError):
    """No provider is registered for a requested key.

    Raised at `Container.freeze()` for an unsatisfied dependency, or at
    resolution time for an unregistered key. Resolve by binding the key on the
    `Container`, passing the right ``tag``, or giving the parameter a
    default.
    """


class CircularDependencyError(DepinError):
    """A cycle was detected in the dependency graph.

    Raised by `Container.freeze()`. Break the cycle by introducing a
    `Token` or interface seam, or restructuring so one side no longer
    depends on the other.
    """


class AsyncInSyncContextError(DepinError):
    """A synchronous resolution requires an async provider.

    Raised by `FrozenContainer.resolve()` (or ``frozen[key]``) when the
    target — or something it depends on — is an async provider. Use
    `FrozenContainer.aresolve()` inside an event loop instead.
    """


class OutsideScopeError(DepinError):
    """A scoped binding was resolved with no active scope.

    Raised when a `Scope.SCOPED` provider is resolved outside any
    `FrozenContainer.scope()` / ``ascope`` block. Open a scope around
    the resolution, or make the provider a singleton.
    """


class DuplicateProviderError(DepinError):
    """Two bindings resolve to the same key and tag.

    Raised by `Container.freeze()`. Remove the redundant binding, or give
    the implementations distinct ``tag`` values to register several under one key.
    """


class CaptiveDependencyError(DepinError):
    """A singleton depends on a scoped provider it would capture for life.

    Raised by `Container.freeze()`. A singleton outlives every scope, so
    it would pin one scope's instance forever. Make the consumer scoped, or the
    dependency a singleton.
    """


class InvalidProviderError(DepinError, TypeError):
    """A binding does not carry the type information depin needs.

    Raised by `Container.freeze()` when a factory has no return annotation and
    no ``provides=``, when a parameter has no type annotation and no default,
    when a value cannot serve as a provider key, or when the registered source
    is neither a class nor a callable. Also raised at resolution time if a
    provider returns something incompatible with its declared shape — an
    ``@contextmanager`` factory that returns a plain value, for instance.

    Inherits ``TypeError``, so existing ``except TypeError`` handlers keep
    working.
    """


class InvalidScopeError(DepinError, ValueError):
    """A binding requests a lifetime it cannot have.

    Raised by `Container.freeze()` when a generator or context-manager provider
    is bound as `Scope.TRANSIENT`: such providers own a teardown, and a
    transient value is never cached, so nothing would ever drain it. Bind it as
    singleton or scoped.

    Inherits ``ValueError``, so existing ``except ValueError`` handlers keep
    working.
    """


class TeardownError(DepinError, RuntimeError):
    """A provider's teardown could not run correctly.

    Raised when a generator provider yields a second time during teardown
    (a provider must yield exactly once), or when an async teardown is drained
    from a synchronous scope. Individual teardown failures raised by user code
    are collected into an ``ExceptionGroup`` instead, so one failure never hides
    another.

    Inherits ``RuntimeError``, so existing ``except RuntimeError`` handlers keep
    working.
    """


class ContainerNotBoundError(DepinError, RuntimeError):
    """No container is hosted in the context a dependency was resolved from.

    Raised by `depin.hosted_container()` when no `depin.Host` has published a
    container here, and by an integration that reads the host itself — the
    FastAPI integration raises it when ``Inject[T]`` is evaluated outside a
    `RequestScope`, naming the middleware to install.

    Resolve it by opening a scope with ``Host.scope()`` / ``Host.ascope()``
    around the unit of work, or by publishing the container with
    ``Host.activated()``.

    Inherits ``RuntimeError``, so existing ``except RuntimeError`` handlers keep
    working.
    """
