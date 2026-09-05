"""Reusable context-to-scope seed contracts."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from depin._core.spec import ProviderKey

if TYPE_CHECKING:
    from depin._core.scope import ScopeFrame


@dataclass(frozen=True, slots=True)
class ScopeSeed:
    """A value to provide to a freshly opened scope.

    Args:
        key: The provider key under which the value is available.
        value: The value available for the scope's lifetime.
        tag: An optional provider tag.
    """

    key: ProviderKey
    value: object
    tag: str | None = None

    def apply(self, frame: 'ScopeFrame') -> None:
        """Provide this seed to ``frame`` without changing provider failures."""
        frame.provide(self.key, self.value, tag=self.tag)


class ScopeSeeder[ContextT](Protocol):
    """Builds an optional scope seed from a framework-specific context."""

    def __call__(self, context: ContextT, /) -> ScopeSeed | None: ...
