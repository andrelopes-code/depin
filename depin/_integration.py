"""Private contracts shared by optional framework integrations."""

from typing import TYPE_CHECKING

from depin._core.lazy_scope import (
    LazyScopeSeed,
    _lazy_host,
    _provide_lazy_seed,
)
from depin._core.lazy_scope import (
    begin_lazy_host as _begin_lazy_host,
)
from depin._core.lazy_scope import (
    finish_lazy_host as _finish_lazy_host,
)
from depin._core.scope import active_eager_frame

if TYPE_CHECKING:
    from depin._core.frozen import FrozenContainer


def _provide_active_eager_seed(container: 'FrozenContainer', key: object, value: object) -> None:
    frame = active_eager_frame(container.scope_owner())
    if frame is not None:
        frame.provide(key, value)


__all__ = [
    'LazyScopeSeed',
    '_begin_lazy_host',
    '_finish_lazy_host',
    '_lazy_host',
    '_provide_active_eager_seed',
    '_provide_lazy_seed',
]
