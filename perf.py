import asyncio
import time

from rich import print

from depin import Container, Provide, RequestScopeService, Scope

container = Container()


class Engine:
    url = '<dburl>'


class Session:
    def __init__(self, engine: Engine) -> None:
        self.session_id = 12345678
        self.engine = engine

    async def commit(self):
        print(f'SESSION <{self.session_id}> COMMITED')


async def db_engine():
    return Engine()


async def db_session(engine: Engine = Provide(db_engine)):
    yield Session(engine)
    print('CLEANING SESSION')


async def db_session_coroutine(engine: Engine = Provide(db_engine)):
    return Session(engine)


class UserRepo:
    def __init__(self, session: Session = Provide(db_session_coroutine)) -> None:
        self.session = session


class UserService:
    def __init__(self, repo: UserRepo) -> None:
        self.repo = repo


container.register(source=db_engine, scope=Scope.TRANSIENT)
container.register(source=db_session_coroutine, scope=Scope.TRANSIENT)
container.register(source=UserRepo, scope=Scope.TRANSIENT)
container.register(source=UserService, scope=Scope.REQUEST)


@container.inject
async def perform1():
    token = RequestScopeService.enter_request_scope()

    s = await container.aresolve(UserService)
    print(s.repo.session)

    await RequestScopeService.aexit_request_scope(token)


async def perform2():
    token = RequestScopeService.enter_request_scope()

    s = await container.aresolve(UserService)
    print(s.repo.session)

    await RequestScopeService.aexit_request_scope(token)


async def main():
    start = time.perf_counter()

    await asyncio.gather(*[perform2() for _ in range(1000)])

    end = time.perf_counter()

    print(f'Elapsed: {end - start}')


asyncio.run(main())
