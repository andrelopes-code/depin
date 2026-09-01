"""An `Inject[T]` parameter used as though it were another type.

`Inject[T]` is a `type` alias to `T` under `TYPE_CHECKING`, so the parameter's
static type is the service itself and nothing wider. A marker that resolved to
`Any` — the failure this suite's anti-erasure pass exists to catch — would make
this assignment legal.

Requires the `fastapi` extra, so `expected/negative.toml` runs it against the
all-extras interpreter.
"""

from depin.ext.fastapi import Inject


class UserService:
    def name(self) -> str:
        return 'user'


class AuditLog:
    def record(self, action: str) -> None:
        _ = action


def route(service: Inject[UserService]) -> str:
    audit: AuditLog = service
    audit.record('read')
    return 'ok'
