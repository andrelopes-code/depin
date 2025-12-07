from fastapi import Request

from example.container import DI
from example.repository.role_repo import RoleRepo
from example.repository.user_repo import UserRepo


@DI.register(DI.Scope.REQUEST)
class UserService:
    def __init__(self, user_repo: UserRepo, role_repo: RoleRepo, request: Request):
        self.user_repo = user_repo
        self.role_repo = role_repo
        self.request = request

    async def get_user(self, user_id: int):
        return await self.user_repo.get_user(user_id)
