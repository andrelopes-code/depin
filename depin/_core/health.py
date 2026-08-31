"""Running the verification callables a graph's bindings declared.

`Container.bind(..., check=...)` records a callable; this module says what a
check's outcome means, which checks a synchronous run may drive, and what a run
reports. Resolution belongs to `FrozenContainer`, which hands each check the
value it verifies.
"""

import inspect
from collections.abc import Iterable
from dataclasses import dataclass
from typing import final

from depin._core.spec import ProviderKey, ProviderSpec, ResolutionPlan, fmt_key
from depin._core.typeguards import as_check, is_awaitable
from depin.errors import AsyncInSyncContextError, InvalidProviderError


@final
@dataclass(frozen=True, slots=True)
class HealthCheck:
    """A verification callable a binding declared, as data.

    Attributes:
        key: The provider whose value the check verifies.
        tag: That provider's tag, when it has one.
        needs_async: Whether running it requires an event loop, because the
            provider needs async resolution or the check is a coroutine
            function.
    """

    key: ProviderKey
    tag: str | None
    needs_async: bool


@final
@dataclass(frozen=True, slots=True)
class HealthResult:
    """What one check said.

    Attributes:
        key: The provider whose value was verified.
        tag: That provider's tag, when it has one.
        healthy: False when the check raised or returned ``False``.
        error: The exception the check raised, when it raised one.
    """

    key: ProviderKey
    tag: str | None
    healthy: bool
    error: Exception | None


@final
@dataclass(frozen=True, slots=True)
class HealthReport:
    """Every check's outcome, in resolution order.

    Example:
        ```pycon
        >>> from depin import Container
        >>> class Database:
        ...     ready = True
        >>> def ping(db: Database) -> bool:
        ...     return db.ready
        >>> di = Container().bind(Database, check=ping).freeze()
        >>> report = di.health()
        >>> report.healthy, len(report.results)
        (True, 1)

        ```
    """

    results: tuple[HealthResult, ...]

    @property
    def healthy(self) -> bool:
        """Whether every check passed. An empty report is healthy."""
        return all(result.healthy for result in self.results)


def checked_specs(plan: ResolutionPlan) -> tuple[ProviderSpec, ...]:
    """The providers that declared a check, in resolution order."""
    return tuple(spec for spec in plan.order if spec.check is not None)


def declared_checks(specs: Iterable[ProviderSpec]) -> tuple[HealthCheck, ...]:
    return tuple(HealthCheck(key=spec.key, tag=spec.tag, needs_async=_needs_async(spec)) for spec in specs)


def reject_async_checks(specs: Iterable[ProviderSpec]) -> None:
    """Refuse a synchronous run over checks that need an event loop.

    Raised before any check runs, so a refusal reports nothing rather than a
    partial set of outcomes.

    Raises:
        AsyncInSyncContextError: Some check needs async resolution or is itself
            a coroutine function.
    """
    pending = tuple(spec.key for spec in specs if _needs_async(spec))
    if not pending:
        return
    names = ', '.join(fmt_key(key) for key in pending)
    raise AsyncInSyncContextError(
        f'health() cannot run the checks for {names}: they require an event loop, '
        'because the provider is async or the check is. Call ahealth() instead.'
    )


def _needs_async(spec: ProviderSpec) -> bool:
    return spec.needs_async or inspect.iscoroutinefunction(spec.check)


def run_check(spec: ProviderSpec, value: object) -> HealthResult:
    """Call one check without an event loop.

    Raises:
        InvalidProviderError: The check returned an awaitable, which a
            synchronous run has no loop to await.
    """
    check = as_check(spec.check, spec.key)
    try:
        outcome = check(value)
    except Exception as error:
        return HealthResult(key=spec.key, tag=spec.tag, healthy=False, error=error)
    if is_awaitable(outcome):
        raise InvalidProviderError(
            f'the health check for {fmt_key(spec.key)} returned an awaitable; an asynchronous '
            'check runs under ahealth(), never under health().'
        )
    return _outcome(spec, outcome)


async def run_check_async(spec: ProviderSpec, value: object) -> HealthResult:
    """Call one check inside an event loop; awaits an asynchronous one."""
    check = as_check(spec.check, spec.key)
    try:
        outcome = check(value)
        if is_awaitable(outcome):
            outcome = await outcome
    except Exception as error:
        return HealthResult(key=spec.key, tag=spec.tag, healthy=False, error=error)
    return _outcome(spec, outcome)


def _outcome(spec: ProviderSpec, outcome: object) -> HealthResult:
    """A check is healthy unless it returned exactly ``False``.

    Identity against `False` rather than truthiness: a check returning ``0`` or
    an empty string returned a value, not a verdict, and reading it as a failure
    would make a working check fail for the shape of what it happened to return.
    """
    return HealthResult(key=spec.key, tag=spec.tag, healthy=outcome is not False, error=None)
