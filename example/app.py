import sys
from pathlib import Path

# Add project root dir to python path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))


from fastapi import FastAPI, Request
from rich import print

from depin import Inject, RequestScopeService, Scope
from depin.extensions.fastapi import RequestScopeMiddleware
from example.database import Session
from example.dependencies.container import DI
from example.dependencies.database import db_session
from example.service.user_service import UserService

DI.bind(
    source=lambda: RequestScopeService.get_current_request(),
    abstract=Request,
    scope=Scope.REQUEST,
)


app = FastAPI()
app.add_middleware(RequestScopeMiddleware)


@DI.inject
async def procedure(
    us_param: UserService = Inject(UserService),
    db_session: Session = Inject(db_session),
):
    us_resolved = await DI.get_async(UserService)

    print(f'REQID = {us_resolved} ', us_resolved.request.query_params.get('reqid'))

    # print('SAME US? ---->', us_resolved is us_param)
    # print('REQUEST PARAMS ---->', us_resolved.request.query_params)

    # user = await us_param.get_user(999)
    # print('USER ---->', user)

    # await db_session.commit()
    # await db_session.rollback()

    return 'success'


@app.get('/')
async def index(s: UserService = DI.Depends(UserService)):
    return {'message': await procedure()}


if __name__ == '__main__':
    import uvicorn

    ENTRY = 'app:app'
    HOST = '0.0.0.0'
    PORT = 8001

    uvicorn.run(
        app=ENTRY,
        host=HOST,
        port=PORT,
        reload=True,
    )
