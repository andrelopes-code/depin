from di_framework import Scope, injectable


@injectable(scope=Scope.REQUEST)
class UserRepository:
    def __init__(self):
        self.session = '<DB-SESSION-123>'
