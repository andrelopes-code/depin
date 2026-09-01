"""`depin.ext.fastapi`: `Inject[T]` beside ordinary FastAPI parameters.

The single promise `Inject` makes is that the parameter's static type is `T`
itself, so a route body reaches the service's members with no cast and no
marker default. It is a `type` alias under `TYPE_CHECKING`, so the assertion is
exact and `assert_type` is honest.

The parameter is mixed with a path parameter, a query parameter and a request
body on the same routes, because that mixture is where a wrong annotation would
show: FastAPI reads every parameter of a route through the same machinery, and
a marker that widened to `Any` would take the ordinary parameters' inference
with it.

Requires the `fastapi` extra, so this file is checked in all-extras mode only.
"""

from typing import Annotated, assert_type

from fastapi import FastAPI, Query
from pydantic import BaseModel

from depin import Container, FrozenContainer
from depin.ext.fastapi import Inject, RequestScope


class Settings:
    def __init__(self) -> None:
        self.page_size = 25


class UserService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def name(self, user_id: int) -> str:
        return f'user-{user_id}'


class AuditLog:
    def record(self, action: str) -> None:
        _ = action


class NewUser(BaseModel):
    name: str


def build() -> FrozenContainer:
    return Container().bind(Settings).bind(UserService).bind(AuditLog).freeze()


app = FastAPI()


@app.get('/users/{user_id}')
def read_user(user_id: int, service: Inject[UserService]) -> str:
    assert_type(service, UserService)
    assert_type(service.settings.page_size, int)
    return service.name(user_id)


@app.get('/users')
def list_users(
    service: Inject[UserService],
    page: Annotated[int, Query(ge=1)] = 1,
) -> list[str]:
    assert_type(service, UserService)
    assert_type(page, int)
    return [service.name(page)]


@app.post('/users')
async def create_user(body: NewUser, service: Inject[UserService], audit: Inject[AuditLog]) -> str:
    assert_type(service, UserService)
    assert_type(audit, AuditLog)
    assert_type(body.name, str)
    audit.record('create')
    return service.name(len(body.name))


@app.get('/settings')
async def read_settings(settings: Inject[Settings]) -> int:
    assert_type(settings, Settings)
    return settings.page_size


def the_middleware_is_installed_with_the_container() -> None:
    application = FastAPI()
    application.add_middleware(RequestScope, container=build())


def the_middleware_wraps_an_application_directly() -> None:
    application = FastAPI()
    _wrapped: RequestScope = RequestScope(application, build())
