"""Private support for declaring and enforcing deprecation windows."""

from dataclasses import dataclass
from importlib.metadata import version
from warnings import warn

from depin.errors import InvalidScopeError


def _version_parts(value: str) -> tuple[int, int, int]:
    parts = value.split('.')
    if len(parts) != 3 or any(not part.isdecimal() for part in parts):
        raise InvalidScopeError(f'Deprecation versions must use major.minor.patch, got {value!r}.')
    return int(parts[0]), int(parts[1]), int(parts[2])


@dataclass(frozen=True, slots=True)
class Deprecation:
    """A bounded migration notice for a public symbol."""

    symbol: str
    action: str
    introduced_in: str
    removal_in: str

    def __post_init__(self) -> None:
        if not self.symbol:
            raise InvalidScopeError('A deprecation must name the affected symbol.')
        if not self.action:
            raise InvalidScopeError(f'Deprecation {self.symbol!r} must state the replacement or required action.')
        if _version_parts(self.removal_in) <= _version_parts(self.introduced_in):
            raise InvalidScopeError(
                f'Deprecation {self.symbol!r} removal version must be later than introduced version.'
            )


def emit_deprecation(deprecation: Deprecation) -> None:
    """Emit a migration warning for one active deprecation."""
    warn(
        (
            f'{deprecation.symbol} is deprecated. {deprecation.action} Introduced in {deprecation.introduced_in}; '
            f'removal version: {deprecation.removal_in}.'
        ),
        DeprecationWarning,
        stacklevel=2,
    )


def validate_expiry(deprecations: tuple[Deprecation, ...]) -> None:
    """Reject registered deprecations whose removal version has been reached."""
    current = _version_parts(version('pydepin'))
    expired = tuple(deprecation for deprecation in deprecations if current >= _version_parts(deprecation.removal_in))
    if expired:
        symbols = ', '.join(deprecation.symbol for deprecation in expired)
        raise InvalidScopeError(
            f'Deprecations reached their removal version: {symbols}. Remove their compatibility paths.'
        )
