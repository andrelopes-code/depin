from depin import Inject
from example.container import DI
from example.database import Session
from example.dependencies.database import db_session


@DI.register(DI.Scope.REQUEST)
class RoleRepo:
    def __init__(self, session: Session = Inject(db_session)) -> None:
        self.session = session
