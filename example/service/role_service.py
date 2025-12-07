from example.container import DI
from example.repository.role_repo import RoleRepo
from example.repository.user_repo import UserRepo


@DI.register(DI.Scope.REQUEST)
class RoleService:
    def __init__(self, repo: UserRepo, role_repo: RoleRepo) -> None:
        self.repo = repo
