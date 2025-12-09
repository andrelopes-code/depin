class MissingProviderError(RuntimeError):
    pass


class UnexpectedCoroutineError(RuntimeError):
    pass


class CircularDependencyError(Exception):
    pass
