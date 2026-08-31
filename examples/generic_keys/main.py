"""A parameterised generic as a provider key: two repositories, two entity types.

Run with ``python -m examples.generic_keys.main``.
"""

from depin import Container, FrozenContainer


class User:
    def __init__(self, name: str) -> None:
        self.name = name


class Order:
    def __init__(self, reference: str) -> None:
        self.reference = reference


class Repo[T]:
    """Bound once per entity type, each under its own `Repo[T]` key."""

    def __init__(self, rows: list[T]) -> None:
        self.rows = rows


def user_repo() -> Repo[User]:
    return Repo([User('ana'), User('bia')])


def order_repo() -> Repo[Order]:
    return Repo([Order('#1001')])


class ReportService:
    """Depends on both repositories, each resolved by its own parameterised key."""

    def __init__(self, users: Repo[User], orders: Repo[Order]) -> None:
        self.users = users
        self.orders = orders

    def summary(self) -> str:
        return f'{len(self.users.rows)} users, {len(self.orders.rows)} orders'


def build() -> FrozenContainer:
    return Container().bind(user_repo).bind(order_repo).bind(ReportService).freeze()


def main() -> None:
    di = build()
    print([user.name for user in di.resolve(Repo[User]).rows])
    print([order.reference for order in di.resolve(Repo[Order]).rows])
    print(di[ReportService].summary())
    print(di.explain(Repo[User]))


if __name__ == '__main__':
    main()
