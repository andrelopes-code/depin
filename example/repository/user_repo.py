from depin import Inject
from example.database import Session
from example.dependencies.container import DI
from example.dependencies.database import db_session


@DI.register(DI.Scope.REQUEST)
class UserRepo:
    def __init__(self, session: Session = Inject(db_session)) -> None:
        self.session = session

    async def get_user(self, user_id: int):
        return {'user_id': user_id, 'name': 'John Doe'}
