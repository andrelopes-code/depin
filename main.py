import asyncio

from fastapi import Depends, FastAPI
from rich import print

from di_framework import Container, Provide, Scope

container = Container()


class Engine:
    url = '<dburl>'


class Session:
    def __init__(self, engine: Engine) -> None:
        self.session_id = 12345678
        self.engine = engine

    def commit(self):
        print(f'SESSION <{self.session_id}> COMMITED')


async def db_engine():
    await asyncio.sleep(0.2)
    return Engine()


async def db_session(engine: Engine = Provide(db_engine)):
    await asyncio.sleep(0.2)
    yield Session(engine)
    print('CLEANING SESSION')


class UserRepo:
    def __init__(self, session: Session = Provide(db_session)) -> None:
        self.session = session


class UserService:
    def __init__(self, repo: UserRepo) -> None:
        self.repo = repo


container.register(provider_fn=db_engine, scope=Scope.SINGLETON)
container.register(provider_fn=db_session, scope=Scope.REQUEST)
container.register(implementation=UserRepo, scope=Scope.REQUEST)
container.register(implementation=UserService, scope=Scope.REQUEST)


app = FastAPI()
container.wire_fastapi(app)


@app.get('/')
async def index(
    dep: UserService = Depends(container.provide(UserService)),
):
    dep.repo.session.commit()

    return {
        'message': 'Hello World',
        'dep': str(dep),
    }
