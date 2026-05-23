from typing import Annotated

from fastapi import FastAPI

from depin import Container
from depin.ext.fastapi import Inject, RequestScope

from .registries import infra
from .registries import services as services_reg
from .services import UserService

di = Container.from_(infra, services_reg).freeze()

app = FastAPI()
app.add_middleware(RequestScope, container=di)


@app.get('/users/{uid}')
async def get_user(  # pyright: ignore[reportUnusedFunction]
    uid: int,
    svc: Annotated[UserService, Inject(UserService)],
) -> dict[str, int | str]:
    return await svc.get(uid)
