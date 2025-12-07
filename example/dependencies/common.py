from uuid import uuid4

from depin import Scope
from example.container import DI


@DI.register(Scope.TRANSIENT)
def random_id():
    return uuid4().hex
