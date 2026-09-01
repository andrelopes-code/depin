"""Infrastructure and service bindings, declared as reusable registries."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from starlette.requests import Request

from depin import Registry

infra = Registry('infra')
services = Registry('services')


@dataclass(frozen=True, slots=True)
class Settings:
    db_url: str = 'postgres://example'


@infra.singleton()
def load_settings() -> Settings:
    """In a real app this would read the environment; the shape is what matters."""
    return Settings()


class Database:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.db_url
        self.open_sessions = 0


class Session:
    def __init__(self, db: Database) -> None:
        self.db = db


@infra.singleton()
async def connect(settings: Settings) -> AsyncGenerator[Database]:
    """A singleton that owns a connection: torn down by ``aclose()`` on shutdown."""
    db = Database(settings)
    yield db


@services.scoped()
async def open_session(db: Database) -> AsyncGenerator[Session]:
    """One session per request. The middleware opens and closes the scope."""
    db.open_sessions += 1
    yield Session(db)
    db.open_sessions -= 1


@services.scoped()
class RequestTrace:
    """Reads the request `RequestScope` seeded into the frame, headers and URL only.

    The seeded request carries no receive channel, so the body belongs to the
    route handler and never to a provider.
    """

    def __init__(self, request: Request) -> None:
        self.path = request.url.path
        self.agent = request.headers.get('user-agent', 'unknown')
