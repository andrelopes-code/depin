from di_framework import Scope, injectable
from services.user_repository import UserRepository


@injectable(scope=Scope.REQUEST)
class UserService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository
