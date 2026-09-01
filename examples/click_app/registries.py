"""Infrastructure and service bindings, declared as reusable registries."""

from collections.abc import Generator
from dataclasses import dataclass
from typing import Annotated

from click import Context

from depin import Registry, Token

infra = Registry('infra')
services = Registry('services')

TENANT: Token[str] = Token[str]('tenant')
"""The key the callback fills from an option, alongside the context depin seeds."""


@dataclass(frozen=True, slots=True)
class Settings:
    db_url: str = 'postgres://example'


@infra.singleton()
def load_settings() -> Settings:
    """In a real CLI this would read the environment; the shape is what matters."""
    return Settings()


class Database:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.db_url
        self.open_sessions = 0
        self.closed = False


class Session:
    def __init__(self, db: Database) -> None:
        self.db = db


@infra.singleton()
def connect(settings: Settings) -> Generator[Database]:
    """A singleton that owns a connection: torn down by ``close()``, not by the scope.

    Every provider here is synchronous, because Click never awaits a command
    callback. An async one would leave a teardown the invocation's scope cannot
    run.
    """
    db = Database(settings)
    yield db
    db.closed = True


@services.scoped()
def open_session(db: Database) -> Generator[Session]:
    """One session per invocation. The Click context opens and closes the scope."""
    db.open_sessions += 1
    yield Session(db)
    db.open_sessions -= 1


@services.scoped()
class CommandTrace:
    """Reads both halves of the frame: the seeded context, and the tenant the callback placed.

    ``invoked_subcommand`` is filled only on a group's context, which is what
    the seed is: the context of the callback that opened the scope, not the
    child context Click pushes for the subcommand.
    """

    def __init__(self, ctx: Context, tenant: Annotated[str, TENANT]) -> None:
        self.subcommand = ctx.invoked_subcommand or ''
        self.tenant = tenant
