import pytest

from depin.errors import (
    AlreadyFrozenError,
    AsyncInSyncContextError,
    CircularDependencyError,
    DepinError,
    DuplicateProviderError,
    MissingProviderError,
    OutsideScopeError,
)


@pytest.mark.parametrize(
    'exc_type',
    [
        MissingProviderError,
        CircularDependencyError,
        AsyncInSyncContextError,
        OutsideScopeError,
        AlreadyFrozenError,
        DuplicateProviderError,
    ],
)
def test_errors_inherit_depin_error(exc_type: type[DepinError]) -> None:
    assert issubclass(exc_type, DepinError)
    assert issubclass(exc_type, Exception)


def test_depin_error_carries_message() -> None:
    err = DepinError('boom')
    assert str(err) == 'boom'
