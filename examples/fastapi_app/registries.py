from collections.abc import AsyncGenerator

from depin import Registry

services = Registry('services')
infra = Registry('infra')


class Settings:
    db_url: str = 'postgres://example'


@infra.singleton(provides=Settings)
class SettingsImpl(Settings): ...


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


@infra.singleton(provides=Database)
class DatabaseImpl(Database): ...


class Session:
    def __init__(self, db: Database) -> None:
        self.db = db


@services.scoped(provides=Session)
async def make_session(db: Database) -> AsyncGenerator[Session]:
    yield Session(db)
