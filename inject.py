import asyncio

from rich import print

from depin import Container, Provide, RequestScopeService, Scope

container = Container()


class Engine:
    url = '<dburl>'


async def db_engine():
    return Engine()


container.register(abstract=Engine, source=db_engine, scope=Scope.TRANSIENT)


class Session:
    def __init__(self, engine: Engine) -> None:
        self.session_id = 12345678
        self.engine = engine

    async def commit(self):
        print(f'SESSION <{self.session_id}> COMMITED')

    @container.inject
    async def get_engine(
        self,
        non_injected: int,
        engine: Engine = Provide(Engine),
    ):
        return engine, non_injected


@container.inject
async def perform():
    token = RequestScopeService.enter_request_scope()

    engine = await container.aresolve(Engine)
    s = Session(engine)
    print(await s.get_engine(1))

    await RequestScopeService.aexit_request_scope(token)


async def main():
    await perform()


asyncio.run(main())
