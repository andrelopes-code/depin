class DepinError(Exception):
    """Base class for all depin-raised errors."""


class MissingProviderError(DepinError):
    """No provider is registered for a requested key."""


class CircularDependencyError(DepinError):
    """A cycle was detected in the dependency graph."""


class AsyncInSyncContextError(DepinError):
    """A sync resolution path requires an async provider."""


class OutsideScopeError(DepinError):
    """A scoped binding was resolved with no active scope."""


class DuplicateProviderError(DepinError):
    """A binding conflicts with an existing one for the same (key, tag)."""


class CaptiveDependencyError(DepinError):
    """A singleton depends on a scoped provider it would capture for life."""
