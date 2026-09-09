"""The context-local binding shared by eager and lazy container hosts."""

from contextvars import ContextVar
from contextvars import Token as ContextToken
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from depin._core.frozen import FrozenContainer


class HostedBinding(Protocol):
    @property
    def container(self) -> 'FrozenContainer': ...


_binding: ContextVar[HostedBinding | None] = ContextVar('depin_hosted_binding', default=None)


def get_hosted_binding() -> HostedBinding | None:
    return _binding.get()


def set_hosted_binding(binding: HostedBinding) -> ContextToken[HostedBinding | None]:
    return _binding.set(binding)


def reset_hosted_binding(token: ContextToken[HostedBinding | None]) -> None:
    _binding.reset(token)
