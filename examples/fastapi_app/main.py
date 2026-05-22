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
# `Inject(...)` in the default position is required by FastAPI's dependency-injection API.
@app.get('/users/{uid}')
async def get_user(  # pyright: ignore[reportUnusedFunction]
    uid: int,
    svc: UserService = Inject(UserService),  # noqa: B008
) -> dict[str, int | str]:
    return await svc.get(uid)
