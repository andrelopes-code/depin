"""The integration contract, and what a consumer's `except` clause catches.

`Host.activated()`, `Host.scope()` and `Host.ascope()` are context managers, so
each is witnessed at the abstract type it satisfies and asserted on the value
its `with` statement binds.

`ContractVersion` is declared ``order=True``, so its comparisons are public
typed surface and not an implementation detail: an integration that guards on
``CONTRACT_VERSION >= ContractVersion(1, 0)`` is writing against them.

The public exceptions are witnessed through `depin.errors`; lifecycle errors
that are also convenience exports are witnessed through both surfaces. A
builtin second base is a typing fact rather than a detail because it changes
which existing ``except`` clauses catch the error.
"""

from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import assert_type

from depin import (
    CONTRACT_VERSION,
    Container,
    ContractVersion,
    FrozenContainer,
    Host,
    ScopeFrame,
    hosted_container,
    optional_hosted_container,
)
from depin import (
    AsyncInSyncContextError as PublicAsyncInSyncContextError,
)
from depin import (
    ContainerClosedError as PublicContainerClosedError,
)
from depin import (
    ContainerLifecycleError as PublicContainerLifecycleError,
)
from depin.errors import (
    AsyncInSyncContextError,
    CaptiveDependencyError,
    CircularDependencyError,
    ContainerClosedError,
    ContainerLifecycleError,
    ContainerNotBoundError,
    DepinError,
    DuplicateProviderError,
    InvalidProviderError,
    InvalidScopeError,
    MissingProviderError,
    OutsideScopeError,
    TeardownError,
)


class Config:
    def __init__(self) -> None:
        self.dsn = 'sqlite://'


_public_async_error: type[AsyncInSyncContextError] = PublicAsyncInSyncContextError
_public_closed_error: type[ContainerClosedError] = PublicContainerClosedError
_public_lifecycle_error: type[ContainerLifecycleError] = PublicContainerLifecycleError


def build() -> FrozenContainer:
    return Container().bind(Config).freeze()


def a_host_holds_the_container_it_publishes() -> None:
    host = Host(build())
    assert_type(host, Host)
    assert_type(host.container, FrozenContainer)
    assert_type(host.container.resolve(Config), Config)


def activation_publishes_the_container_without_opening_a_scope() -> None:
    host = Host(build())
    _activation: AbstractContextManager[None] = host.activated()
    with host.activated():
        assert_type(hosted_container(), FrozenContainer)
        assert_type(hosted_container().resolve(Config), Config)


def a_host_scope_publishes_the_container_and_yields_a_frame() -> None:
    host = Host(build())
    _manager: AbstractContextManager[ScopeFrame] = host.scope()
    with host.scope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(hosted_container(), FrozenContainer)


def a_host_async_scope_is_an_async_context_manager() -> None:
    host = Host(build())
    _manager: AbstractAsyncContextManager[ScopeFrame] = host.ascope()


async def an_async_host_scope_yields_a_frame() -> None:
    host = Host(build())
    async with host.ascope() as frame:
        assert_type(frame, ScopeFrame)
        assert_type(await hosted_container().aresolve(Config), Config)


def the_optional_lookup_reports_absence_in_its_type() -> None:
    assert_type(optional_hosted_container(), FrozenContainer | None)
    container = optional_hosted_container()
    if container is not None:
        assert_type(container.resolve(Config), Config)


def the_contract_version_is_a_pair_of_integers() -> None:
    assert_type(CONTRACT_VERSION, ContractVersion)
    assert_type(CONTRACT_VERSION.major, int)
    assert_type(CONTRACT_VERSION.minor, int)
    assert_type(str(CONTRACT_VERSION), str)


def the_contract_version_is_ordered() -> None:
    # Bound to a local first: `ruff`'s SIM300 reads an upper-case name as a
    # constant and rejects it on the left of a comparison, and the operator
    # direction an integration writes is the point of the assertions.
    published = CONTRACT_VERSION
    assert_type(published >= ContractVersion(1, 0), bool)
    assert_type(published > ContractVersion(0, 9), bool)
    assert_type(published < ContractVersion(2, 0), bool)
    assert_type(published <= ContractVersion(2, 0), bool)
    assert_type(published == ContractVersion(1, 0), bool)


def every_depin_error_is_catchable_as_the_base() -> None:
    di = build()
    try:
        _ = di.resolve(Config)
    except DepinError as error:
        assert_type(error, DepinError)
        _base: Exception = error


def each_resolution_error_narrows_to_its_own_class() -> None:
    di = build()
    try:
        _ = di.resolve(Config)
    except MissingProviderError as error:
        _missing: DepinError = error
    except CircularDependencyError as error:
        _circular: DepinError = error
    except AsyncInSyncContextError as error:
        _async_in_sync: DepinError = error
    except ContainerClosedError as error:
        _closed: ContainerLifecycleError = error
    except ContainerLifecycleError as error:
        _lifecycle: DepinError = error
    except OutsideScopeError as error:
        _outside: DepinError = error


def each_registration_error_narrows_to_its_own_class() -> None:
    try:
        _ = Container().bind(Config).freeze()
    except DuplicateProviderError as error:
        _duplicate: DepinError = error
    except CaptiveDependencyError as error:
        _captive: DepinError = error


def the_four_errors_that_inherit_a_builtin_are_catchable_as_both() -> None:
    def invalid_provider(error: InvalidProviderError) -> None:
        _depin: DepinError = error
        _builtin: TypeError = error

    def invalid_scope(error: InvalidScopeError) -> None:
        _depin: DepinError = error
        _builtin: ValueError = error

    def teardown(error: TeardownError) -> None:
        _depin: DepinError = error
        _builtin: RuntimeError = error

    def not_bound(error: ContainerNotBoundError) -> None:
        _depin: DepinError = error
        _builtin: RuntimeError = error

    _ = (invalid_provider, invalid_scope, teardown, not_bound)


def an_unhosted_lookup_raises_the_declared_error() -> None:
    try:
        _ = hosted_container()
    except ContainerNotBoundError as error:
        assert_type(error, ContainerNotBoundError)
        _base: DepinError = error
