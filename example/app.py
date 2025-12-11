import sys
from pathlib import Path

from example.database import Session
from example.dependencies.database import db_session

# Add project root dir to python path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))


from fastapi import FastAPI, Request

from depin import Inject, RequestScopeService, Scope
from depin.extensions.fastapi import RequestScopeMiddleware
from example.dependencies.container import DI
from example.service.user_service import UserService

DI.bind(
    # Needed to access the current request in request-scoped providers.
    source=lambda: RequestScopeService.get_current_request(),
    abstract=Request,
    scope=Scope.REQUEST,
)


app = FastAPI()
app.add_middleware(RequestScopeMiddleware)


@DI.inject
async def get_user(user_service: UserService = Inject(UserService)):
    user = await user_service.get_user(999)
    return user


@app.get('/')
async def index(session: Session = DI.Depends(db_session)):
    user = await get_user()
    await session.commit()

    return {'user': user}


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
