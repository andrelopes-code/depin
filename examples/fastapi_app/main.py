from fastapi import FastAPI

from depin import Container
from depin.ext.fastapi import Inject, RequestScope

from .registries import infra
from .registries import services as services_reg
from .services import UserService


di = Container.from_(infra, services_reg).freeze()

app = FastAPI()
app.add_middleware(RequestScope, container=di)


# FastAPI consumes the route via @app.get; the function binding looks unused statically.
@app.get('/users/{uid}')
async def get_user(uid: int, svc: UserService = Inject(UserService)) -> dict[str, int | str]:  # pyright: ignore[reportUnusedFunction]
    return await svc.get(uid)
