"""A parameterised key resolved at the wrong type argument.

`Repo[User]` and `Repo[Order]` are two keys, not one, and resolution keeps the
argument it was asked for. A checker that erased the parameterisation would
accept this assignment, which is the failure mode the positive corpus's generic
cases exist to detect from the other side.
"""

from depin import Container


class User: ...


class Order: ...


class Repo[T]:
    def __init__(self) -> None:
        self.items: list[T] = []


def make_orders() -> Repo[Order]:
    return Repo()


def main() -> None:
    di = Container().bind(make_orders).freeze()
    _users: Repo[User] = di.resolve(Repo[Order])
