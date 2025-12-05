import asyncio
from uuid import uuid4

from fastapi import FastAPI, Request
from rich import print

from depin import Container, Provide, RequestScopeService, Scope
from depin.extensions.fastapi import wire_fastapi

container = Container()


def random_id():
    return 'ID-' + uuid4().hex.upper()[:8]


class Engine:
    url = '<dburl>'


class Session:
    @container.inject
    def __init__(self, engine: Engine, session_id: str) -> None:
        self.session_id = session_id
        self.engine = engine

    async def commit(self):
        print(f'SESSION <{self.session_id}> COMMITED')


async def db_engine():
    await asyncio.sleep(0.05)
    return Engine()


async def db_session(engine: Engine = Provide(db_engine), session_id: str = Provide(random_id)):
    await asyncio.sleep(0.05)
    session = Session(engine, session_id)
    yield session
    print(f'<<CLEANING SESSION {session.session_id}>>')


class UserRepo:
    def __init__(self, session: Session = Provide(db_session)) -> None:
        self.session = session


class UserService:
    def __init__(self, repo: UserRepo, request: Request) -> None:
        self.repo = repo
        self.request = request


container.register(
    source=lambda: RequestScopeService.get_current_request(),
    abstract=Request,
    scope=Scope.REQUEST,
)

container.register(source=random_id, scope=Scope.TRANSIENT)
container.register(source=db_engine, scope=Scope.SINGLETON)
container.register(source=db_session, scope=Scope.REQUEST)
container.register(source=UserRepo, scope=Scope.REQUEST)
container.register(source=UserService, scope=Scope.REQUEST)


app = FastAPI()
wire_fastapi(app)


@container.inject
async def procedure(
    us_param: UserService = Provide(UserService),
    db_session: Session = Provide(db_session),
):
    us_resolved = await container.aresolve(UserService)
    print('SAME US? ---->', us_resolved is us_param)
    print('US RESOLVED ---->', us_resolved.request.query_params)
    print('US PARAMS ---->', us_param.request.query_params)
    print('DB SESSION ---->', db_session)

    return 'success'


@app.get('/')
async def index():
    return {'message': await procedure()}


if __name__ == '__main__':
    import uvicorn

    ENTRY = 'main:app'
    HOST = '0.0.0.0'
    PORT = 8000

    uvicorn.run(
        app=ENTRY,
        host=HOST,
        port=PORT,
        reload=True,
    )
