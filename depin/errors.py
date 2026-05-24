"""Exceptions raised by depin, all rooted at `DepinError`."""


class DepinError(Exception):
    """Base class for every error raised by depin.

    Catch this to handle any depin failure uniformly; catch a subclass for a
    specific cause.
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
