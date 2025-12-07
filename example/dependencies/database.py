from contextlib import asynccontextmanager

import rich

from depin import Inject, Scope
from example.container import DI
from example.database import Engine, Session
from example.dependencies.common import random_id


@DI.register(Scope.SINGLETON)
async def db_engine():
    return Engine()


@DI.register(Scope.REQUEST)
async def db_session(engine: Engine = Inject(db_engine), session_id: str = Inject(random_id)):
    async with db_session_ctx(engine, session_id) as session:
        yield session


@asynccontextmanager
async def db_session_ctx(engine: Engine, session_id: str):
    rich.print(f'[magenta]<STARTING NEW SESSION {session_id}>[/magenta]')

    session = Session(engine, session_id)
    yield session

    rich.print(f'[magenta]<CLEANING SESSION WITH {session.session_id}>[/magenta]')
