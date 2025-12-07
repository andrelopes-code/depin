class MissingProviderError(RuntimeError):
    pass


class UnexpectedCoroutineError(RuntimeError):
    pass


class UnexpectedAsyncCallableError(RuntimeError):
    pass
